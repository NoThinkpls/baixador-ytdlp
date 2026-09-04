"""Página 'Fila': acompanha, cancela, repete e abre o que já foi baixado."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QPlainTextEdit,
                               QVBoxLayout, QWidget)
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, InfoBar,
                            InfoBarPosition, ProgressBar, PushButton,
                            SmoothScrollArea, StrongBodyLabel, TitleLabel,
                            TransparentToolButton)

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
    except OSError:
        pass


class JobCard(CardWidget):
    cancel_requested = Signal(int)
    retry_requested = Signal(int)
    transcribe_requested = Signal(str)   # caminho do arquivo

    def __init__(self, job_id: int, opts: DownloadOptions, parent=None):
        super().__init__(parent)
        self.job_id = job_id
        self.files: list[Path] = []
        self.detail = ""

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        self.title = StrongBodyLabel(opts.title or opts.url, self)
        self.title.setWordWrap(True)

        self.transcribe_btn = TransparentToolButton(FIF.MESSAGE, self)
        self.transcribe_btn.setToolTip("Gerar legenda deste arquivo")
        self.transcribe_btn.clicked.connect(self._transcribe)
        self.transcribe_btn.hide()

        self.detail_btn = TransparentToolButton(FIF.INFO, self)
        self.detail_btn.setToolTip("Ver o erro completo")
        self.detail_btn.clicked.connect(self._show_detail)
        self.detail_btn.hide()

        self.retry_btn = TransparentToolButton(FIF.SYNC, self)
        self.retry_btn.setToolTip("Tentar de novo")
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.job_id))
        self.retry_btn.hide()

        self.open_btn = TransparentToolButton(FIF.FOLDER, self)
        self.open_btn.setToolTip("Mostrar na pasta")
        self.open_btn.clicked.connect(self._reveal)
        self.open_btn.hide()

        self.cancel_btn = TransparentToolButton(FIF.CLOSE, self)
        self.cancel_btn.setToolTip("Cancelar")
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))

        top.addWidget(self.title, 1)
        for button in (self.transcribe_btn, self.detail_btn, self.retry_btn,
                       self.open_btn, self.cancel_btn):
            top.addWidget(button)

        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)
        self.status = CaptionLabel("Na fila", self)
        self.status.setWordWrap(True)

        layout.addLayout(top)
        layout.addWidget(self.bar)
        layout.addWidget(self.status)

    # ------------------------------------------------------------- estados
    def reset(self) -> None:
        self.files = []
        self.detail = ""
        self.bar.setValue(0)
        self.status.setText("Na fila")
        self.cancel_btn.show()
        for button in (self.retry_btn, self.detail_btn, self.open_btn, self.transcribe_btn):
            button.hide()

    def update_progress(self, prog: Progress) -> None:
        if prog.stage:
            self.status.setText(prog.stage)
            if prog.percent:
                self.bar.setValue(int(prog.percent))
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
        self.retry_btn.hide()
        if files:
            self.open_btn.show()
            self.transcribe_btn.setVisible(files[0].exists())
            self.status.setText(f"Concluído — {files[0].name}"
                                + (f" (+{len(files) - 1})" if len(files) > 1 else ""))
        else:
            self.status.setText("Concluído")

    def mark_failed(self, message: str, detail: str = "") -> None:
        self.cancel_btn.hide()
        self.bar.setValue(0)
        self.status.setText(message)
        self.detail = detail
        self.retry_btn.setVisible(message != "Cancelado")
        self.detail_btn.setVisible(bool(detail))

    # -------------------------------------------------------------- ações
    def _reveal(self) -> None:
        if self.files:
            reveal(self.files[0])

    def _transcribe(self) -> None:
        if self.files:
            self.transcribe_requested.emit(str(self.files[0]))

    def _show_detail(self) -> None:
        """Mostra a saída do yt-dlp numa janela rolável.

        Não usa MessageBox de propósito: aquele widget fixa a altura na construção
        e reflowa o texto a cada resize, então um log de várias linhas empurra os
        botões para fora do cartão — e, sendo modal com máscara, deixa o aplicativo
        inteiro inacessível. Log é conteúdo longo; precisa de rolagem.
        """
        dialog = QDialog(self.window())
        dialog.setWindowTitle("Saída do yt-dlp")
        dialog.resize(760, 460)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        view = QPlainTextEdit(self.detail or "Sem detalhes.", dialog)
        view.setReadOnly(True)
        view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        layout.addWidget(view, 1)

        buttons = QHBoxLayout()
        copy_btn = PushButton(FIF.COPY, "Copiar tudo", dialog)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.detail))
        close_btn = PushButton(FIF.CLOSE, "Fechar", dialog)
        close_btn.clicked.connect(dialog.accept)
        buttons.addStretch(1)
        buttons.addWidget(copy_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)

        dialog.exec()


@dataclass
class Job:
    id: int
    opts: DownloadOptions
    card: JobCard
    worker: DownloadWorker | None = None
    active: bool = False


class QueuePage(QWidget):
    """Fila com limite de downloads simultâneos."""

    job_finished = Signal(object, object)  # DownloadOptions, list[Path]
    transcribe_requested = Signal(str)
    overall_progress = Signal(float)       # -1 = sem download ativo

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
        self.summary = CaptionLabel("", self)
        header.addWidget(self.summary)
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
        card.retry_requested.connect(self.retry)
        card.transcribe_requested.connect(self.transcribe_requested)
        self.cards.insertWidget(0, card)
        self.jobs[job_id] = Job(job_id, opts, card)
        self.pending.append(job_id)
        self.empty.hide()
        self.scroll.show()
        self._pump()

    def retry(self, job_id: int) -> None:
        job = self.jobs.get(job_id)
        if not job or job.active:
            return
        job.card.reset()
        if job_id not in self.pending:
            self.pending.append(job_id)
        self._pump()

    def _running(self) -> int:
        # Contador barato: o estado 'active' é mantido pelos próprios callbacks,
        # sem interrogar cada QThread a cada evento de progresso.
        return sum(1 for job in self.jobs.values() if job.active)

    def _pump(self) -> None:
        while self.pending and self._running() < max(1, self.cfg.max_parallel_downloads):
            job = self.jobs[self.pending.pop(0)]
            worker = DownloadWorker(job.id, job.opts, self.cfg, self.toolchain, self)
            worker.progress.connect(self._on_progress)
            worker.finished_ok.connect(self._on_done)
            worker.failed.connect(self._on_failed)
            worker.finished.connect(worker.deleteLater)
            job.worker = worker
            job.active = True
            job.card.status.setText("Iniciando…")
            worker.start()
        self._refresh_summary()

    def cancel(self, job_id: int) -> None:
        job = self.jobs.get(job_id)
        if not job:
            return
        if job.active and job.worker:
            job.worker.cancel()
        elif job_id in self.pending:
            self.pending.remove(job_id)
            job.card.mark_failed("Cancelado")
            self._refresh_summary()

    def _on_progress(self, job_id: int, prog: Progress) -> None:
        if job := self.jobs.get(job_id):
            job.card.update_progress(prog)
            self._emit_overall()

    def _on_done(self, job_id: int, files: list) -> None:
        job = self.jobs.get(job_id)
        if job:
            job.active = False
            job.worker = None
            paths = [Path(f) for f in files]
            job.card.mark_done(paths)
            self.job_finished.emit(job.opts, paths)
            if self.cfg.open_folder_on_finish and paths:
                reveal(paths[0])
        self._pump()
        self._emit_overall()

    def _on_failed(self, job_id: int, message: str, detail: str = "") -> None:
        job = self.jobs.get(job_id)
        if job:
            job.active = False
            job.worker = None
            job.card.mark_failed(message, detail)
            if message != "Cancelado":
                InfoBar.error("Falha no download", message, duration=9000,
                              position=InfoBarPosition.TOP_RIGHT, parent=self.window())
        self._pump()
        self._emit_overall()

    # ------------------------------------------------------------ resumo
    def _refresh_summary(self) -> None:
        running, waiting = self._running(), len(self.pending)
        parts = []
        if running:
            parts.append(f"{running} baixando")
        if waiting:
            parts.append(f"{waiting} na fila")
        self.summary.setText(" · ".join(parts))

    def _emit_overall(self) -> None:
        """Média dos downloads ativos — alimenta a barra de tarefas do Windows."""
        active = [job for job in self.jobs.values() if job.active]
        if not active:
            self.overall_progress.emit(-1.0)
            return
        total = sum(job.card.bar.value() for job in active)
        self.overall_progress.emit(total / len(active))

    def clear_finished(self) -> None:
        for job_id, job in list(self.jobs.items()):
            if job.active or job_id in self.pending:
                continue
            job.card.setParent(None)
            job.card.deleteLater()
            del self.jobs[job_id]
        if not self.jobs:
            self.scroll.hide()
            self.empty.show()
        self._refresh_summary()

    def stop_all(self) -> None:
        for job in self.jobs.values():
            if job.active and job.worker:
                job.worker.cancel()
        for job in self.jobs.values():
            if job.worker:
                job.worker.wait(3000)
