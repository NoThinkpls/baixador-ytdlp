"""Fluxo guiado para edições locais de mídia com o FFmpeg do aplicativo."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFileDialog, QGridLayout,
                               QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget)

from ..media_tools import MediaToolOptions, available_destination, default_destination
from ..workers import MediaToolWorker
from . import icons, theme
from .components import (Button, Divider, Headline, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ProgressBar, ScrollColumn, SectionLabel, Select,
                         SettingRow, Switch, TextField, Toast)

MEDIA_FILTER = ("Mídia (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.mp3 *.m4a *.wav *.flac);;"
                "Todos os arquivos (*.*)")
SUBTITLE_FILTER = "Legendas (*.srt *.vtt *.ass);;Todos os arquivos (*.*)"

OPERATIONS = {
    "trim": {
        "title": "Recortar trecho", "icon": "cut", "tag": "Sem perda",
        "summary": "Escolha o início e o fim sem recomprimir o vídeo.",
        "action": "Recortar",
    },
    "audio": {
        "title": "Extrair áudio", "icon": "media", "tag": "MP3",
        "summary": "Crie uma faixa MP3 a partir de um vídeo ou áudio.",
        "action": "Extrair áudio",
    },
    "remux": {
        "title": "Trocar container", "icon": "media", "tag": "Sem perda",
        "summary": "Converta para MKV sem mexer em imagem ou som.",
        "action": "Criar MKV",
    },
    "compress": {
        "title": "Reduzir tamanho", "icon": "tools", "tag": "H.264",
        "summary": "Crie um MP4 menor, equilibrando tamanho e qualidade.",
        "action": "Comprimir",
    },
    "target_size": {
        "title": "Caber em um limite", "icon": "tools", "tag": "MB",
        "summary": "Comprima para caber no limite do Discord, WhatsApp ou e-mail.",
        "action": "Comprimir para o limite",
    },
    "shorts": {
        "title": "Criar versão vertical", "icon": "media", "tag": "9:16",
        "summary": "Prepare um vídeo vertical para Shorts, Reels ou TikTok.",
        "action": "Criar versão vertical",
    },
    "burn": {
        "title": "Adicionar legendas ao vídeo", "icon": "captions", "tag": "Legenda fixa",
        "summary": "Adicione um arquivo SRT, VTT ou ASS diretamente à imagem do vídeo.",
        "action": "Adicionar legendas",
    },
}


class ToolCard(QAbstractButton):
    """Escolha visual de uma ferramenta, com contexto antes da execução."""

    def __init__(self, operation: str, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.data = OPERATIONS[operation]
        self.setText(self.data["title"])
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(112)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(self.data["summary"])
        self.setAccessibleName(self.data["title"])
        self.setAccessibleDescription(self.data["summary"])
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggled.connect(self.update)
        self.pressed.connect(self.update)
        self.released.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(250, 112)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        active = self.isChecked()
        hovered = self.underMouse()
        fill = theme.qcolor("accent_soft") if active else theme.qcolor(
            "surface_hover" if hovered else "surface")
        border = theme.qcolor("accent" if active else (
            "border_strong" if hovered else "border"))
        painter.setPen(QPen(border, 1.2 if active else 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(rect, theme.RADIUS_CARD, theme.RADIUS_CARD)

        icon_rect = QRectF(14, 14, 34, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qcolor("accent_soft" if not active else "accent"))
        painter.drawRoundedRect(icon_rect, 10, 10)
        icon_tone = "accent" if not active else "on_accent"
        painter.drawPixmap(22, 22, icons.pixmap(self.data["icon"], theme.color(icon_tone), 18))

        title_x = 60
        painter.setFont(theme.headline())
        painter.setPen(QPen(theme.qcolor("text")))
        painter.drawText(QRectF(title_x, 14, self.width() - title_x - 12, 22),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.data["title"])

        painter.setFont(theme.footnote())
        painter.setPen(QPen(theme.qcolor("text_secondary")))
        metrics = QFontMetrics(painter.font())
        summary = metrics.elidedText(self.data["summary"], Qt.TextElideMode.ElideRight,
                                     max(40, self.width() - 28))
        painter.drawText(QRectF(14, 58, self.width() - 28, 20),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), summary)

        painter.setFont(theme.caption())
        painter.setPen(QPen(theme.qcolor("accent_text" if active else "text_tertiary")))
        painter.drawText(QRectF(14, 84, self.width() - 28, 16),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.data["tag"])
        if self.hasFocus():
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(theme.qcolor("accent_text"), 2))
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1),
                                    theme.RADIUS_CARD, theme.RADIUS_CARD)

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class MediaToolsPage(QWidget):
    """Executa uma única tarefa local por vez, sempre fora da thread da UI."""

    taskbar_progress = Signal(float)
    operation_finished = Signal(str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("mediaToolsPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: MediaToolWorker | None = None
        self._operation_key = "trim"
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(16)
        root.addWidget(PageHeader(
            "Ferramentas",
            "Escolha uma tarefa, informe o arquivo e processe. O original nunca é alterado.",
            self))

        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)

        page.add(SectionLabel("1. O que você quer fazer?", self))
        page.add(self._tool_picker())
        page.add(SectionLabel("2. Arquivo de origem", self))
        page.add(self._source_group())
        page.add(SectionLabel("3. Ajustes desta tarefa", self))
        page.add(self._options_group())
        page.add(SectionLabel("4. Onde salvar", self))
        page.add(self._destination_group())
        page.add_stretch()

        root.addWidget(self._action_bar())
        self._tool_cards["trim"].setChecked(True)
        self._operation_changed("trim")

    def _tool_picker(self) -> QWidget:
        host = QWidget(self)
        layout = QGridLayout(host)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(10)
        self.operation_buttons = QButtonGroup(self)
        self.operation_buttons.setExclusive(True)
        self._tool_cards: dict[str, ToolCard] = {}
        for index, operation in enumerate(OPERATIONS):
            card = ToolCard(operation, host)
            self._tool_cards[operation] = card
            self.operation_buttons.addButton(card)
            card.toggled.connect(
                lambda checked, value=operation: self._operation_changed(value) if checked else None)
            layout.addWidget(card, index // 2, index % 2)
        return host

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou áudio de origem", group)
        self.source_edit.editingFinished.connect(self._suggest_destination)
        source_button = Button("Escolher arquivo", "folder", "secondary", group)
        source_button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Arquivo de origem",
            "Escolha o arquivo que será processado. A versão original fica intacta.",
            self.source_edit, source_button))
        return group

    def _options_group(self) -> InsetGroup:
        group = InsetGroup(self)
        intro = QWidget(group)
        intro_layout = QVBoxLayout(intro)
        intro_layout.setContentsMargins(16, 12, 16, 14)
        intro_layout.setSpacing(4)
        self.options_title = Headline("Ajustes", intro)
        self.options_summary = Muted("", intro)
        intro_layout.addWidget(self.options_title)
        intro_layout.addWidget(self.options_summary)
        group.add_row(intro)

        self.start_edit = TextField("início 00:01:30", group)
        self.start_edit.setFixedWidth(150)
        self.end_edit = TextField("fim 00:04:00", group)
        self.end_edit.setFixedWidth(150)
        times = QWidget(group)
        times_row = QHBoxLayout(times)
        times_row.setContentsMargins(0, 0, 0, 0)
        times_row.setSpacing(8)
        times_row.addWidget(self.start_edit)
        times_row.addWidget(self.end_edit)
        times_row.addStretch(1)
        self.trim_row = SettingRow(
            "Início e fim", "Use mm:ss ou hh:mm:ss. O corte sem recompressão pode cair "
            "no quadro-chave mais próximo.", times, group)
        group.add_row(self.trim_row)

        self.subtitle_edit = TextField("Arquivo .srt, .vtt ou .ass", group)
        subtitle_button = Button("Escolher legenda", "document", "secondary", group)
        subtitle_button.clicked.connect(self._choose_subtitles)
        self.subtitle_row = self._path_row(
            group, "Arquivo de legenda",
            "A legenda será incorporada na imagem do vídeo e não poderá ser desligada no player.",
            self.subtitle_edit, subtitle_button)
        group.add_row(self.subtitle_row)

        self.target_combo = Select(group)
        for label, value in (("8 MB — e-mail pequeno", 8), ("10 MB — Discord (grátis)", 10),
                             ("16 MB — WhatsApp (vídeo)", 16), ("25 MB — e-mail / Discord antigo", 25),
                             ("50 MB — Discord Nitro Basic", 50), ("100 MB", 100)):
            self.target_combo.addItem(label, userData=value)
        self.target_combo.setCurrentIndex(1)
        self.target_row = SettingRow(
            "Tamanho máximo", "A resolução baixa sozinha quando o limite é apertado.",
            self.target_combo, group)
        group.add_row(self.target_row)

        self.blur_switch = Switch(group)
        self.blur_switch.setChecked(True)
        self.blur_row = SettingRow(
            "Fundo desfocado", "Preenche as laterais com o próprio vídeo desfocado "
            "em vez de barras pretas.", self.blur_switch, group)
        group.add_row(self.blur_row)
        return group

    def _destination_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.destination_edit = TextField(
            "A saída será sugerida ao escolher o arquivo", group)
        destination_button = Button("Escolher local", "save", "secondary", group)
        destination_button.clicked.connect(self._choose_destination)
        group.add_row(self._path_row(
            group, "Salvar resultado", "Você pode alterar nome, pasta ou extensão antes de processar.",
            self.destination_edit, destination_button))
        return group

    @staticmethod
    def _path_row(parent, title: str, subtitle: str, field: TextField,
                  button: Button) -> QWidget:
        row = QWidget(parent)
        column = QVBoxLayout(row)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Headline(title, row))
        if subtitle:
            column.addWidget(Muted(subtitle, row))
        line = QHBoxLayout()
        line.setSpacing(10)
        line.addWidget(field, 1)
        line.addWidget(button)
        column.addLayout(line)
        return row

    def _action_bar(self) -> QWidget:
        bar = QWidget(self)
        column = QVBoxLayout(bar)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(0)
        column.addWidget(Divider(bar))

        self.progress_host = QWidget(bar)
        progress_row = QHBoxLayout(self.progress_host)
        progress_row.setContentsMargins(0, 0, 0, 0)
        progress_row.setSpacing(10)
        self.progress = ProgressBar(self.progress_host)
        self.progress_percent = Muted("0%", self.progress_host)
        self.progress_percent.setFixedWidth(42)
        self.progress_percent.setWordWrap(False)
        progress_row.addWidget(self.progress, 1)
        progress_row.addWidget(self.progress_percent)
        self.progress_host.hide()
        column.addWidget(self.progress_host)

        row = QHBoxLayout()
        row.setContentsMargins(0, 14, 0, 16)
        row.setSpacing(10)
        self.status = Muted("Escolha uma tarefa e selecione um arquivo para começar.", bar)
        row.addWidget(self.status, 1)

        self.cancel_button = Button("Cancelar", "close", "ghost", bar)
        self.cancel_button.setMinimumHeight(42)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.run_button = PrimaryButton("Processar", "sparkle", bar)
        self.run_button.setMinimumHeight(42)
        self.run_button.setMinimumWidth(172)
        self.run_button.clicked.connect(self._run)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        column.addLayout(row)
        return bar

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)
        self._suggest_destination()

    def _operation(self) -> str:
        return self._operation_key

    def _operation_changed(self, operation: str) -> None:
        self._operation_key = operation
        data = OPERATIONS[operation]
        self.options_title.setText(data["title"])
        self.options_summary.setText(data["summary"])
        self.trim_row.setVisible(operation == "trim")
        self.subtitle_row.setVisible(operation == "burn")
        self.target_row.setVisible(operation == "target_size")
        self.blur_row.setVisible(operation == "shorts")
        self.run_button.setText(data["action"])
        self._suggest_destination()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar mídia", "", MEDIA_FILTER)
        if path:
            self.source_edit.setText(path)
            self._suggest_destination()

    def _choose_subtitles(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar legenda", "", SUBTITLE_FILTER)
        if path:
            self.subtitle_edit.setText(path)

    def _suggest_destination(self) -> None:
        source = Path(self.source_edit.text().strip())
        if source.is_file():
            self.destination_edit.setText(str(default_destination(source, self._operation())))

    def _choose_destination(self) -> None:
        suggested = self.destination_edit.text().strip()
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar resultado", suggested,
            "Arquivo MP4 (*.mp4);;Arquivo MKV (*.mkv);;Arquivo MP3 (*.mp3);;Todos os arquivos (*.*)",
        )
        if path:
            self.destination_edit.setText(path)

    def _run(self) -> None:
        if self.worker and self.worker.isRunning():
            return
        if not self.toolchain:
            self._show_error("As dependências ainda não estão prontas.")
            return
        source = Path(self.source_edit.text().strip())
        destination_text = self.destination_edit.text().strip()
        if not destination_text:
            self._show_error("Escolha onde salvar o resultado.")
            return
        destination = available_destination(Path(destination_text))
        self.destination_edit.setText(str(destination))
        options = MediaToolOptions(
            source=source,
            destination=destination,
            operation=self._operation(),
            start=self.start_edit.text().strip(),
            end=self.end_edit.text().strip(),
            subtitles=Path(self.subtitle_edit.text().strip()) if self.subtitle_edit.text().strip() else None,
            target_mb=int(self.target_combo.currentData() or 25),
            shorts_blur=self.blur_switch.isChecked(),
        )
        worker = MediaToolWorker(options, self.toolchain, self)
        self.worker = worker
        worker.progress.connect(self.status.setText)
        worker.progress_value.connect(self._set_progress)
        worker.finished_ok.connect(self._done)
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_worker(w))
        worker.start()
        self._set_progress(0)
        self.progress_host.show()
        self.run_button.setEnabled(False)
        self.cancel_button.show()
        self.status.setText(f"Preparando: {OPERATIONS[self._operation()]['title'].lower()}…")

    def _clear_worker(self, worker: MediaToolWorker) -> None:
        if self.worker is worker:
            self.worker = None

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelando…")

    def cancel_current(self) -> None:
        self._cancel()

    def _done(self, output: str) -> None:
        self._set_progress(100)
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.status.setText(f"Concluído: {Path(output).name}")
        self.operation_finished.emit(output)
        Toast.success("Processamento concluído", f"Arquivo salvo em {output}",
                      parent=self.window(), duration=7000)

    def _failed(self, message: str) -> None:
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self.run_button.setEnabled(True)
        self.cancel_button.hide()
        self.status.setText(message)
        self._show_error(message)

    def _set_progress(self, value: int) -> None:
        percent = max(0, min(100, int(value)))
        self.progress.setValue(percent)
        self.progress_percent.setText(f"{percent}%")
        self.taskbar_progress.emit(float(percent))

    def _show_error(self, message: str) -> None:
        title = ("Não foi possível adicionar as legendas"
                 if self._operation() == "burn" else "Não foi possível processar a mídia")
        Toast.error(title, message,
                    parent=self.window(), duration=8000)

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.worker.wait(3000)
