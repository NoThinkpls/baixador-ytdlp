"""Cortes verticais (1080x1920) com legenda palavra a palavra e título animado ou fixo."""
from __future__ import annotations

import contextlib
import re
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, QThread, QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QColor, QDesktopServices, QFontDatabase, QImage, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QApplication, QColorDialog, QFileDialog,
                               QGridLayout, QHBoxLayout, QVBoxLayout, QWidget)

from ..clips import (BANNER_CAPTION_MIN, HIGHLIGHT_HEX, TITLE_MAX, TITLE_MIN, CaptionStyle,
                     ClipError, ClipOptions, format_clock, is_url, make_range, parse_time)
from ..effects import Marker
from ..plano_ia import markers_text, parse_look, parse_plan
from ..processes import CREATE_NO_WINDOW
from ..workers import ClipWorker
from . import theme
from .clip_preview import (POSITION_MAX, POSITION_MIN, CaptionPreview, ChoicePicker,
                           StickyRail)
from .components import (Button, Divider, Headline, IconButton, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ProgressBar, ScrollColumn, SectionLabel, Select,
                         SettingRow, Stepper, Switch, TextField, Toast)
from .i18n import tr
from .transcription_page import LANGUAGES, MODELS

MAX_CLIPS = 20
PAUSES = [("0,4 s — ritmo acelerado", 0.4), ("0,6 s — recomendado", 0.6),
          ("0,8 s — mais natural", 0.8), ("1,2 s — só pausas longas", 1.2)]
# (nome, complemento, valor, o que muda na miniatura)
FRAMINGS = [("Seguir a pessoa", "automático", "track", {"framing": "track"}),
            ("Fundo desfocado", "vídeo inteiro", "blur", {"framing": "blur"}),
            ("Cortar no centro", "tela cheia", "crop", {"framing": "crop"})]
FRAMING_HINTS = {
    "track": "Aproxima e acompanha quem está falando, como o reenquadrar do CapCut. Procura "
             "rostos e, sem rosto, segue o movimento. Vídeos já verticais ficam como estão.",
    "blur": "Mostra o quadro todo, com o próprio vídeo desfocado atrás.",
    "crop": "Preenche a tela com o centro do vídeo; as laterais ficam de fora.",
}
TITLE_MODES = [("Título animado", "entra e some", "animated", {"banner": False}),
               ("Título fixo no topo", "faixa com cartão", "banner", {"banner": True})]
TITLE_HINTS = {
    "animated": "O título de cada corte entra com um pulo e some depois do tempo escolhido.",
    "banner": "Uma faixa escura no alto com o título num cartão na cor de destaque, do começo "
              "ao fim; o vídeo fica embaixo, como nos canais de cortes de podcast.",
}
RANGES_HINTS = {
    "animated": "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título aparece "
                "animado nos primeiros segundos.",
    "banner": "Informe início e fim de cada corte em mm:ss ou hh:mm:ss. O título fica no "
              "cartão do topo durante todo o corte.",
}
TITLE_PLACEHOLDERS = {"animated": "Título animado (opcional)",
                      "banner": "Título no cartão (opcional)"}
ANIMATION_CHOICES = [("Destaque — cor e maior", "highlight"), ("Só a cor muda", "color"),
                     ("Karaokê — pinta ao falar", "karaoke"),
                     ("Uma palavra por vez", "word"), ("Grupo entra com pulo", "pop"),
                     ("Sem destaque — legenda simples", "none")]
TITLE_TIMES = [("2 segundos", 2.0), ("3 segundos", 3.0), ("5 segundos", 5.0),
               ("O corte inteiro", 0.0)]
VIDEO_FILTER = ("Vídeos (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.ts *.mpg *.mpeg *.wmv *.flv);;"
                "Todos os arquivos (*.*)")
SIZES = [("Pequena", 64), ("Média", 76), ("Grande", 88), ("Muito grande", 104),
         ("Enorme", 124)]
