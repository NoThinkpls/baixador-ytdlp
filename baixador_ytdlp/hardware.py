"""Dimensionamento automático conforme a máquina.

Um valor fixo bom num desktop de 16 núcleos é ruim num notebook de 4: o mesmo
`--concurrent-fragments 8` que satura a banda numa máquina rápida enfileira
processos numa lenta. Aqui as escolhas saem do hardware real, uma vez por
execução — todas as funções são cacheadas.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from functools import lru_cache


@lru_cache(maxsize=1)
def logical_cores() -> int:
    return os.cpu_count() or 2


@lru_cache(maxsize=1)
def usable_cores() -> int:
    """Núcleos que o processo pode realmente usar (respeita afinidade da CPU)."""
    try:
        return max(1, len(os.sched_getaffinity(0)))  # type: ignore[attr-defined]
    except AttributeError:      # Windows não expõe sched_getaffinity
        return logical_cores()


@lru_cache(maxsize=1)
def total_ram_gb() -> float:
    """RAM total em GB. Zero quando não dá para descobrir sem dependência extra."""
    try:  # POSIX
        pages = os.sysconf("SC_PHYS_PAGES")              # type: ignore[attr-defined]
        size = os.sysconf("SC_PAGE_SIZE")                # type: ignore[attr-defined]
        if pages > 0 and size > 0:
            return pages * size / 1024 ** 3
    except (AttributeError, ValueError, OSError):
        pass
    try:  # Windows
        import ctypes

        class _Status(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong),
                        ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong),
                        ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong),
                        ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        status = _Status()
        status.dwLength = ctypes.sizeof(_Status)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return status.ullTotalPhys / 1024 ** 3
    except Exception:
        return 0.0


@lru_cache(maxsize=1)
def default_fragments() -> int:
    """Fragmentos simultâneos por vídeo.

    Cada fragmento é uma conexão HTTP mais uma escrita em disco; passar de ~4 por
    núcleo só troca vazão por disputa de CPU e de I/O.
    """
    return max(2, min(16, usable_cores() * 2))


@lru_cache(maxsize=1)
def default_parallel_downloads() -> int:
    """Itens da fila em paralelo. Conservador de propósito: a banda é compartilhada."""
    return 1 if usable_cores() <= 2 else (2 if usable_cores() <= 8 else 3)


@lru_cache(maxsize=1)
def apple_performance_cores() -> int:
    """Núcleos de desempenho do Apple Silicon, quando o macOS os informa.

    Misturar todos os núcleos de eficiência numa tarefa pesada de CPU pode
    aumentar consumo e latência sem ajudar tanto a transcrição. O MLX usa a GPU
    unificada normalmente; este número é para o fallback CTranslate2/NEON.
    """
    if sys.platform != "darwin" or platform.machine().lower() not in {"arm64", "aarch64"}:
        return 0
    for key in ("hw.perflevel0.physicalcpu", "hw.physicalcpu"):
        try:
            value = subprocess.run(
                ["sysctl", "-n", key], capture_output=True, text=True, timeout=1,
            ).stdout.strip()
            count = int(value)
            if count > 0:
                return count
        except (OSError, ValueError, subprocess.SubprocessError):
            continue
    return 0


@lru_cache(maxsize=1)
def whisper_threads() -> int:
    """Threads do CTranslate2 na CPU.

    Deixa pelo menos um núcleo livre para a interface não travar durante a
    transcrição, e não passa de 8 — acima disso o ganho some e a memória sobe.
    """
    apple_cores = apple_performance_cores()
    if apple_cores:
        return max(2, min(8, apple_cores))
    return max(1, min(8, usable_cores() - 1)) if usable_cores() > 2 else 1


def whisper_model_fits(model_size: str) -> bool:
    """Se o modelo escolhido cabe com folga na RAM da máquina (execução em CPU)."""
    needed = {"tiny": 1.0, "base": 1.5, "small": 3.0, "medium": 6.0,
              "large-v3": 11.0, "large-v2": 11.0, "large": 11.0}
    ram = total_ram_gb()
    return ram <= 0 or ram >= needed.get(model_size, 6.0)
