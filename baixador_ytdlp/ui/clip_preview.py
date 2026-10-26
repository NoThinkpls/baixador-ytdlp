"""Prévias da página Cortes: a tela de celular grande e as miniaturas de cada formato.

As duas desenham com a mesma função (``paint_vertical``), então a miniatura de um
enquadramento mostra exatamente o que a prévia grande mostraria com ele escolhido: o
bonequinho (ou um quadro do vídeo), o título e a legenda nas cores escolhidas.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QImage, QKeyEvent, QLinearGradient,
                           QPainter, QPainterPath, QPen)
from PySide6.QtWidgets import QAbstractButton, QButtonGroup, QHBoxLayout, QWidget

from ..clips import (BANNER_BACKGROUND, BANNER_CAPTION_MIN, BANNER_CARD, BANNER_HEIGHT,
                     BANNER_LABEL_SPACE, BANNER_LINE_HEIGHT, BANNER_PADDING, BANNER_RADIUS,
                     HEIGHT, TITLE_MAX, TITLE_MIN, WIDTH, CaptionStyle, banner_label_size,
                     banner_label_text, banner_title_layout, is_light, video_height)
from . import theme
from .i18n import tr

POSITION_MIN, POSITION_MAX = 8, 92
PREVIEW_WORDS = ("essa", "é", "a", "sua", "legenda")
# O libass mede o \fs pela altura da linha; a letra em si (o "em" do Qt) é ~86% disso.
ASS_EM = 0.86
# Miniaturas são desenhadas nesta largura e reduzidas: fonte de 2 px não existe, e o texto
# ficaria desproporcional ao resto do desenho.
DRAW_WIDTH = 190.0


@dataclass
class PreviewState:
    """O que a prévia mostra; as miniaturas copiam e trocam só o enquadramento ou o título."""
    style: CaptionStyle = field(default_factory=CaptionStyle)
    framing: str = "blur"
    banner: bool = False
    frame: QImage = field(default_factory=QImage)
    title: str = ""          # vazio = "Título do corte"
    label: str = ""          # linha de cima do cartão (título fixo)

    def caption_position(self) -> int:
        position = self.style.position
        return max(position, BANNER_CAPTION_MIN) if self.banner else position


# ----------------------------------------------------------------- desenho

def _silhouette(painter: QPainter, cx: float, cy: float, radius: float) -> None:
    """Bonequinho: cabeça em ``(cx, cy)`` e o tronco descendo até sair do quadro."""
    painter.drawEllipse(QPointF(cx, cy), radius, radius)
    painter.drawRoundedRect(QRectF(cx - radius * 1.87, cy + radius * 1.4, radius * 3.73,
                                   radius * 6), radius * 1.33, radius * 1.33)


def _paint_placeholder(painter: QPainter, area: QRectF, framing: str) -> None:
    """Sem vídeo escolhido: um desenho que explica o enquadramento."""
    width, height = area.width(), area.height()
    background = QLinearGradient(0, area.top(), 0, area.bottom())
    background.setColorAt(0, QColor("#4A5568"))
    background.setColorAt(1, QColor("#1A202C"))
    painter.fillRect(area, background)
    painter.setPen(Qt.PenStyle.NoPen)
    if framing == "blur":
        # O vídeo 16:9 inteiro no meio, com ele mesmo desfocado e escuro atrás.
        painter.setBrush(QColor(255, 255, 255, 18))
        _silhouette(painter, area.center().x(), area.top() + height * 0.36, width * 0.2)
        band = QRectF(area.left(), area.center().y() - width * 9 / 32, width, width * 9 / 16)
        stripe = QLinearGradient(0, band.top(), 0, band.bottom())
        stripe.setColorAt(0, QColor("#718096"))
        stripe.setColorAt(1, QColor("#2D3748"))
        painter.fillRect(band, stripe)
        painter.save()
        painter.setClipRect(band, Qt.ClipOperation.IntersectClip)
        painter.setBrush(QColor(255, 255, 255, 60))
        for share in (0.3, 0.7):
            _silhouette(painter, area.left() + width * share, band.top() + band.height() * 0.38,
                        band.height() * 0.13)
        painter.restore()
        return
    painter.setBrush(QColor(255, 255, 255, 38))
    if framing == "track":
        # A pessoa fora do centro e a "mira" no rosto: a janela vai atrás dela.
        cx, cy, radius = area.left() + width * 0.56, area.top() + height * 0.38, width * 0.15
        _silhouette(painter, cx, cy, radius)
        pen = QPen(QColor(255, 255, 255, 170), max(1.0, width / 110))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        side, arm = radius * 1.55, radius * 0.55
        for dx in (-1, 1):
            for dy in (-1, 1):
                corner = QPointF(cx + dx * side, cy + dy * side)
                painter.drawLine(corner, QPointF(corner.x() - dx * arm, corner.y()))
                painter.drawLine(corner, QPointF(corner.x(), corner.y() - dy * arm))
        painter.setPen(Qt.PenStyle.NoPen)
        return
    _silhouette(painter, area.center().x(), area.top() + height * 0.40, width * 0.15)


def _paint_video(painter: QPainter, area: QRectF, framing: str, frame: QImage) -> None:
    if frame.isNull():
        _paint_placeholder(painter, area, framing)
        return
    width, height = int(area.width()), int(area.height())
    cover = frame.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
    origin = QPointF(area.left() - (cover.width() - width) / 2,
                     area.top() - (cover.height() - height) / 2)
    painter.save()
    painter.setClipRect(area, Qt.ClipOperation.IntersectClip)
    if framing == "blur":
        # Desfoque barato: reduz e amplia de novo, escurecido como no corte.
        tiny = cover.scaled(max(1, cover.width() // 12), max(1, cover.height() // 12),
                            Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)
        blurred = tiny.scaled(cover.width(), cover.height(), Qt.AspectRatioMode.IgnoreAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(origin, blurred)
        painter.fillRect(area, QColor(0, 0, 0, 50))
        fit = frame.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(QPointF(area.left() + (width - fit.width()) / 2,
                                  area.top() + (height - fit.height()) / 2), fit)
    else:
        painter.drawImage(origin, cover)
    painter.restore()


def _bold(style: CaptionStyle, pixels: float) -> QFont:
    font = QFont(style.font)
    font.setBold(True)
    font.setPixelSize(max(2, round(pixels)))
    return font


def _wrap(metrics: QFontMetricsF, text: str, width: float) -> list[str]:
    lines: list[str] = []
    for word in text.split():
        if lines and metrics.horizontalAdvance(f"{lines[-1]} {word}") <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines or [""]


def _paint_banner(painter: QPainter, rect: QRectF, scale: float, state: PreviewState) -> None:
    """Faixa escura e o cartão, com a mesma conta de quebra de linha do ASS."""
    style = state.style
    painter.fillRect(QRectF(rect.left(), rect.top(), rect.width(), BANNER_HEIGHT * scale),
                     QColor(BANNER_BACKGROUND))
    title = banner_label_text(state.title or tr("Título do corte"), style.uppercase)
    label = banner_label_text(state.label, style.uppercase)
    x1, y1, x2, y2 = BANNER_CARD
    card = QRectF(rect.left() + x1 * scale, rect.top() + y1 * scale, (x2 - x1) * scale,
                  (y2 - y1) * scale)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(style.highlight_color))
    painter.drawRoundedRect(card, BANNER_RADIUS * scale, BANNER_RADIUS * scale)
    painter.setPen(QColor("#141414") if is_light(style.highlight_color) else QColor("#FFFFFF"))
    top = y1 + BANNER_PADDING
    if label:
        font = _bold(style, banner_label_size(label) * ASS_EM * scale)
        painter.setFont(font)
        line = QRectF(card.left(), rect.top() + top * scale, card.width(),
                      QFontMetricsF(font).height())
        painter.drawText(line, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, label)
        top += BANNER_LABEL_SPACE
    size, lines = banner_title_layout(title, bool(label))
    font = _bold(style, size * ASS_EM * scale)
    painter.setFont(font)
    step = size * BANNER_LINE_HEIGHT * scale
    middle = rect.top() + (top + y2 - BANNER_PADDING) / 2 * scale
    first = middle - step * len(lines) / 2
    for index, text in enumerate(lines):
        painter.drawText(QRectF(card.left(), first + index * step, card.width(), step),
                         Qt.AlignmentFlag.AlignCenter, text)


def _paint_title(painter: QPainter, rect: QRectF, scale: float, state: PreviewState) -> None:
    """Título animado: caixa na cor de destaque, na altura escolhida, quebrando como o ASS."""
    style = state.style
    font = _bold(style, style.size * 0.84 * scale)
    painter.setFont(font)
    metrics = QFontMetricsF(font)
    lines = _wrap(metrics, state.title or tr("Título do corte"), rect.width() * (900 / WIDTH))
    pad = 22 * scale                          # o contorno de 22 px do estilo Title
    step = metrics.height()
    middle = rect.top() + rect.height() * style.resolved_title_position() / 100
    first = middle - step * len(lines) / 2
    colour = QColor("#141414") if is_light(style.highlight_color) else QColor("#FFFFFF")
    for index, line in enumerate(lines):
        width = metrics.horizontalAdvance(line)
        box = QRectF(rect.left() + (rect.width() - width) / 2, first + index * step, width, step)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(style.highlight_color))
        painter.drawRect(box.adjusted(-pad, -pad / 2, pad, pad / 2))
    painter.setPen(colour)
    for index, line in enumerate(lines):
        painter.drawText(QRectF(rect.left(), first + index * step, rect.width(), step),
                         Qt.AlignmentFlag.AlignCenter, line)


def _paint_caption(painter: QPainter, rect: QRectF, scale: float, state: PreviewState) -> None:
    """O grupo com a segunda palavra sendo falada, como na animação escolhida."""
    style = state.style
    words = [w.upper() if style.uppercase else w for w in PREVIEW_WORDS[:style.words]]
    active = min(1, len(words) - 1)
    if style.animation == "word":
        words, active = [words[active]], 0
    grow = style.animation in {"highlight", "pop"}
    base = _bold(style, style.size * scale)
    big = _bold(style, style.size * (1.12 if grow else 1) * scale)
    space = QFontMetricsF(base).horizontalAdvance(" ")
    fonts = [big if i == active else base for i in range(len(words))]
    advances = [QFontMetricsF(font).horizontalAdvance(word)
                for font, word in zip(fonts, words, strict=True)]
    line_width = sum(advances) + space * (len(words) - 1)
    x = rect.left() + (rect.width() - line_width) / 2
    middle = rect.top() + rect.height() * state.caption_position() / 100
    baseline = middle + QFontMetricsF(base).ascent() / 2 - 1
    if style.background:
        pad = max(2.0, style.size / 5 * scale)
        box_h = QFontMetricsF(base).height()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 160))
        painter.drawRect(QRectF(x - pad, middle - box_h / 2 - pad / 2,
                                line_width + 2 * pad, box_h + pad))
    outline = QPen(QColor("#000000"), max(0.8, style.size / 12 * scale * 2))
    outline.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    for index, word in enumerate(words):
        if style.animation in {"none", "word"}:
            colour = style.text_color
        elif style.animation == "karaoke":
            colour = style.highlight_color if index <= active else style.text_color
        else:
            colour = style.highlight_color if index == active else style.text_color
        path = QPainterPath()
        path.addText(QPointF(x, baseline), fonts[index], word)
        if not style.background:
            painter.strokePath(path, outline)
        painter.fillPath(path, QColor(colour))
        x += advances[index] + space


def paint_vertical(painter: QPainter, rect: QRectF, state: PreviewState,
                   radius: float = 14) -> None:
    """O corte 9:16 em miniatura dentro de ``rect``: vídeo, título e legenda."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if rect.width() < DRAW_WIDTH:
        factor = rect.width() / DRAW_WIDTH
        painter.translate(rect.topLeft())
        painter.scale(factor, factor)
        rect = QRectF(0, 0, DRAW_WIDTH, rect.height() / factor)
        radius /= factor
    outline = QPainterPath()
    outline.addRoundedRect(rect, radius, radius)
    painter.setClipPath(outline)
    scale = rect.height() / HEIGHT
    top = BANNER_HEIGHT * scale if state.banner else 0.0
    area = QRectF(rect.left(), rect.top() + top, rect.width(),
                  video_height(state.banner) * scale)
    _paint_video(painter, area, state.framing, state.frame)
    if state.banner:
        _paint_banner(painter, rect, scale, state)
    else:
        _paint_title(painter, rect, scale, state)
    _paint_caption(painter, rect, scale, state)
    painter.restore()


