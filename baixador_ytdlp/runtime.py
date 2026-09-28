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
from .plataforma import pasta_do_executavel

ProgressCB = Callable[[str, int], None]
PYPI_INDEX = "https://pypi.org/simple"

# O faster-whisper roda sobre CTranslate2, sem PyTorch.
#
# Estas versões espelham ``requirements.txt`` e ``requirements-windows.lock``
# (tests/test_cuda_stack.py garante isso). As DLLs CUDA são embarcadas a partir
# do que está instalado na máquina de build. Desde a 4.5 o CTranslate2 usa
# cuDNN 9: embutir cuDNN 8 com ele fazia a transcrição cair para CPU sem aviso.
# O wheel do CTranslate2 4.8.2 traz o cudnn64_9.dll 9.10.2.21; as
# sub-bibliotecas vêm do pacote NVIDIA e precisam ser da mesma versão.
PACKAGES = ("faster-whisper==1.1.1", "ctranslate2==4.8.2")
CUDA_PACKAGES = (
    "nvidia-cuda-runtime-cu12==12.8.90",
    "nvidia-cublas-cu12==12.8.4.1",
    "nvidia-cudnn-cu12==9.10.2.21",
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

# O nome das bibliotecas do cuDNN muda entre as versões maiores. Cada variante
# lista (obrigatórias, opcionais) na ordem de carregamento: a principal vem por
# último, depois das sub-bibliotecas de que ela depende. As opcionais só são
# usadas por outros tipos de modelo (RNN/atenção) ou por engines compiladas em
# tempo de execução; o Whisper não precisa delas.
_CUDNN_VARIANTS: dict[int, tuple[tuple[str, ...], tuple[str, ...]]] = {
    9: (
        ("cudnn_graph64_9.dll", "cudnn_ops64_9.dll", "cudnn_cnn64_9.dll",
         "cudnn_engines_precompiled64_9.dll", "cudnn_heuristic64_9.dll", "cudnn64_9.dll"),
        ("cudnn_engines_runtime_compiled64_9.dll", "cudnn_adv64_9.dll"),
    ),
    8: (
        ("cudnn_ops_infer64_8.dll", "cudnn_cnn_infer64_8.dll", "cudnn64_8.dll"),
        ("cudnn_adv_infer64_8.dll",),
    ),
}


def required_cudnn_major(ct2_version: str | None = None) -> int:
    """Versão maior do cuDNN que o CTranslate2 instalado exige.

    O CTranslate2 4.5 trocou o cuDNN 8 pelo 9 sem manter compatibilidade. Ler o
    metadado evita importar o pacote (e carregar DLLs) no processo da interface.
    """
    if ct2_version is None:
        try:
            ct2_version = importlib.metadata.version("ctranslate2")
        except importlib.metadata.PackageNotFoundError:
            return 9
    try:
        major, minor = (int(part) for part in ct2_version.split(".")[:2])
    except ValueError:
        return 9
    return 9 if (major, minor) >= (4, 5) else 8


def missing_cudnn_files(folders: list[Path] | tuple[Path, ...], major: int) -> list[str]:
    """DLLs obrigatórias do cuDNN ``major`` que não estão em nenhuma pasta."""
    required, _optional = _CUDNN_VARIANTS[major]
    return [name for name in required if not any((folder / name).is_file() for folder in folders)]


def cudnn_version_major(version: int) -> int:
    """Converte ``cudnnGetVersion()`` (8907 ou 91002) na versão maior."""
    return version // 10000 if version >= 90000 else version // 1000


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


def _embedded_roots() -> list[Path]:
    """Raízes possíveis da distribuição congelada ou do ambiente de desenvolvimento.

    PyInstaller fornece ``_MEIPASS``; no Nuitka as bibliotecas ficam ao lado do
    executável. Ao aceitar ambos, o carregador de CUDA continua sendo uma
    responsabilidade do aplicativo, não do empacotador.
    """
    candidates: list[Path] = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        candidates.append(Path(frozen_root))

    candidates.append(pasta_do_executavel())
    candidates.extend(Path(item) for item in sys.path if item)

    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            key = str(candidate.resolve())
        except OSError:
            key = str(candidate)
        if key not in seen:
            seen.add(key)
            roots.append(candidate)
    return roots


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
    folders: list[Path] = []
    for root in _embedded_roots():
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
    folders = [folder for root in _embedded_roots() for folder in _cuda_dll_dirs(root) if folder.is_dir()]
    if not folders:
        return False

    def exists(name: str) -> bool:
        return any((folder / name).is_file() for folder in folders)

    # Só a variante que o CTranslate2 instalado usa conta. Aceitar qualquer
    # cuDNN mostrava "CUDA" na interface enquanto a transcrição caía para CPU.
    return (all(exists(name) for name in _CUDA_CORE_DLLS)
            and not missing_cudnn_files(folders, required_cudnn_major()))


def prepare_embedded_cuda() -> str | None:
    """Pré-carrega DLLs CUDA pelo caminho absoluto antes do CTranslate2."""
    activate_embedded_cuda()
    if not IS_WINDOWS:
        return None
    folders = [folder for root in _embedded_roots() for folder in _cuda_dll_dirs(root) if folder.is_dir()]
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

    major = required_cudnn_major()
    missing_cudnn = missing_cudnn_files(folders, major)
    if missing_cudnn:
        other = 8 if major == 9 else 9
        wrong = "" if missing_cudnn_files(folders, other) else (
            f" A build embutiu cuDNN {other}, que esta versão do CTranslate2 não aceita.")
        return (f"cuDNN {major} ausente ou incompleto no executável "
                f"({', '.join(missing_cudnn)}).{wrong} Reinstale a versão mais recente.")
    required, optional = _CUDNN_VARIANTS[major]
    for name in required:
        if error := load(locate(name), name):
            return error
    for name in optional:
        path = locate(name)
        if path is not None:
            load(path, name)  # falha aqui não afeta o Whisper
    return None


def cudnn_smoke_test(create_handle: bool = False) -> tuple[int, str]:
    """Confere o cuDNN já carregado: versão e, com GPU, a criação de um handle.

    Usado pelo autoteste da build. Devolve ``(versão, erro)``; erro vazio = ok.
    """
    if not IS_WINDOWS:
        return 0, ""
    major = required_cudnn_major()
    try:
        library = ctypes.WinDLL(f"cudnn64_{major}.dll")
        library.cudnnGetVersion.restype = ctypes.c_size_t
        version = int(library.cudnnGetVersion())
    except (OSError, AttributeError) as exc:
        return 0, f"cudnn64_{major}.dll não pôde ser aberto: {exc}"
    if cudnn_version_major(version) != major:
        return version, f"cuDNN {version} carregado, mas o CTranslate2 exige a versão {major}"
    if create_handle:
        handle = ctypes.c_void_p()
        status = library.cudnnCreate(ctypes.byref(handle))
        if status != 0:
            return version, f"cudnnCreate falhou (status {status})"
        library.cudnnDestroy(handle)
    return version, ""


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
        if os.environ.get("BAIXADOR_DEV_RUNTIME") != "1":
            raise RuntimeError(
                "O runtime de transcrição não foi incluído nesta build. "
                "Reinstale uma versão oficial; downloads automáticos de pacotes estão desativados."
            )
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
