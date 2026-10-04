"""Transcrição local e exportação de legendas.

O modelo só é carregado quando a transcrição começa. NVIDIA usa
faster-whisper/CUDA; no Apple Silicon o MLX Whisper usa a GPU integrada. Todo
backend possui fallback para faster-whisper em CPU/int8, sem impedir o uso do
restante do programa.
"""
from __future__ import annotations

import gc
import json
import os
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path

from .config import MODEL_DIR
from .diagnostics import get_logger, log_event
from .hardware import whisper_threads
from .processes import popen_isolated, terminate_process_tree
from .tools import CREATE_NO_WINDOW, Toolchain
import contextlib

# Sequência padrão do Whisper: com uma temperatura só, o fallback que tira o
# decodificador de laços de repetição ficava desligado.
TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
# O VAD cortava a fala em blocos de 6 s antes do modelo e tirava contexto; a
# divisão curta das legendas já acontece depois, por palavra.
VAD_MAX_SPEECH_SECONDS = 20.0

_CUDA_ERROR_MARKERS = (
    "cublas", "cudnn", "cudart", "cuda", "cufft", "curand",
    "no cuda-capable device", "cuda driver", "out of memory",
)


def _load_wav_samples(path: Path):
    """Lê o WAV PCM16 mono gerado pelo app como float32 em [-1, 1]."""
    import wave

    import numpy as np

    with wave.open(str(path), "rb") as handle:
        frames = handle.readframes(handle.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


FORMATS = {
    "srt": ("SRT — compatível com players", ".srt"),
    "vtt": ("WebVTT — ideal para web", ".vtt"),
    "ass": ("ASS — estilo avançado", ".ass"),
    "karaoke": ("ASS karaoke — palavras sincronizadas", ".ass"),
    "txt": ("Texto simples", ".txt"),
    "json": ("JSON — segmentos e timestamps", ".json"),
}



class TranscriptionCancelled(RuntimeError):
    """Cancelamento solicitado pelo usuário."""


def _is_cuda_failure(exc: BaseException) -> bool:
    """Distingue uma falha real de CUDA de um erro do motor em geral.

    O VAD usa onnxruntime em CPU mesmo quando o Whisper usa a GPU. Portanto,
    um modelo ONNX ausente não deve descarregar vários gigabytes da GPU nem ser
    apresentado como erro de CUDA.
    """
    if type(exc).__module__.startswith("onnxruntime"):
        return False
    if isinstance(exc, (FileNotFoundError, TypeError, ValueError)):
        return False
    text = str(exc).casefold()
    return isinstance(exc, (RuntimeError, OSError)) and any(
        marker in text for marker in _CUDA_ERROR_MARKERS
    )


def _is_cuda_out_of_memory(exc: BaseException) -> bool:
    return _is_cuda_failure(exc) and "out of memory" in str(exc).casefold()


def friendly_transcription_error(exc: BaseException) -> str:
    """Torna arquivos internos ausentes acionáveis para quem usa o aplicativo."""
    text = str(exc)
    match = re.search(r"silero_(?:encoder|decoder)_v5\.onnx", text, flags=re.IGNORECASE)
    if match and ("file doesn't exist" in text.casefold() or "no_suchfile" in text.casefold()):
        from .ui.i18n import tr

        return tr("Arquivo interno do motor de transcrição ausente ({file}). "
                  "A instalação está incompleta — reinstale a versão mais recente.").format(
                      file=match.group(0))
    from .ui.i18n import tr

    folded = text.casefold()
    if "no space left" in folded or "errno 28" in folded:
        hint = tr("Não há espaço livre no disco. Libere espaço e tente de novo.")
    elif "ffmpeg" in folded and ("no such file" in folded or "errno 2" in folded or "not found" in folded):
        hint = tr("O FFmpeg do aplicativo não foi encontrado. Abra Configurações e atualize "
                  "as ferramentas, ou reinstale o aplicativo.")
    elif any(mark in folded for mark in (
            "certificate verify", "ssl:", "connection", "timed out", "name resolution",
            "max retries", "offline")):
        hint = tr("Não foi possível baixar o modelo. Verifique a conexão com a internet "
                  "e tente de novo; o download continua de onde parou.")
    elif "metadata_errors" in folded:
        hint = tr("Um componente de áudio da instalação está desatualizado. "
                  "Reinstale a versão mais recente do aplicativo.")
    elif isinstance(exc, MemoryError) or "out of memory" in folded or "cannot allocate" in folded:
        hint = tr("Faltou memória para esta transcrição. Feche outros programas ou "
                  "escolha um modelo menor.")
    else:
        return text
    return f"{hint} ({tr('detalhe técnico')}: {text})"


@dataclass(frozen=True)
class TranscriptionOptions:
    media_path: Path
    output_path: Path
    language: str = "pt"
    model_size: str = "medium"
    output_format: str = "srt"
    aggressive_filter: bool = False
    task: str = "transcribe"
    initial_prompt: str = ""
    max_chars_per_line: int = 50
    min_duration: float = 0.8
    max_duration: float = 4.5
    batched: bool = False     # BatchedInferencePipeline (somente CUDA)
    low_vram: bool = False    # int8_float16 em GPUs com pouca memória


@dataclass(frozen=True)
class DecodedInfo:
    """Campos comuns aos resultados do faster-whisper e do MLX Whisper."""

    language: str
    language_probability: float = 0.0


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
        # Bibliotecas do motor (ex.: mlx_whisper) chamam "ffmpeg" pelo PATH. O do
        # app fica na pasta de binários; vale só para este processo auxiliar.
        ffmpeg = getattr(toolchain, "ffmpeg", None)
        if ffmpeg:
            folder = str(Path(ffmpeg).parent)
            paths = os.environ.get("PATH", "").split(os.pathsep)
            if folder not in paths:
                os.environ["PATH"] = os.pathsep.join([folder, *paths])
        self.model = None
        self._model_path: Path | None = None
        # O processo persistente conserva o motor na memória entre itens da
        # fila.  Estes campos identificam exatamente qual configuração está
        # carregada para recarregar somente quando a pessoa troca o modelo ou
        # o perfil de memória da GPU.
        self._loaded_model_size: str | None = None
        self._loaded_model_profile: tuple[str, str, str] | None = None
        self._hardware_label_base = self.hardware_label
        self._cuda_profile = (self.backend, self.device, self.compute_type, self.hardware_label) \
            if self.device == "cuda" else None
        self._retry_cuda_after_oom = False

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
        model_path = download_model_snapshot(
            model_size,
            mlx=False,
            status=self.status,
            progress=self.progress,
            progress_range=(5, 14),
        )
        self.status(f"Carregando Whisper {model_size} em {self.hardware_label}…")
        kwargs = {"device": self.device, "compute_type": self.compute_type}
        if self.device == "cpu":
            kwargs.update(cpu_threads=whisper_threads(), num_workers=1)
        try:
            self.model = WhisperModel(str(model_path), **kwargs)
        except Exception as exc:
            if self.device != "cuda" or not _is_cuda_failure(exc):
                raise
            # OOM costuma ser resolvido pelo perfil de pouca VRAM sem abandonar
            # a GPU. Demais falhas CUDA deixam o processo em CPU até reiniciar.
            if _is_cuda_out_of_memory(exc) and self.compute_type != "int8_float16":
                self.status("GPU sem memória ao carregar o modelo. Tentando modo pouca VRAM…")
                self.compute_type = "int8_float16"
                self.hardware_label = self._hardware_label_base + " · int8_float16"
                try:
                    self.model = WhisperModel(
                        str(model_path), device="cuda", compute_type="int8_float16",
                    )
                except Exception as retry_exc:
                    if not _is_cuda_failure(retry_exc):
                        raise
                    self._set_cpu_fallback(retry_exc, retry_gpu_next_job=_is_cuda_out_of_memory(retry_exc))
                    self.model = WhisperModel(
                        str(model_path), device="cpu", compute_type="int8",
                        cpu_threads=whisper_threads(), num_workers=1,
                    )
            else:
                self._set_cpu_fallback(exc)
                self.model = WhisperModel(
                    str(model_path), device="cpu", compute_type="int8",
                    cpu_threads=whisper_threads(), num_workers=1,
                )
        self.progress(15)
        self._loaded_model_size = model_size
        self._loaded_model_profile = (self.backend, self.device, self.compute_type)
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
        self._model_path = download_model_snapshot(
            model_size,
            mlx=True,
            status=self.status,
            progress=self.progress,
            progress_range=(5, 14),
        )
        self._loaded_model_size = model_size
        self._loaded_model_profile = (self.backend, self.device, self.compute_type)
        self.status(f"Carregando Whisper {model_size} em {self.hardware_label}…")

    @staticmethod
    def _model_spec(model_size: str, *, mlx: bool) -> tuple[str, str]:
        return model_spec(model_size, mlx=mlx)

    @classmethod
    def _pinned_model_path(cls, model_size: str, *, mlx: bool) -> Path:
        # Mantido como helper simples e determinístico para integrações e testes.
        # Os fluxos da interface usam ``download_model_snapshot`` para também
        # receber andamento em bytes.
        from huggingface_hub import snapshot_download

        repo, revision = cls._model_spec(model_size, mlx=mlx)
        cache = _model_cache_dir(mlx)
        cache.mkdir(parents=True, exist_ok=True)
        return Path(snapshot_download(
            repo_id=repo,
            revision=revision,
            cache_dir=str(cache),
        ))

    def _set_cpu_fallback(self, reason: BaseException, *, retry_gpu_next_job: bool = False) -> None:
        """Registra e ativa CPU para uma falha CUDA confirmada."""
        continuation = (
            " A GPU será tentada novamente no próximo item."
            if retry_gpu_next_job else
            " O servidor continuará em CPU até o aplicativo ser reiniciado."
        )
        self.status(
            f"CUDA indisponível durante a transcrição ({reason}). Alternando para CPU int8…"
            + continuation
        )
        log_event("Fallback CUDA para CPU: %s%s", reason, continuation)
        self.device, self.compute_type = "cpu", "int8"
        self.hardware_label = "CPU — fallback automático (int8)"
        self._hardware_label_base = self.hardware_label
        self._retry_cuda_after_oom = retry_gpu_next_job

    def _restore_cuda_after_oom(self) -> None:
        if not self._retry_cuda_after_oom or self._cuda_profile is None:
            return
        self._discard_model()
        self.backend, self.device, self.compute_type, self.hardware_label = self._cuda_profile
        self._hardware_label_base = self.hardware_label
        self._retry_cuda_after_oom = False
        self.status("Tentando a GPU novamente após a falta de memória no item anterior…")

    def _switch_to_cpu(
        self, model_size: str, reason: BaseException, *, retry_gpu_next_job: bool = False,
    ) -> None:
        """Troca de CUDA para CPU quando uma DLL/driver falha durante o uso."""
        from faster_whisper import WhisperModel

        self._discard_model()
        self._set_cpu_fallback(reason, retry_gpu_next_job=retry_gpu_next_job)
        model_path = download_model_snapshot(
            model_size,
            mlx=False,
            status=self.status,
            progress=self.progress,
            progress_range=(5, 14),
        )
        self.model = WhisperModel(
            str(model_path), device="cpu", compute_type="int8",
            cpu_threads=whisper_threads(), num_workers=1,
        )
        self._loaded_model_size = model_size
        self._loaded_model_profile = (self.backend, self.device, self.compute_type)
        self.status(f"Modelo pronto: {self.hardware_label}")

    def _switch_to_low_vram(self, model_size: str, reason: BaseException) -> None:
        """Tenta a GPU em int8_float16 antes de desistir dela por falta de VRAM."""
        from faster_whisper import WhisperModel

        self.status(f"GPU sem memória durante a transcrição ({reason}). Tentando modo pouca VRAM…")
        self._discard_model()
        self.compute_type = "int8_float16"
        self.hardware_label = self._hardware_label_base + " · int8_float16"
        model_path = download_model_snapshot(
            model_size,
            mlx=False,
            status=self.status,
            progress=self.progress,
            progress_range=(5, 14),
        )
        self.model = WhisperModel(str(model_path), device="cuda", compute_type="int8_float16")
        self._loaded_model_size = model_size
        self._loaded_model_profile = (self.backend, self.device, self.compute_type)
        self.status(f"Modelo pronto: {self.hardware_label}")

    def _switch_mlx_to_cpu(self, model_size: str, reason: Exception) -> None:
        """Fallback seguro quando um Mac não consegue inicializar o MLX."""
        self.status(f"MLX indisponível durante a transcrição ({reason}). Alternando para CPU int8…")
        # O pacote de diagnóstico só recebia a mensagem da interface; o tipo da
        # exceção e o rastreio ficam no log para achar a causa (ex.: ffmpeg ausente).
        get_logger().warning(
            "Fallback MLX para CPU: %s: %s", type(reason).__name__, reason, exc_info=reason)
        self.backend, self.device, self.compute_type = "faster-whisper", "cpu", "int8"
        self.hardware_label = "Apple Silicon — fallback CPU/NEON (int8)"
        self._discard_model()
        self._load_model(model_size)

    def _discard_model(self) -> None:
        """Libera o modelo somente quando ele não serve mais para o próximo item."""
        self.model = None
        self._loaded_model_size = None
        self._loaded_model_profile = None
        gc.collect()

    def close(self) -> None:
        """Libera os pesos ao encerrar o processo persistente do legendador."""
        self._discard_model()
        self._model_path = None

    def _prepare_model_for(self, opts: TranscriptionOptions) -> None:
        """Mantém o modelo vivo se o próximo item usa a mesma configuração."""
        self._restore_cuda_after_oom()
        if self.backend == "mlx":
            if self._loaded_model_size != opts.model_size or self._model_path is None:
                self._prepare_mlx(opts.model_size)
            return

        desired_compute = self.compute_type
        if self.device == "cuda":
            desired_compute = "int8_float16" if opts.low_vram else "float16"
            suffix = " · int8_float16" if opts.low_vram else ""
            self.hardware_label = self._hardware_label_base + suffix

        desired_profile = (self.backend, self.device, desired_compute)
        if (self.model is not None and
                (self._loaded_model_size != opts.model_size or
                 self._loaded_model_profile != desired_profile)):
            self._discard_model()
        self.compute_type = desired_compute
        if self.model is None:
            self._load_model(opts.model_size)

    def _decode_faster_whisper(self, audio: Path, opts: TranscriptionOptions,
                               duration: float) -> tuple[list[dict], object]:
        """Consome o gerador do faster-whisper; erros de DLL podem ocorrer só aqui."""
        segments, info = self.model.transcribe(
            self._audio_input(audio), language=None if opts.language == "auto" else opts.language,
            task=opts.task if opts.task in {"transcribe", "translate"} else "transcribe",
            initial_prompt=opts.initial_prompt.strip() or None,
            word_timestamps=True, vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 250, "speech_pad_ms": 50,
                            "max_speech_duration_s": VAD_MAX_SPEECH_SECONDS},
            **self._model_options(opts.model_size),
        ) if not (opts.batched and self.device == "cuda") else self._batched_transcribe(audio, opts)
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
        # O MLX só tem decodificação gulosa/amostragem: beam_size levanta
        # "Beam search decoder is not yet implemented" e patience exige beam_size.
        options.pop("beam_size", None)
        options.pop("patience", None)
        temperature = options.pop("temperature", 0.0)
        condition = options.pop("condition_on_previous_text", True)
        compression = options.pop("compression_ratio_threshold", 2.4)
        log_probability = options.pop("log_prob_threshold", -1.0)
        no_speech = options.pop("no_speech_threshold", 0.6)
        # O mlx_whisper decodifica caminhos chamando "ffmpeg" pelo PATH, mas o
        # FFmpeg do app fica na pasta de binários (fora do PATH do Mac). O WAV
        # 16 kHz mono já foi gerado por _extract_audio; entregamos as amostras.
        result = mlx_whisper.transcribe(
            _load_wav_samples(audio), path_or_hf_repo=str(self._model_path), verbose=None,
            language=None if opts.language == "auto" else opts.language,
            task=opts.task if opts.task in {"transcribe", "translate"} else "transcribe",
            initial_prompt=opts.initial_prompt.strip() or None,
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
        handle = tempfile.NamedTemporaryFile(  # noqa: SIM115 - fechado logo abaixo; o arquivo fica (delete=False)
            prefix="baixador-ytdlp-whisper-", suffix=".wav", delete=False)
        handle.close()
        target = Path(handle.name)
        self.status("Preparando áudio em 16 kHz mono…")
        cmd = [str(self.toolchain.ffmpeg), "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "pcm_s16le", str(target)]
        proc = popen_isolated(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
        )
        try:
            while True:
                try:
                    _, stderr = proc.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    self._check_interrupt()
        except BaseException:
            terminate_process_tree(proc)
            with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
                proc.communicate(timeout=3)
            target.unlink(missing_ok=True)
            raise
        if proc.returncode:
            target.unlink(missing_ok=True)
            raise RuntimeError("Não foi possível extrair o áudio: " + (stderr or "")[-600:])
        return target

    def run(self, opts: TranscriptionOptions) -> list[dict]:
        if not opts.media_path.is_file():
            raise FileNotFoundError("Selecione um arquivo de áudio ou vídeo válido.")
        audio: Path | None = None
        try:
            self._check_interrupt()
            self._prepare_model_for(opts)
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
                elif self.device == "cuda" and _is_cuda_failure(exc):
                    # A carga das DLLs CUDA é preguiçosa; erros como
                    # cublas64_12.dll ausente aparecem ao iterar os segmentos.
                    if _is_cuda_out_of_memory(exc) and self.compute_type != "int8_float16":
                        self._switch_to_low_vram(opts.model_size, exc)
                        try:
                            raw, info = self._decode(audio, opts, duration)
                        except Exception as retry_exc:
                            if not _is_cuda_failure(retry_exc):
                                raise
                            self._switch_to_cpu(
                                opts.model_size,
                                retry_exc,
                                retry_gpu_next_job=_is_cuda_out_of_memory(retry_exc),
                            )
                            raw, info = self._decode(audio, opts, duration)
                    else:
                        self._switch_to_cpu(
                            opts.model_size,
                            exc,
                            retry_gpu_next_job=_is_cuda_out_of_memory(exc),
                        )
                        raw, info = self._decode(audio, opts, duration)
                else:
                    raise
            language = str(getattr(info, "language", "auto"))
            probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            confidence = f" ({probability:.0%})" if probability else ""
            self.status(f"{len(raw)} segmentos brutos · idioma {language}{confidence}")
            self.max_chars_per_line = max(20, min(100, int(opts.max_chars_per_line)))
            self.min_duration = max(0.2, min(5.0, float(opts.min_duration)))
            self.max_duration = max(self.min_duration, min(15.0, float(opts.max_duration)))
            result = self._fix_timing(self._split_segments(self._clean(raw)))
            self._write(opts.output_path, opts.output_format, result, language)
            self.progress(100)
            self.status(f"Legenda criada: {opts.output_path.name}")
            return result
        finally:
            if audio:
                audio.unlink(missing_ok=True)

    def _batched_transcribe(self, audio: Path, opts: TranscriptionOptions):
        """Processa vários trechos em paralelo na GPU (faster-whisper ≥ 1.1).

        A assinatura do pipeline em lote aceita menos parâmetros que a do
        modelo; filtrar pelo ``inspect`` evita TypeError entre versões.
        """
        import inspect

        from faster_whisper import BatchedInferencePipeline

        self.status("Modo rápido: processando trechos em lote na GPU…")
        pipeline = BatchedInferencePipeline(model=self.model)
        options = {
            "language": None if opts.language == "auto" else opts.language,
            "task": opts.task if opts.task in {"transcribe", "translate"} else "transcribe",
            "initial_prompt": opts.initial_prompt.strip() or None,
            "word_timestamps": True,
            "batch_size": 8 if opts.low_vram else 16,
            **self._model_options(opts.model_size),
        }
        accepted = inspect.signature(pipeline.transcribe).parameters
        options = {key: value for key, value in options.items() if key in accepted}
        return pipeline.transcribe(self._audio_input(audio), **options)

    @staticmethod
    def _audio_input(audio: Path):
        """Entrega ao faster-whisper o WAV 16 kHz mono que o app gerou, como amostras.

        Assim ele não decodifica o arquivo de novo com o PyAV (``av.open(...,
        metadata_errors=...)`` falha com um PyAV antigo) e a transcrição não
        depende de componentes do ambiente do usuário.
        """
        return _load_wav_samples(audio)

    def _model_options(self, model: str) -> dict:
        # Equilibra qualidade e velocidade como no legendador original.
        if self.device == "cuda":
            result = {"beam_size": 5, "best_of": 5, "temperature": TEMPERATURE_FALLBACK,
                      "condition_on_previous_text": True}
        else:
            result = {"beam_size": 3, "best_of": 3, "temperature": TEMPERATURE_FALLBACK,
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
        # Por palavra inteira: "musical", "precisos" e "compartilhei" contêm "music", "risos" e
        # "compartilhe" e eram descartados como se fossem marcações do Whisper.
        if any(len(phrase) / len(text) > .5 and re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text)
               for phrase in self.hallucination_phrases):
            return True
        log_limit = -0.8 if self.aggressive_filter else -1.0
        speech_limit = .6 if self.aggressive_filter else .8
        return ((item.get("avg_logprob") is not None and item["avg_logprob"] < log_limit) or
                (item.get("no_speech_prob") is not None and item["no_speech_prob"] > speech_limit))

    # Símbolos que aparecem em fala transcrita ficam (R$ 50, 24/7, 50%, e-mail@x,
    # C++). Saem emoji, notas musicais e marcação que players interpretariam
    # como tag ou estilo (<>, {}).
    _DISALLOWED_CHARS = re.compile(
        r"[^\w\s.,!?;:'\"()\[\]%$€£/&@#+=*«»“”‘’…¿¡–—°ºª-]", re.UNICODE)

    def _normalize_text(self, value: str) -> str:
        value = self._DISALLOWED_CHARS.sub("", value)
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
                shown = group[-1]["end"] - group[0]["start"]
                sentence_break = group[-1]["text"].endswith((".", "!", "?"))
                # A duração máxima vale também no caminho por palavra, que é o
                # usado sempre (word_timestamps=True). Sem isto, fala lenta
                # gerava blocos de 8–10 s ignorando o limite da interface.
                too_long = elapsed > self.max_duration and shown >= self.min_duration
                # O grupo pode caber em 2×limite caracteres e mesmo assim precisar de 3 linhas
                # (palavras longas); o corte em max_lines apagava o fim do texto.
                overflow = len(self._lines(" ".join([g["text"] for g in group] + [word["text"]]))
                               ) > self.max_lines
                if (char_count + len(word["text"]) + 1 > self.max_chars_per_line * self.max_lines
                        or overflow
                        or (sentence_break and elapsed >= self.min_duration)
                        or too_long):
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


# O que mudou de módulo continua importável daqui (workers, UI e testes usam estes nomes).
from .models import (  # noqa: E402, F401
    FASTER_MODEL_SPECS,
    MLX_MODEL_SPECS,
    MODEL_ORDER,
    ProgressCB,
    StatusCB,
    _is_apple_silicon,
    _mlx_available,
    _model_cache_dir,
    _repo_blob_size,
    _snapshot_download_with_symlink_retry,
    _warm_huggingface_symlink_support,
    cached_model_path,
    download_model_snapshot,
    legacy_model_cache_size,
    migrate_legacy_model_cache,
    model_cache_size,
    model_spec,
    preferred_model_backend,
    remove_cached_model,
    remove_legacy_model_cache,
)


def __getattr__(name: str):
    """Os processos de transcrição vivem em ``transcription_server`` (evita import circular)."""
    if name in {"transcription_server_main", "transcription_process_main"}:
        from . import transcription_server

        return getattr(transcription_server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
