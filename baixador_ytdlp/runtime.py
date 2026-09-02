"""Atualização do runtime de transcrição antes de liberar a interface.

O executável contém uma cópia funcional do motor de transcrição para primeiro
uso/offline. Antes de cada abertura, os pacotes são conferidos e atualizados em
um diretório isolado do usuário. Nada de Whisper/PyTorch é importado antes do
processo terminar, evitando DLLs presas durante a troca.
"""
from __future__ import annotations

import ctypes
import importlib
import importlib.metadata
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import IS_WINDOWS, RUNTIME_DIR, ensure_dirs

ProgressCB = Callable[[str, int], None]
CUDA_INDEX = "https://download.pytorch.org/whl/cu126"
CPU_INDEX = "https://download.pytorch.org/whl/cpu"
PYPI_INDEX = "https://pypi.org/simple"
PACKAGES = ("torch", "faster-whisper", "ctranslate2")


@dataclass(frozen=True)
class RuntimeInfo:
    versions: dict[str, str]
    cuda_package: bool
    updated: bool = False

    @property
    def summary(self) -> str:
        torch = self.versions.get("torch", "—")
        whisper = self.versions.get("faster-whisper", "—")
        ct2 = self.versions.get("ctranslate2", "—")
        kind = "CUDA" if self.cuda_package else "CPU"
        return f"Whisper {whisper} · CTranslate2 {ct2} · PyTorch {torch} ({kind})"


def activate_runtime(runtime_dir: Path = RUNTIME_DIR) -> None:
    """Prioriza os pacotes atualizados, sem remover o fallback empacotado."""
    path = str(runtime_dir)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
    importlib.invalidate_caches()


def _has_nvidia_driver() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        ctypes.WinDLL("nvcuda.dll")
        return True
    except OSError:
        return False


def _versions(path: Path | None = None) -> dict[str, str]:
    result: dict[str, str] = {}
    paths = [str(path)] if path and path.exists() else None
    for dist in importlib.metadata.distributions(path=paths):
        name = (dist.metadata.get("Name") or "").lower().replace("_", "-")
        if name in PACKAGES:
            result[name] = dist.version
    return result


class RuntimeManager:
    """Instala/atualiza o conjunto Python de forma bloqueante e antes da UI."""

    def __init__(self, runtime_dir: Path = RUNTIME_DIR):
        self.runtime_dir = runtime_dir
        self.info = RuntimeInfo({}, False)

    def _pip(self, args: list[str]) -> int:
        """Pip é empacotado no executável; em desenvolvimento usa o pip do venv."""
        try:
            from pip._internal.cli.main import main as pip_main
        except Exception as exc:  # pragma: no cover - falha de empacotamento
            raise RuntimeError("O atualizador interno do Python não está disponível.") from exc
        return int(pip_main(args) or 0)

    def _fallback_available(self) -> bool:
        try:
            return all(importlib.util.find_spec(item.replace("-", "_")) is not None
                       for item in ("torch", "faster_whisper", "ctranslate2"))
        except (ImportError, AttributeError):
            return False

    def ensure(self, progress: ProgressCB, force: bool = False) -> RuntimeInfo:
        ensure_dirs()
        activate_runtime(self.runtime_dir)
        use_cuda = _has_nvidia_driver()
        before = _versions(self.runtime_dir)
        missing = [name for name in PACKAGES if name not in before]
        mode = "CUDA" if use_cuda else "CPU"
        progress(f"Verificando runtime do legendador ({mode})…", -1)

        # --upgrade consulta o índice sempre; com o runtime já ativo, pip só baixa
        # wheels quando encontra uma versão mais nova ou algum pacote estiver ausente.
        args = [
            "install", "--upgrade", "--upgrade-strategy", "only-if-needed", "--no-input",
            "--disable-pip-version-check", "--only-binary", ":all:", "--target", str(self.runtime_dir),
            "--index-url", CUDA_INDEX if use_cuda else CPU_INDEX,
            "--extra-index-url", PYPI_INDEX,
            *PACKAGES,
        ]
        try:
            progress("Checando atualizações de PyTorch e do motor Whisper…", -1)
            code = self._pip(args)
            if code:
                raise RuntimeError(f"pip terminou com código {code}")
        except Exception as exc:
            # O pacote embutido mantém o programa utilizável offline. Se não há uma
            # cópia nem atualizada nem embutida, a tela de inicialização bloqueia o app.
            if before or self._fallback_available():
                progress(f"Não foi possível atualizar o legendador ({exc}). Usando a versão disponível.", 100)
                self.info = RuntimeInfo(before or _versions(), use_cuda, False)
                return self.info
            raise RuntimeError(f"Não foi possível preparar PyTorch/faster-whisper: {exc}") from exc

        activate_runtime(self.runtime_dir)
        after = _versions(self.runtime_dir)
        missing_after = [name for name in PACKAGES if name not in after]
        if missing_after:
            raise RuntimeError("A instalação do legendador ficou incompleta: " + ", ".join(missing_after))
        updated = force or before != after or bool(missing)
        self.info = RuntimeInfo(after, use_cuda, updated)
        progress("Runtime de transcrição atualizado e pronto", 100)
        return self.info
