"""Bootstrap seguro do runtime de transcrição.

O aplicativo só libera a interface depois de verificar PyTorch,
faster-whisper e CTranslate2. A cópia empacotada continua sendo o fallback
offline: uma atualização falha nunca impede downloads nem deixa o aplicativo
apontar para um runtime incompleto.
"""
from __future__ import annotations

import contextlib
import ctypes
import importlib
import importlib.metadata
import importlib.util
import io
import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config import IS_WINDOWS, RUNTIME_DIR, ensure_dirs

ProgressCB = Callable[[str, int], None]
PYPI_INDEX = "https://pypi.org/simple"

# O faster-whisper roda sobre CTranslate2, não sobre PyTorch. O torch só estava
# aqui por dois motivos: detectar CUDA e carregar cuBLAS/cuDNN. A detecção agora
# sai do driver e do próprio CTranslate2; as bibliotecas CUDA vêm dos pacotes
# oficiais da NVIDIA, que somam algumas centenas de MB no lugar dos ~2,5 GB do
# torch. Para voltar ao comportamento antigo, basta acrescentar "torch" abaixo.
PACKAGES = ("faster-whisper", "ctranslate2")
CUDA_PACKAGES = ("nvidia-cublas-cu12", "nvidia-cudnn-cu12")
_DLL_DIRECTORY_HANDLES: list[object] = []  # os.add_dll_directory precisa permanecer vivo


@dataclass(frozen=True)
class RuntimeInfo:
    versions: dict[str, str]
    cuda_package: bool
    updated: bool = False
    source: str = "runtime atualizado"

    @property
    def summary(self) -> str:
        whisper = self.versions.get("faster-whisper", "—")
        ct2 = self.versions.get("ctranslate2", "—")
        kind = "CUDA" if self.cuda_package else "CPU"
        return f"Whisper {whisper} · CTranslate2 {ct2} ({kind})"


def _runtime_dll_dirs(runtime_dir: Path) -> tuple[Path, ...]:
    """Pastas de DLL que o CTranslate2 procura na hora de abrir o backend CUDA."""
    nvidia = runtime_dir / "nvidia"
    return (
        runtime_dir / "torch" / "lib",          # mantido: instalação antiga ainda funciona
        nvidia / "cublas" / "bin",
        nvidia / "cudnn" / "bin",
        nvidia / "cuda_runtime" / "bin",
    )


def activate_runtime(runtime_dir: Path = RUNTIME_DIR) -> None:
    """Prioriza o runtime externo somente depois de ele estar validado."""
    path = str(runtime_dir)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
    if IS_WINDOWS and hasattr(os, "add_dll_directory"):
        for folder in _runtime_dll_dirs(runtime_dir):
            if folder.is_dir():
                try:
                    _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(folder)))
                except OSError:
                    pass
    importlib.invalidate_caches()


def deactivate_runtime(runtime_dir: Path = RUNTIME_DIR) -> None:
    """Volta ao runtime empacotado após uma instalação externa mal sucedida."""
    path = str(runtime_dir)
    while path in sys.path:
        sys.path.remove(path)
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
    """Lê versões sem supor que há um diretório externo instalado.

    ``importlib.metadata.distributions(path=None)`` não é válido em algumas
    versões do Python; a chamada sem argumento é obrigatória para o ambiente
    embutido. Essa era a origem do erro ``'NoneType' object is not iterable``.
    """
    result: dict[str, str] = {}
    try:
        distributions = (importlib.metadata.distributions()
                         if path is None else importlib.metadata.distributions(path=[str(path)]))
        tracked = set(PACKAGES) | set(CUDA_PACKAGES)
        for dist in distributions:
            name = (dist.metadata.get("Name") or "").lower().replace("_", "-")
            if name in tracked:
                result[name] = dist.version
    except Exception:
        # Metadados ausentes não são uma falha do aplicativo; a disponibilidade
        # real do pacote é confirmada abaixo por find_spec/import.
        return {}
    return result


