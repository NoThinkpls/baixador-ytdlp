"""Ciclo de vida seguro dos subprocessos e de todos os seus descendentes.

No Windows cada subprocesso entra num *Job Object* com
``JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE``. Cancelar vira ``TerminateJobObject``,
que encerra a árvore inteira de uma vez — inclusive o processo filho do
``yt-dlp.exe`` (PyInstaller *onefile*), o FFmpeg e o Deno. Se o aplicativo
cair, o Windows fecha o handle do job e mata tudo sozinho.

``CTRL_BREAK_EVENT`` não é usado: ele exige que quem envia compartilhe o
console com o alvo, o que nunca acontece num app gráfico sem console. A falha
levava ao ``terminate()`` só do pai e deixava a árvore órfã.
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
import weakref

from .config import IS_WINDOWS


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
CREATE_NEW_PROCESS_GROUP = (
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if IS_WINDOWS else 0
)
POSIX_GRACE_SECONDS = 2.0

# Popen -> handle do Job Object. WeakKeyDictionary: o job é fechado quando o
# Popen deixa de existir (ver _close_job), e o dicionário não segura objetos.
_JOBS: "weakref.WeakKeyDictionary[subprocess.Popen, int]" = weakref.WeakKeyDictionary()
_JOBS_LOCK = threading.Lock()


def isolated_process_kwargs() -> dict[str, object]:
    """Opções de ``Popen`` que colocam cada tarefa em seu próprio grupo."""
    if IS_WINDOWS:
        return {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


# ----------------------------------------------------------------- Windows
def _kernel32():  # pragma: no cover - somente Windows
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = (
        wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
    kernel32.SetInformationJobObject.restype = wintypes.BOOL
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
    kernel32.TerminateJobObject.argtypes = (wintypes.HANDLE, wintypes.UINT)
    kernel32.TerminateJobObject.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _create_kill_on_close_job() -> int:  # pragma: no cover - somente Windows
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [(name, ctypes.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class BASIC_LIMIT(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_longlong),
            ("PerJobUserTimeLimit", ctypes.c_longlong),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class EXTENDED_LIMIT(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", BASIC_LIMIT),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = _kernel32()
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        raise OSError(ctypes.get_last_error(), "CreateJobObjectW falhou")
    info = EXTENDED_LIMIT()
    info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
        kernel32.CloseHandle(job)
        raise OSError(ctypes.get_last_error(), "SetInformationJobObject falhou")
    return int(job)


def _close_job(job: int) -> None:  # pragma: no cover - somente Windows
    try:
        _kernel32().CloseHandle(job)
    except OSError:
        pass


def attach_kill_job(process: subprocess.Popen) -> bool:
    """Associa o processo a um job que encerra a árvore toda. Sem efeito fora do Windows."""
    if not IS_WINDOWS:
        return False
    try:  # pragma: no cover - somente Windows
        job = _create_kill_on_close_job()
        handle = int(getattr(process, "_handle"))
        if not _kernel32().AssignProcessToJobObject(job, handle):
            _close_job(job)
            return False
        with _JOBS_LOCK:
            _JOBS[process] = job
        weakref.finalize(process, _close_job, job)
        return True
    except Exception:  # noqa: BLE001 - sem job, o taskkill continua como rede de segurança
        return False


def attach_pid_to_kill_job(pid: int) -> int:
    """Prende um processo já criado (ex.: ``multiprocessing``) a um job próprio.

    Devolve o handle do job, que precisa ficar vivo enquanto o processo existir;
    fechá-lo encerra a árvore. ``0`` fora do Windows ou em caso de falha.
    """
    if not IS_WINDOWS or not pid:
        return 0
    try:  # pragma: no cover - somente Windows
        from ctypes import wintypes

        kernel32 = _kernel32()
        kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel32.OpenProcess.restype = wintypes.HANDLE
        handle = kernel32.OpenProcess(0x0100 | 0x0001, False, int(pid))  # SET_QUOTA | TERMINATE
        if not handle:
            return 0
        try:
            job = _create_kill_on_close_job()
            if kernel32.AssignProcessToJobObject(job, handle):
                return job
            _close_job(job)
            return 0
        finally:
            kernel32.CloseHandle(handle)
    except Exception:  # noqa: BLE001
        return 0


def release_job(job: int) -> None:
    """Fecha um job criado por :func:`attach_pid_to_kill_job`."""
    if job and IS_WINDOWS:
        _close_job(job)


def popen_isolated(args, **kwargs) -> subprocess.Popen:
    """``Popen`` em grupo próprio e, no Windows, preso a um Job Object."""
    options = dict(isolated_process_kwargs())
    extra_flags = int(kwargs.pop("creationflags", 0) or 0)
    if IS_WINDOWS:
        options["creationflags"] = int(options["creationflags"]) | extra_flags
    options.update(kwargs)
    process = subprocess.Popen(args, **options)
    attach_kill_job(process)
    return process


def _taskkill(pid: int) -> None:  # pragma: no cover - somente Windows
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    subprocess.Popen(
        [os.path.join(system_root, "System32", "taskkill.exe"), "/T", "/F", "/PID", str(pid)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=CREATE_NO_WINDOW,
    )


def terminate_process_tree(process: subprocess.Popen, *, force: bool = True) -> None:
    """Encerra o processo e seus filhos sem bloquear a thread chamadora."""
    try:
        if IS_WINDOWS:
            with _JOBS_LOCK:
                job = _JOBS.get(process)
            if job:
                _kernel32().TerminateJobObject(job, 1)
                return
            if process.poll() is not None:
                return
            # Sem job (criação falhou): taskkill ANTES de qualquer terminate().
            # Com o pai vivo, /T ainda enxerga a árvore inteira.
            _taskkill(process.pid)
            return

        os.killpg(process.pid, signal.SIGTERM)
        if force:
            def force_group_later() -> None:
                time.sleep(POSIX_GRACE_SECONDS)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except OSError:
                    pass  # grupo já terminou

            threading.Thread(
                target=force_group_later, name="process-group-stop", daemon=True
            ).start()
    except (OSError, subprocess.SubprocessError, ValueError):
        try:
            process.kill() if force else process.terminate()
        except OSError:
            pass
