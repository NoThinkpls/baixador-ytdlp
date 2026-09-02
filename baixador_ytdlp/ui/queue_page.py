"""Página 'Fila': acompanha, cancela e abre o que já foi baixado."""
from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, InfoBar,
                            InfoBarPosition, ProgressBar, PushButton, StrongBodyLabel,
                            TitleLabel, TransparentToolButton)
from qfluentwidgets import SmoothScrollArea

from ..config import Settings
from ..downloader import DownloadOptions, Progress
from ..probe import human_size
from ..workers import DownloadWorker


def reveal(path: Path) -> None:
    """Abre o Explorer com o arquivo selecionado (ou a pasta, nos outros sistemas)."""
    try:
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
    except Exception:
        pass


class JobCard(CardWidget):
    cancel_requested = Signal(int)

    def __init__(self, job_id: int, opts: DownloadOptions, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.files: list[Path] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.title = StrongBodyLabel(opts.title or opts.url, self)
        self.title.setWordWrap(True)
        self.cancel_btn = TransparentToolButton(FIF.CLOSE, self)
        self.cancel_btn.setToolTip("Cancelar")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))
        self.open_btn = TransparentToolButton(FIF.FOLDER, self)
        self.open_btn.setToolTip("Mostrar na pasta")
        self.open_btn.clicked.connect(self._reveal)
        self.open_btn.hide()
        top.addWidget(self.title, 1)
        top.addWidget(self.open_btn)
        top.addWidget(self.cancel_btn)

        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)
        self.status = CaptionLabel("Na fila", self)

        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

    def update_progress(self, prog: Progress) -> None:
        if prog.stage:
            self.status.setText(prog.stage)
            self.bar.setValue(int(prog.percent) if prog.percent else self.bar.value())
            return
        self.bar.setValue(int(prog.percent))
        parts = [f"{prog.percent:.1f}%"]
        if prog.total:
            parts.append(f"{human_size(prog.downloaded)} de {human_size(prog.total)}")
        if prog.speed:
            parts.append(f"{human_size(prog.speed)}/s")
        if prog.eta:
            parts.append(f"faltam {prog.eta // 60}m {prog.eta % 60}s")
        if prog.count > 1:
            parts.append(f"item {prog.index} de {prog.count}")
        self.status.setText(" · ".join(parts))

    def mark_done(self, files: list[Path]) -> None:
        self.files = files
        self.bar.setValue(100)
        self.cancel_btn.hide()
        if files:
            self.open_btn.show()
            self.status.setText(f"Concluído — {files[0].name}"
                                + (f" (+{len(files) - 1})" if len(files) > 1 else ""))
        else:
            self.status.setText("Concluído")

    def mark_failed(self, message: str) -> None:
        self.cancel_btn.hide()
        self.bar.setValue(0)
        self.status.setText(message)

    def _reveal(self) -> None:
        if self.files:
            reveal(self.files[0])


@dataclass
class Job:
    id: int
    opts: DownloadOptions
    card: JobCard
    worker: DownloadWorker | None = None


class QueuePage(QWidget):
    """Fila com limite de downloads simultâneos."""

    job_finished = Signal(str)

    def __init__(self, cfg: Settings, parent=None):
        super().__init__(parent)
        self.setObjectName("queuePage")
        self.cfg = cfg
        self.toolchain = None
        self._next_id = 1
        self.jobs: dict[int, Job] = {}
        self.pending: list[int] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(TitleLabel("Fila", self), 1)
        self.clear_btn = PushButton(FIF.BROOM, "Limpar concluídos", self)
        self.clear_btn.clicked.connect(self.clear_finished)
        header.addWidget(self.clear_btn)
        root.addLayout(header)

        self.empty = BodyLabel("Nada na fila ainda. Analise um link na página Baixar.", self)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty, 1)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.container = QWidget(self.scroll)
        self.container.setStyleSheet("background: transparent;")
        self.cards = QVBoxLayout(self.container)
        self.cards.setContentsMargins(0, 0, 8, 0)
        self.cards.setSpacing(10)
        self.cards.addStretch(1)
        self.scroll.setWidget(self.container)
        self.scroll.hide()
        root.addWidget(self.scroll, 3)

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    # ------------------------------------------------------------- fila
    def add(self, opts: DownloadOptions) -> None:
        job_id = self._next_id
        self._next_id += 1
        card = JobCard(job_id, opts, self.container)
        card.cancel_requested.connect(self.cancel)
        self.cards.insertWidget(0, card)
        self.jobs[job_id] = Job(job_id, opts, card)
        self.pending.append(job_id)
        self.empty.hide()
        self.scroll.show()
        self._pump()

    def _running(self) -> int:
        return sum(1 for j in self.jobs.values() if j.worker and j.worker.isRunning())

    def _pump(self) -> None:
        while self.pending and self._running() < max(1, self.cfg.max_parallel_downloads):
            job = self.jobs[self.pending.pop(0)]
            worker = DownloadWorker(job.id, job.opts, self.cfg, self.toolchain, self)
            worker.progress.connect(self._on_progress)
            worker.finished_ok.connect(self._on_done)
            worker.failed.connect(self._on_failed)
            job.worker = worker
            job.card.status.setText("Iniciando…")
            worker.start()

    def cancel(self, job_id: int) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        if job.worker and job.worker.isRunning():
            job.worker.cancel()
        elif job_id in self.pending:
            self.pending.remove(job_id)
            job.card.mark_failed("Cancelado")

    def _on_progress(self, job_id: int, prog: Progress) -> None:
        if job := self.jobs.get(job_id):
            job.card.update_progress(prog)

    def _on_done(self, job_id: int, files: list) -> None:
        if job := self.jobs.get(job_id):
            paths = [Path(f) for f in files]
            job.card.mark_done(paths)
            self.job_finished.emit(job.opts.title or job.opts.url)
            if self.cfg.open_folder_on_finish and paths:
                reveal(paths[0])
        self._pump()

    def _on_failed(self, job_id: int, message: str) -> None:
        if job := self.jobs.get(job_id):
            job.card.mark_failed(message)
            if message != "Cancelado":
                InfoBar.error("Falha no download", message, duration=9000,
                              position=InfoBarPosition.TOP_RIGHT, parent=self.window())
        self._pump()

    def clear_finished(self) -> None:
        for job_id, job in list(self.jobs.items()):
            if job.worker and job.worker.isRunning():
                continue
            if job_id in self.pending:
                continue
            job.card.setParent(None)
            job.card.deleteLater()
            del self.jobs[job_id]
        if not self.jobs:
            self.scroll.hide()
            self.empty.show()

    def stop_all(self) -> None:
        for job in self.jobs.values():
            if job.worker and job.worker.isRunning():
                job.worker.cancel()
                job.worker.wait(3000)
