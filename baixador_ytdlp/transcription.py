"""Transcrição local e exportação de legendas.

O modelo só é carregado quando a transcrição começa. NVIDIA usa
faster-whisper/CUDA; no Apple Silicon o MLX Whisper usa a GPU integrada. Todo
backend possui fallback para faster-whisper em CPU/int8, sem impedir o uso do
restante do programa.
"""
from __future__ import annotations

import gc
import importlib.util
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import threading
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import MODEL_DIR
from .diagnostics import install_diagnostics, log_event, report_exception
from .hardware import whisper_threads
from .tools import CREATE_NO_WINDOW, Toolchain

StatusCB = Callable[[str], None]
ProgressCB = Callable[[int], None]

FORMATS = {
    "srt": ("SRT — compatível com players", ".srt"),
    "vtt": ("WebVTT — ideal para web", ".vtt"),
    "ass": ("ASS — estilo avançado", ".ass"),
    "karaoke": ("ASS karaoke — palavras sincronizadas", ".ass"),
    "txt": ("Texto simples", ".txt"),
    "json": ("JSON — segmentos e timestamps", ".json"),
}

# Pesos já convertidos e mantidos pela comunidade oficial do MLX. Não usamos o
# modelo CTranslate2 no Mac quando o runtime MLX está presente: além de tirar
# proveito da GPU integrada, evita copiar o áudio pela memória mais vezes que o
# necessário na arquitetura de memória unificada da Apple.
MLX_MODEL_REPOS = {
    "tiny": "mlx-community/whisper-tiny-mlx",
    "base": "mlx-community/whisper-base-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "medium": "mlx-community/whisper-medium-mlx",
    "large": "mlx-community/whisper-large-v3-mlx",
    "large-v2": "mlx-community/whisper-large-v3-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}


class TranscriptionCancelled(RuntimeError):
    """Cancelamento solicitado pelo usuário."""


@dataclass(frozen=True)
class TranscriptionOptions:
    media_path: Path
    output_path: Path
    language: str = "pt"
    model_size: str = "medium"
    output_format: str = "srt"
    aggressive_filter: bool = False


@dataclass(frozen=True)
class DecodedInfo:
    """Campos comuns aos resultados do faster-whisper e do MLX Whisper."""

    language: str
    language_probability: float = 0.0


def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine().lower() in {"arm64", "aarch64"}


def _mlx_available() -> bool:
    """Evita importar MLX na abertura; o pacote só existe na build macOS."""
    try:
        return importlib.util.find_spec("mlx_whisper") is not None
    except (ImportError, AttributeError, ValueError):
        return False


class Transcriber:
    """Motor isolado da UI, com filtros de leitura do legendador original."""

    max_chars_per_line = 50
    max_lines = 2
    min_duration = 0.8
    max_duration = 4.5
    chars_per_second = 15
    min_gap = 0.1
    hallucination_phrases = (
        "obrigado por assistir", "inscreva se", "like e se inscreva", "se inscreva no canal",
        "thank you for watching", "please subscribe", "like and subscribe", "subscribe to channel",
        "clique aqui", "ativar notificações", "deixe seu like", "compartilhe", "music",
        "música", "aplausos", "applause", "risos", "laughter", "plateia",
    )

    def __init__(self, toolchain: Toolchain, status: StatusCB, progress: ProgressCB,
                 aggressive_filter: bool = False, cancel_event=None, pause_event=None, force_cpu: bool = False):
        self.toolchain = toolchain
        self.status = status
        self.progress = progress
        self.aggressive_filter = aggressive_filter
        # Em execução normal são Events de thread. No processo isolado, são
        # Events do multiprocessing e preservam a pausa/cancelamento entre processos.
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self.pause_event = pause_event if pause_event is not None else threading.Event()
        if force_cpu:
            self.backend, self.device, self.compute_type, self.hardware_label = (
                "faster-whisper", "cpu", "int8", "CPU — CUDA interno indisponível (int8)")
        else:
            self.backend, self.device, self.compute_type, self.hardware_label = self._detect_hardware()
        self.model = None

    def cancel(self) -> None:
        self.cancel_event.set()

    def pause(self, paused: bool) -> None:
        if paused:
            self.pause_event.set()
        else:
            self.pause_event.clear()

    def _check_interrupt(self) -> None:
        while self.pause_event.is_set():
            if self.cancel_event.wait(0.1):
                raise TranscriptionCancelled("Transcrição cancelada")
        if self.cancel_event.is_set():
            raise TranscriptionCancelled("Transcrição cancelada")

    @staticmethod
    def _detect_hardware() -> tuple[str, str, str, str]:
        """Pergunta ao CTranslate2, que é quem de fato executa o modelo.

        Antes isso importava o PyTorch inteiro só para ler `cuda.is_available()`.
        O CTranslate2 já está carregado de qualquer jeito e responde a mesma
        pergunta em milissegundos — o torch continua sendo aceito como plano B
        para quem tiver uma instalação antiga.
        """
        if _is_apple_silicon() and _mlx_available():
            return "mlx", "metal", "float16", "Apple Silicon — MLX na GPU integrada"
        try:
            import ctranslate2
            if ctranslate2.get_cuda_device_count() > 0:
                return "faster-whisper", "cuda", "float16", "CUDA — GPU NVIDIA detectada"
        except Exception:
            pass
        try:
            import torch  # opcional; não faz parte do runtime instalado
            if torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory / 1024 ** 3
                return "faster-whisper", "cuda", "float16", f"CUDA — {name} ({vram:.1f} GB VRAM)"
        except Exception:
            pass
        cores = whisper_threads()
        if _is_apple_silicon():
            return "faster-whisper", "cpu", "int8", f"Apple Silicon — CPU/NEON em até {cores} threads (int8)"
        return "faster-whisper", "cpu", "int8", f"CPU — até {cores} threads (int8)"

    def _load_model(self, model_size: str) -> None:
        from faster_whisper import WhisperModel

        self.status(f"Carregando Whisper {model_size} em {self.hardware_label}…")
        self.progress(5)
        kwargs = {"device": self.device, "compute_type": self.compute_type,
                  "download_root": str(MODEL_DIR)}
        if self.device == "cpu":
            kwargs.update(cpu_threads=whisper_threads(), num_workers=1)
        try:
            self.model = WhisperModel(model_size, **kwargs)
        except Exception as exc:
            if self.device != "cuda":
                raise
            # Driver, wheel CUDA ou cuDNN podem não estar presentes; CPU é melhor que falhar.
            self.status(f"CUDA indisponível para o Whisper ({exc}). Alternando para CPU int8…")
            self.device, self.compute_type = "cpu", "int8"
            self.hardware_label = "CPU — fallback automático (int8)"
            self.model = WhisperModel(
                model_size, device="cpu", compute_type="int8", download_root=str(MODEL_DIR),
                cpu_threads=whisper_threads(), num_workers=1,
            )
        self.progress(15)
        self.status(f"Modelo pronto: {self.hardware_label}")

    def _prepare_mlx(self, model_size: str) -> None:
        """Prepara o cache do MLX antes da importação preguiçosa do backend."""
        cache = MODEL_DIR / "mlx"
        cache.mkdir(parents=True, exist_ok=True)
        # huggingface_hub lê HF_HOME no primeiro import. Como este método roda
        # no processo auxiliar, não altera o ambiente do aplicativo Qt.
        os.environ.setdefault("HF_HOME", str(cache))
        self.status(f"Carregando Whisper {model_size} em {self.hardware_label}…")
        self.progress(5)

    @staticmethod
    def _mlx_model_repo(model_size: str) -> str:
        return MLX_MODEL_REPOS.get(model_size, MLX_MODEL_REPOS["medium"])

    def _switch_to_cpu(self, model_size: str, reason: Exception) -> None:
        """Troca de CUDA para CPU quando uma DLL/driver falha durante o uso."""
        from faster_whisper import WhisperModel

        self.status(f"CUDA indisponível durante a transcrição ({reason}). Alternando para CPU int8…")
        self.model = None
        gc.collect()
        self.device, self.compute_type = "cpu", "int8"
        self.hardware_label = "CPU — fallback automático (int8)"
        self.model = WhisperModel(
            model_size, device="cpu", compute_type="int8", download_root=str(MODEL_DIR),
            cpu_threads=whisper_threads(), num_workers=1,
        )
        self.status(f"Modelo pronto: {self.hardware_label}")

    def _switch_mlx_to_cpu(self, model_size: str, reason: Exception) -> None:
        """Fallback seguro quando um Mac não consegue inicializar o MLX."""
        self.status(f"MLX indisponível durante a transcrição ({reason}). Alternando para CPU int8…")
        self.backend, self.device, self.compute_type = "faster-whisper", "cpu", "int8"
        self.hardware_label = "Apple Silicon — fallback CPU/NEON (int8)"
        self.model = None
        gc.collect()
        self._load_model(model_size)

    def _decode_faster_whisper(self, audio: Path, opts: TranscriptionOptions,
                               duration: float) -> tuple[list[dict], object]:
        """Consome o gerador do faster-whisper; erros de DLL podem ocorrer só aqui."""
        segments, info = self.model.transcribe(
            str(audio), language=None if opts.language == "auto" else opts.language,
            word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250, "speech_pad_ms": 50,
                            "max_speech_duration_s": 6.0},
            **self._model_options(opts.model_size),
        )
        raw: list[dict] = []
        for item in segments:
            self._check_interrupt()
            words = []
            for word in getattr(item, "words", None) or ():
                word_text = (getattr(word, "word", "") or "").strip()
                if word_text:
                    words.append({
                        "text": word_text,
                        "start": float(getattr(word, "start", None) or item.start),
                        "end": float(getattr(word, "end", None) or item.end),
                    })
            raw.append({"start": float(item.start), "end": float(item.end),
                        "text": item.text.strip(), "words": words,
                        "avg_logprob": item.avg_logprob,
                        "no_speech_prob": item.no_speech_prob})
            if duration:
                self.progress(min(90, max(16, int(item.end * 74 / duration) + 16)))
        return raw, info

    def _decode_mlx(self, audio: Path, opts: TranscriptionOptions,
                    duration: float) -> tuple[list[dict], DecodedInfo]:
        """Transcreve na GPU integrada Apple via MLX, preservando a saída comum."""
        import mlx_whisper

        options = self._model_options(opts.model_size).copy()
        temperature = options.pop("temperature", 0.0)
        condition = options.pop("condition_on_previous_text", True)
        compression = options.pop("compression_ratio_threshold", 2.4)
        log_probability = options.pop("log_prob_threshold", -1.0)
        no_speech = options.pop("no_speech_threshold", 0.6)
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=self._mlx_model_repo(opts.model_size), verbose=None,
            language=None if opts.language == "auto" else opts.language,
            word_timestamps=True, temperature=temperature,
            condition_on_previous_text=condition,
            compression_ratio_threshold=compression, logprob_threshold=log_probability,
            no_speech_threshold=no_speech, **options,
        )
        raw: list[dict] = []
        for item in result.get("segments") or ():
            self._check_interrupt()
            start = float(item.get("start") or 0.0)
            end = float(item.get("end") or start)
            words = []
            for word in item.get("words") or ():
                word_text = str(word.get("word") or word.get("text") or "").strip()
                if word_text:
                    words.append({
                        "text": word_text,
                        "start": float(word.get("start") if word.get("start") is not None else start),
                        "end": float(word.get("end") if word.get("end") is not None else end),
                    })
            raw.append({
                "start": start, "end": end, "text": str(item.get("text") or "").strip(),
                "words": words, "avg_logprob": item.get("avg_logprob"),
                "no_speech_prob": item.get("no_speech_prob"),
            })
            if duration:
                self.progress(min(90, max(16, int(end * 74 / duration) + 16)))
        language = str(result.get("language") or (opts.language if opts.language != "auto" else "auto"))
        probability = float(result.get("language_probability") or 0.0)
        return raw, DecodedInfo(language, probability)

    def _decode(self, audio: Path, opts: TranscriptionOptions,
                duration: float) -> tuple[list[dict], object]:
        if self.backend == "mlx":
            return self._decode_mlx(audio, opts, duration)
        return self._decode_faster_whisper(audio, opts, duration)

    def _duration(self, media: Path) -> float:
        try:
            proc = subprocess.run(
                [str(self.toolchain.ffprobe), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nokey=1:noprint_wrappers=1", str(media)],
                capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW,
            )
            return float(proc.stdout.strip())
        except Exception:
            return 0.0

    def _extract_audio(self, media: Path) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix="baixador-ytdlp-whisper-", suffix=".wav", delete=False)
        handle.close()
        target = Path(handle.name)
        self.status("Preparando áudio em 16 kHz mono…")
        cmd = [str(self.toolchain.ffmpeg), "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(target)]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=CREATE_NO_WINDOW)
        if proc.returncode:
            target.unlink(missing_ok=True)
            raise RuntimeError("Não foi possível extrair o áudio: " + proc.stderr[-600:])
        return target

    def run(self, opts: TranscriptionOptions) -> list[dict]:
        if not opts.media_path.is_file():
            raise FileNotFoundError("Selecione um arquivo de áudio ou vídeo válido.")
        audio: Path | None = None
        try:
            self._check_interrupt()
            if self.backend == "mlx":
                self._prepare_mlx(opts.model_size)
            elif not self.model:
                self._load_model(opts.model_size)
            audio = self._extract_audio(opts.media_path)
            duration = self._duration(opts.media_path)
            self.status(f"Transcrevendo {opts.media_path.name}…")
            try:
                raw, info = self._decode(audio, opts, duration)
            except TranscriptionCancelled:
                raise
            except Exception as exc:
                if self.backend == "mlx":
                    self._switch_mlx_to_cpu(opts.model_size, exc)
                    raw, info = self._decode(audio, opts, duration)
                elif self.device == "cuda":
                    # A carga das DLLs CUDA é preguiçosa; erros como
                    # cublas64_12.dll ausente aparecem ao iterar os segmentos.
                    self._switch_to_cpu(opts.model_size, exc)
                    raw, info = self._decode(audio, opts, duration)
                else:
                    raise
            language = str(getattr(info, "language", "auto"))
            probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            confidence = f" ({probability:.0%})" if probability else ""
            self.status(f"{len(raw)} segmentos brutos · idioma {language}{confidence}")
            result = self._fix_timing(self._split_segments(self._clean(raw)))
            self._write(opts.output_path, opts.output_format, result, language)
            self.progress(100)
            self.status(f"Legenda criada: {opts.output_path.name}")
            return result
        finally:
            if audio:
                audio.unlink(missing_ok=True)
            self.model = None
            # Descarregar o modelo já devolve a VRAM no CTranslate2; o gc fecha
            # as referências restantes sem depender do torch.
            gc.collect()

    def _model_options(self, model: str) -> dict:
        # Equilibra qualidade e velocidade como no legendador original.
        if self.device == "cuda":
            result = {"beam_size": 5, "best_of": 5, "temperature": 0.0,
                      "condition_on_previous_text": True}
        else:
            result = {"beam_size": 3, "best_of": 3, "temperature": 0.1,
                      "condition_on_previous_text": True, "patience": 1}
        if model.startswith("large"):
            result.update(beam_size=3 if self.device == "cuda" else 2, best_of=2,
                          compression_ratio_threshold=2.0, log_prob_threshold=-0.8,
                          no_speech_threshold=0.5, condition_on_previous_text=False)
        if self.aggressive_filter:
            result.update(compression_ratio_threshold=1.8, log_prob_threshold=-0.5,
                          no_speech_threshold=0.4)
        return result

    def _is_hallucination(self, item: dict) -> bool:
        text = item["text"].lower().strip()
        if len(text) < 3:
            return True
        words = text.split()
        if any(words[i] == words[i - 1] == words[i - 2] for i in range(2, len(words))):
            return True
        if any(phrase in text and len(phrase) / len(text) > .5 for phrase in self.hallucination_phrases):
            return True
        log_limit = -0.8 if self.aggressive_filter else -1.0
        speech_limit = .6 if self.aggressive_filter else .8
        return ((item.get("avg_logprob") is not None and item["avg_logprob"] < log_limit) or
                (item.get("no_speech_prob") is not None and item["no_speech_prob"] > speech_limit))

    def _normalize_text(self, value: str) -> str:
        value = re.sub(r"[^\w\s\.,!?;:\-\'\"()]", "", value, flags=re.UNICODE)
        return re.sub(r"\s+", " ", value).strip()

    def _clean(self, segments: list[dict]) -> list[dict]:
        cleaned = []
        for item in segments:
            self._check_interrupt()
            if self._is_hallucination(item):
                continue
            text = self._normalize_text(item["text"])
            if not text:
                continue
            words = []
            for word in item.get("words") or ():
                word_text = self._normalize_text(str(word.get("text") or ""))
                if word_text:
                    words.append({
                        "text": word_text,
                        "start": float(word.get("start", item["start"])),
                        "end": float(word.get("end", item["end"])),
                    })
            cleaned.append({
                "start": item["start"], "end": item["end"], "text": text, "words": words,
            })
        self.status(f"Filtro de qualidade: {len(segments) - len(cleaned)} segmentos removidos")
        return cleaned

    def _lines(self, text: str) -> list[str]:
        lines, current = [], ""
        for word in text.split():
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > self.max_chars_per_line:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        return lines

    def _split_word_segment(self, segment: dict) -> list[dict]:
        """Agrupa timestamps de palavras sem inventar uma nova linha do tempo."""
        result: list[dict] = []
        group: list[dict] = []
        char_count = 0

        def flush() -> None:
            nonlocal group, char_count
            if not group:
                return
            text = " ".join(word["text"] for word in group)
            lines = self._lines(text)
            result.append({
                "start": max(segment["start"], group[0]["start"]),
                "end": min(segment["end"], group[-1]["end"]),
                "text": "\n".join(lines[:self.max_lines]),
                "words": group,
            })
            group = []
            char_count = 0

        for word in segment["words"]:
            if group:
                elapsed = word["end"] - group[0]["start"]
                sentence_break = group[-1]["text"].endswith((".", "!", "?"))
                if char_count + len(word["text"]) + 1 > self.max_chars_per_line * self.max_lines or (
                    sentence_break and elapsed >= self.min_duration
                ):
                    flush()
            group.append(word)
            char_count += len(word["text"]) + (1 if len(group) > 1 else 0)
        flush()
        return result

    def _split_segments(self, segments: list[dict]) -> list[dict]:
        result = []
        for segment in segments:
            self._check_interrupt()
            if segment.get("words"):
                result.extend(self._split_word_segment(segment))
                continue
            text, start, end = segment["text"], segment["start"], segment["end"]
            chunks = [x.strip() for x in re.split(r"(?<=[.!?])\s+", text) if x.strip()]
            if len(chunks) == 1:
                lines = self._lines(text)
                chunks = ["\n".join(lines[i:i + self.max_lines]) for i in range(0, len(lines), self.max_lines)]
            total = sum(len(x.replace("\n", " ")) for x in chunks) or 1
            cursor = start
            for index, chunk in enumerate(chunks):
                if index == len(chunks) - 1:
                    chunk_end = end
                else:
                    ideal = max(self.min_duration, min(self.max_duration,
                                len(chunk.replace("\n", " ")) / self.chars_per_second))
                    proportional = (end - start) * len(chunk.replace("\n", " ")) / total
                    chunk_end = min(end, cursor + max(self.min_duration, (ideal + proportional) / 2))
                result.append({"start": cursor, "end": chunk_end, "text": chunk, "words": []})
                cursor = chunk_end
        return result

    def _fix_timing(self, segments: list[dict]) -> list[dict]:
        for index, item in enumerate(segments):
            if index and item["start"] < segments[index - 1]["end"] + self.min_gap:
                item["start"] = segments[index - 1]["end"] + self.min_gap
            if item["end"] <= item["start"]:
                item["end"] = item["start"] + self.min_duration
            if item.get("words"):
                item["words"][0]["start"] = max(item["words"][0]["start"], item["start"])
                item["words"][-1]["end"] = min(item["words"][-1]["end"], item["end"])
        return segments

    @staticmethod
    def _timestamp(seconds: float, separator: str = ",") -> str:
        milliseconds = round(max(0, seconds) * 1000)
        hours, rest = divmod(milliseconds, 3_600_000)
        minutes, rest = divmod(rest, 60_000)
        secs, millis = divmod(rest, 1000)
        return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"

    def _write(self, path: Path, output_format: str, segments: list[dict], language: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if output_format == "srt":
            text = "\n\n".join(f"{i}\n{self._timestamp(s['start'])} --> {self._timestamp(s['end'])}\n{s['text']}"
                               for i, s in enumerate(segments, 1)) + "\n"
        elif output_format == "vtt":
            text = "WEBVTT\n\n" + "\n\n".join(
                f"{self._timestamp(s['start'], '.')} --> {self._timestamp(s['end'], '.')}\n{s['text']}"
                for s in segments) + "\n"
        elif output_format in ("ass", "karaoke"):
            style_name = "Karaoke" if output_format == "karaoke" else "Default"
            header = (
                "[Script Info]\nTitle: Baixador YT-DLP\nScriptType: v4.00+\n\n"
                "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,"
                "OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,"
                "Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
                "Style: Default,Arial,42,&H00FFFFFF,&H000000FF,&H00101010,&H80000000,0,0,0,0,"
                "100,100,0,0,1,2,1,2,32,32,28,1\n"
                "Style: Karaoke,Arial,52,&H00FFFFFF,&H0000D7FF,&H00101010,&H80000000,1,0,0,0,"
                "100,100,0,0,1,3,1,2,32,32,70,1\n\n[Events]\n"
                "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
            )

            def ass_time(value: float) -> str:
                hundredths = round(value * 100)
                hours, rest = divmod(hundredths, 360000)
                minutes, rest = divmod(rest, 6000)
                secs, cs = divmod(rest, 100)
                return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"

            def ass_escape(value: str) -> str:
                return value.replace("\\", "\\\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")

            def karaoke_text(segment: dict) -> str:
                words = segment.get("words") or []
                if not words:
                    return ass_escape(segment["text"])
                chunks = []
                for index, word in enumerate(words):
                    start = max(segment["start"], float(word["start"]))
                    end = min(segment["end"], float(word["end"]))
                    if index + 1 < len(words):
                        end = min(end, float(words[index + 1]["start"]))
                    duration = max(1, round((end - start) * 100))
                    chunks.append(f"{{\\kf{duration}}}{ass_escape(word['text'])}")
                return " ".join(chunks)

            rows = []
            for segment in segments:
                subtitle_text = (
                    karaoke_text(segment) if output_format == "karaoke"
                    else ass_escape(segment["text"])
                )
                rows.append(
                    f"Dialogue: 0,{ass_time(segment['start'])},{ass_time(segment['end'])},"
                    f"{style_name},,0,0,0,,{subtitle_text}")
            text = header + "\n".join(rows) + "\n"
        elif output_format == "txt":
            text = "\n".join(s["text"].replace("\n", " ") for s in segments) + "\n"
        elif output_format == "json":
            text = json.dumps({"language": language, "segments": segments}, ensure_ascii=False, indent=2)
        else:
            raise ValueError(f"Formato não suportado: {output_format}")
        path.write_text(text, encoding="utf-8")


def transcription_process_main(opts: TranscriptionOptions, toolchain: Toolchain, events,
                               cancel_event, pause_event) -> None:
    """Executa o motor nativo fora do processo da interface.

    Esta função fica no nível do módulo para ser serializável pelo modo
    ``spawn`` do Windows. Qualquer access violation de CTranslate2/CUDA encerra
    apenas este processo auxiliar; o processo Qt detecta o exit code.
    """
    install_diagnostics("transcription-worker")
    # O processo spawnado no Windows começa com um sys.path novo. Reativa o
    # runtime validado pelo setup antes de importar CTranslate2/faster-whisper.
    from .runtime import prepare_embedded_cuda
    cuda_problem = prepare_embedded_cuda()

    def send(kind: str, value=None) -> None:
        try:
            events.put((kind, value))
        except Exception as exc:  # noqa: BLE001 - o processo pai pode ter fechado
            report_exception("envio de evento da transcrição", exc)

    try:
        log_event("Transcrição auxiliar iniciada: entrada=%s saída=%s modelo=%s",
                  opts.media_path, opts.output_path, opts.model_size)
        transcriber = Transcriber(
            toolchain, lambda message: send("status", message),
            lambda percent: send("progress", percent), opts.aggressive_filter,
            cancel_event=cancel_event, pause_event=pause_event, force_cpu=bool(cuda_problem),
        )
        if cuda_problem:
            send("status", f"CUDA interno indisponível ({cuda_problem}). Usando CPU int8…")
        transcriber.run(opts)
    except TranscriptionCancelled:
        log_event("Transcrição auxiliar cancelada pelo usuário")
        send("cancelled")
    except Exception as exc:  # noqa: BLE001 - precisa voltar à interface sem fechá-la
        report_exception("transcrição auxiliar", exc)
        send("error", {"message": str(exc), "traceback": traceback.format_exc()})
    else:
        log_event("Transcrição auxiliar concluída: %s", opts.output_path)
        send("finished", str(opts.output_path))
