"""Threads de trabalho — nada de I/O de rede ou subprocesso na thread da interface."""
from __future__ import annotations

import multiprocessing
import queue
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .config import Settings
from .diagnostics import get_logger, log_event, report_exception
from .downloader import (DownloadOptions, DownloadRunner, Progress, Transcoder,
                         is_retryable_error)
from .gpu import GpuInfo, detect
from .media_tools import MediaToolError, MediaToolOptions, build_command, operation_duration, time_seconds
from .processes import attach_pid_to_kill_job, popen_isolated, release_job, terminate_process_tree
from .probe import playlist_entries, probe
from .security import validate_media_url
from .tools import ToolManager, Toolchain, USER_AGENT, _verified_ssl_context
from .updater import AppUpdater, ReleaseInfo
from .transcription import (TranscriptionOptions, transcription_process_main,
                            transcription_server_main)


class SetupWorker(QThread):
    """Checa e atualiza yt-dlp/FFmpeg na inicialização."""

    progress = Signal(str, int)
    finished_ok = Signal(object)      # Toolchain
    failed = Signal(str)

    def __init__(self, manager: ToolManager, check_now: bool = False, parent=None):
        super().__init__(parent)
        self.manager, self.check_now = manager, check_now

    def run(self) -> None:
        try:
            log_event("Setup iniciado (consultar agora=%s)", self.check_now)
            tc = self.manager.ensure_all(
                lambda msg, pct: self.progress.emit(msg, pct), self.check_now)
        except Exception as exc:  # noqa: BLE001 — a mensagem vai para a UI
            report_exception("preparação do ambiente", exc)
            self.failed.emit(str(exc))
        else:
            log_event("Setup concluído: yt-dlp=%s ffmpeg=%s", tc.ytdlp_version, tc.ffmpeg_version)
            self.finished_ok.emit(tc)


