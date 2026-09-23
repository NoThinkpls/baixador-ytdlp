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
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import MODEL_DIR
from .diagnostics import install_diagnostics, log_event, report_exception
from .hardware import whisper_threads
from .processes import popen_isolated, terminate_process_tree
from .tools import CREATE_NO_WINDOW, Toolchain

StatusCB = Callable[[str], None]
ProgressCB = Callable[[int], None]

# Sequência padrão do Whisper: com uma temperatura só, o fallback que tira o
# decodificador de laços de repetição ficava desligado.
TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
# O VAD cortava a fala em blocos de 6 s antes do modelo e tirava contexto; a
# divisão curta das legendas já acontece depois, por palavra.
VAD_MAX_SPEECH_SECONDS = 20.0

MODEL_ORDER = ("tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")

FORMATS = {
    "srt": ("SRT — compatível com players", ".srt"),
    "vtt": ("WebVTT — ideal para web", ".vtt"),
    "ass": ("ASS — estilo avançado", ".ass"),
    "karaoke": ("ASS karaoke — palavras sincronizadas", ".ass"),
    "txt": ("Texto simples", ".txt"),
    "json": ("JSON — segmentos e timestamps", ".json"),
}

# Repositórios e revisões imutáveis dos pesos. Usar ``main`` permitiria trocar
# vários gigabytes de código/dados sem uma nova versão do aplicativo.
FASTER_MODEL_SPECS = {
    "tiny": ("Systran/faster-whisper-tiny", "d90ca5fe260221311c53c58e660288d3deb8d356"),
    "base": ("Systran/faster-whisper-base", "ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66"),
    "small": ("Systran/faster-whisper-small", "536b0662742c02347bc0e980a01041f333bce120"),
    "medium": ("Systran/faster-whisper-medium", "08e178d48790749d25932bbc082711ddcfdfbc4f"),
    "large": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
    "large-v2": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
    "large-v3": ("Systran/faster-whisper-large-v3", "edaa852ec7e145841d8ffdb056a99866b5f0a478"),
    "large-v3-turbo": (
        "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
        "0a363e9161cbc7ed1431c9597a8ceaf0c4f78fcf",
    ),
}

