"""Processos de transcrição: o servidor persistente e o processo de uma execução só.

Ficam fora do ``transcription.py`` para separar o motor (``Transcriber``) da orquestração por filas
e eventos que roda num processo ``spawn`` próprio.
"""
from __future__ import annotations

import queue
import threading
import traceback

from .diagnostics import install_diagnostics, log_event, report_exception
from .tools import Toolchain
from .transcription import (
    Transcriber, TranscriptionCancelled, TranscriptionOptions, friendly_transcription_error,
)

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
        send("error", {"message": friendly_transcription_error(exc),
                        "traceback": traceback.format_exc()})
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
    # Protege a troca de item ativo: sem ela, um cancelamento que chegasse entre
    # "active_job = X" e "cancel_event.clear()" era apagado e o item seguia.
    state_lock = threading.Lock()

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
                with state_lock:
                    if target == active_job[0]:
                        cancel_event.set()
                    elif isinstance(target, int):
                        pending_cancellations.add(target)
            elif kind == "pause":
                paused = bool(command[2])
                with state_lock:
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
            with state_lock:
                cancel_event.clear()
                pause_event.clear()
                active_job[0] = int(job_id)
                if int(job_id) in pending_cancellations:
                    pending_cancellations.discard(int(job_id))
                    cancel_event.set()
                if pending_pauses.pop(int(job_id), False):
                    pause_event.set()
            current_job = int(job_id)
            try:
                if transcriber is None:
                    transcriber = Transcriber(
                        toolchain,
                        lambda message, jid=current_job: send(jid, "status", message),
                        lambda percent, jid=current_job: send(jid, "progress", percent),
                        opts.aggressive_filter,
                        cancel_event=cancel_event,
                        pause_event=pause_event,
                        force_cpu=bool(cuda_problem),
                    )
                    if cuda_problem:
                        send(current_job, "status",
                             f"CUDA interno indisponível ({cuda_problem}). Usando CPU int8…")
                else:
                    # Os filtros são escolhas de cada item, não uma propriedade
                    # permanente do modelo em memória.
                    transcriber.aggressive_filter = opts.aggressive_filter
                    transcriber.status = lambda message, jid=current_job: send(jid, "status", message)
                    transcriber.progress = lambda percent, jid=current_job: send(jid, "progress", percent)

                log_event("Transcrição persistente iniciada: entrada=%s saída=%s modelo=%s",
                          opts.media_path, opts.output_path, opts.model_size)
                transcriber.run(opts)
            except TranscriptionCancelled:
                log_event("Transcrição persistente cancelada pelo usuário")
                send(int(job_id), "cancelled")
            except Exception as exc:  # noqa: BLE001 - precisa voltar à interface
                report_exception("transcrição persistente", exc)
                send(int(job_id), "error", {
                    "message": friendly_transcription_error(exc), "traceback": traceback.format_exc(),
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