# Fontes que ficam bem em legenda de vídeo curto; entram primeiro se estiverem instaladas.
PREFERRED_FONTS = ("Arial", "Arial Black", "Impact", "Montserrat", "Montserrat Black",
                   "Poppins", "Bebas Neue", "Anton", "Roboto", "Segoe UI", "Verdana",
                   "Tahoma", "Trebuchet MS", "Helvetica", "Georgia")


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


class FrameGrabber(QThread):
    """Tira um quadro do vídeo com o FFmpeg, fora da thread da interface."""

    ready = Signal(str, QImage)    # arquivo de origem, quadro (nulo se não deu)

    def __init__(self, ffmpeg: Path, source: str, moment: float, parent=None):
        super().__init__(parent)
        self.ffmpeg, self.source, self.moment = ffmpeg, source, moment

    def run(self) -> None:
        image = QImage()
        try:
            with tempfile.TemporaryDirectory(prefix="baixador-ytdlp-previa-") as folder:
                target = Path(folder) / "quadro.jpg"
                subprocess.run(
                    [str(self.ffmpeg), "-v", "error", "-ss", f"{self.moment:.3f}", "-i",
                     self.source, "-frames:v", "1", "-vf", "scale=-2:540", "-y", str(target)],
                    capture_output=True, timeout=20, check=False,
                    creationflags=CREATE_NO_WINDOW)
                if target.is_file():
                    image = QImage(str(target))
        except (OSError, subprocess.SubprocessError):
            image = QImage()
        self.ready.emit(self.source, image)


def field_time(seconds: float) -> str:
    """Tempo para o campo de início/fim, com décimos quando o plano trouxer (12:03.5)."""
    centis = round(max(0.0, seconds) * 100)
    whole, fraction = divmod(centis, 100)
    text = format_clock(whole)
    return f"{text}.{fraction:02}".rstrip("0") if fraction else text


