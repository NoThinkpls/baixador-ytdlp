"""Página 'Fila': acompanha, cancela, repete e abre o que já foi baixado."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QVBoxLayout,
                               QWidget)

from ..config import Settings
from ..downloader import DownloadOptions, Progress
from ..probe import human_size
from ..workers import DownloadWorker
from . import icons, theme
from .components import (Button, Chip, EmptyState, Headline, IconButton, ListRow, LogView,
                         Muted, PageHeader, ProgressBar, ScrollColumn, Toast)


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


def state_badge(parent: QWidget, icon_name: str, tone: str) -> QLabel:
    """Disco colorido com um ícone — identifica o estado do item de relance."""
    badge = QLabel(parent)
    badge.setFixedSize(34, 34)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    apply_badge(badge, icon_name, tone)
    return badge


def apply_badge(badge: QLabel, icon_name: str, tone: str) -> None:
    # 'neutral' é o nome do tom nas etiquetas; nos tokens de cor ele é o
    # cinza terciário, então a tradução acontece aqui e não em cada chamada.
    tone = "text_tertiary" if tone == "neutral" else tone
    color = theme.qcolor(tone)
    badge.setPixmap(icons.pixmap(icon_name, theme.color(tone), 18))
    badge.setStyleSheet(
        f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, 0.14);"
        f" border-radius: 17px;")


class JobCard(ListRow):
    cancel_requested = Signal(int)
    retry_requested = Signal(int)
    transcribe_requested = Signal(str)   # caminho do arquivo

    def __init__(self, job_id: int, opts: DownloadOptions, parent=None):
        super().__init__(parent, padding=(14, 12, 12, 13), spacing=10, horizontal=False)
        self.job_id = job_id
        self.files: list[Path] = []
        self.detail = ""
        self._state = ""

        top = QHBoxLayout()
        top.setSpacing(12)

        self.badge = state_badge(self, "queue", "text_tertiary")
        top.addWidget(self.badge, 0, Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        self.title = Headline(opts.title or opts.url, self, wrap=True)
        self.status = Muted("Na fila", self)
        texts.addWidget(self.title)
        texts.addWidget(self.status)
        top.addLayout(texts, 1)

        self.chip = Chip("Na fila", "neutral", self)
        top.addWidget(self.chip, 0, Qt.AlignmentFlag.AlignTop)

        self.transcribe_btn = IconButton("captions", "Gerar legenda deste arquivo", self)
        self.transcribe_btn.clicked.connect(self._transcribe)
        self.transcribe_btn.hide()

        self.detail_btn = IconButton("info", "Ver o erro completo", self)
        self.detail_btn.clicked.connect(self._show_detail)
        self.detail_btn.hide()

        self.retry_btn = IconButton("refresh", "Tentar de novo", self)
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.job_id))
        self.retry_btn.hide()

        self.open_btn = IconButton("folder", "Mostrar na pasta", self)
        self.open_btn.clicked.connect(self._reveal)
        self.open_btn.hide()

        self.cancel_btn = IconButton("close", "Cancelar", self)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))

        for button in (self.transcribe_btn, self.detail_btn, self.retry_btn,
                       self.open_btn, self.cancel_btn):
            top.addWidget(button, 0, Qt.AlignmentFlag.AlignTop)

        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)

        self.body.addLayout(top)
        self.body.addWidget(self.bar)

    # ------------------------------------------------------------- estados
    def _set_state(self, label: str, tone: str, icon_name: str) -> None:
        """Evita repintar etiqueta e disco a cada evento de progresso."""
        if self._state == label:
            return
        self._state = label
        self.chip.setText(label)
        self.chip.set_tone(tone)
        apply_badge(self.badge, icon_name, tone)

    def _tint_bar(self, token: str) -> None:
        """Barra verde ao concluir: o estado do item se lê sem ler o texto."""
        self.bar.setStyleSheet(
            f"QProgressBar::chunk {{ background-color: {theme.color(token)};"
            f" border-radius: 4px; }}")

    def reset(self) -> None:
        self.files = []
        self.detail = ""
        self._tint_bar("accent")
        self.bar.setValue(0)
        self.status.setText("Na fila")
        self._set_state("Na fila", "neutral", "queue")
        self.cancel_btn.show()
        for button in (self.retry_btn, self.detail_btn, self.open_btn, self.transcribe_btn):
            button.hide()

    def update_progress(self, prog: Progress) -> None:
        self._set_state("Baixando", "accent", "download")
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
        self._tint_bar("success")
        self.bar.setValue(100)
        self._set_state("Concluído", "success", "success")
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
        cancelled = message == "Cancelado"
        self._set_state("Cancelado" if cancelled else "Erro",
                        "neutral" if cancelled else "danger",
                        "stop" if cancelled else "error")
        self.retry_btn.setVisible(not cancelled)
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

        Não usa caixa de diálogo modal com altura fixa de propósito: log é
        conteúdo longo e precisa de rolagem, senão os botões saem do cartão.
        """
        dialog = QDialog(self.window())
        dialog.setWindowTitle("Saída do yt-dlp")
        dialog.resize(780, 480)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)
        layout.addWidget(Headline("Saída do yt-dlp", dialog))

        view = LogView("", dialog)
        view.setPlainText(self.detail or "Sem detalhes.")
        view.setLineWrapMode(LogView.LineWrapMode.NoWrap)
        layout.addWidget(view, 1)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        copy_btn = Button("Copiar tudo", "document", "secondary", dialog)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(self.detail))
        close_btn = Button("Fechar", "close", "ghost", dialog)
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
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(16)

        header = PageHeader("Fila", "Downloads em andamento e concluídos desta sessão.", self)
        self.summary = Muted("", header)
        self.summary.setWordWrap(False)
        header.add_action(self.summary)
        self.clear_btn = Button("Limpar concluídos", "sweep", "secondary", header)
        self.clear_btn.clicked.connect(self.clear_finished)
        header.add_action(self.clear_btn)
        root.addWidget(header)

        self.empty = EmptyState(
            "queue", "A fila está vazia",
            "Analise um link na página Baixar e ele aparece aqui com o progresso.", self)
        root.addWidget(self.empty, 1)

        self.scroll = ScrollColumn(self, spacing=10)
        self.cards = self.scroll.column
        self.cards.addStretch(1)
        self.container = self.scroll.body
        self.scroll.hide()
        root.addWidget(self.scroll, 3)

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    # ------------------------------------------------------------- fila
    def add(self, opts: DownloadOptions) -> bool:
        """Inclui um job, exceto se o mesmo item já estiver pendente ou em andamento."""
        added = self._add(opts)
        if added:
            self._pump()
        return added

    def add_many(self, options: list[DownloadOptions]) -> tuple[int, int]:
        """Importa uma lista e agenda todos os novos jobs de uma única vez."""
        added = sum(1 for opts in options if self._add(opts))
        if added:
            self._pump()
        return added, len(options) - added

    def _add(self, opts: DownloadOptions) -> bool:
        if any(self._same_download(job.opts, opts)
               for job in self.jobs.values()
               if job.active or job.id in self.pending):
            return False
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
        return True

    @staticmethod
    def _same_download(first: DownloadOptions, second: DownloadOptions) -> bool:
        return (
            first.url.strip() == second.url.strip()
            and Path(first.output_dir) == Path(second.output_dir)
            and first.selector == second.selector
            and first.container == second.container
            and first.audio_only == second.audio_only
            and first.audio_format == second.audio_format
            and first.section_start == second.section_start
            and first.section_end == second.section_end
        )

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
                Toast.error("Falha no download", message, parent=self.window(), duration=9000)
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
