"""Ciclo de vida seguro dos subprocessos e de todos os seus descendentes."""
from __future__ import annotations

import os
import signal
import subprocess

from .config import IS_WINDOWS


CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0
CREATE_NEW_PROCESS_GROUP = (
    getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if IS_WINDOWS else 0
)


def isolated_process_kwargs() -> dict[str, object]:
    """Opções de ``Popen`` que colocam cada tarefa em seu próprio grupo.

    O yt-dlp cria FFmpeg e runtimes JavaScript. Sem um grupo separado, encerrar
    apenas o processo pai deixa esses filhos usando CPU e mantendo pipes abertas.
    """
    if IS_WINDOWS:
        return {"creationflags": CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_tree(process: subprocess.Popen, *, force: bool = True) -> None:
    """Encerra o processo e seus filhos sem bloquear a thread chamadora."""
    already_exited = process.poll() is not None
    try:
        if IS_WINDOWS:
            if already_exited:
                return
            # taskkill retorna imediatamente em outro processo; esperar aqui
            # congelaria a interface exatamente quando a pessoa clica em cancelar.
            subprocess.Popen(
                ["taskkill", "/T", "/F", "/PID", str(process.pid)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW,
            )
        else:
            # O líder pode já ter saído enquanto um FFmpeg descendente ainda
            # mantém o grupo vivo; o PGID continua sendo o PID original.
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    except (OSError, subprocess.SubprocessError, ValueError):
        try:
            process.kill() if force else process.terminate()
        except OSError:
            pass