class ClipRow(QWidget):
    """Uma linha da lista de cortes: início, fim, título, duração e remover."""

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
        self.markers: tuple[Marker, ...] = ()
        self.plan_badge = Muted("", self, wrap=False)
        self.plan_badge.hide()
        self.length = Muted("", self, wrap=False)
        self.length.setMinimumWidth(64)
        self.remove = IconButton("trash", "Remover corte", self)
        self.remove.clicked.connect(lambda: self.removed.emit(self))
        for field in (self.start, self.end):
            field.textChanged.connect(self._update_length)
            field.textChanged.connect(self.changed)
        layout.addWidget(self.number)
        layout.addWidget(self.start)
        layout.addWidget(self.end)
        layout.addWidget(self.title, 1)
        layout.addWidget(self.plan_badge)
        layout.addWidget(self.length)
        layout.addWidget(self.remove)
        self.set_number(number)

    def set_number(self, number: int) -> None:
        self.number.setText(f"{number}.")

    def set_markers(self, markers: tuple[Marker, ...]) -> None:
        """Pontos de som e zoom vindos do plano da IA (mostrados como "✦ 3")."""
        self.markers = tuple(markers)
        self.plan_badge.setVisible(bool(self.markers))
        self.plan_badge.setText(f"✦ {len(self.markers)}")
        self.plan_badge.setToolTip(
            tr("Efeitos do plano da IA") + ":\n" + markers_text(self.markers))

    def is_filled(self) -> bool:
        return bool(self.start.text().strip() and self.end.text().strip())

    def _update_length(self, *_args) -> None:
        """Mostra a duração enquanto digita, ou o que está errado, antes de clicar em Criar."""
        if not self.is_filled():
            self.length.setText("")
            self.length.setToolTip("")
            return
        try:
            clip = make_range(self.start.text(), self.end.text())
        except ClipError as exc:
            self.length.setText(tr("inválido"))
            self.length.setToolTip(tr(str(exc)))
            return
        self.length.setText(format_clock(clip.length))
        self.length.setToolTip("")


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
        page = self.page = ScrollColumn(self, spacing=14)
        root.addWidget(page, 1)
        page.add(PageHeader(
            "Cortes",
            "Gere vídeos verticais com legenda palavra a palavra, sem as pausas.",
            self))
        # Origem e destino primeiro: é o que se decide antes de tudo (e o que se esquece).
        page.add(self._source_group())
        page.add(self._destination_group())
        page.add(SectionLabel("Cortes", self))
        page.add(self._ranges_group())
        # Tudo o que muda a imagem fica junto, ao lado de uma prévia que acompanha a rolagem.
        page.add(SectionLabel("Visual do corte", self))
        page.add(self._visual_group())
        page.add(SectionLabel("Ritmo e efeitos", self))
        page.add(self._finish_group())
        page.add(SectionLabel("Saída e transcrição", self))
        page.add(self._transcription_group())
        page.add_stretch()
        root.addWidget(self._action_bar())
        self.preview_rail.follow(page)
        self._frame_timer = QTimer(self)
        self._frame_timer.setSingleShot(True)
        self._frame_timer.setInterval(450)
        self._frame_timer.timeout.connect(self._grab_frame)
        self._grabber: FrameGrabber | None = None
        self._add_row()
        self._layout_changed()

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou link do YouTube", group)
        self.source_edit.textChanged.connect(self._source_changed)
        button = Button("Escolher arquivo", "folder", "secondary", group)
        button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Vídeo de origem",
            "Use um arquivo do computador ou cole um link: só os trechos escolhidos são "
            "baixados. Com um arquivo, a prévia mostra um quadro dele.", self.source_edit,
            button))
        return group

    def _ranges_group(self) -> InsetGroup:
        group = InsetGroup(self)
        host = QWidget(group)
        column = QVBoxLayout(host)
        column.setContentsMargins(16, 12, 16, 14)
        column.setSpacing(8)
        self.ranges_hint = Muted(RANGES_HINTS["animated"], host)
        column.addWidget(self.ranges_hint)
        self.rows_layout = QVBoxLayout()
        self.rows_layout.setSpacing(8)
        column.addLayout(self.rows_layout)
        add_line = QHBoxLayout()
        self.add_button = Button("Adicionar corte", "plus", "secondary", host)
        self.add_button.clicked.connect(lambda: self._add_row(focus=True))
        add_line.addWidget(self.add_button)
        add_line.addStretch(1)
        column.addLayout(add_line)
        column.addWidget(Headline("Plano da IA", host))
        column.addWidget(Muted(
            "Cole a linha {\"bx\":1,…} que a IA entrega no fim da resposta (veja docs/PLANO-DA-IA.md): "
            "ela preenche os cortes, os títulos e onde entra cada som e zoom. Com o campo vazio, "
            "o botão lê a área de transferência (pode ser a resposta inteira).", host))
        plan_line = QHBoxLayout()
        plan_line.setSpacing(10)
        self.plan_edit = TextField('{"bx":1,"c":[…]}', host)
        self.plan_edit.setClearButtonEnabled(True)
        self.plan_edit.returnPressed.connect(self._apply_plan)
        self.plan_button = Button("Aplicar plano", "success", "secondary", host)
        self.plan_button.clicked.connect(self._apply_plan)
        plan_line.addWidget(self.plan_edit, 1)
        plan_line.addWidget(self.plan_button)
        column.addLayout(plan_line)
        group.add_row(host)
        return group

    def _visual_group(self) -> InsetGroup:
        """Prévia à esquerda; à direita, enquadramento, título e legenda, de cima para baixo."""
        group = InsetGroup(self)
        style = self._saved_style()
        host = QWidget(group)
        line = QHBoxLayout(host)
        line.setContentsMargins(16, 14, 16, 16)
        line.setSpacing(24)

        holder = QWidget(host)
        holder_column = QVBoxLayout(holder)
        holder_column.setContentsMargins(0, 0, 0, 0)
        holder_column.setSpacing(8)
        self.preview = CaptionPreview(holder)
        self.preview.position_changed.connect(self._preview_moved)
        holder_column.addWidget(self.preview)
        self.preview_hint = Muted("Arraste a legenda na prévia. A imagem é aproximada.", holder)
        self.preview_hint.setFixedWidth(self.preview.width())
        holder_column.addWidget(self.preview_hint)
        self.preview_rail = StickyRail(holder, host)
        line.addWidget(self.preview_rail)

        column = QVBoxLayout()
        column.setSpacing(8)
        column.addWidget(Headline("Enquadramento", host))
        self.framing_picker = ChoicePicker(FRAMINGS, self.preview.state, host)
        self.framing_picker.set_value(str(getattr(self.cfg, "clips_framing", "blur")))
        column.addWidget(self.framing_picker)
        self.framing_hint = Muted("", host)
        column.addWidget(self.framing_hint)

        column.addSpacing(10)
        column.addWidget(Headline("Título", host))
        self.title_picker = ChoicePicker(TITLE_MODES, self.preview.state, host)
        self.title_picker.set_value(
            "banner" if getattr(self.cfg, "clips_banner", False) else "animated")
        column.addWidget(self.title_picker)
        self.title_hint = Muted("", host)
        column.addWidget(self.title_hint)
        title_form = QGridLayout()
        title_form.setHorizontalSpacing(12)
        title_form.setVerticalSpacing(10)
        title_form.setColumnStretch(1, 1)
        self.title_combo = Select(host)
        for label, value in TITLE_TIMES:
            self.title_combo.addItem(label, userData=value)
        self.title_combo.setCurrentIndex(max(0, self.title_combo.findData(
            float(getattr(self.cfg, "clips_title_seconds", 2.0)))))
        self.title_stepper = Stepper(host)
        self.title_stepper.setRange(TITLE_MIN, TITLE_MAX)
        self.title_stepper.setValue(style.resolved_title_position())
        title_line = QHBoxLayout()
        title_line.setSpacing(10)
        title_line.addWidget(self.title_stepper)
        title_line.addWidget(Muted("% da altura; arraste o título na prévia", host, wrap=False))
        title_line.addStretch(1)
        self.label_edit = TextField("Ex.: nome do podcast, convidado ou episódio", host)
        self.label_edit.setText(str(getattr(self.cfg, "clips_banner_label", "") or ""))
        self.label_edit.setClearButtonEnabled(True)
        self.label_edit.setMaxLength(80)
        self._title_rows: dict[str, list[QWidget]] = {"animated": [], "banner": []}
        title_rows = [("animated", "Tempo na tela", self.title_combo),
                      ("animated", "Altura do título", title_line),
                      ("banner", "Linha de cima", self.label_edit)]
        for index, (mode, label, control) in enumerate(title_rows):
            heading = Headline(label, host)
            title_form.addWidget(heading, index, 0)
            if isinstance(control, QWidget):
                alignment = Qt.AlignmentFlag(0) if control is self.label_edit \
                    else Qt.AlignmentFlag.AlignLeft
                title_form.addWidget(control, index, 1, alignment)
                widgets = [heading, control]
            else:
                holder_row = QWidget(host)
                holder_row.setLayout(control)
                control.setContentsMargins(0, 0, 0, 0)
                title_form.addWidget(holder_row, index, 1)
                widgets = [heading, holder_row]
            self._title_rows[mode] += widgets
        column.addLayout(title_form)

        column.addSpacing(6)
        column.addWidget(Divider(host))
        column.addSpacing(6)
        column.addWidget(Headline("Legenda", host))
        column.addLayout(self._caption_form(host, style))
        column.addWidget(Muted(
            "A fonte precisa estar instalada no computador. O título usa a fonte da legenda "
            "e a cor da palavra falada.", host))
        column.addStretch(1)
        line.addLayout(column, 1)
        group.add_row(host)

        self.framing_picker.changed.connect(self._layout_changed)
        self.title_picker.changed.connect(self._layout_changed)
        self.title_combo.currentIndexChanged.connect(self._save_style)
        self.title_stepper.valueChanged.connect(self._save_style)
        self.preview.title_position_changed.connect(self.title_stepper.setValue)
        self.label_edit.textChanged.connect(self._refresh_preview)
        self.label_edit.editingFinished.connect(self._save_style)
        self.preview.set_style(style)
        return group

    def _caption_form(self, host: QWidget, style: CaptionStyle) -> QGridLayout:
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
        colors.addWidget(Muted("Palavra falada e título", host, wrap=False))
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
        self.animation_combo = Select(host)
        for label, value in ANIMATION_CHOICES:
            self.animation_combo.addItem(label, userData=value)
        self.animation_combo.setCurrentIndex(max(0, self.animation_combo.findData(style.animation)))
        self.background_switch = Switch(host)
        self.background_switch.setChecked(style.background)

        rows = [("Animação", self.animation_combo), ("Fonte", self.font_combo),
                ("Tamanho", self.size_combo), ("Cores", colors), ("Altura", position_line),
                ("Palavras", self.words_combo), ("Maiúsculas", self.upper_switch),
                ("Caixa atrás", self.background_switch)]
        for index, (label, control) in enumerate(rows):
            form.addWidget(Headline(label, host), index, 0)
            if isinstance(control, QWidget):
                form.addWidget(control, index, 1, Qt.AlignmentFlag.AlignLeft)
            else:
                form.addLayout(control, index, 1)

        for combo in (self.font_combo, self.size_combo, self.words_combo, self.animation_combo):
            combo.currentIndexChanged.connect(self._save_style)
        for button in (self.text_color, self.highlight_color):
            button.color_changed.connect(self._save_style)
        self.upper_switch.toggled.connect(self._save_style)
        self.background_switch.toggled.connect(self._save_style)
        self.position_stepper.valueChanged.connect(self._save_style)
        return form

    def _finish_group(self) -> InsetGroup:
        group = self.finish_group = InsetGroup(self)
        cfg = self.cfg
        self.pauses_switch = Switch(group)
        self.pauses_switch.setChecked(bool(getattr(cfg, "clips_remove_pauses", True)))
        self.pauses_switch.toggled.connect(self._pauses_toggled)
        group.add_row(SettingRow(
            "Remover pausas",
            "Corta os silêncios entre as falas usando o tempo de cada palavra.",
            self.pauses_switch, group))
        self.pause_combo = Select(group)
        for label, value in PAUSES:
            self.pause_combo.addItem(label, userData=value)
        self.pause_combo.setCurrentIndex(max(0, self.pause_combo.findData(
            float(getattr(cfg, "clips_min_pause", 0.6)))))
        self.pause_combo.currentIndexChanged.connect(self._save_style)
        self.pause_row = group.add_row(SettingRow(
            "Pausa mínima", "Silêncios menores que isso ficam no vídeo.", self.pause_combo, group))
        self.zoom_switch = Switch(group)
        self.zoom_switch.setChecked(bool(getattr(cfg, "clips_zoom_cuts", False)))
        self.zoom_row = group.add_row(SettingRow(
            "Zoom nas emendas",
            "Alterna uma leve aproximação a cada pausa removida: o salto vira um corte de "
            "câmera, como nos vídeos de quem edita à mão.", self.zoom_switch, group))
        self.punch_switch = Switch(group)
        self.punch_switch.setChecked(bool(getattr(cfg, "clips_emphasis_zoom", False)))
        group.add_row(SettingRow(
            "Zoom na ênfase",
            "Aproxima rápido a imagem nos pontos do plano da IA ou, sem plano, na palavra dita "
            "com mais força.", self.punch_switch, group))
        self.sfx_switch = Switch(group)
        self.sfx_switch.setChecked(bool(getattr(cfg, "clips_sound_effects", False)))
        group.add_row(SettingRow(
            "Efeitos sonoros",
            "Com plano da IA, cada som entra na palavra que ela indicou (whoosh, pop, impacto, "
            "ding ou subida). Sem plano, uma regra simples: whoosh nas pausas longas cortadas "
            "e pop nas palavras ditas bem mais alto.", self.sfx_switch, group))
        self.sounds_edit = TextField("Sons do próprio app", group)
        self.sounds_edit.setText(str(getattr(cfg, "clips_sounds_folder", "") or ""))
        self.sounds_edit.setClearButtonEnabled(True)
        self.sounds_edit.editingFinished.connect(self._save_style)
        sounds_button = Button("Escolher pasta", "folder", "secondary", group)
        sounds_button.clicked.connect(self._choose_sounds)
        self.sounds_row = group.add_row(self._path_row(
            group, "Seus sons (opcional)",
            "Uma pasta com arquivos chamados whoosh, pop, impacto, ding e subida (WAV, MP3, OGG…) "
            "troca os sons padrão pelos seus. O que faltar continua com o som do app.",
            self.sounds_edit, sounds_button))
        for switch in (self.zoom_switch, self.sfx_switch, self.punch_switch):
            switch.toggled.connect(self._save_style)
        self.sfx_switch.toggled.connect(self._sounds_toggled)
        self._pauses_toggled(self.pauses_switch.isChecked(), save=False)
        self._sounds_toggled(self.sfx_switch.isChecked())
        return group

    def _transcription_group(self) -> InsetGroup:
        group = InsetGroup(self)
        cfg = self.cfg
        self.progress_switch = Switch(group)
        self.progress_switch.setChecked(bool(getattr(cfg, "clips_progress_bar", False)))
        group.add_row(SettingRow(
            "Barra de progresso",
            "Uma linha fina no rodapé, na cor de destaque, mostrando quanto falta.",
            self.progress_switch, group))
        self.loudness_switch = Switch(group)
        self.loudness_switch.setChecked(bool(getattr(cfg, "clips_normalize_audio", False)))
        group.add_row(SettingRow(
            "Volume equilibrado",
            "Ajusta o som para -14 LUFS, o padrão do YouTube, TikTok e Reels.",
            self.loudness_switch, group))
        self.srt_switch = Switch(group)
        self.srt_switch.setChecked(bool(getattr(cfg, "clips_save_srt", False)))
        group.add_row(SettingRow(
            "Salvar a legenda em .srt",
            "Um arquivo ao lado de cada corte, para enviar como legenda separada.",
            self.srt_switch, group))
        for switch in (self.progress_switch, self.loudness_switch, self.srt_switch):
            switch.toggled.connect(self._save_style)
        self.language_combo = Select(group)
        for label, value in LANGUAGES:
            self.language_combo.addItem(label, userData=value)
        self.language_combo.setCurrentIndex(max(0, self.language_combo.findData(
            getattr(cfg, "transcription_language", "pt"))))
        group.add_row(SettingRow("Idioma da fala", "", self.language_combo, group))
        self.model_combo = Select(group)
        for label, value in MODELS:
            self.model_combo.addItem(label, userData=value)
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(
            getattr(cfg, "transcription_model", "medium"))))
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
        row.title.textChanged.connect(self._refresh_preview)
        if hasattr(self, "title_picker"):
            row.title.setPlaceholderText(tr(TITLE_PLACEHOLDERS[self.title_picker.value()]))
        if not self.rows:
            row.start.editingFinished.connect(self._frame_timer.start)
        self.rows.append(row)
        self.rows_layout.addWidget(row)
        self._refresh_rows()
        if focus:
            row.start.setFocus(Qt.FocusReason.OtherFocusReason)

    def apply_plan_text(self, text: str) -> int:
        """Troca a lista de cortes pelos do plano; devolve quantos cortes entraram."""
        ranges = parse_plan(text)
        look = parse_look(text)
        while len(self.rows) > 1:
            row = self.rows.pop()
            self.rows_layout.removeWidget(row)
            row.deleteLater()
        for index, clip in enumerate(ranges):
            if index:
                self._add_row()
            row = self.rows[index]
            row.start.setText(field_time(clip.start))
            row.end.setText(field_time(clip.end))
            row.title.setText(clip.title)
            row.set_markers(clip.markers)
        if any(clip.markers for clip in ranges):
            # Quem colou um plano com sons quer ouvir os sons.
            self.sfx_switch.setChecked(any(m.sound for c in ranges for m in c.markers))
            self.punch_switch.setChecked(any(m.zoom for c in ranges for m in c.markers))
        if look.label is not None:
            self.label_edit.setText(look.label)
        if look.title_mode:
            # O tamanho dos títulos que a IA escreveu depende do tipo: segue o dela.
            self.title_picker.set_value(look.title_mode)
        self._refresh_rows()
        self._save_style()
        return len(ranges)

    def _apply_plan(self) -> None:
        text = self.plan_edit.text().strip() or QApplication.clipboard().text()
        try:
            count = self.apply_plan_text(text)
        except ClipError as exc:
            Toast.error("Plano da IA", tr(str(exc)), parent=self.window(), duration=7000)
            return
        effects = sum(len(row.markers) for row in self.rows)
        self.plan_edit.clear()
        Toast.success("Plano da IA", f"{count} {tr('corte(s)')} e {effects} "
                      f"{tr('ponto(s) de efeito carregados.')}", parent=self.window())

    def _remove_row(self, row: ClipRow) -> None:
        if len(self.rows) == 1:
            for field in (row.start, row.end, row.title):
                field.clear()
            row.set_markers(())
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
        self._refresh_preview()

    def _pauses_toggled(self, checked: bool, save: bool = True) -> None:
        # Sem pausas removidas não há pausa mínima nem emendas para disfarçar.
        self.finish_group.set_row_visible(self.pause_row, checked)
        self.finish_group.set_row_visible(self.zoom_row, checked)
        if save:
            self._save_style()

    def _sounds_toggled(self, checked: bool) -> None:
        self.finish_group.set_row_visible(self.sounds_row, checked)

    def _layout_changed(self, *_args) -> None:
        """Enquadramento ou título trocados: textos de apoio, campos que valem e prévia."""
        framing, mode = self.framing_picker.value(), self.title_picker.value()
        self.framing_hint.setText(tr(FRAMING_HINTS.get(framing, "")))
        self.title_hint.setText(tr(TITLE_HINTS[mode]))
        self.ranges_hint.setText(tr(RANGES_HINTS[mode]))
        for key, widgets in self._title_rows.items():
            for widget in widgets:
                widget.setVisible(key == mode)
        for row in self.rows:
            row.title.setPlaceholderText(tr(TITLE_PLACEHOLDERS[mode]))
        # Com a faixa no topo a legenda não pode subir para dentro dela.
        low = BANNER_CAPTION_MIN if mode == "banner" else POSITION_MIN
        self.position_stepper.setRange(low, POSITION_MAX)
        self._save_style()

    def banner(self) -> bool:
        return self.title_picker.value() == "banner"

    def _preview_title(self) -> str:
        """O título do primeiro corte que tiver um, para a prévia mostrar o texto de verdade."""
        return next((row.title.text().strip() for row in self.rows if row.title.text().strip()),
                    "")

    def _refresh_preview(self, *_args) -> None:
        if not hasattr(self, "srt_switch"):
            return   # ainda montando a página
        preview = self.preview
        preview.set_style(self.caption_style())
        preview.set_framing(self.framing_picker.value())
        preview.set_banner(self.banner())
        preview.set_texts(self._preview_title(), self.label_edit.text())
        self.framing_picker.refresh()
        self.title_picker.refresh()

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
            animation=str(getattr(cfg, "clips_animation", "highlight")),
            background=bool(getattr(cfg, "clips_background", False)),
            title_position=int(getattr(cfg, "clips_title_position", 0) or 0),
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
            animation=str(self.animation_combo.currentData() or "highlight"),
            background=self.background_switch.isChecked(),
            title_position=self.title_stepper.value(),
        ).normalized()

    def _preview_moved(self, value: int) -> None:
        self.position_stepper.setValue(value)

    def _save_style(self, *_args) -> None:
        """Toda mudança vai para a prévia e para as Configurações (vale na próxima abertura)."""
        if not hasattr(self, "srt_switch"):
            return   # ainda montando a página
        style = self.caption_style()
        self._refresh_preview()
        self.words_combo.setEnabled(style.animation != "word")
        cfg = self.cfg
        cfg.clips_framing = self.framing_picker.value()
        cfg.clips_banner = self.banner()
        cfg.clips_banner_label = self.label_edit.text().strip()
        cfg.clips_remove_pauses = self.pauses_switch.isChecked()
        cfg.clips_min_pause = float(self.pause_combo.currentData() or 0.6)
        cfg.clips_font = style.font
        cfg.clips_font_size = style.size
        cfg.clips_text_color = style.text_color
        cfg.clips_highlight_color = style.highlight_color
        cfg.clips_position = style.position
        cfg.clips_words = style.words
        cfg.clips_uppercase = style.uppercase
        cfg.clips_animation = style.animation
        cfg.clips_background = style.background
        cfg.clips_title_position = style.title_position
        cfg.clips_sounds_folder = self.sounds_edit.text().strip()
        cfg.clips_title_seconds = float(self.title_combo.currentData() or 0.0)
        cfg.clips_zoom_cuts = self.zoom_switch.isChecked()
        cfg.clips_progress_bar = self.progress_switch.isChecked()
        cfg.clips_sound_effects = self.sfx_switch.isChecked()
        cfg.clips_emphasis_zoom = self.punch_switch.isChecked()
        cfg.clips_normalize_audio = self.loudness_switch.isChecked()
        cfg.clips_save_srt = self.srt_switch.isChecked()
        cfg.save()

    # ------------------------------------------------------------------ origem e destino
    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain
        self._frame_timer.start()

    def _grab_frame(self) -> None:
        """Quadro do início do primeiro corte para a prévia (só arquivo local)."""
        source = self._source()
        if (not self.toolchain or not source or is_url(source) or not Path(source).is_file()
                or (self._grabber and self._grabber.isRunning())):
            if not source or is_url(source):
                self.preview.set_frame(QImage())
            return
        moment = 1.0
        if self.rows:
            with contextlib.suppress(ClipError):
                moment = parse_time(self.rows[0].start.text()) + 0.5
        grabber = FrameGrabber(Path(self.toolchain.ffmpeg), source, moment, self)
        grabber.ready.connect(self._frame_ready)
        grabber.finished.connect(grabber.deleteLater)
        self._grabber = grabber
        grabber.start()

    def _frame_ready(self, source: str, image: QImage) -> None:
        self._grabber = None
        if source == self._source():
            self.preview.set_frame(image)
        else:
            self._frame_timer.start()   # a origem mudou enquanto o quadro era tirado

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)

    def _source(self) -> str:
        return self.source_edit.text().strip().strip('"')

    def _source_changed(self, *_args) -> None:
        self._frame_timer.start()
        source = self._source()
        if not self.output_edit.text().strip():
            if is_url(source):
                self.output_edit.setText(str(getattr(self.cfg, "download_dir", "") or ""))
            elif source and Path(source).is_file():
                self.output_edit.setText(str(Path(source).parent))
        self._update_run_enabled()

    def _choose_source(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Selecionar vídeo", "", VIDEO_FILTER)
        if path:
            self.output_edit.clear()
            self.source_edit.setText(path)

    def _choose_sounds(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Pasta com os seus sons",
                                                self.sounds_edit.text().strip())
        if path:
            self.sounds_edit.setText(path)
            self._save_style()

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
                ranges.append(replace(make_range(row.start.text(), row.end.text(),
                                                 row.title.text()), markers=row.markers))
            except ClipError as exc:
                raise ClipError(f"{tr('Corte')} {number}: {tr(str(exc))}") from exc
        if not ranges:
            raise ClipError("Adicione pelo menos um corte com início e fim.")
        return ClipOptions(
            source=self._source(),
            ranges=tuple(ranges),
            output_dir=Path(self.output_edit.text().strip()),
            framing=self.framing_picker.value(),
            banner=self.banner(),
            banner_label=self.label_edit.text().strip(),
            remove_pauses=self.pauses_switch.isChecked(),
            min_pause=float(self.pause_combo.currentData() or 0.6),
            style=self.caption_style(),
            title_seconds=float(self.title_combo.currentData() or 0.0),
            zoom_cuts=self.zoom_switch.isChecked(),
            progress_bar=self.progress_switch.isChecked(),
            sound_effects=self.sfx_switch.isChecked(),
            emphasis_zoom=self.punch_switch.isChecked(),
            sounds_folder=Path(self.sounds_edit.text().strip())
            if self.sounds_edit.text().strip() else None,
            normalize_audio=self.loudness_switch.isChecked(),
            save_srt=self.srt_switch.isChecked(),
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
        if self._grabber and self._grabber.isRunning():
            self._grabber.wait(3000)