# Pesos convertidos para MLX. Não usamos CTranslate2 no Mac quando o runtime MLX
# está presente: a GPU integrada é mais rápida e compartilha memória com a CPU.
MLX_MODEL_SPECS = {
    "tiny": ("mlx-community/whisper-tiny-mlx", "b8e1517aa75d652c34086b8f5a47cee5b7edee3e"),
    "base": ("mlx-community/whisper-base-mlx", "dbd18c08dc2a2e299c3f16b25902a785af158c9e"),
    "small": ("mlx-community/whisper-small-mlx", "eb52dbc58f50f19eb8c87b54b7c621633c67b7e0"),
    "medium": ("mlx-community/whisper-medium-mlx", "23bf35993c90e62837672b12d4d2e481d73db2da"),
    "large": ("mlx-community/whisper-large-v3-mlx", "ac13a70a47c7176ba7b69b4f1ebe6877ccd460d0"),
    "large-v2": ("mlx-community/whisper-large-v3-mlx", "ac13a70a47c7176ba7b69b4f1ebe6877ccd460d0"),
    "large-v3": ("mlx-community/whisper-large-v3-mlx", "ac13a70a47c7176ba7b69b4f1ebe6877ccd460d0"),
    "large-v3-turbo": (
        "mlx-community/whisper-large-v3-turbo",
        "a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
    ),
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


def preferred_model_backend() -> bool:
    """Retorna ``True`` quando o gerenciador deve operar sobre pesos MLX."""
    return _is_apple_silicon() and _mlx_available()


def _model_cache_dir(mlx: bool) -> Path:
    return MODEL_DIR / ("mlx" if mlx else "ctranslate2")


def _repo_blob_size(cache: Path, repo: str) -> int:
    blobs = cache / f"models--{repo.replace('/', '--')}" / "blobs"
    total = 0
    if not blobs.is_dir():
        return 0
    for path in blobs.iterdir():
        try:
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def cached_model_path(model_size: str, *, mlx: bool | None = None) -> Path | None:
    """Localiza uma revisão completa sem abrir rede nem carregar o modelo."""
    from huggingface_hub import snapshot_download

    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo, revision = Transcriber._model_spec(model_size, mlx=use_mlx)
    cache = _model_cache_dir(use_mlx)
    try:
        return Path(snapshot_download(
            repo_id=repo,
            revision=revision,
            cache_dir=str(cache),
            local_files_only=True,
        ))
    except Exception:
        return None


def model_cache_size(model_size: str, *, mlx: bool | None = None) -> int:
    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo, _revision = Transcriber._model_spec(model_size, mlx=use_mlx)
    return _repo_blob_size(_model_cache_dir(use_mlx), repo)


def remove_cached_model(model_size: str, *, mlx: bool | None = None) -> int:
    """Remove somente a revisão fixada do modelo e devolve os bytes liberados."""
    from huggingface_hub import scan_cache_dir

    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo_id, revision = Transcriber._model_spec(model_size, mlx=use_mlx)
    cache = _model_cache_dir(use_mlx)
    before = model_cache_size(model_size, mlx=use_mlx)
    if not cache.exists():
        return 0
    info = scan_cache_dir(cache)
    revisions = [
        item.commit_hash
        for repo in info.repos if repo.repo_id == repo_id
        for item in repo.revisions if item.commit_hash.startswith(revision)
    ]
    if revisions:
        info.delete_revisions(*revisions).execute()
    return max(0, before - model_cache_size(model_size, mlx=use_mlx))


def download_model_snapshot(
    model_size: str,
    *,
    mlx: bool | None = None,
    status: StatusCB | None = None,
    progress: ProgressCB | None = None,
    progress_range: tuple[int, int] = (0, 100),
) -> Path:
    """Baixa uma revisão imutável e acompanha os bytes gravados no cache."""
    from huggingface_hub import HfApi, snapshot_download

    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo, revision = Transcriber._model_spec(model_size, mlx=use_mlx)
    cache = _model_cache_dir(use_mlx)
    cache.mkdir(parents=True, exist_ok=True)
    existing = cached_model_path(model_size, mlx=use_mlx)
    if existing is not None:
        if progress:
            progress(progress_range[1])
        return existing

    if status:
        status(f"Baixando modelo Whisper {model_size}…")
    low, high = progress_range
    if progress:
        progress(low)
    try:
        metadata = HfApi().model_info(repo, revision=revision, files_metadata=True)
        total = sum(int(getattr(item, "size", 0) or 0) for item in metadata.siblings or ())
    except Exception:
        total = 0
    before = _repo_blob_size(cache, repo)
    outcome: dict[str, object] = {}

    def fetch() -> None:
        try:
            outcome["path"] = snapshot_download(
                repo_id=repo,
                revision=revision,
                cache_dir=str(cache),
            )
        except BaseException as exc:  # propagado na thread chamadora
            outcome["error"] = exc

    download = threading.Thread(target=fetch, name="whisper-model-download", daemon=True)
    download.start()
    while download.is_alive():
        if progress and total > 0:
            received = max(0, _repo_blob_size(cache, repo) - before)
            progress(min(high - 1, low + round((high - low) * received / total)))
        time.sleep(0.2)
    download.join()
    if "error" in outcome:
        raise outcome["error"]  # type: ignore[misc]
    if progress:
        progress(high)
    return Path(str(outcome["path"]))


def migrate_legacy_model_cache(model_dir: Path = MODEL_DIR) -> list[str]:
    """Move pesos baixados por versões ≤ 1.7 para o cache novo.

    Até a 1.7 o faster-whisper gravava em ``models/models--*`` e o MLX em
    ``models/mlx/hub/models--*``. Desde a 1.8 os caches são ``models/ctranslate2``
    e ``models/mlx``; sem migrar, os gigabytes antigos ficavam invisíveis para
    o gerenciador e os mesmos modelos eram baixados de novo. Mover dentro do
    mesmo volume é instantâneo, e os blobs já existentes são reaproveitados
    pela revisão fixada.
    """
    moved: list[str] = []
    pairs = ((model_dir, model_dir / "ctranslate2"),
             (model_dir / "mlx" / "hub", model_dir / "mlx"))
    for legacy_root, new_root in pairs:
        if not legacy_root.is_dir():
            continue
        for legacy in legacy_root.glob("models--*"):
            target = new_root / legacy.name
            if not legacy.is_dir() or target.exists():
                continue
            try:
                new_root.mkdir(parents=True, exist_ok=True)
                legacy.replace(target)
                moved.append(legacy.name)
            except OSError:
                continue
    return moved


def legacy_model_cache_size(model_dir: Path = MODEL_DIR) -> int:
    """Bytes que sobraram no formato antigo (duplicados já migrados etc.)."""
    total = 0
    for root in (model_dir, model_dir / "mlx" / "hub"):
        if not root.is_dir():
            continue
        for legacy in root.glob("models--*"):
            for path in legacy.rglob("*"):
                try:
                    if path.is_file() and not path.is_symlink():
                        total += path.stat().st_size
                except OSError:
                    continue
    return total


def remove_legacy_model_cache(model_dir: Path = MODEL_DIR) -> int:
    import shutil

    freed = legacy_model_cache_size(model_dir)
    for root in (model_dir, model_dir / "mlx" / "hub"):
        if root.is_dir():
            for legacy in root.glob("models--*"):
                shutil.rmtree(legacy, ignore_errors=True)
    return freed


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
        self._model_path: Path | None = None
        # O processo persistente conserva o motor na memória entre itens da
        # fila.  Estes campos identificam exatamente qual configuração está
        # carregada para recarregar somente quando a pessoa troca o modelo ou
        # o perfil de memória da GPU.
        self._loaded_model_size: str | None = None
        self._loaded_model_profile: tuple[str, str, str] | None = None
        self._hardware_label_base = self.hardware_label

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
            if self.device != "cuda":
                raise
            # Driver, wheel CUDA ou cuDNN podem não estar presentes; CPU é melhor que falhar.
            self.status(f"CUDA indisponível para o Whisper ({exc}). Alternando para CPU int8…")
            self.device, self.compute_type = "cpu", "int8"
            self.hardware_label = "CPU — fallback automático (int8)"
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
        specs = MLX_MODEL_SPECS if mlx else FASTER_MODEL_SPECS
        return specs.get(model_size, specs["medium"])

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

    def _switch_to_cpu(self, model_size: str, reason: Exception) -> None:
        """Troca de CUDA para CPU quando uma DLL/driver falha durante o uso."""
        from faster_whisper import WhisperModel

        self.status(f"CUDA indisponível durante a transcrição ({reason}). Alternando para CPU int8…")
        self._discard_model()
        self.device, self.compute_type = "cpu", "int8"
        self.hardware_label = "CPU — fallback automático (int8)"
        self._hardware_label_base = self.hardware_label
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

    def _switch_mlx_to_cpu(self, model_size: str, reason: Exception) -> None:
        """Fallback seguro quando um Mac não consegue inicializar o MLX."""
        self.status(f"MLX indisponível durante a transcrição ({reason}). Alternando para CPU int8…")
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
            str(audio), language=None if opts.language == "auto" else opts.language,
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
        temperature = options.pop("temperature", 0.0)
        condition = options.pop("condition_on_previous_text", True)
        compression = options.pop("compression_ratio_threshold", 2.4)
        log_probability = options.pop("log_prob_threshold", -1.0)
        no_speech = options.pop("no_speech_threshold", 0.6)
        result = mlx_whisper.transcribe(
            str(audio), path_or_hf_repo=str(self._model_path), verbose=None,
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
        handle = tempfile.NamedTemporaryFile(prefix="baixador-ytdlp-whisper-", suffix=".wav", delete=False)
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
            try:
                proc.communicate(timeout=3)
            except (subprocess.TimeoutExpired, OSError, ValueError):
                pass
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
        return pipeline.transcribe(str(audio), **options)

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


def transcription_server_main(toolchain: Toolchain, commands, events) -> None:
    """Mantém um único processo de Whisper para toda a fila de legendas.

    O processo continua separado da interface para que uma falha nativa de
    CUDA/CTranslate2 nunca derrube a janela. Diferente do worker antigo, ele
    recebe vários trabalhos pela fila de comandos e preserva o ``Transcriber``
    (e portanto os pesos já carregados) enquanto modelo e perfil de GPU não
    mudarem.
    """
    install_diagnostics("transcription-server")
    from .runtime import prepare_embedded_cuda

    cuda_problem = prepare_embedded_cuda()
    jobs: queue.Queue = queue.Queue()
    cancel_event = threading.Event()
    pause_event = threading.Event()
    stop_event = threading.Event()
    active_job: list[int | None] = [None]
    pending_cancellations: set[int] = set()
    pending_pauses: dict[int, bool] = {}

    def send(job_id: int, kind: str, value=None) -> None:
        try:
            events.put((job_id, kind, value))
        except Exception as exc:  # noqa: BLE001 - o pai pode ter sido encerrado
            report_exception("envio de evento do servidor de transcrição", exc)

    def receive_commands() -> None:
        """Escuta pausa/cancelamento enquanto o motor nativo está ocupado."""
        while not stop_event.is_set():
            try:
                command = commands.get()
            except (EOFError, OSError):
                stop_event.set()
                cancel_event.set()
                return
            if not command:
                continue
            kind = command[0]
            target = command[1] if len(command) > 1 else None
            if kind == "cancel":
                if target == active_job[0]:
                    cancel_event.set()
                elif isinstance(target, int):
                    pending_cancellations.add(target)
            elif kind == "pause":
                paused = bool(command[2])
                if target == active_job[0]:
                    if paused:
                        pause_event.set()
                    else:
                        pause_event.clear()
                elif isinstance(target, int):
                    pending_pauses[target] = paused
            elif kind == "shutdown":
                stop_event.set()
                cancel_event.set()
                jobs.put(("shutdown",))
                return
            elif kind == "run":
                jobs.put(command)

    listener = threading.Thread(
        target=receive_commands, name="whisper-command-listener", daemon=True,
    )
    listener.start()
    transcriber: Transcriber | None = None

    try:
        while not stop_event.is_set():
            command = jobs.get()
            if not command or command[0] == "shutdown":
                break
            _kind, job_id, opts = command
            active_job[0] = int(job_id)
            cancel_event.clear()
            pause_event.clear()
            if int(job_id) in pending_cancellations:
                pending_cancellations.discard(int(job_id))
                cancel_event.set()
            if pending_pauses.pop(int(job_id), False):
                pause_event.set()
            try:
                if transcriber is None:
                    transcriber = Transcriber(
                        toolchain,
                        lambda message: send(int(job_id), "status", message),
                        lambda percent: send(int(job_id), "progress", percent),
                        opts.aggressive_filter,
                        cancel_event=cancel_event,
                        pause_event=pause_event,
                        force_cpu=bool(cuda_problem),
                    )
                    if cuda_problem:
                        send(int(job_id), "status",
                             f"CUDA interno indisponível ({cuda_problem}). Usando CPU int8…")
                else:
                    # Os filtros são escolhas de cada item, não uma propriedade
                    # permanente do modelo em memória.
                    transcriber.aggressive_filter = opts.aggressive_filter
                    transcriber.status = lambda message: send(int(job_id), "status", message)
                    transcriber.progress = lambda percent: send(int(job_id), "progress", percent)

                log_event("Transcrição persistente iniciada: entrada=%s saída=%s modelo=%s",
                          opts.media_path, opts.output_path, opts.model_size)
                transcriber.run(opts)
            except TranscriptionCancelled:
                log_event("Transcrição persistente cancelada pelo usuário")
                send(int(job_id), "cancelled")
            except Exception as exc:  # noqa: BLE001 - precisa voltar à interface
                report_exception("transcrição persistente", exc)
                send(int(job_id), "error", {
                    "message": str(exc), "traceback": traceback.format_exc(),
                })
            else:
                log_event("Transcrição persistente concluída: %s", opts.output_path)
                send(int(job_id), "finished", str(opts.output_path))
            finally:
                active_job[0] = None
                pause_event.clear()
    finally:
        if transcriber is not None:
            transcriber.close()