class RuntimeManager:
    """Verifica e atualiza, de forma bloqueante, o motor local do legendador."""

    def __init__(self, runtime_dir: Path = RUNTIME_DIR, check_hours: int = 24):
        self.runtime_dir = runtime_dir
        self.check_hours = max(0, int(check_hours))
        self.log_path = runtime_dir.parent / "logs" / "runtime-update.log"
        self.stamp_path = runtime_dir.parent / "runtime_state.json"
        self.info = RuntimeInfo({}, False, source="ainda não verificado")

    # ------------------------------------------------------------- cache
    def _stamp(self) -> dict:
        try:
            return json.loads(self.stamp_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _write_stamp(self, versions: dict[str, str], use_cuda: bool) -> None:
        try:
            self.stamp_path.parent.mkdir(parents=True, exist_ok=True)
            self.stamp_path.write_text(json.dumps({
                "checked_at": time.time(), "cuda": use_cuda, "versions": versions,
            }), encoding="utf-8")
        except OSError:
            pass

    def _fresh_enough(self, current: dict[str, str], use_cuda: bool) -> bool:
        """Pula a consulta ao pip quando nada mudou desde a última checagem.

        A consulta de rede do pip é o passo mais lento da abertura do aplicativo.
        Ela só é dispensada quando as três condições valem ao mesmo tempo: os
        pacotes estão instalados, a variante (CPU/CUDA) bate com a máquina de
        agora, e a última checagem bem-sucedida foi dentro do prazo escolhido.
        """
        if not self.check_hours:
            return False
        stamp = self._stamp()
        if not stamp or bool(stamp.get("cuda")) != use_cuda:
            return False
        if stamp.get("versions") != current:
            return False
        age = time.time() - float(stamp.get("checked_at") or 0)
        return 0 <= age < self.check_hours * 3600

    def _write_log(self, text: str) -> None:
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            self.log_path.write_text(text[-12_000:], encoding="utf-8")
        except OSError:
            pass

    def _pip(self, args: list[str]) -> tuple[int, str]:
        """Executa o pip embutido e captura o detalhe para o log de diagnóstico."""
        try:
            from pip._internal.cli.main import main as pip_main
        except Exception as exc:  # pragma: no cover - depende do pacote PyInstaller
            raise RuntimeError("O atualizador interno (pip) não foi empacotado.") from exc

        output = io.StringIO()
        try:
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = pip_main(args)
        except SystemExit as exc:
            result = exc.code
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"pip não conseguiu iniciar: {exc}") from exc
        code = 0 if result is None else int(result)
        return code, output.getvalue()

    @staticmethod
    def _available_packages() -> bool:
        module_names = ("faster_whisper", "ctranslate2")
        try:
            return all(importlib.util.find_spec(name) is not None for name in module_names)
        except (ImportError, AttributeError, ValueError):
            return False

    def _needs_update(self, current: dict[str, str], use_cuda: bool) -> bool:
        wanted = PACKAGES + (CUDA_PACKAGES if use_cuda else ())
        # Quando a máquina ganha ou perde GPU, as bibliotecas CUDA entram ou saem
        # na próxima abertura.
        return any(name not in current for name in wanted)

    def _install_args(self, use_cuda: bool) -> list[str]:
        return [
            "install", "--upgrade", "--upgrade-strategy", "only-if-needed", "--no-input",
            "--disable-pip-version-check", "--only-binary", ":all:",
            "--target", str(self.runtime_dir),
            "--index-url", PYPI_INDEX,
            *PACKAGES, *(CUDA_PACKAGES if use_cuda else ()),
        ]

    def ensure(self, progress: ProgressCB, force: bool = False) -> RuntimeInfo:
        ensure_dirs()
        use_cuda = _has_nvidia_driver()
        before = _versions(self.runtime_dir)
        mode = "CUDA" if use_cuda else "CPU"
        progress(f"Verificando runtime do legendador ({mode})…", -1)

        # Não importa torch/faster-whisper antes daqui. Assim uma atualização nunca
        # tenta substituir DLL que está carregada pelo próprio processo.
        needs_update = force or self._needs_update(before, use_cuda)

        if not needs_update and self._fresh_enough(before, use_cuda):
            # Tudo na versão certa e verificado há pouco: ativa o runtime já
            # instalado e devolve o controle à interface sem tocar na rede.
            activate_runtime(self.runtime_dir)
            self.info = RuntimeInfo(before, use_cuda, False, "runtime verificado recentemente")
            progress("Runtime do legendador já verificado — pulando a checagem", 100)
            return self.info

        pip_output = ""
        try:
            progress("Instalando ou atualizando PyTorch e o motor Whisper…" if needs_update
                     else "Checando atualizações de PyTorch e do motor Whisper…", -1)
            code, pip_output = self._pip(self._install_args(use_cuda))
            if code:
                raise RuntimeError(f"pip terminou com código {code}")

            after = _versions(self.runtime_dir)
            missing = [name for name in PACKAGES if name not in after]
            if missing:
                raise RuntimeError("instalação incompleta: " + ", ".join(missing))

            activate_runtime(self.runtime_dir)
            self._write_stamp(after, use_cuda)
            self.info = RuntimeInfo(after, use_cuda, updated=(before != after), source="runtime atualizado")
            self._write_log(pip_output or "Atualização concluída sem saída adicional.")
            progress("Runtime de transcrição atualizado e pronto", 100)
            return self.info
        except Exception as exc:  # noqa: BLE001
            self._write_log((pip_output + "\n\nERRO: " + repr(exc)).strip())
            deactivate_runtime(self.runtime_dir)
            embedded = _versions()
            if self._available_packages():
                self.info = RuntimeInfo(embedded, use_cuda, False, "runtime embutido (atualização indisponível)")
                progress("Atualização indisponível; usando o runtime embutido com segurança", 100)
                return self.info
            raise RuntimeError(
                "Não foi possível preparar o runtime de transcrição. "
                f"Detalhe registrado em {self.log_path}: {exc}") from exc
