"""Cortes verticais (1080x1920) com legenda palavra a palavra e título animado."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, QSize, QUrl, Qt, Signal
from PySide6.QtGui import (QColor, QDesktopServices, QFont, QFontDatabase, QFontMetricsF,
                           QLinearGradient, QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import (QAbstractButton, QColorDialog, QFileDialog, QGridLayout,
                               QHBoxLayout, QVBoxLayout, QWidget)

from ..clips import (HEIGHT, HIGHLIGHT_HEX, CaptionStyle, ClipError, ClipOptions,
                     format_clock, is_light, is_url, make_range)
from ..workers import ClipWorker
from . import theme
from .components import (Button, Divider, Headline, IconButton, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ProgressBar, ScrollColumn, SectionLabel, Select,
                         SettingRow, Stepper, Switch, TextField, Toast)
from .i18n import tr
from .media_tools_page import MEDIA_FILTER
from .transcription_page import LANGUAGES, MODELS

MAX_CLIPS = 20
PAUSES = [("0,4 s — ritmo acelerado", 0.4), ("0,6 s — recomendado", 0.6),
          ("0,8 s — mais natural", 0.8), ("1,2 s — só pausas longas", 1.2)]
FRAMINGS = [("Seguir a pessoa — automático", "track"),
            ("Fundo desfocado — vídeo inteiro", "blur"),
            ("Cortar no centro — tela cheia", "crop")]
FRAMING_HINTS = {
    "track": "Aproxima e acompanha quem está em cena, como o reenquadrar do CapCut. Procura "
             "rostos e, sem rosto, segue o movimento. Vídeos já verticais ficam como estão.",
    "blur": "Mostra o quadro todo, com o próprio vídeo desfocado atrás.",
    "crop": "Preenche a tela com o centro do vídeo; as laterais ficam de fora.",
}
SIZES = [("Pequena", 64), ("Média", 76), ("Grande", 88), ("Muito grande", 104),
         ("Enorme", 124)]
POSITION_MIN, POSITION_MAX = 8, 92
# Fontes que ficam bem em legenda de vídeo curto; entram primeiro se estiverem instaladas.
PREFERRED_FONTS = ("Arial", "Arial Black", "Impact", "Montserrat", "Montserrat Black",
                   "Poppins", "Bebas Neue", "Anton", "Roboto", "Segoe UI", "Verdana",
                   "Tahoma", "Trebuchet MS", "Helvetica", "Georgia")
PREVIEW_WORDS = ("essa", "é", "a", "sua", "legenda")


def valid_hex(value, fallback: str) -> str:
    text = value.strip() if isinstance(value, str) else ""
    return text.upper() if re.fullmatch(r"#[0-9A-Fa-f]{6}", text) else fallback


def caption_fonts(current: str = "") -> list[str]:
    """Fontes instaladas, com as boas para legenda no topo e a escolha salva sempre presente."""
    installed = [family for family in QFontDatabase.families()
                 if not family.startswith("@") and QFontDatabase.writingSystems(family)]
    available = set(installed)
    ordered = [family for family in PREFERRED_FONTS if family in available]
    if current and current not in ordered:
        ordered.insert(0, current)
    if not ordered:
        ordered.append("Arial")
    return ordered + sorted((f for f in installed if f not in ordered), key=str.casefold)


class ColorButton(QAbstractButton):
    """Amostra de cor clicável; abre o seletor do sistema."""

    color_changed = Signal(str)

    def __init__(self, value: str, title: str, parent=None):
        super().__init__(parent)
        self._color = valid_hex(value, "#FFFFFF")
        self._title = title
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tr(title))
        self.setAccessibleName(tr(title))
        self.clicked.connect(self._choose)

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        return QSize(34, 34)

    def color(self) -> str:
        return self._color

    def set_color(self, value: str) -> None:
        value = valid_hex(value, self._color)
        if value != self._color:
            self._color = value
            self.update()
            self.color_changed.emit(value)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._color), self.window(), tr(self._title))
        if chosen.isValid():
            self.set_color(chosen.name().upper())

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        border = theme.qcolor("accent" if self.hasFocus() or self.underMouse()
                              else "border_strong")
        painter.setPen(QPen(border, 2 if self.hasFocus() else 1.2))
        painter.setBrush(QColor(self._color))
        painter.drawRoundedRect(rect, theme.RADIUS_SMALL, theme.RADIUS_SMALL)

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class CaptionPreview(QWidget):
    """Tela de celular em miniatura: mostra a legenda como vai sair e aceita arrastar."""

    position_changed = Signal(int)
    PREVIEW_WIDTH = 162

    def __init__(self, parent=None):
        super().__init__(parent)
        self.style = CaptionStyle()
        self.setFixedSize(self.PREVIEW_WIDTH, round(self.PREVIEW_WIDTH * 16 / 9))
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(tr("Arraste para cima ou para baixo para posicionar a legenda"))
        self.setAccessibleName(tr("Prévia da legenda"))

    def set_style(self, style: CaptionStyle) -> None:
        self.style = style.normalized()
        self.update()

    def _move_to(self, y: float) -> None:
        value = round(y / max(1, self.height()) * 100)
        self.position_changed.emit(max(POSITION_MIN, min(POSITION_MAX, value)))

    def mousePressEvent(self, event):  # noqa: N802 - assinatura do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_to(event.position().y())

    def mouseMoveEvent(self, event):  # noqa: N802 - assinatura do Qt
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_to(event.position().y())

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        style = self.style
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        width, height = self.width(), self.height()
        frame = QRectF(0.5, 0.5, width - 1, height - 1)
        clip = QPainterPath()
        clip.addRoundedRect(frame, 14, 14)
        painter.setClipPath(clip)
        background = QLinearGradient(0, 0, 0, height)
        background.setColorAt(0, QColor("#4A5568"))
        background.setColorAt(1, QColor("#1A202C"))
        painter.fillRect(frame, background)
        # Silhueta de quem fala, só para dar escala.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 38))
        painter.drawEllipse(QPointF(width / 2, height * 0.40), width * 0.15, width * 0.15)
        painter.drawRoundedRect(QRectF(width * 0.22, height * 0.50, width * 0.56, height * 0.6),
                                width * 0.2, width * 0.2)

        scale = height / HEIGHT
        family = QFont(style.font)
        family.setBold(True)
        # Título no topo, na caixa da cor de destaque.
        title_font = QFont(family)
        title_font.setPixelSize(max(6, round(style.size * 0.84 * scale)))
        painter.setFont(title_font)
        metrics = QFontMetricsF(title_font)
        title = tr("Título do corte")
        box_width = metrics.horizontalAdvance(title) + 12
        box = QRectF((width - box_width) / 2, 300 * scale, box_width, metrics.height() + 6)
        painter.setBrush(QColor(style.highlight_color))
        painter.drawRect(box)
        dark_text = is_light(style.highlight_color)   # mesma regra do ASS
        painter.setPen(QColor("#141414") if dark_text else QColor("#FFFFFF"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, title)

        # Legenda: grupo de palavras com a segunda (a "falada") em destaque.
        words = [w.upper() if style.uppercase else w for w in PREVIEW_WORDS[:style.words]]
        active = min(1, len(words) - 1)
        base = QFont(family)
        base.setPixelSize(max(6, round(style.size * scale)))
        big = QFont(family)
        big.setPixelSize(max(6, round(style.size * 1.12 * scale)))
        space = QFontMetricsF(base).horizontalAdvance(" ")
        advances = [QFontMetricsF(big if i == active else base).horizontalAdvance(word)
                    for i, word in enumerate(words)]
        x = (width - sum(advances) - space * (len(words) - 1)) / 2
        baseline = height * style.position / 100 + QFontMetricsF(base).ascent() / 2 - 1
        outline = QPen(QColor("#000000"), max(1.5, style.size / 12 * scale * 2))
        outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        for index, word in enumerate(words):
            path = QPainterPath()
            path.addText(QPointF(x, baseline), big if index == active else base, word)
            painter.strokePath(path, outline)
            painter.fillPath(path, QColor(style.highlight_color if index == active
                                          else style.text_color))
            x += advances[index] + space
        painter.setClipping(False)
        painter.setPen(QPen(theme.qcolor("border_strong"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, 14, 14)


class ClipRow(QWidget):
    """Uma linha da lista de cortes: início, fim, título e remover."""

    removed = Signal(object)
    changed = Signal()

    def __init__(self, number: int, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.number = Muted("", self)
        self.number.setFixedWidth(22)
        self.start = TextField("início 01:30", self)
        self.start.setFixedWidth(118)
        self.end = TextField("fim 02:15", self)
        self.end.setFixedWidth(118)
        self.title = TextField("Título animado (opcional)", self)
        self.remove = IconButton("trash", "Remover corte", self)
        self.remove.clicked.connect(lambda: self.removed.emit(self))
        for field in (self.start, self.end):
            field.textChanged.connect(self.changed)
        layout.addWidget(self.number)
        layout.addWidget(self.start)
        layout.addWidget(self.end)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.remove)
        self.set_number(number)

    def set_number(self, number: int) -> None:
        self.number.setText(f"{number}.")

    def is_filled(self) -> bool:
        return bool(self.start.text().strip() and self.end.text().strip())


class ClipsPage(QWidget):
    """Gera um ou vários cortes por vez, sempre fora da thread da UI."""

    taskbar_progress = Signal(float)
    operation_finished = Signal(str)
    # Para o histórico: arquivo do corte, vídeo de origem, título e intervalo.
    clip_finished = Signal(str, str, str, str)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setObjectName("clipsPage")
        self.cfg = cfg
        self.toolchain = None
        self.worker: ClipWorker | None = None
        self.rows: list[ClipRow] = []
        self._outputs: list[str] = []
        self._build_ui()

    # ------------------------------------------------------------------ interface
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 20, 28, 0)
        root.setSpacing(0)
        page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)
        page.add(PageHeader(
            "Cortes",
            "Gere vídeos verticais com legenda palavra a palavra, sem as pausas.",
            self))
        page.add(self._source_group())
        page.add(SectionLabel("Cortes", self))
        page.add(self._ranges_group())
        page.add(SectionLabel("Enquadramento", self))
        page.add(self._style_group())
        page.add(SectionLabel("Legenda", self))
        page.add(self._caption_group())
        page.add(SectionLabel("Transcrição", self))
        page.add(self._transcription_group())
        page.add(self._destination_group())
        page.add_stretch()
        root.addWidget(self._action_bar())
        self._add_row()

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou link do YouTube", group)
        self.source_edit.textChanged.connect(self._source_changed)
        button = Button("Escolher arquivo", "folder", "secondary", group)
        button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Vídeo de origem",
            "Use um arquivo do computador ou cole um link: só os trechos escolhidos são "
            "baixados.", self.source_edit, button))
        return group

    def _ranges_group(self) -> InsetGroup:
        group = InsetGroup(self)
        host = QWidget(group)
        column = QVBoxLayout(host)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        column.addWidget(Muted(
            "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título aparece "
            "animado nos primeiros segundos.", host))
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        column.addLayout(self.rows_layout)
        add_line = QHBoxLayout()
        self.add_button = Button("Adicionar corte", "plus", "secondary", host)
        self.add_button.clicked.connect(lambda: self._add_row(focus=True))
        add_line.addWidget(self.add_button)
        add_line.addStretch(1)
        column.addLayout(add_line)
        group.add_row(host)
        return group

    def _style_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.framing_combo = Select(group)
        for label, value in FRAMINGS:
            self.framing_combo.addItem(label, userData=value)
        self.framing_combo.setCurrentIndex(max(0, self.framing_combo.findData(
            getattr(self.cfg, "clips_framing", "blur"))))
        self.framing_combo.currentIndexChanged.connect(self._framing_changed)
        # O texto de apoio muda com a opção escolhida (_framing_changed).
        self.framing_row = SettingRow(
            "Enquadramento 9:16", " ", self.framing_combo, group)
        group.add_row(self.framing_row)

        self.pauses_switch = Switch(group)
        self.pauses_switch.setChecked(bool(getattr(self.cfg, "clips_remove_pauses", True)))
        self.pauses_switch.toggled.connect(self._pauses_toggled)
        group.add_row(SettingRow(
            "Remover pausas",
            "Corta os silêncios entre as falas usando o tempo de cada palavra.",
            self.pauses_switch, group))
        self.pause_combo = Select(group)
        for label, value in PAUSES:
            self.pause_combo.addItem(label, userData=value)
        self.pause_combo.setCurrentIndex(max(0, self.pause_combo.findData(
            float(getattr(self.cfg, "clips_min_pause", 0.6)))))
        self.pause_combo.setEnabled(self.pauses_switch.isChecked())
        self.pause_combo.currentIndexChanged.connect(self._save_style)
        self.pause_row = group.add_row(SettingRow(
            "Pausa mínima", "Silêncios menores que isso ficam no vídeo.", self.pause_combo, group))
        self._framing_changed()
        return group

    def _caption_group(self) -> InsetGroup:
        group = InsetGroup(self)
        style = self._saved_style()
        host = QWidget(group)
        line = QHBoxLayout(host)
        line.setContentsMargins(16, 14, 16, 14)
        line.setSpacing(22)
        self.preview = CaptionPreview(host)
        self.preview.position_changed.connect(self._preview_moved)
        line.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)

        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.setColumnStretch(1, 1)

        self.font_combo = Select(host)
        for family in caption_fonts(style.font):
            self.font_combo.addItem(family, userData=family)
        self.font_combo.setCurrentIndex(max(0, self.font_combo.findData(style.font)))
        self.size_combo = Select(host)
        for label, value in SIZES:
            self.size_combo.addItem(label, userData=value)
        if self.size_combo.findData(style.size) < 0:
            self.size_combo.addItem(f"{style.size} px", userData=style.size)
        self.size_combo.setCurrentIndex(self.size_combo.findData(style.size))
        self.text_color = ColorButton(style.text_color, "Cor do texto", host)
        self.highlight_color = ColorButton(style.highlight_color, "Cor da palavra falada", host)
        colors = QHBoxLayout()
        colors.setSpacing(8)
        colors.addWidget(self.text_color)
        colors.addWidget(Muted("Texto", host, wrap=False))
        colors.addSpacing(10)
        colors.addWidget(self.highlight_color)
        colors.addWidget(Muted("Palavra falada", host, wrap=False))
        colors.addStretch(1)
        self.position_stepper = Stepper(host)
        self.position_stepper.setRange(POSITION_MIN, POSITION_MAX)
        self.position_stepper.setValue(style.position)
        position_line = QHBoxLayout()
        position_line.setSpacing(10)
        position_line.addWidget(self.position_stepper)
        position_line.addWidget(Muted("% da altura; arraste na prévia", host, wrap=False))
        position_line.addStretch(1)
        self.words_combo = Select(host)
        for count in range(1, 5):
            self.words_combo.addItem(
                tr("1 palavra") if count == 1 else f"{count} {tr('palavras')}", userData=count)
        self.words_combo.setCurrentIndex(max(0, self.words_combo.findData(style.words)))
        self.upper_switch = Switch(host)
        self.upper_switch.setChecked(style.uppercase)

        rows = [("Fonte", self.font_combo), ("Tamanho", self.size_combo), ("Cores", colors),
                ("Altura", position_line), ("Palavras", self.words_combo),
                ("Maiúsculas", self.upper_switch)]
        for index, (label, control) in enumerate(rows):
            form.addWidget(Headline(label, host), index, 0)
            if isinstance(control, QWidget):
                form.addWidget(control, index, 1, Qt.AlignmentFlag.AlignLeft)
            else:
                form.addLayout(control, index, 1)
        column = QVBoxLayout()
        column.setSpacing(12)
        column.addLayout(form)
        column.addWidget(Muted(
            "A fonte precisa estar instalada no computador. A prévia é aproximada; o título "
            "usa a cor da palavra falada.", host))
        column.addStretch(1)
        line.addLayout(column, 1)
        group.add_row(host)

        for combo in (self.font_combo, self.size_combo, self.words_combo):
            combo.currentIndexChanged.connect(self._save_style)
        for button in (self.text_color, self.highlight_color):
            button.color_changed.connect(self._save_style)
        self.upper_switch.toggled.connect(self._save_style)
        self.position_stepper.valueChanged.connect(self._save_style)
        self.preview.set_style(style)
        return group

    def _transcription_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.language_combo = Select(group)
        for label, value in LANGUAGES:
            self.language_combo.addItem(label, userData=value)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(
            getattr(self.cfg, "transcription_language", "pt"))))
        group.add_row(SettingRow("Idioma da fala", "", self.language_combo, group))
        self.model_combo = Select(group)
        for label, value in MODELS:
            self.model_combo.addItem(label, userData=value)
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(
            getattr(self.cfg, "transcription_model", "medium"))))
        group.add_row(SettingRow(
            "Modelo Whisper",
            "O mesmo da aba Legendar. Usa a GPU NVIDIA quando disponível e a CPU nos demais "
            "casos.", self.model_combo, group))
        return group

    def _destination_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.output_edit = TextField("Pasta onde os cortes serão salvos", group)
        self.output_edit.textChanged.connect(self._update_run_enabled)
        button = Button("Escolher pasta", "folder", "secondary", group)
        button.clicked.connect(self._choose_output)
        group.add_row(self._path_row(
            group, "Salvar cortes em",
            "Cada corte vira um MP4 1080x1920 separado. O original nunca é alterado.",
            self.output_edit, button))
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
        self.status = Muted("Escolha um vídeo e informe os cortes para começar.", bar)
        row.addWidget(self.status, 1)
        self.open_button = Button("Abrir pasta", "folder", "ghost", bar)
        self.open_button.setMinimumHeight(42)
        self.open_button.clicked.connect(self._open_output)
        self.open_button.hide()
        self.cancel_button = Button("Cancelar", "close", "ghost", bar)
        self.cancel_button.setMinimumHeight(42)
        self.cancel_button.clicked.connect(self._cancel)
        self.cancel_button.hide()
        self.run_button = PrimaryButton("Criar cortes", "sparkle", bar)
        self.run_button.setMinimumHeight(42)
        self.run_button.setMinimumWidth(172)
        self.run_button.clicked.connect(self._run)
        self.run_button.setEnabled(False)
        row.addWidget(self.open_button)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        column.addLayout(row)
        return bar

    # ------------------------------------------------------------------ lista de cortes
    def _add_row(self, focus: bool = False) -> None:
        if len(self.rows) >= MAX_CLIPS:
            Toast.info("Limite de cortes", f"Crie até {MAX_CLIPS} cortes por vez.",
                       parent=self.window())
            return
        row = ClipRow(len(self.rows) + 1, self)
        row.removed.connect(self._remove_row)
        row.changed.connect(self._update_run_enabled)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self._refresh_rows()
        if focus:
            row.start.setFocus(Qt.FocusReason.OtherFocusReason)

    def _remove_row(self, row: ClipRow) -> None:
        if len(self.rows) == 1:
            for field in (row.start, row.end, row.title):
                field.clear()
            return
        self.rows.remove(row)
        self.rows_layout.removeWidget(row)
        row.deleteLater()
        self._refresh_rows()

    def _refresh_rows(self) -> None:
        for number, row in enumerate(self.rows, start=1):
            row.set_number(number)
        self.add_button.setEnabled(len(self.rows) < MAX_CLIPS)
        self._update_run_enabled()

    def _pauses_toggled(self, checked: bool) -> None:
        self.pause_combo.setEnabled(checked)
        self._save_style()

    def _framing_changed(self, *_args) -> None:
        value = str(self.framing_combo.currentData() or "blur")
        self.framing_row.subtitle.setText(tr(FRAMING_HINTS.get(value, "")))
        self._save_style()

    # ------------------------------------------------------------------ estilo da legenda
    def _saved_style(self) -> CaptionStyle:
        cfg = self.cfg
        return CaptionStyle(
            font=str(getattr(cfg, "clips_font", "Arial")),
            size=int(getattr(cfg, "clips_font_size", 88)),
            text_color=valid_hex(getattr(cfg, "clips_text_color", ""), "#FFFFFF"),
            highlight_color=valid_hex(getattr(cfg, "clips_highlight_color", ""), HIGHLIGHT_HEX),
            position=int(getattr(cfg, "clips_position", 70)),
            words=int(getattr(cfg, "clips_words", 3)),
            uppercase=bool(getattr(cfg, "clips_uppercase", True)),
        ).normalized()

    def caption_style(self) -> CaptionStyle:
        return CaptionStyle(
            font=str(self.font_combo.currentData() or "Arial"),
            size=int(self.size_combo.currentData() or 88),
            text_color=self.text_color.color(),
            highlight_color=self.highlight_color.color(),
            position=self.position_stepper.value(),
            words=int(self.words_combo.currentData() or 3),
            uppercase=self.upper_switch.isChecked(),
        ).normalized()

    def _preview_moved(self, value: int) -> None:
        self.position_stepper.setValue(value)

    def _save_style(self, *_args) -> None:
        """Toda mudança vai para a prévia e para as Configurações (vale na próxima abertura)."""
        if not hasattr(self, "upper_switch"):
            return   # ainda montando a página
        style = self.caption_style()
        self.preview.set_style(style)
        cfg = self.cfg
        cfg.clips_framing = str(self.framing_combo.currentData() or "blur")
        cfg.clips_remove_pauses = self.pauses_switch.isChecked()
        cfg.clips_min_pause = float(self.pause_combo.currentData() or 0.6)
        cfg.clips_font = style.font
        cfg.clips_font_size = style.size
        cfg.clips_text_color = style.text_color
        cfg.clips_highlight_color = style.highlight_color
        cfg.clips_position = style.position
        cfg.clips_words = style.words
        cfg.clips_uppercase = style.uppercase
        cfg.save()

    # ------------------------------------------------------------------ origem e destino
    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)

    def _source(self) -> str:
        return self.source_edit.text().strip().strip('"')

    def _source_changed(self, *_args) -> None:
        source = self._source()
        if not self.output_edit.text().strip():
            if is_url(source):
                self.output_edit.setText(str(getattr(self.cfg, "download_dir", "") or ""))
            elif source and Path(source).is_file():
                self.output_edit.setText(str(Path(source).parent))
        self._update_run_enabled()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar vídeo", "", MEDIA_FILTER)
        if path:
            self.output_edit.clear()
            self.source_edit.setText(path)

    def _choose_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Salvar cortes em",
                                                self.output_edit.text().strip())
        if path:
            self.output_edit.setText(path)

    def _open_output(self) -> None:
        folder = Path(self._outputs[-1]).parent if self._outputs else Path(
            self.output_edit.text().strip())
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _update_run_enabled(self, *_args) -> None:
        if not hasattr(self, "run_button"):
            return
        source = self._source()
        valid_source = is_url(source) or (bool(source) and Path(source).is_file())
        self.run_button.setEnabled(
            valid_source and bool(self.output_edit.text().strip())
            and any(row.is_filled() for row in self.rows)
            and not self.has_active_work())

    # ------------------------------------------------------------------ execução
    def _options(self) -> ClipOptions:
        ranges = []
        for number, row in enumerate(self.rows, start=1):
            if not (row.start.text().strip() or row.end.text().strip()):
                continue
            try:
                ranges.append(make_range(row.start.text(), row.end.text(), row.title.text()))
            except ClipError as exc:
                raise ClipError(f"{tr('Corte')} {number}: {tr(str(exc))}") from exc
        if not ranges:
            raise ClipError("Adicione pelo menos um corte com início e fim.")
        return ClipOptions(
            source=self._source(),
            ranges=tuple(ranges),
            output_dir=Path(self.output_edit.text().strip()),
            framing=str(self.framing_combo.currentData() or "blur"),
            remove_pauses=self.pauses_switch.isChecked(),
            min_pause=float(self.pause_combo.currentData() or 0.6),
            style=self.caption_style(),
            language=str(self.language_combo.currentData() or "pt"),
            model_size=str(self.model_combo.currentData() or "medium"),
        )

    def _run(self) -> None:
        if self.has_active_work():
            return
        if not self.toolchain:
            self._show_error("As dependências ainda não estão prontas.")
            return
        try:
            options = self._options()
        except ClipError as exc:
            self._show_error(str(exc))
            return
        self._outputs = []
        self._running = options
        worker = ClipWorker(options, self.toolchain, self.cfg, self)
        self.worker = worker
        worker.progress.connect(self.status.setText)
        worker.progress_value.connect(self._set_progress)
        worker.clip_done.connect(self._clip_done)
        worker.finished_ok.connect(self._done)
        worker.failed.connect(self._failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_worker(w))
        worker.start()
        self._set_progress(0)
        self.progress_host.show()
        self.open_button.hide()
        self.run_button.setEnabled(False)
        self.cancel_button.show()
        count = len(options.ranges)
        self.status.setText(tr("Preparando 1 corte…") if count == 1
                            else f"{tr('Preparando')} {count} {tr('cortes')}…")

    def _clear_worker(self, worker: ClipWorker) -> None:
        if self.worker is worker:
            self.worker = None
            self._update_run_enabled()

    def _cancel(self) -> None:
        if self.has_active_work():
            assert self.worker is not None
            self.worker.cancel()
            self.status.setText(tr("Cancelando…"))

    def has_active_work(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def cancel_current(self) -> None:
        self._cancel()

    def _clip_done(self, path: str) -> None:
        self._outputs.append(path)
        self.open_button.show()
        options = getattr(self, "_running", None)
        index = len(self._outputs) - 1
        if options is not None and index < len(options.ranges):
            clip = options.ranges[index]
            span = f"{format_clock(clip.start)}–{format_clock(clip.end)}"
            self.clip_finished.emit(path, options.source, clip.title, span)

    def _finish_ui(self) -> None:
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self.cancel_button.hide()
        self.open_button.setVisible(bool(self._outputs))
        self._update_run_enabled()

    def _done(self, outputs: list) -> None:
        self._set_progress(100)
        self._finish_ui()
        count = len(outputs)
        folder = str(Path(outputs[-1]).parent) if outputs else ""
        self.status.setText(f"{tr('Cortes prontos')}: {count} · {folder}")
        if outputs:
            self.operation_finished.emit(outputs[-1])
        Toast.success("Cortes concluídos",
                      f"{count} {tr('corte(s) salvos em')} {folder}",
                      parent=self.window(), duration=7000)

    def _failed(self, message: str) -> None:
        self._finish_ui()
        self.status.setText(message)
        self._show_error(message)

    def _set_progress(self, value: int) -> None:
        percent = max(0, min(100, int(value)))
        self.progress.setValue(percent)
        self.progress_percent.setText(f"{percent}%")
        self.taskbar_progress.emit(float(percent))

    def _show_error(self, message: str) -> None:
        Toast.error("Não foi possível criar os cortes", message,
                    parent=self.window(), duration=8000)

    def shutdown(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            if not self.worker.wait(5000):
                self.worker.force_stop()
                self.worker.wait(3000)
