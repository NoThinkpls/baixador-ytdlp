"""Threads de trabalho — nada de I/O de rede ou subprocesso na thread da interface."""
from __future__ import annotations

import multiprocessing
import queue
import time
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .config import Settings
from .diagnostics import get_logger, log_event, report_exception
from .downloader import DownloadOptions, DownloadRunner, Progress, Transcoder
from .gpu import GpuInfo, detect
from .probe import probe
from .tools import ToolManager, Toolchain
from .updater import AppUpdater, ReleaseInfo
from .transcription import TranscriptionOptions, transcription_process_main


class SetupWorker(QThread):
    """Checa e atualiza yt-dlp/FFmpeg na inicialização."""

    progress = Signal(str, int)
    finished_ok = Signal(object)      # Toolchain
    failed = Signal(str)

    def __init__(self, manager: ToolManager, force: bool = False, parent=None):
        super().__init__(parent)
        self.manager, self.force = manager, force

    def run(self) -> None:
        try:
            log_event("Setup iniciado (forçar atualização=%s)", self.force)
            tc = self.manager.ensure_all(lambda msg, pct: self.progress.emit(msg, pct), self.force)
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

    def cancel(self) -> None:
        self.runner.cancel()
        if self.transcoder:
            self.transcoder.cancel()

    def run(self) -> None:
        try:
            log_event("Download iniciado: job=%s url=%s", self.job_id, self.opts.url)
            files = self.runner.run(lambda p: self.progress.emit(self.job_id, p))
            if self.runner.cancelled:
                self.failed.emit(self.job_id, "Cancelado", "")
                return

            if self.cfg.transcode_enabled and not self.opts.audio_only and files:
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
            if events is not None:
                events.close()
                events.join_thread()
