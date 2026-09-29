"""Pesos do Whisper: repositórios fixos, cache local, download e migração.

Separado do ``transcription.py`` (o motor de decodificação): aqui não há nada de GPU nem de
áudio, só onde os modelos ficam no disco e de onde eles vêm.
"""
from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from .config import MODEL_DIR
from .diagnostics import log_event

StatusCB = Callable[[str], None]
ProgressCB = Callable[[int], None]

MODEL_ORDER = ("tiny", "base", "small", "medium", "large-v3-turbo", "large-v3")

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


def model_spec(model_size: str, *, mlx: bool) -> tuple[str, str]:
    """Repositório e revisão fixos do modelo (``medium`` se o nome for desconhecido)."""
    specs = MLX_MODEL_SPECS if mlx else FASTER_MODEL_SPECS
    return specs.get(model_size, specs["medium"])


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
    repo, revision = model_spec(model_size, mlx=use_mlx)
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


def _warm_huggingface_symlink_support(cache: Path, repo: str) -> None:
    """Resolve antes das threads se este cache pode usar symlinks no Windows."""
    from huggingface_hub.file_download import are_symlinks_supported

    repo_cache = cache / f"models--{repo.replace('/', '--')}"
    repo_cache.mkdir(parents=True, exist_ok=True)
    try:  # noqa: SIM105 - o motivo está no comentário do except
        are_symlinks_supported(repo_cache)
    except OSError:
        # O hub cai para cópia de arquivos quando symlink não é permitido.
        pass


def _snapshot_download_with_symlink_retry(snapshot_download, **kwargs) -> str:
    """Repete uma vez o caso transitório de privilégio de symlink do Windows."""
    try:
        return snapshot_download(**kwargs)
    except OSError as exc:
        if getattr(exc, "winerror", None) != 1314:
            raise
        log_event("Hugging Face recusou symlink (WinError 1314); repetindo download em modo cópia")
        return snapshot_download(**kwargs)


def model_cache_size(model_size: str, *, mlx: bool | None = None) -> int:
    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo, _revision = model_spec(model_size, mlx=use_mlx)
    return _repo_blob_size(_model_cache_dir(use_mlx), repo)


def remove_cached_model(model_size: str, *, mlx: bool | None = None) -> int:
    """Remove somente a revisão fixada do modelo e devolve os bytes liberados."""
    from huggingface_hub import scan_cache_dir

    use_mlx = preferred_model_backend() if mlx is None else mlx
    repo_id, revision = model_spec(model_size, mlx=use_mlx)
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
    repo, revision = model_spec(model_size, mlx=use_mlx)
    cache = _model_cache_dir(use_mlx)
    cache.mkdir(parents=True, exist_ok=True)
    existing = cached_model_path(model_size, mlx=use_mlx)
    if existing is not None:
        if progress:
            progress(progress_range[1])
        return existing

    _warm_huggingface_symlink_support(cache, repo)

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
            outcome["path"] = _snapshot_download_with_symlink_retry(
                snapshot_download,
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

    freed = legacy_model_cache_size(model_dir)
    for root in (model_dir, model_dir / "mlx" / "hub"):
        if root.is_dir():
            for legacy in root.glob("models--*"):
                shutil.rmtree(legacy, ignore_errors=True)
    return freed


def _is_apple_silicon() -> bool:
    from .plataforma import is_apple_silicon

    return is_apple_silicon(sys.platform, platform.machine())


def _mlx_available() -> bool:
    """Evita importar MLX na abertura; o pacote só existe na build macOS."""
    try:
        return importlib.util.find_spec("mlx_whisper") is not None
    except (ImportError, AttributeError, ValueError):
        return False