# ----------------------------------------------------------------- widgets

class CaptionPreview(QWidget):
    """Tela de celular em miniatura: mostra o corte como vai sair e aceita arrastar.

    Com um arquivo local escolhido, o fundo é um quadro do próprio vídeo, enquadrado como
    no corte (cortado no centro ou inteiro sobre o desfoque).
    """

    position_changed = Signal(int)
    title_position_changed = Signal(int)
    PREVIEW_WIDTH = 190

    def __init__(self, parent=None):
        super().__init__(parent)
        self.state = PreviewState()
        self._dragging_title = False
        self.setFixedSize(self.PREVIEW_WIDTH, round(self.PREVIEW_WIDTH * HEIGHT / WIDTH))
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(tr("Arraste a legenda ou o título para cima ou para baixo"))
        self.setAccessibleName(tr("Prévia do corte"))

    # Atalhos usados pela página e pelos testes.
    @property
    def caption(self) -> CaptionStyle:
        return self.state.style

    @property
    def framing(self) -> str:
        return self.state.framing

    @property
    def frame(self) -> QImage:
        return self.state.frame

    def set_style(self, style: CaptionStyle) -> None:
        self.state.style = style.normalized()
        self.update()

    def set_framing(self, framing: str) -> None:
        self.state.framing = framing
        self.update()

    def set_banner(self, banner: bool) -> None:
        self.state.banner = banner
        self.setToolTip(tr("Arraste a legenda para cima ou para baixo") if banner
                        else tr("Arraste a legenda ou o título para cima ou para baixo"))
        self.update()

    def set_texts(self, title: str, label: str) -> None:
        self.state.title, self.state.label = title.strip(), label.strip()
        self.update()

    def set_frame(self, image: QImage) -> None:
        self.state.frame = image
        self.update()

    def _move_to(self, y: float) -> None:
        value = round(y / max(1, self.height()) * 100)
        if self._dragging_title:
            self.title_position_changed.emit(max(TITLE_MIN, min(TITLE_MAX, value)))
        else:
            low = BANNER_CAPTION_MIN if self.state.banner else POSITION_MIN
            self.position_changed.emit(max(low, min(POSITION_MAX, value)))

    def mousePressEvent(self, event):  # noqa: N802 - assinatura do Qt
        if event.button() == Qt.MouseButton.LeftButton:
            # Clicou perto do título: arrasta o título; no resto, a legenda. O título fixo
            # no topo não se move.
            y = event.position().y() / max(1, self.height()) * 100
            title = self.caption.resolved_title_position()
            self._dragging_title = (not self.state.banner
                                    and abs(y - title) < abs(y - self.caption.position))
            self._move_to(event.position().y())

    def mouseMoveEvent(self, event):  # noqa: N802 - assinatura do Qt
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_to(event.position().y())

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        frame = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        paint_vertical(painter, frame, self.state)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(theme.qcolor("border_strong"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(frame, 14, 14)


class ChoiceCard(QAbstractButton):
    """Cartão clicável com a miniatura do corte e um nome curto embaixo."""

    PHONE = QSize(60, 107)

    def __init__(self, title: str, subtitle: str, value: str, look: dict,
                 state: PreviewState, parent=None):
        super().__init__(parent)
        self.value = value
        self.look = look                 # o que esta opção muda na prévia
        self.state = state               # a prévia grande (o resto vem dela)
        self._title, self._subtitle = tr(title), tr(subtitle)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(self._title)
        self.setAccessibleDescription(self._subtitle)
        self.setToolTip(f"{self._title}: {self._subtitle}")

    def sizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        return QSize(124, self.PHONE.height() + 66)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - assinatura do Qt
        return QSize(96, self.PHONE.height() + 66)

    def keyPressEvent(self, event: QKeyEvent):  # noqa: N802 - assinatura do Qt
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Right: 1}.get(Qt.Key(event.key()), 0)
        group = self.group()
        if step and group is not None:
            buttons = group.buttons()
            target = buttons[(buttons.index(self) + step) % len(buttons)]
            target.setFocus(Qt.FocusReason.TabFocusReason)
            target.click()
            return
        super().keyPressEvent(event)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        box = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        selected = self.isChecked()
        hovered = self.underMouse() or self.hasFocus()
        painter.setPen(QPen(theme.qcolor("accent" if selected or self.hasFocus()
                                         else "border"), 2 if selected else 1))
        painter.setBrush(theme.qcolor("accent_soft") if selected
                         else theme.qcolor("surface_hover" if hovered else "surface"))
        painter.drawRoundedRect(box, theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
        phone = QRectF((self.width() - self.PHONE.width()) / 2, 10, self.PHONE.width(),
                       self.PHONE.height())
        paint_vertical(painter, phone, replace(self.state, **self.look), radius=7)
        painter.setPen(QPen(theme.qcolor("border_strong"), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(phone, 7, 7)
        title_font = theme.font(12, 600)
        painter.setFont(title_font)
        painter.setPen(theme.qcolor("accent_text" if selected else "text"))
        line = QRectF(4, phone.bottom() + 8, self.width() - 8, 18)
        painter.drawText(line, Qt.AlignmentFlag.AlignCenter,
                         QFontMetricsF(title_font).elidedText(
                             self._title, Qt.TextElideMode.ElideRight, line.width()))
        small = theme.font(11)
        painter.setFont(small)
        painter.setPen(theme.qcolor("text_secondary"))
        line = QRectF(4, line.bottom() + 1, self.width() - 8, 16)
        painter.drawText(line, Qt.AlignmentFlag.AlignCenter,
                         QFontMetricsF(small).elidedText(
                             self._subtitle, Qt.TextElideMode.ElideRight, line.width()))

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class ChoicePicker(QWidget):
    """Uma fileira de ``ChoiceCard``: escolha única, como botões de opção com figura."""

    changed = Signal(str)

    def __init__(self, choices: list[tuple[str, str, str, dict]], state: PreviewState,
                 parent=None):
        super().__init__(parent)
        line = QHBoxLayout(self)
        line.setContentsMargins(0, 0, 0, 0)
        line.setSpacing(10)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.cards: list[ChoiceCard] = []
        for title, subtitle, value, look in choices:
            card = ChoiceCard(title, subtitle, value, look, state, self)
            self.group.addButton(card)
            self.cards.append(card)
            line.addWidget(card)
        line.addStretch(1)
        self.cards[0].setChecked(True)
        self.group.buttonToggled.connect(self._toggled)

    def _toggled(self, card, checked: bool) -> None:
        if checked:
            self.changed.emit(card.value)

    def value(self) -> str:
        checked = self.group.checkedButton()
        return checked.value if isinstance(checked, ChoiceCard) else self.cards[0].value

    def set_value(self, value: str) -> None:
        for card in self.cards:
            if card.value == value:
                card.setChecked(True)
                return

    def refresh(self) -> None:
        for card in self.cards:
            card.update()


class StickyRail(QWidget):
    """Coluna que mantém o conteúdo à vista enquanto a página rola (a prévia do corte)."""

    def __init__(self, content: QWidget, parent=None):
        super().__init__(parent)
        self.content = content
        content.setParent(self)
        content.adjustSize()
        self.setFixedWidth(content.width())
        self.setMinimumHeight(content.height())
        self._area = None

    def follow(self, scroll_area) -> None:
        self._area = scroll_area
        scroll_area.verticalScrollBar().valueChanged.connect(self.place)

    def place(self, *_args) -> None:
        offset = 0
        if self._area is not None and self._area.widget() is not None \
                and self._area.widget().isAncestorOf(self):
            top = self.mapTo(self._area.widget(), QPoint(0, 0)).y()
            offset = self._area.verticalScrollBar().value() + 12 - top
        offset = max(0, min(offset, self.height() - self.content.height()))
        self.content.move(0, int(offset))

    def resizeEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().resizeEvent(event)
        self.place()
