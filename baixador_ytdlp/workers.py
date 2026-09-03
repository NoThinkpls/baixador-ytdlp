"""Threads de trabalho — nada de I/O de rede ou subprocesso na thread da interface."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .config import Settings
from .downloader import DownloadOptions, DownloadRunner, Progress, Transcoder
from .gpu import GpuInfo, detect
from .probe import probe
from .tools import ToolManager, Toolchain
from .transcription import Transcriber, TranscriptionCancelled, TranscriptionOptions


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
            tc = self.manager.ensure_all(lambda msg, pct: self.progress.emit(msg, pct), self.force)
        except Exception as exc:  # noqa: BLE001 — a mensagem vai para a UI
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(tc)


class ProbeWorker(QThread):
    """Analisa a URL e devolve os formatos disponíveis."""

    finished_ok = Signal(object)      # MediaInfo
    failed = Signal(str)

    def __init__(self, url: str, tc: Toolchain, cfg: Settings, parent=None):
        super().__init__(parent)
        self.url, self.tc, self.cfg = url, tc, cfg

    def run(self) -> None:
        try:
            info = probe(self.url, self.tc.ytdlp, self.cfg.cookies_browser, self.cfg.proxy)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
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
            self.failed.emit(self.job_id, str(exc), self.runner.tail())


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
        except Exception:  # noqa: BLE001 - detecção nunca deve derrubar o app
            info = GpuInfo()
        self.finished_ok.emit(info)


class TranscriptionWorker(QThread):
    """Executa Whisper fora da interface e encaminha eventos para a aba Legendar."""

    status = Signal(str)
    progress = Signal(int)
    finished_ok = Signal(str)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, opts: TranscriptionOptions, tc: Toolchain, parent=None):
        super().__init__(parent)
        self.opts, self.tc = opts, tc
        self.transcriber: Transcriber | None = None

    def cancel(self) -> None:
        if self.transcriber:
            self.transcriber.cancel()

    def pause(self, paused: bool) -> None:
        if self.transcriber:
            self.transcriber.pause(paused)

    def run(self) -> None:
        try:
            self.transcriber = Transcriber(
                self.tc, self.status.emit, self.progress.emit, self.opts.aggressive_filter)
            self.transcriber.run(self.opts)
        except TranscriptionCancelled:
            self.cancelled.emit()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        else:
            self.finished_ok.emit(str(self.opts.output_path))
