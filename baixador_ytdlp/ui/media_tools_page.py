"""Fluxo guiado para edições locais de mídia com o FFmpeg do aplicativo."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFileDialog, QGridLayout,
                               QHBoxLayout, QSizePolicy, QVBoxLayout, QWidget)

from ..media_tools import (DEFAULT_CHOICE, MediaToolOptions, available_destination,
                           default_destination)
from ..workers import MediaToolWorker
from . import icons, theme
from .components import (Button, Divider, Headline, Hint, InsetGroup, Muted, PageHeader,
                         PrimaryButton, ProgressBar, ScrollColumn, SectionLabel, Select,
                         SettingRow, Switch, TextField, Toast)
from .i18n import tr

MEDIA_FILTER = ("Mídia (*.mp4 *.mkv *.webm *.mov *.avi *.m4v *.ts *.mpg *.mpeg *.wmv *.flv "
                "*.3gp *.mp3 *.m4a *.aac *.ogg *.opus *.wav *.flac);;"
                "Todos os arquivos (*.*)")
SUBTITLE_FILTER = "Legendas (*.srt *.vtt *.ass);;Todos os arquivos (*.*)"

# Cada ferramenta é só dados: a página monta cartão, ajustes e botão a partir deles.
#   "time":   linha de início/fim (``end`` False = só um momento);
#   "choice": lista única de valores (os mesmos de ``media_tools.CHOICES``).
OPERATIONS = {
    "trim": {
        "title": "Recortar trecho", "icon": "cut", "tag": "Corte preciso",
        "summary": "Crie um novo vídeo apenas com o intervalo escolhido.",
        "action": "Recortar",
        "time": {"title": "Início e fim",
                 "hint": "Use mm:ss ou hh:mm:ss. O vídeo será recodificado para "
                         "começar e terminar nos pontos escolhidos.",
                 "end": True, "start": "início 00:01:30", "stop": "fim 00:04:00"},
    },
    "speed": {
        "title": "Ajustar velocidade", "icon": "speed", "tag": "Lento ou rápido",
        "summary": "Deixe o vídeo em câmera lenta ou acelerado, com o som junto.",
        "action": "Ajustar velocidade",
        "choice": {"title": "Velocidade",
                   "hint": "Vale para imagem e som. Abaixo de 1x é câmera lenta.",
                   "options": [("0,25x — muito lento", "0.25"), ("0,5x — câmera lenta", "0.5"),
                               ("0,75x — um pouco mais lento", "0.75"),
                               ("1,25x — um pouco mais rápido", "1.25"),
                               ("1,5x — rápido", "1.5"), ("2x — o dobro", "2"),
                               ("3x — três vezes", "3"), ("4x — timelapse", "4")]},
    },
    "rotate": {
        "title": "Girar ou espelhar", "icon": "rotate", "tag": "Orientação",
        "summary": "Corrija vídeos de celular tortos ou espelhe a imagem.",
        "action": "Girar vídeo",
        "choice": {"title": "Transformação",
                   "hint": "A imagem é recodificada; o som é mantido.",
                   "options": [("Girar 90° para a direita", "cw"),
                               ("Girar 90° para a esquerda", "ccw"), ("Girar 180°", "180"),
                               ("Espelhar na horizontal", "flip_h"),
                               ("Espelhar na vertical", "flip_v")]},
    },
    "shorts": {
        "title": "Criar versão vertical", "icon": "media", "tag": "9:16",
        "summary": "Prepare um vídeo vertical para Shorts, Reels ou TikTok.",
        "action": "Criar versão vertical",
    },
    "audio": {
        "title": "Extrair áudio", "icon": "media", "tag": "MP3, M4A, Opus…",
        "summary": "Salve só o som de um vídeo ou converta entre formatos de áudio.",
        "action": "Extrair áudio",
        "choice": {"title": "Formato do áudio",
                   "hint": "MP3 toca em tudo; M4A e Opus rendem mais por megabyte; "
                           "FLAC e WAV não perdem qualidade.",
                   "options": [("MP3 — compatível com tudo", "mp3"),
                               ("M4A (AAC) — celulares e Apple", "m4a"),
                               ("Opus — menor tamanho", "opus"), ("FLAC — sem perda", "flac"),
                               ("WAV — sem compressão", "wav")]},
    },
    "normalize": {
        "title": "Nivelar volume", "icon": "wave", "tag": "EBU R128",
        "summary": "Iguale o volume de vídeos e músicas sem recodificar a imagem.",
        "action": "Nivelar volume",
        "choice": {"title": "Volume alvo",
                   "hint": "Medido em LUFS. -16 serve para a maioria dos casos; -14 é o "
                           "padrão do YouTube e do Spotify.",
                   "options": [("-16 LUFS — web e podcast", "-16"),
                               ("-14 LUFS — YouTube e Spotify", "-14"),
                               ("-23 LUFS — TV (EBU R128)", "-23")]},
    },
    "mute": {
        "title": "Remover áudio", "icon": "volume-off", "tag": "Sem perda",
        "summary": "Crie uma cópia do vídeo sem som, sem recodificar a imagem.",
        "action": "Remover áudio",
    },
    "convert": {
        "title": "Converter formato", "icon": "convert", "tag": "MP4 · WebM",
        "summary": "Reencode para MP4 (H.264) ou WebM (VP9) e abra em qualquer aparelho.",
        "action": "Converter",
        "choice": {"title": "Formato de saída",
                   "hint": "MP4 abre em qualquer lugar; WebM é ideal para sites e costuma "
                           "ficar menor, mas demora mais.",
                   "options": [("MP4 — H.264 e AAC", "mp4"),
                               ("WebM — VP9 e Opus (mais lento)", "webm")]},
    },
    "remux": {
        "title": "Trocar contêiner", "icon": "media", "tag": "Sem perda",
        "summary": "Converta para MKV sem mexer em imagem ou som.",
        "action": "Criar MKV",
    },
    "compress": {
        "title": "Reduzir tamanho", "icon": "compress", "tag": "H.264",
        "summary": "Crie um MP4 menor, equilibrando tamanho e qualidade.",
        "action": "Comprimir",
    },
    "target_size": {
        "title": "Caber em um limite", "icon": "limit", "tag": "MB",
        "summary": "Comprima para caber no limite do Discord, WhatsApp ou e-mail.",
        "action": "Comprimir para o limite",
    },
    "gif": {
        "title": "Criar GIF animado", "icon": "film", "tag": "GIF",
        "summary": "Transforme um trecho curto em GIF leve, com as cores otimizadas.",
        "action": "Criar GIF",
        "time": {"title": "Trecho do GIF",
                 "hint": "Use mm:ss ou hh:mm:ss, com até 30 s. Em branco, começa do zero.",
                 "end": True, "start": "início 00:00:05", "stop": "fim 00:00:12"},
        "choice": {"title": "Tamanho",
                   "hint": "Quanto maior a largura, maior o arquivo. O GIF nunca passa da "
                           "largura original do vídeo.",
                   "options": [("Pequeno — 480 px, 12 quadros/s", "480"),
                               ("Médio — 640 px, 15 quadros/s", "640"),
                               ("Grande — 800 px, 20 quadros/s", "800")]},
    },
    "frame": {
        "title": "Capturar imagem", "icon": "image", "tag": "PNG · JPG",
        "summary": "Salve um quadro do vídeo como imagem, no momento que você escolher.",
        "action": "Capturar imagem",
        "time": {"title": "Momento do quadro",
                 "hint": "Use mm:ss ou hh:mm:ss. Em branco, captura o primeiro quadro.",
                 "end": False, "start": "momento 00:01:30", "stop": ""},
        "choice": {"title": "Formato da imagem",
                   "hint": "PNG não perde qualidade; JPG e WebP ficam bem menores.",
                   "options": [("PNG — sem perda", "png"), ("JPG — leve e compatível", "jpg"),
                               ("WebP — leve e moderno", "webp")]},
    },
    "burn": {
        "title": "Adicionar legendas ao vídeo", "icon": "captions", "tag": "Legenda fixa",
        "summary": "Grave uma legenda SRT, VTT ou ASS na imagem do vídeo.",
        "action": "Adicionar legendas",
    },
    "extract_subs": {
        "title": "Extrair legendas", "icon": "document", "tag": "SRT · ASS · VTT",
        "summary": "Salve como arquivo a legenda que já vem dentro do vídeo.",
        "action": "Extrair legendas",
        "choice": {"title": "Formato da legenda",
                   "hint": "Usa a primeira faixa de legenda em texto. O arquivo é salvo "
                           "ao lado do vídeo, com o mesmo nome.",
                   "options": [("SRT — o mais compatível", "srt"),
                               ("ASS — mantém o estilo", "ass"), ("VTT — para a web", "vtt")]},
    },
    "strip": {
        "title": "Limpar metadados", "icon": "shield", "tag": "Privacidade",
        "summary": "Apague localização, data, câmera e título do arquivo, sem recodificar.",
        "action": "Limpar metadados",
    },
}

# Ordem e agrupamento dos cartões na página.
GROUPS = (
    ("Cortar e ajustar", ("trim", "speed", "rotate", "shorts")),
    ("Áudio", ("audio", "normalize", "mute")),
    ("Converter e reduzir", ("convert", "remux", "compress", "target_size")),
    ("Imagem e animação", ("gif", "frame")),
    ("Legendas e privacidade", ("burn", "extract_subs", "strip")),
)


def wrap_lines(text: str, metrics: QFontMetrics, width: int, max_lines: int = 2) -> list[str]:
    """Quebra ``text`` em palavras para caber em ``width``; a última linha vira reticências
    só se ainda sobrar texto depois de ``max_lines``."""
    lines: list[str] = []
    current = ""
    words = text.split()
    for position, word in enumerate(words):
        candidate = f"{current} {word}".strip()
        if not current or metrics.horizontalAdvance(candidate) <= width:
            current = candidate
            continue
        lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            current = " ".join(words[position:])
            break
    lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    # elidedText pode elidar uma linha que cabe por exatamente 1 px (arredondamento e kerning
    # diferem de horizontalAdvance em cada plataforma); só elida o que de fato passa da largura.
    if metrics.horizontalAdvance(lines[-1]) > width:
        lines[-1] = metrics.elidedText(lines[-1], Qt.TextElideMode.ElideRight, width)
    return lines


class ToolCard(QAbstractButton):
    """Escolha visual de uma ferramenta, com contexto antes da execução."""

    def __init__(self, operation: str, parent=None):
        super().__init__(parent)
        self.operation = operation
        self.data = OPERATIONS[operation]
        self.setText(tr(self.data["title"]))
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(84)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip(tr(self.data["summary"]))
        self.setAccessibleName(tr(self.data["title"]))
        self.setAccessibleDescription(tr(self.data["summary"]))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.toggled.connect(self.update)
        self.pressed.connect(self.update)
        self.released.connect(self.update)

    _TITLE_X = 56
    _TEXT_TOP = 37
    _MIN_HEIGHT = 84

    def _text_width(self, card_width: int) -> int:
        return max(40, card_width - self._TITLE_X - 12)

    def text_lines(self, card_width: int) -> list[str]:
        """Linhas da descrição para um cartão desta largura; nunca cortadas com "…"."""
        metrics = QFontMetrics(theme.footnote())
        return wrap_lines(tr(self.data["summary"]), metrics, self._text_width(card_width),
                          max_lines=99)

    def hasHeightForWidth(self) -> bool:  # noqa: N802 - assinatura do Qt
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 - assinatura do Qt
        """Cresce em vez de cortar: janelas estreitas precisam de mais linhas."""
        line_height = QFontMetrics(theme.footnote()).height() + 1
        needed = self._TEXT_TOP + len(self.text_lines(width)) * line_height + 12
        return max(self._MIN_HEIGHT, needed)

    def sizeHint(self) -> QSize:
        return QSize(250, self.heightForWidth(250))

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

        icon_top = (self.height() - 34) / 2
        icon_rect = QRectF(12, icon_top, 34, 34)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.qcolor("accent_soft" if not active else "accent"))
        painter.drawRoundedRect(icon_rect, 10, 10)
        icon_tone = "accent" if not active else "on_accent"
        painter.drawPixmap(20, int(icon_top) + 8, icons.pixmap(self.data["icon"], theme.color(icon_tone), 18))

        title_x = self._TITLE_X
        painter.setFont(theme.headline())
        painter.setPen(QPen(theme.qcolor("text")))
        painter.drawText(QRectF(title_x, 13, self.width() - title_x - 12, 22),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         tr(self.data["title"]))

        painter.setFont(theme.footnote())
        painter.setPen(QPen(theme.qcolor("text_secondary")))
        metrics = QFontMetrics(painter.font())
        text_width = self._text_width(self.width())
        lines = self.text_lines(self.width())
        line_height = metrics.height() + 1
        for index, line in enumerate(lines):
            painter.drawText(QRectF(title_x, 37 + index * line_height, text_width, line_height),
                             int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft), line)
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

        page.add(SectionLabel("1. Arquivo de origem", self))
        page.add(self._source_group())
        page.add(SectionLabel("2. O que você quer fazer?", self))
        page.add(self._tool_picker())
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
        column = QVBoxLayout(host)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        self.operation_buttons = QButtonGroup(self)
        self.operation_buttons.setExclusive(True)
        self._tool_cards: dict[str, ToolCard] = {}
        for position, (group_title, operations) in enumerate(GROUPS):
            label = Hint(group_title, host)
            label.setContentsMargins(2, 8 if position else 0, 0, 0)
            column.addWidget(label)
            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(10)
            for index, operation in enumerate(operations):
                card = ToolCard(operation, host)
                self._tool_cards[operation] = card
                self.operation_buttons.addButton(card)
                card.toggled.connect(
                    lambda checked, value=operation: self._operation_changed(value) if checked else None)
                grid.addWidget(card, index // 2, index % 2)
            column.addLayout(grid)
        return host

    def _source_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.source_edit = TextField("Arquivo de vídeo ou áudio de origem", group)
        self.source_edit.editingFinished.connect(self._suggest_destination)
        self.source_edit.textChanged.connect(self._update_run_enabled)
        source_button = Button("Escolher arquivo", "folder", "secondary", group)
        source_button.clicked.connect(self._choose_source)
        group.add_row(self._path_row(
            group, "Arquivo de origem",
            "Escolha o arquivo que será processado. A versão original fica intacta.",
            self.source_edit, source_button))
        return group

    def _options_group(self) -> InsetGroup:
        group = InsetGroup(self)
        self.options_group = group
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
        self.time_row = SettingRow("Início e fim", "Use mm:ss ou hh:mm:ss.", times, group)
        group.add_row(self.time_row)
        self.fast_trim_switch = Switch(group)
        self.fast_trim_row = SettingRow(
            "Corte rápido, sem reencodar",
            "Instantâneo e sem perda de qualidade, mas começa no quadro-chave mais "
            "próximo: podem sobrar alguns segundos antes do início escolhido.",
            self.fast_trim_switch, group)
        group.add_row(self.fast_trim_row)

        self.choice_combo = Select(group)
        self.choice_combo.currentIndexChanged.connect(self._choice_changed)
        self.choice_row = SettingRow("Formato", "Escolha uma opção.", self.choice_combo, group)
        group.add_row(self.choice_row)

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
        self.run_button.setEnabled(False)
        row.addWidget(self.cancel_button)
        row.addWidget(self.run_button)
        column.addLayout(row)
        return bar

    def set_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain

    def set_media(self, path: str) -> None:
        self.source_edit.setText(path)
        self._suggest_destination()

    def _update_run_enabled(self, *_args) -> None:
        if hasattr(self, "run_button"):
            self.run_button.setEnabled(
                Path(self.source_edit.text().strip()).is_file()
                and not (self.worker and self.worker.isRunning()))

    def _operation(self) -> str:
        return self._operation_key

    def _operation_changed(self, operation: str) -> None:
        self._operation_key = operation
        data = OPERATIONS[operation]
        self.options_title.setText(tr(data["title"]))
        self.options_summary.setText(tr(data["summary"]))
        timing = data.get("time")
        show = self.options_group.set_row_visible
        show(self.time_row, bool(timing))
        if timing:
            self.time_row.title.setText(tr(timing["title"]))
            self.time_row.subtitle.setText(tr(timing["hint"]))
            self.start_edit.setPlaceholderText(tr(timing["start"]))
            self.end_edit.setPlaceholderText(tr(timing["stop"]))
            self.end_edit.setVisible(timing["end"])
        show(self.fast_trim_row, operation == "trim")
        self._fill_choices(data.get("choice"), operation)
        show(self.subtitle_row, operation == "burn")
        show(self.target_row, operation == "target_size")
        show(self.blur_row, operation == "shorts")
        self.run_button.setText(tr(data["action"]))
        self._suggest_destination()

    def _fill_choices(self, choice: dict | None, operation: str) -> None:
        self.options_group.set_row_visible(self.choice_row, bool(choice))
        if not choice:
            return
        self.choice_row.title.setText(tr(choice["title"]))
        self.choice_row.subtitle.setText(tr(choice["hint"]))
        self.choice_combo.blockSignals(True)
        try:
            self.choice_combo.clear()
            for label, value in choice["options"]:
                self.choice_combo.addItem(label, userData=value)
            self.choice_combo.setCurrentIndex(
                max(0, self.choice_combo.findData(DEFAULT_CHOICE.get(operation, ""))))
            # A largura da lista é calculada uma só vez pelo Qt; cada ferramenta tem itens
            # diferentes, então ajustamos ao mais longo (texto + margem + seta).
            metrics = self.choice_combo.fontMetrics()
            widest = max(metrics.horizontalAdvance(self.choice_combo.itemText(index))
                         for index in range(self.choice_combo.count()))
            self.choice_combo.setMinimumWidth(widest + 60)
        finally:
            self.choice_combo.blockSignals(False)

    def _choice_changed(self, *_args) -> None:
        # A escolha muda a extensão sugerida (MP3 → FLAC, PNG → JPG…).
        self._suggest_destination()

    def _choice(self) -> str:
        if not self.choice_row.isVisibleTo(self):
            return ""
        return str(self.choice_combo.currentData() or "")

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
            self.destination_edit.setText(str(default_destination(
                source, self._operation(), choice=self._choice())))
        self._update_run_enabled()

    def _choose_destination(self) -> None:
        suggested = self.destination_edit.text().strip()
        suffix = Path(suggested).suffix.casefold()
        typed = f"Arquivo {suffix[1:].upper()} (*{suffix});;" if suffix else ""
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar resultado", suggested,
            f"{typed}Arquivo MP4 (*.mp4);;Arquivo MKV (*.mkv);;Arquivo MP3 (*.mp3);;"
            "Todos os arquivos (*.*)",
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
            start=self.start_edit.text().strip() if self.time_row.isVisibleTo(self) else "",
            end=self.end_edit.text().strip() if self.end_edit.isVisibleTo(self) else "",
            subtitles=Path(self.subtitle_edit.text().strip()) if self.subtitle_edit.text().strip() else None,
            target_mb=int(self.target_combo.currentData() or 25),
            shorts_blur=self.blur_switch.isChecked(),
            fast_trim=self.fast_trim_switch.isChecked(),
            choice=self._choice(),
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
        self.status.setText(f"{tr('Preparando')}: {tr(OPERATIONS[self._operation()]['title']).lower()}…")

    def _clear_worker(self, worker: MediaToolWorker) -> None:
        if self.worker is worker:
            self.worker = None
            self._update_run_enabled()

    def _cancel(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status.setText("Cancelando…")

    def has_active_work(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def cancel_current(self) -> None:
        self._cancel()

    def _done(self, output: str) -> None:
        self._set_progress(100)
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self._update_run_enabled()
        self.cancel_button.hide()
        self.status.setText(f"Concluído: {Path(output).name}")
        self.operation_finished.emit(output)
        Toast.success("Processamento concluído", f"Arquivo salvo em {output}",
                      parent=self.window(), duration=7000)

    def _failed(self, message: str) -> None:
        self.progress_host.hide()
        self.taskbar_progress.emit(-1.0)
        self._update_run_enabled()
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