class AppUpdateCheckWorker(QThread):
    """Consulta a release mais recente sem travar a interface."""

    finished_ok = Signal(object, float)  # ReleaseInfo | None, instante da consulta
    failed = Signal(str)

    def __init__(
        self,
        *,
        enabled: bool,
        last_checked_at: float,
        interval_hours: int,
        dismissed_version: str,
        force: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.enabled = enabled
        self.last_checked_at = last_checked_at
        self.interval_hours = max(0, interval_hours)
        self.dismissed_version = dismissed_version
        self.force = force

    def run(self) -> None:
        try:
            now = time.time()
            elapsed = now - self.last_checked_at
            if (not self.force and (
                not self.enabled or elapsed < self.interval_hours * 3600
            )):
                self.finished_ok.emit(None, 0.0)
                return

            release = AppUpdater().find_update()
            if (release and not self.force
                    and release.version == self.dismissed_version):
                release = None
            self.finished_ok.emit(release, now)
        except Exception as exc:  # noqa: BLE001
            report_exception("verificação de atualização do aplicativo", exc)
            self.failed.emit(str(exc))


class AppUpdateDownloadWorker(QThread):
    """Baixa e valida o instalador selecionado em segundo plano."""

    progress = Signal(int, int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, release: ReleaseInfo, parent=None):
        super().__init__(parent)
        self.release = release

    def run(self) -> None:
        try:
            path = AppUpdater().download(
                self.release,
                lambda received, total: self.progress.emit(received, total),
            )
        except Exception as exc:  # noqa: BLE001
            report_exception("download de atualização do aplicativo", exc)
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(str(path))


class MediaToolWorker(QThread):
    """Executa FFmpeg para edição local e permite cancelamento sem bloquear a UI."""

    progress = Signal(str)
    progress_value = Signal(int)
    finished_ok = Signal(str)
    failed = Signal(str)

    def __init__(self, options: MediaToolOptions, tc: Toolchain, parent=None):
        super().__init__(parent)
        self.options = options
        self.tc = tc
        self._cancelled = threading.Event()
        self._process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancelled.set()
        process = self._process
        if process and process.poll() is None:
            terminate_process_tree(process)

    def run(self) -> None:
        try:
            if self._cancelled.is_set():
                raise MediaToolError("Operação cancelada.")
            command = build_command(self.options, self.tc)
            duration = operation_duration(self.options, self.tc)
            self.options.destination.parent.mkdir(parents=True, exist_ok=True)
            self.progress.emit("Processando com FFmpeg…")
            self._process = popen_isolated(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if self._cancelled.is_set():
                terminate_process_tree(self._process)
            output_tail: list[str] = []
            assert self._process.stdout is not None
            for raw_line in self._process.stdout:
                line = raw_line.strip()
                if line:
                    output_tail.append(line)
                    del output_tail[:-80]
                if duration and line.startswith("out_time="):
                    elapsed = time_seconds(line.partition("=")[2])
                    percent = max(0, min(99, round(elapsed * 100 / duration)))
                    self.progress_value.emit(percent)
                    self.progress.emit(f"Processando com FFmpeg… {percent}%")
                if self._cancelled.is_set() and self._process.poll() is None:
                    terminate_process_tree(self._process)
            self._process.wait()
            if self._cancelled.is_set():
                raise MediaToolError("Operação cancelada.")
            if self._process.returncode:
                raise MediaToolError(
                    output_tail[-1] if output_tail else "O FFmpeg encerrou com erro."
                )
            if not self.options.destination.is_file():
                raise MediaToolError("O FFmpeg terminou sem gerar o arquivo esperado.")
            self.progress_value.emit(100)
        except Exception as exc:  # noqa: BLE001
            report_exception("ferramenta local de mídia", exc)
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(str(self.options.destination))
        finally:
            self._process = None


ALLOWED_THUMBNAIL_TYPES = frozenset({"image/jpeg", "image/jpg", "image/png", "image/webp"})


def _is_private_host(host: str) -> bool:
    import ipaddress
    import socket

    if not host or host.casefold() in {"localhost", "localhost.localdomain"}:
        return True
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, 443)}
    except OSError:
        return False  # a própria conexão vai falhar; não bloqueia por DNS instável
    for address in addresses:
        ip = ipaddress.ip_address(address.split("%")[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return True
    return False


class ThumbnailWorker(QThread):
    """Obtém uma miniatura pequena sem bloquear a interface nem relaxar o TLS."""

    finished_ok = Signal(str, bytes)
    failed = Signal(str)

    def __init__(self, url: str, proxy: str = "", parent=None):
        super().__init__(parent)
        self.url = url
        self.proxy = proxy.strip()

    def run(self) -> None:
        try:
            url = validate_media_url(self.url)
            parsed = urllib.parse.urlsplit(url)
            # A URL vem dos metadados do extrator (conteúdo remoto): só HTTPS e
            # nunca endereços da rede local/loopback.
            if parsed.scheme != "https" or _is_private_host(parsed.hostname or ""):
                raise ValueError("Miniatura ignorada: endereço não permitido.")
            handlers = [urllib.request.HTTPSHandler(context=_verified_ssl_context())]
            if self.proxy:
                handlers.append(urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy}))
            opener = urllib.request.build_opener(*handlers)
            request = urllib.request.Request(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/*"},
            )
            with opener.open(request, timeout=15) as response:
                content_type = str(response.headers.get("Content-Type") or "").casefold()
                if content_type.split(";")[0].strip() not in ALLOWED_THUMBNAIL_TYPES:
                    raise ValueError("A miniatura recebida não é uma imagem.")
                chunks: list[bytes] = []
                size = 0
                while True:
                    if self.isInterruptionRequested():
                        return
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    chunks.append(chunk)
                    size += len(chunk)
                    if size > 8 * 1024 * 1024:
                        raise ValueError("A miniatura ultrapassa o limite de 8 MB.")
                data = b"".join(chunks)
            if not data or len(data) > 8 * 1024 * 1024:
                raise ValueError("A miniatura ultrapassa o limite de 8 MB.")
        except Exception as exc:  # noqa: BLE001 - miniatura é melhoria opcional
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(self.url, data)


class ModelCacheWorker(QThread):
    """Baixa ou remove pesos do Whisper fora da thread da interface."""

    status = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str, int)
    failed = Signal(str)

    def __init__(self, action: str, model_size: str, mlx: bool, parent=None):
        super().__init__(parent)
        self.action = action
        self.model_size = model_size
        self.mlx = mlx

    def run(self) -> None:
        try:
            from .transcription import download_model_snapshot, model_cache_size, remove_cached_model

            if self.action == "download":
                download_model_snapshot(
                    self.model_size,
                    mlx=self.mlx,
                    status=self.status.emit,
                    progress=self.progress.emit,
                )
                changed = model_cache_size(self.model_size, mlx=self.mlx)
            elif self.action == "remove":
                self.status.emit(f"Removendo modelo {self.model_size}…")
                changed = remove_cached_model(self.model_size, mlx=self.mlx)
                self.progress.emit(100)
            else:
                raise ValueError("Ação desconhecida para o cache de modelos.")
        except Exception as exc:  # noqa: BLE001
            report_exception(f"{self.action} do modelo Whisper", exc)
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(self.model_size, int(changed))


class PlaylistEntriesWorker(QThread):
    """Lista os itens de uma playlist para o seletor, fora da thread da interface."""

    finished_ok = Signal(list)
    failed = Signal(str)

    def __init__(self, url: str, tc: Toolchain, cfg: Settings, parent=None):
        super().__init__(parent)
        self.url, self.tc, self.cfg = url, tc, cfg

    def run(self) -> None:
        try:
            entries = playlist_entries(
                self.url, self.tc.ytdlp, self.cfg.cookies_browser, self.cfg.cookies_file,
                self.cfg.proxy, extractor_args=self.cfg.extractor_args, env=self.tc.env())
        except Exception as exc:  # noqa: BLE001
            report_exception("listagem da playlist", exc)
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(entries)


class ProbeWorker(QThread):
    """Analisa a URL e devolve os formatos disponíveis."""

    finished_ok = Signal(object)      # MediaInfo
    failed = Signal(str)

    def __init__(self, url: str, tc: Toolchain, cfg: Settings, parent=None):
        super().__init__(parent)
        self.url, self.tc, self.cfg = url, tc, cfg

    def run(self) -> None:
        try:
            log_event("Análise iniciada: %s", self.url)
            info = probe(self.url, self.tc.ytdlp, self.cfg.cookies_browser,
                         self.cfg.cookies_file, self.cfg.proxy,
                         extractor_args=self.cfg.extractor_args, env=self.tc.env())
        except Exception as exc:  # noqa: BLE001
            report_exception("análise de mídia", exc)
            self.failed.emit(str(exc))
        else:
            log_event("Análise concluída: %s", self.url)
            self.finished_ok.emit(info)


class DownloadWorker(QThread):
    """Baixa um item da fila e, se pedido, converte com NVENC em seguida."""

    progress = Signal(int, object)          # job_id, Progress
    finished_ok = Signal(int, object)       # job_id, list[Path]
    failed = Signal(int, str, str)          # job_id, mensagem, saída completa

    def __init__(self, job_id: int, opts: DownloadOptions, cfg: Settings,
                 tc: Toolchain, parent=None):
        super().__init__(parent)
        self.job_id, self.opts, self.cfg, self.tc = job_id, opts, cfg, tc
        self.runner = DownloadRunner(opts, cfg, tc)
        self.transcoder: Transcoder | None = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        self.runner.cancel()
        if self.transcoder:
            self.transcoder.cancel()

    def run(self) -> None:
        try:
            log_event("Download iniciado: job=%s url=%s", self.job_id, self.opts.url)
            files: list[Path] = []
            last_error: Exception | None = None
            retries = max(0, min(5, int(self.cfg.auto_retry_attempts)))
            for attempt in range(retries + 1):
                if self._cancelled.is_set():
                    self.failed.emit(self.job_id, "Cancelado", "")
                    return
                # Uma nova execução é importante: o processo do yt-dlp que
                # recebeu erro de rede não deve ser reutilizado. Os .part ficam
                # no destino e --continue começa exatamente de onde parou.
                self.runner = DownloadRunner(self.opts, self.cfg, self.tc)
                # cancel() pode ocorrer entre a verificação no início do laço e
                # esta nova instância. Reaplicar o estado impede que um yt-dlp
                # nasça depois de o usuário já ter removido o item da fila.
                if self._cancelled.is_set():
                    self.runner.cancel()
                    self.failed.emit(self.job_id, "Cancelado", "")
                    return
                try:
                    files = self.runner.run(lambda p: self.progress.emit(self.job_id, p))
                except Exception as exc:  # o detalhe final preserva a saída útil
                    last_error = exc
                    if (self._cancelled.is_set() or self.runner.cancelled
                            or not is_retryable_error(str(exc)) or attempt >= retries):
                        raise

                    delay = max(1, min(60, int(self.cfg.auto_retry_delay))) * (attempt + 1)
                    log_event(
                        "Download transitório; job=%s tentativa=%s/%s nova tentativa em %ss: %s",
                        self.job_id, attempt + 1, retries + 1, delay, exc,
                    )
                    self.progress.emit(self.job_id, Progress(
                        status="retrying", stage=(
                            f"Conexão instável — nova tentativa {attempt + 2} de {retries + 1} "
                            f"em {delay}s"
                        ),
                    ))
                    # Espera curta e cancelável: não há trabalho na interface e
                    # o botão Cancelar continua respondendo imediatamente.
                    if self._cancelled.wait(delay):
                        self.failed.emit(self.job_id, "Cancelado", "")
                        return
                    continue
                else:
                    break
            else:  # defesa para alterações futuras no laço
                raise last_error or RuntimeError("O download não terminou.")

            if self._cancelled.is_set() or self.runner.cancelled:
                self.failed.emit(self.job_id, "Cancelado", "")
                return

            # Um recorte exato já precisa reencodar dentro do FFmpeg downloader
            # e usa o codec acelerado selecionado quando disponível. Rodar o
            # Transcoder novamente só perderia qualidade e dobraria o trabalho.
            has_section = bool(self.opts.section_start.strip() or self.opts.section_end.strip())
            if (self.cfg.transcode_enabled and not has_section
                    and not self.opts.audio_only and files):
                self.transcoder = Transcoder(self.tc, self.cfg)
                converted: list[Path] = []
                for path in files:
                    if not path.exists():
                        continue

                    def report(pct: float, path=path) -> None:
                        prog = Progress(status="processing", percent=pct,
                                        stage=f"Convertendo na GPU — {path.name}")
                        self.progress.emit(self.job_id, prog)

                    converted.append(self.transcoder.run(path, report))
                files = converted or files

            self.finished_ok.emit(self.job_id, files)
        except Exception as exc:  # noqa: BLE001
            report_exception(f"download do job {self.job_id}", exc)
            self.failed.emit(self.job_id, str(exc), self.runner.tail())
        else:
            log_event("Download concluído: job=%s arquivos=%s", self.job_id, len(files))


class GpuWorker(QThread):
    """Detecta NVENC fora da thread da interface.

    A detecção roda `nvidia-smi` e duas vezes o FFmpeg; na thread da UI isso
    congelava a janela por até alguns segundos logo após a tela de setup.
    """

    finished_ok = Signal(object)      # GpuInfo

    def __init__(self, ffmpeg: Path, parent=None):
        super().__init__(parent)
        self.ffmpeg = ffmpeg

    def run(self) -> None:
        try:
            info = detect(self.ffmpeg)
        except Exception as exc:  # noqa: BLE001 - detecção nunca deve derrubar o app
            get_logger().warning("Detecção de GPU indisponível: %s", exc)
            info = GpuInfo()
        self.finished_ok.emit(info)


class TranscriptionWorker(QThread):
    """Coordena a transcrição isolada e encaminha eventos para a aba Legendar.

    A interface Qt permanece neste processo. O modelo Whisper/CTranslate2 roda
    em outro processo, evitando que uma DLL CUDA instável encerre o aplicativo.
    """

    status = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, opts: TranscriptionOptions, tc: Toolchain, parent=None):
        super().__init__(parent)
        self.opts, self.tc = opts, tc
        self._process = None
        self._cancel_event = None
        self._pause_event = None
        self._force_stopped = False
        self._cancel_requested = False
        self._pause_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._cancel_event is not None:
            self._cancel_event.set()

    def pause(self, paused: bool) -> None:
        self._pause_requested = paused
        if self._pause_event is None:
            return
        if paused:
            self._pause_event.set()
        else:
            self._pause_event.clear()

    def force_stop(self) -> None:
        """Interrompe o filho só no encerramento da janela, se ele não respondeu."""
        self._force_stopped = True
        self.cancel()
        process = self._process
        if process is not None and process.is_alive():
            log_event("Forçando encerramento do processo de transcrição")
            process.terminate()

    def _handle_event(self, event) -> tuple[str, object] | None:
        kind, value = event
        if kind == "status":
            self.status.emit(str(value))
        elif kind == "progress":
            self.progress.emit(max(0, min(100, int(value))))
        elif kind in {"finished", "cancelled", "error"}:
            return kind, value
        else:
            get_logger().warning("Evento desconhecido do processo de transcrição: %r", event)
        return None

    def run(self) -> None:
        process = None
        events = None
        terminal: tuple[str, object] | None = None
        kill_job = 0
        try:
            context = multiprocessing.get_context("spawn")
            self._cancel_event = context.Event()
            self._pause_event = context.Event()
            if self._cancel_requested:
                self._cancel_event.set()
            if self._pause_requested:
                self._pause_event.set()
            events = context.Queue()
            process = context.Process(
                name="baixador-ytdlp-transcription",
                target=transcription_process_main,
                args=(self.opts, self.tc, events, self._cancel_event, self._pause_event),
            )
            self._process = process
            log_event("Iniciando processo isolado do legendador")
            process.start()
            # Se o app cair, o Windows encerra o legendador e o FFmpeg dele.
            kill_job = attach_pid_to_kill_job(process.pid or 0)

            while process.is_alive():
                try:
                    event = events.get(timeout=0.15)
                except queue.Empty:
                    continue
                except (EOFError, OSError):
                    # O filho pode ter caído em código nativo antes de fechar
                    # o pipe de eventos de forma limpa.
                    break
                received = self._handle_event(event)
                if received is not None:
                    terminal = received

            process.join()
            # Eventos escritos logo antes de o filho sair ainda podem estar no pipe.
            while True:
                try:
                    event = events.get_nowait()
                except queue.Empty:
                    break
                except (EOFError, OSError):
                    break
                received = self._handle_event(event)
                if received is not None:
                    terminal = received

            if terminal is None:
                if self._cancel_event.is_set() or self._cancel_requested or self._force_stopped:
                    terminal = ("cancelled", None)
                else:
                    code = process.exitcode
                    raise RuntimeError(
                        "O motor de transcrição encerrou inesperadamente "
                        f"(código {code}). O aplicativo continuou aberto; consulte native-fault.log."
                    )

            kind, value = terminal
            if kind == "cancelled":
                self.cancelled.emit()
            elif kind == "error":
                message = value.get("message", "Falha desconhecida no motor de transcrição")
                trace = value.get("traceback", "")
                get_logger().error("Falha recebida do processo de transcrição:\n%s", trace.rstrip())
                self.failed.emit(message)
            else:
                self.finished_ok.emit(str(value))
        except Exception as exc:  # noqa: BLE001
            report_exception("coordenação da transcrição", exc)
            self.failed.emit(str(exc))
        finally:
            if process is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                self._process = None
                process.close()
            release_job(kill_job)
            if events is not None:
                events.close()
                events.join_thread()


class PersistentTranscriptionWorker(QThread):
    """Ponte Qt para o processo de transcrição que atende vários itens.

    Há um processo filho por sessão da aba, mas não um por arquivo. Isso mantém
    os pesos do Whisper na RAM/VRAM entre itens consecutivos sem abrir mão do
    isolamento contra falhas das bibliotecas nativas.
    """

    status = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, tc: Toolchain, parent=None):
        super().__init__(parent)
        self.tc = tc
        self._context = multiprocessing.get_context("spawn")
        self._commands = self._context.Queue()
        self._events = self._context.Queue()
        self._process = None
        self._active_job = 0
        self._busy = False
        self._closing = False
        self._force_stopped = False
        self._state_lock = threading.Lock()

    def is_busy(self) -> bool:
        with self._state_lock:
            return self._busy

    def submit(self, opts: TranscriptionOptions) -> None:
        """Envia o próximo item. A página só submete um por vez."""
        with self._state_lock:
            if self._closing:
                raise RuntimeError("O processo de transcrição está sendo encerrado")
            if self._busy:
                raise RuntimeError("Já há uma transcrição em andamento")
            self._active_job += 1
            job_id = self._active_job
            self._busy = True
        if not self.isRunning():
            self.start()
        self._commands.put(("run", job_id, opts))

    def cancel(self) -> None:
        with self._state_lock:
            job_id = self._active_job
        if job_id:
            self._commands.put(("cancel", job_id))

    def pause(self, paused: bool) -> None:
        with self._state_lock:
            job_id = self._active_job
        if job_id:
            self._commands.put(("pause", job_id, bool(paused)))

    def shutdown(self) -> None:
        """Pede o encerramento seguro; ``force_stop`` é só o último recurso."""
        with self._state_lock:
            self._closing = True
            job_id = self._active_job
        if job_id:
            self._commands.put(("cancel", job_id))
        if self.isRunning():
            self._commands.put(("shutdown",))

    def force_stop(self) -> None:
        self._force_stopped = True
        self.shutdown()
        process = self._process
        if process is not None and process.is_alive():
            log_event("Forçando encerramento do servidor de transcrição")
            process.terminate()

    def _terminal(self, kind: str, value) -> None:
        with self._state_lock:
            self._busy = False
        if kind == "cancelled":
            self.cancelled.emit()
        elif kind == "error":
            message = value.get("message", "Falha desconhecida no motor de transcrição")
            trace = value.get("traceback", "")
            get_logger().error("Falha recebida do servidor de transcrição:\n%s", trace.rstrip())
            self.failed.emit(str(message))
        else:
            self.finished_ok.emit(str(value))

    def run(self) -> None:
        process = None
        kill_job = 0
        reported_crash = False
        try:
            process = self._context.Process(
                name="baixador-ytdlp-transcription-server",
                target=transcription_server_main,
                args=(self.tc, self._commands, self._events),
            )
            self._process = process
            log_event("Iniciando processo persistente do legendador")
            process.start()
            # Se o app cair, o Windows encerra o servidor e o FFmpeg que ele abriu.
            kill_job = attach_pid_to_kill_job(process.pid or 0)

            # Mesmo no encerramento, deixe o filho receber ``shutdown`` e
            # fechar o modelo de forma limpa; a tela usa ``wait`` antes de
            # recorrer a ``force_stop``.
            while process.is_alive():
                try:
                    event = self._events.get(timeout=0.15)
                except queue.Empty:
                    continue
                except (EOFError, OSError):
                    break
                try:
                    job_id, kind, value = event
                except (TypeError, ValueError):
                    get_logger().warning("Evento inválido do servidor de transcrição: %r", event)
                    continue
                with self._state_lock:
                    active = self._active_job
                if job_id != active:
                    continue
                if kind == "status":
                    self.status.emit(str(value))
                elif kind == "progress":
                    self.progress.emit(max(0, min(100, int(value))))
                elif kind in {"finished", "cancelled", "error"}:
                    self._terminal(kind, value)
                else:
                    get_logger().warning("Evento desconhecido do servidor de transcrição: %r", event)

            with self._state_lock:
                was_busy = self._busy
            if was_busy and not self._closing and not self._force_stopped:
                reported_crash = True
                self._terminal("error", {
                    "message": (
                        "O motor de transcrição encerrou inesperadamente. O aplicativo continuou aberto; "
                        "consulte native-fault.log."
                    ),
                    "traceback": "",
                })
        except Exception as exc:  # noqa: BLE001
            report_exception("coordenação persistente da transcrição", exc)
            with self._state_lock:
                was_busy = self._busy
            if was_busy:
                self._terminal("error", {"message": str(exc), "traceback": ""})
        finally:
            if process is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(2)
                self._process = None
                process.close()
            release_job(kill_job)
            if not reported_crash:
                with self._state_lock:
                    if self._closing:
                        self._busy = False

    def close_queues(self) -> None:
        """Fecha pipes após a thread encerrar, evitando recursos pendentes no Qt."""
        for channel in (self._commands, self._events):
            try:
                channel.close()
                channel.join_thread()
            except (OSError, ValueError):
                pass

