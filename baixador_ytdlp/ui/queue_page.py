"""Página 'Fila': acompanha, cancela, repete e abre o que já foi baixado."""
from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QSizePolicy,
                               QVBoxLayout, QWidget)

from ..config import Settings
from ..downloader import DownloadOptions, Progress
from ..probe import human_size
from ..queue_state import QueueState
from ..workers import DownloadWorker
from . import icons, theme
from .i18n import tr
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
    pause_requested = Signal(int)
    resume_requested = Signal(int)
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
        self.kind = self.describe(opts)
        self.status = Muted(f"Na fila · {self.kind}", self)
        texts.addWidget(self.title)
        texts.addWidget(self.status)
        top.addLayout(texts, 1)

        # Estado e ações dividem o mesmo grupo: assim seus centros verticais
        # permanecem alinhados, em vez de o chip ficar alguns pixels acima dos
        # ícones por estar ancorado ao topo do cartão.
        self.action_group = QWidget(self)
        self.action_group.setObjectName("jobActions")
        self.action_group.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        actions = QHBoxLayout(self.action_group)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)

        self.chip = Chip("Na fila", "neutral", self.action_group)
        actions.addWidget(self.chip)

        self.transcribe_btn = IconButton("captions", "Gerar legenda deste arquivo", self.action_group)
        self.transcribe_btn.clicked.connect(self._transcribe)
        self.transcribe_btn.hide()

        self.detail_btn = IconButton("info", "Ver o erro completo", self.action_group)
        self.detail_btn.clicked.connect(self._show_detail)
        self.detail_btn.hide()

        self.retry_btn = IconButton("refresh", "Tentar de novo", self.action_group)
        self.retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.job_id))
        self.retry_btn.hide()

        self.open_btn = IconButton("folder", "Mostrar na pasta", self.action_group)
        self.open_btn.clicked.connect(self._reveal)
        self.open_btn.hide()

        self.cancel_btn = IconButton("close", "Cancelar e remover da fila", self.action_group)
        self.cancel_btn.clicked.connect(lambda: self.cancel_requested.emit(self.job_id))
        self.pause_btn = IconButton("pause", "Pausar download", self.action_group)
        self.pause_btn.clicked.connect(lambda: self.pause_requested.emit(self.job_id))
        self.resume_btn = IconButton("play", "Retomar download", self.action_group)
        self.resume_btn.clicked.connect(lambda: self.resume_requested.emit(self.job_id))
        self.resume_btn.hide()

        for button in (self.transcribe_btn, self.detail_btn, self.retry_btn,
                       self.open_btn, self.pause_btn, self.resume_btn, self.cancel_btn):
            actions.addWidget(button)
        top.addWidget(self.action_group, 0, Qt.AlignmentFlag.AlignVCenter)

        self.bar = ProgressBar(self)
        self.bar.setRange(0, 100)

        self.body.addLayout(top)
        self.body.addWidget(self.bar)

    @staticmethod
    def describe(opts: DownloadOptions) -> str:
        """Tipo, formato e destino em uma linha: o que vai sair e onde."""
        if opts.audio_only:
            kind = f"Áudio {opts.audio_format.upper()}"
        else:
            kind = "Vídeo" if opts.container == "original" else f"Vídeo {opts.container.upper()}"
        if opts.playlist:
            kind += " · playlist"
        if opts.section_start.strip() or opts.section_end.strip():
            kind += " · trecho"
        folder = Path(opts.output_dir).name or opts.output_dir
        return f"{kind} · {folder}"

    def _show_removable(self) -> None:
        """Itens finalizados também saem da lista um a um."""
        self.cancel_btn.setToolTip("Remover da fila (o arquivo continua no disco)")
        self.cancel_btn.show()
        self.pause_btn.hide()
        self.resume_btn.hide()

    # ------------------------------------------------------------- estados
    def _set_state(self, label: str, tone: str, icon_name: str) -> None:
        """Evita repintar etiqueta e disco a cada evento de progresso."""
        if self._state == label:
            return
        self._state = label
        self.chip.setText(tr(label))
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
        self.bar.show()
        self.status.setText(f"Na fila · {self.kind}")
        self._set_state("Na fila", "neutral", "queue")
        self.cancel_btn.setToolTip("Cancelar e remover da fila")
        self.cancel_btn.show()
        self.pause_btn.show()
        self.resume_btn.hide()
        for button in (self.retry_btn, self.detail_btn, self.open_btn, self.transcribe_btn):
            button.hide()

    def mark_starting(self) -> None:
        self.pause_btn.show()
        self.resume_btn.hide()
        self.status.setText(tr("Iniciando…"))
        self._set_state("Iniciando", "accent", "download")

    def mark_paused(self) -> None:
        self.status.setText(f"Pausado · {self.kind}")
        self._set_state("Pausado", "neutral", "pause")
        self.pause_btn.hide()
        self.resume_btn.show()
        self.bar.show()

    def update_progress(self, prog: Progress) -> None:
        if prog.status == "retrying":
            self._set_state("Tentando novamente", "warning", "refresh")
            self.status.setText(tr(prog.stage or "Aguardando nova tentativa…"))
            return
        if prog.status == "processing":
            self._set_state("Processando", "accent", "tools")
        else:
            self._set_state("Baixando", "accent", "download")
        if prog.stage:
            self.status.setText(tr(prog.stage))
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

    def mark_done(self, files: list[Path], warning: str = "") -> None:
        self.pause_btn.hide()
        self.resume_btn.hide()
        self.files = files
        self._tint_bar("warning" if warning else "success")
        self.bar.setValue(100)
        if warning:
            self._set_state("Concluído com aviso", "warning", "warning")
        else:
            self._set_state("Concluído", "success", "success")
        self.detail = warning
        self.detail_btn.setToolTip("Ver o aviso completo" if warning else "Ver o erro completo")
        self.detail_btn.setVisible(bool(warning))
        self._show_removable()
        self.retry_btn.hide()
        if files:
            self.open_btn.show()
            self.transcribe_btn.setVisible(files[0].exists())
            self.status.setText(f"Concluído — {files[0].name}"
                                + (f" (+{len(files) - 1})" if len(files) > 1 else ""))
        else:
            self.status.setText(tr("Concluído"))

    def mark_failed(self, message: str, detail: str = "") -> None:
        self.pause_btn.hide()
        self.resume_btn.hide()
        self._show_removable()
        self.bar.setValue(0)
        self.bar.hide()  # barra vazia no erro só ocupava espaço
        self.status.setText(tr(message))
        self.detail = detail
        cancelled = message == "Cancelado"
        self._set_state("Cancelado" if cancelled else "Erro",
                        "neutral" if cancelled else "danger",
                        "stop" if cancelled else "error")
        self.retry_btn.setVisible(not cancelled)
        self.detail_btn.setToolTip("Ver o erro completo")
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
    removing: bool = False
    warning: str = ""
    failed: bool = False
    paused: bool = False
    pause_requested: bool = False


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
        self._state = QueueState()
        self._state_restored = False
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(16)

        header = PageHeader("Fila", "Downloads em andamento e concluídos desta sessão.", self)
        self.summary = Muted("", header)
        self.summary.setWordWrap(False)
        header.add_action(self.summary)
        self.retry_failed_btn = Button("Tentar de novo as falhas", "refresh", "secondary", header)
        self.retry_failed_btn.clicked.connect(self.retry_failed)
        self.retry_failed_btn.hide()
        header.add_action(self.retry_failed_btn)
        self.pause_all_btn = Button("Pausar tudo", "pause", "secondary", header)
        self.pause_all_btn.clicked.connect(self.pause_all)
        self.pause_all_btn.setEnabled(False)
        header.add_action(self.pause_all_btn)
        self.clear_btn = Button("Limpar finalizados", "sweep", "secondary", header)
        self.clear_btn.setToolTip("Remove da lista os itens concluídos, com erro ou cancelados")
        self.clear_btn.clicked.connect(self.clear_finished)
        self.clear_btn.setEnabled(False)
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
        self._restore_pending()

    # ------------------------------------------------------------- fila
    def add(self, opts: DownloadOptions, *, allow_duplicate: bool = False) -> bool:
        """Inclui um job, exceto se o mesmo item já estiver pendente ou em andamento."""
        added = self._add(opts, allow_duplicate=allow_duplicate)
        if added:
            self._pump()
        return added

    def add_many(
        self,
        options: list[DownloadOptions],
        *,
        allow_duplicates: bool = False,
    ) -> tuple[int, list[DownloadOptions]]:
        """Importa uma lista e devolve os itens repetidos para confirmação."""
        added = 0
        duplicates: list[DownloadOptions] = []
        for opts in options:
            if self._add(opts, allow_duplicate=allow_duplicates):
                added += 1
            else:
                duplicates.append(opts)
        if added:
            self._pump()
        return added, duplicates

    def _add(
        self,
        opts: DownloadOptions,
        *,
        persist: bool = True,
        allow_duplicate: bool = False,
    ) -> bool:
        # Dentro da mesma sessão um cartão existente já é a fonte de verdade:
        # em caso de falha a pessoa pode usar o botão "Tentar de novo" sem
        # criar dois jobs concorrentes para o mesmo arquivo.
        if not allow_duplicate and any(
            not job.removing and self._same_download(job.opts, opts)
            for job in self.jobs.values()
        ):
            return False
        job_id = self._next_id
        self._next_id += 1
        card = JobCard(job_id, opts, self.container)
        card.cancel_requested.connect(self.cancel)
        card.pause_requested.connect(self.pause)
        card.resume_requested.connect(self.resume)
        card.retry_requested.connect(self.retry)
        card.transcribe_requested.connect(self.transcribe_requested)
        # Ordem de chegada, a mesma do processamento: o próximo a baixar fica em
        # cima. Antes o mais novo entrava no topo e a fila parecia invertida.
        self.cards.insertWidget(self.cards.count() - 1, card)
        self.jobs[job_id] = Job(job_id, opts, card)
        self.pending.append(job_id)
        self.empty.hide()
        self.scroll.show()
        if persist:
            self._persist()
        return True

    def _restore_pending(self) -> None:
        """Restaura uma fila deixada pela sessão anterior uma única vez."""
        if self._state_restored or self.toolchain is None:
            return
        self._state_restored = True
        if not self.cfg.resume_queue:
            self._state.save([])
            return
        # O arquivo pode conter repetições que o usuário confirmou na sessão
        # anterior. A restauração deve preservar essa escolha.
        restored = 0
        for opts, paused in self._state.load_entries():
            if self._add(opts, persist=False, allow_duplicate=True):
                restored += 1
                if paused:
                    job_id = self._next_id - 1
                    self.pending.remove(job_id)
                    self.jobs[job_id].paused = True
                    self.jobs[job_id].card.mark_paused()
        if restored:
            self._pump()
        else:
            self._persist()

    def _persist(self) -> None:
        """Mantém somente jobs que ainda precisam de trabalho no próximo início."""
        options = [
            (job.opts, job.paused or job.pause_requested) for job in self.jobs.values()
            if not job.removing and (job.active or job.id in self.pending or job.paused)
        ]
        self._state.save_entries(options)

    def pause(self, job_id: int) -> None:
        job = self.jobs.get(job_id)
        if not job or job.removing or job.paused or job.pause_requested:
            return
        if job_id in self.pending:
            self.pending.remove(job_id)
            job.paused = True
            job.card.mark_paused()
        elif job.active and job.worker:
            job.pause_requested = True
            job.card.mark_paused()
            job.worker.cancel()  # DownloadRunner conserva os arquivos .part.
        self._persist()
        self._refresh_summary()
        self._pump()

    def resume(self, job_id: int) -> None:
        job = self.jobs.get(job_id)
        if not job or job.removing or not job.paused or job.active:
            return
        job.paused = False
        job.card.reset()
        self.pending.append(job_id)
        self._persist()
        self._pump()

    def pause_all(self) -> None:
        for job_id in list(self.pending):
            self.pending.remove(job_id)
            job = self.jobs[job_id]
            job.paused = True
            job.card.mark_paused()
        for job_id in [job.id for job in self.jobs.values() if job.active]:
            self.pause(job_id)
        self._persist()
        self._refresh_summary()

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
        job.warning = ""
        job.failed = False
        if job_id not in self.pending:
            self.pending.append(job_id)
        self._persist()
        self._pump()

    def _running(self) -> int:
        # Contador barato: o estado 'active' é mantido pelos próprios callbacks,
        # sem interrogar cada QThread a cada evento de progresso.
        # Um item que o usuário removeu deixa de ocupar a fila imediatamente,
        # mesmo enquanto o processo recebe o sinal de encerramento.
        return sum(1 for job in self.jobs.values() if job.active and not job.removing)

    def _pump(self) -> None:
        while self.pending and self._running() < max(1, self.cfg.max_parallel_downloads):
            job = self.jobs[self.pending.pop(0)]
            worker = DownloadWorker(job.id, job.opts, self.cfg, self.toolchain, self)
            worker.progress.connect(self._on_progress)
            worker.warning.connect(self._on_warning)
            worker.finished_ok.connect(self._on_done)
            worker.failed.connect(self._on_failed)
            worker.finished.connect(worker.deleteLater)
            job.worker = worker
            job.active = True
            job.card.mark_starting()
            worker.start()
        self._persist()
        self._refresh_summary()

    def cancel(self, job_id: int) -> None:
        """Remove o cartão e cancela qualquer processo associado sem restaurá-lo."""
        job = self.jobs.get(job_id)
        if not job or job.removing:
            return
        job.removing = True
        job.card.hide()
        if job_id in self.pending:
            self.pending.remove(job_id)
        # Remover da persistência acontece antes de esperar o processo: mesmo
        # que o SO demore a encerrá-lo, o cartão não volta na próxima abertura.
        self._persist()
        self._refresh_visibility()
        self._refresh_summary()
        self._emit_overall()
        if job.active and job.worker:
            job.worker.cancel()
            self._pump()
            return
        self._finalize_removal(job_id)
        self._pump()

    def _finalize_removal(self, job_id: int) -> None:
        job = self.jobs.pop(job_id, None)
        if not job:
            return
        if job_id in self.pending:
            self.pending.remove(job_id)
        job.card.setParent(None)
        job.card.deleteLater()
        self._refresh_visibility()

    def _refresh_visibility(self) -> None:
        if any(not job.removing for job in self.jobs.values()):
            self.empty.hide()
            self.scroll.show()
        else:
            self.scroll.hide()
            self.empty.show()

    def _on_progress(self, job_id: int, prog: Progress) -> None:
        if job := self.jobs.get(job_id):
            if not job.pause_requested:
                job.card.update_progress(prog)
            self._emit_overall()

    def _on_warning(self, job_id: int, message: str) -> None:
        if job := self.jobs.get(job_id):
            job.warning = message

    def _on_done(self, job_id: int, files: list) -> None:
        job = self.jobs.get(job_id)
        if job:
            job.active = False
            job.worker = None
            if job.removing:
                self._finalize_removal(job_id)
                self._pump()
                self._emit_overall()
                return
            paths = [Path(f) for f in files]
            job.pause_requested = False
            job.card.mark_done(paths, job.warning)
            if job.warning:
                Toast.warning("Concluído com aviso", job.warning.split("\n", 1)[0],
                              parent=self.window(), duration=7000)
            self.job_finished.emit(job.opts, paths)
            if self.cfg.open_folder_on_finish and paths:
                reveal(paths[0])
            self._persist()
        self._pump()
        self._emit_overall()

    def _on_failed(self, job_id: int, message: str, detail: str = "") -> None:
        job = self.jobs.get(job_id)
        if job:
            job.active = False
            job.worker = None
            if job.removing:
                self._finalize_removal(job_id)
                self._pump()
                self._emit_overall()
                return
            if job.pause_requested:
                job.pause_requested = False
                job.paused = True
                job.card.mark_paused()
                self._persist()
                self._pump()
                self._emit_overall()
                return
            job.card.mark_failed(message, detail)
            job.failed = message != "Cancelado"
            if message != "Cancelado":
                Toast.error("Falha no download", message, parent=self.window(), duration=9000)
            self._persist()
        self._pump()
        self._emit_overall()

    # ------------------------------------------------------------ resumo
    def _refresh_summary(self) -> None:
        running = sum(1 for job in self.jobs.values() if job.active and not job.removing)
        waiting = sum(1 for job_id in self.pending if not self.jobs[job_id].removing)
        paused = sum(1 for job in self.jobs.values() if job.paused and not job.removing)
        parts = []
        if running:
            parts.append(f"{running} baixando")
        if waiting:
            parts.append(f"{waiting} na fila")
        if paused:
            parts.append(f"{paused} pausado{'s' if paused != 1 else ''}")
        self.pause_all_btn.setEnabled(bool(running or waiting))
        self.summary.setText(" · ".join(parts))
        visible = [job for job_id, job in self.jobs.items() if not job.removing]
        finished = [job for job in visible if not job.active and job.id not in self.pending
                    and not job.paused]
        failed = sum(1 for job in finished if job.failed)
        self.clear_btn.setEnabled(bool(finished))
        self.retry_failed_btn.setVisible(failed > 0)
        if failed:
            self.retry_failed_btn.setText(
                "Tentar de novo a falha" if failed == 1 else f"Tentar de novo as {failed} falhas")

    def retry_failed(self) -> None:
        for job_id, job in list(self.jobs.items()):
            if job.failed and not job.active and not job.removing:
                self.retry(job_id)

    def _emit_overall(self) -> None:
        """Média dos downloads ativos — alimenta a barra de tarefas do Windows."""
        active = [job for job in self.jobs.values() if job.active and not job.removing]
        if not active:
            self.overall_progress.emit(-1.0)
            return
        total = sum(job.card.bar.value() for job in active)
        self.overall_progress.emit(total / len(active))

    def clear_finished(self) -> None:
        for job_id, job in list(self.jobs.items()):
            if job.active or job_id in self.pending or job.paused:
                continue
            job.card.setParent(None)
            job.card.deleteLater()
            del self.jobs[job_id]
        if not self.jobs:
            self.scroll.hide()
            self.empty.show()
        self._persist()
        self._refresh_summary()

    def stop_all(self) -> None:
        for job in self.jobs.values():
            if job.active and job.worker:
                job.worker.cancel()
        deadline = time.monotonic() + 3.0
        for job in self.jobs.values():
            if job.worker and job.worker.isRunning():
                remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
                if not remaining_ms:
                    break
                job.worker.wait(remaining_ms)
        self._persist()

    def cancel_all(self) -> None:
        """Cancela e remove a fila inteira sem iniciar novos itens no intervalo."""
        self.pending.clear()
        for job_id, job in list(self.jobs.items()):
            job.removing = True
            job.card.hide()
            if job.active and job.worker:
                job.worker.cancel()
            else:
                self._finalize_removal(job_id)
        self._persist()
        self._refresh_summary()
        self._emit_overall()

    def has_pending_work(self) -> bool:
        return bool(self.pending) or any(job.active for job in self.jobs.values())
