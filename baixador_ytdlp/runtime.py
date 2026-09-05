"""Bootstrap do runtime de transcrição incluído no instalador.

O Whisper, CTranslate2 e as DLLs CUDA necessárias são empacotados juntos.
Não há download de dependência de IA na máquina do usuário; o runtime externo
legado só é usado como último recurso durante desenvolvimento.
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

# O faster-whisper roda sobre CTranslate2, sem PyTorch.
#
# As versões abaixo são as que funcionam na build atual e NÃO devem ser trocadas
# sem recompilar o executável: as DLLs de CUDA são embarcadas pelo PyInstaller a
# partir do que estiver instalado na máquina de build. Fixar aqui uma versão de
# cuDNN diferente da que foi embutida faz o carregador procurar nomes que não
# existem no pacote e cair para CPU em silêncio.
PACKAGES = ("faster-whisper", "ctranslate2")
CUDA_PACKAGES = (
    "nvidia-cuda-runtime-cu12==12.4.127",
    "nvidia-cublas-cu12==12.4.5.8",
    "nvidia-cudnn-cu12==8.9.7.29",
)


def _requirement_name(requirement: str) -> str:
    """Nome puro do pacote, sem o especificador de versão."""
    for separator in (">=", "<=", "==", "~=", ">", "<", "!="):
        requirement = requirement.split(separator, 1)[0]
    return requirement.strip()


PACKAGE_NAMES = tuple(_requirement_name(item) for item in PACKAGES)
CUDA_PACKAGE_NAMES = tuple(_requirement_name(item) for item in CUDA_PACKAGES)
_DLL_DIRECTORY_HANDLES: list[object] = []  # os.add_dll_directory precisa permanecer vivo
_DLL_DIRECTORY_PATHS: set[str] = set()
_CUDA_DLL_HANDLES: list[object] = []
_CUDA_DLL_PATHS: set[str] = set()
# A ordem importa: cada DLL precisa das anteriores já carregadas no processo.
_CUDA_CORE_DLLS = ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll")

# O nome das bibliotecas do cuDNN muda entre as versões maiores, e o que vale é o
# que foi de fato embutido no executável — não uma versão escolhida aqui. Cada
# variante lista as auxiliares primeiro e a principal por último; a detecção usa
# a principal para decidir qual conjunto existe.
_CUDNN_VARIANTS = (
    ("cudnn_graph64_9.dll", "cudnn_engines_precompiled64_9.dll",
     "cudnn_engines_runtime_compiled64_9.dll", "cudnn_heuristic64_9.dll",
     "cudnn_ops64_9.dll", "cudnn64_9.dll"),
    ("cudnn_ops_infer64_8.dll", "cudnn_cnn_infer64_8.dll",
     "cudnn_adv_infer64_8.dll", "cudnn64_8.dll"),
)


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


def _cuda_dll_dirs(root: Path) -> tuple[Path, ...]:
    """Pastas de DLL que o CTranslate2 procura ao abrir o backend CUDA."""
    nvidia = root / "nvidia"
    return (
        root / "torch" / "lib",                  # instalação antiga ainda funciona
        nvidia / "cuda_runtime" / "bin",
        nvidia / "cublas" / "bin",
        nvidia / "cudnn" / "bin",
    )


def _add_dll_dirs(folders: tuple[Path, ...] | list[Path]) -> None:
    if not IS_WINDOWS or not hasattr(os, "add_dll_directory"):
        return
    for folder in folders:
        key = str(folder.resolve())
        if not folder.is_dir() or key in _DLL_DIRECTORY_PATHS:
            continue
        try:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(folder)))
            _DLL_DIRECTORY_PATHS.add(key)
        except OSError:
            pass


def activate_embedded_cuda() -> None:
    """Mantém acessíveis as DLLs CUDA empacotadas ou presentes no venv atual."""
    roots: list[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(Path(frozen_root))
    else:
        roots.extend(Path(item) for item in sys.path if item)
    folders: list[Path] = []
    for root in roots:
        folders.extend(_cuda_dll_dirs(root))
    _add_dll_dirs(folders)


def embedded_cuda_available() -> bool:
    """Confere o conjunto CUDA sem carregar DLLs no processo da interface.

    A abertura só precisa saber se a distribuição inclui os arquivos. O
    carregamento propriamente dito fica no processo isolado de transcrição,
    imediatamente antes de criar o CTranslate2; assim as DLLs grandes não
    elevam a memória do aplicativo enquanto ele só baixa vídeos.
    """
    if not IS_WINDOWS:
        return False
    roots = ([Path(getattr(sys, "_MEIPASS"))]
             if getattr(sys, "_MEIPASS", None) else [Path(item) for item in sys.path if item])
    folders = [folder for root in roots for folder in _cuda_dll_dirs(root) if folder.is_dir()]
    if not folders:
        return False

    def exists(name: str) -> bool:
        return any((folder / name).is_file() for folder in folders)

    return all(exists(name) for name in _CUDA_CORE_DLLS) and any(
        exists(variant[-1]) for variant in _CUDNN_VARIANTS
    )


def prepare_embedded_cuda() -> str | None:
    """Pré-carrega DLLs CUDA pelo caminho absoluto antes do CTranslate2."""
    activate_embedded_cuda()
    if not IS_WINDOWS:
        return None
    roots = [Path(getattr(sys, "_MEIPASS"))] if getattr(sys, "_MEIPASS", None) else [Path(p) for p in sys.path if p]
    folders = [folder for root in roots for folder in _cuda_dll_dirs(root) if folder.is_dir()]
    if folders:
        os.environ["PATH"] = os.pathsep.join([*(str(p) for p in folders), os.environ.get("PATH", "")])
    def locate(name: str) -> Path | None:
        return next((p / name for p in folders if (p / name).is_file()), None)

    def load(path: Path, name: str) -> str | None:
        key = str(path.resolve())
        if key in _CUDA_DLL_PATHS:
            return None
        try:
            _CUDA_DLL_HANDLES.append(ctypes.WinDLL(str(path)))
            _CUDA_DLL_PATHS.add(key)
        except OSError as exc:
            return f"não foi possível carregar {name} incluída no aplicativo: {exc}"
        return None

    missing = [name for name in _CUDA_CORE_DLLS if locate(name) is None]
    if missing:
        return "DLL(s) CUDA ausente(s) no executável: " + ", ".join(missing)
    for name in _CUDA_CORE_DLLS:
        if error := load(locate(name), name):
            return error

    # Usa a variante de cuDNN que existe no pacote, seja qual for a versão maior.
    for variant in _CUDNN_VARIANTS:
        principal = variant[-1]
        if locate(principal) is None:
            continue
        for name in variant:                 # auxiliares ausentes são normais
            path = locate(name)
            if path is not None and (error := load(path, name)):
                return error
        return None

    esperadas = " ou ".join(v[-1] for v in _CUDNN_VARIANTS)
    return f"cuDNN ausente no executável (procurei {esperadas})"


def activate_runtime(runtime_dir: Path = RUNTIME_DIR) -> None:
    """Prioriza o runtime externo somente depois de ele estar validado."""
    path = str(runtime_dir)
    if path in sys.path:
        sys.path.remove(path)
    sys.path.insert(0, path)
    _add_dll_dirs(_cuda_dll_dirs(runtime_dir))
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
        tracked = set(PACKAGE_NAMES) | set(CUDA_PACKAGE_NAMES)
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
    """Usa primeiro o motor incluído e só recorre ao runtime legado se necessário."""

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
        wanted = PACKAGE_NAMES + (CUDA_PACKAGE_NAMES if use_cuda else ())
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

    def ensure(self, progress: ProgressCB, check_now: bool = False) -> RuntimeInfo:
        ensure_dirs()
        use_cuda = _has_nvidia_driver()
        # O instalador contém o motor e as DLLs CUDA; priorizá-lo impede que
        # uma cópia antiga/parcial em %LOCALAPPDATA% substitua o pacote validado.
        deactivate_runtime(self.runtime_dir)
        if self._available_packages():
            # Não carrega cudnn/cublas aqui: a transcrição roda em processo
            # separado e faz o carregamento completo só quando o usuário a usa.
            # Isso reduz memória e I/O logo na abertura sem mudar o backend que
            # será empregado no processamento real.
            use_cuda = use_cuda and embedded_cuda_available()
            embedded = _versions()
            self.info = RuntimeInfo(embedded, use_cuda, False, "runtime incluído no aplicativo")
            progress("Motor de transcrição incluído e pronto", 100)
            return self.info

        # Caminho de desenvolvimento/recuperação para instalações sem o pacote.
        # Uma build oficial nunca deve chegar aqui.
        before = _versions(self.runtime_dir)
        mode = "CUDA" if use_cuda else "CPU"
        progress(f"Verificando runtime do legendador ({mode})…", -1)

        # Não importa torch/faster-whisper antes daqui. Assim uma atualização nunca
        # tenta substituir DLL que está carregada pelo próprio processo.
        needs_update = self._needs_update(before, use_cuda)

        if not needs_update and not check_now and self._fresh_enough(before, use_cuda):
            # Tudo na versão certa e verificado há pouco: ativa o runtime já
            # instalado e devolve o controle à interface sem tocar na rede.
            activate_runtime(self.runtime_dir)
            self.info = RuntimeInfo(before, use_cuda, False, "runtime verificado recentemente")
            progress("Runtime do legendador já verificado — pulando a checagem", 100)
            return self.info

        pip_output = ""
        try:
            progress("Recuperando o motor de transcrição…" if needs_update
                     else "Checando o motor de transcrição…", -1)
            code, pip_output = self._pip(self._install_args(use_cuda))
            if code:
                raise RuntimeError(f"pip terminou com código {code}")

            after = _versions(self.runtime_dir)
            missing = [name for name in PACKAGE_NAMES if name not in after]
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
