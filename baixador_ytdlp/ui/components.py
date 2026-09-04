"""Componentes da interface: os tijolos com que todas as telas são montadas.

Cada peça segue o mesmo par de referências do módulo `theme`: o comportamento
e o formato vêm da Apple (interruptores em cápsula, listas agrupadas com
separadores finos, títulos grandes), a cor e a densidade vêm do Discord.

Nenhum componente aqui conhece regra de negócio — todos recebem texto e sinais
e devolvem widgets. Isso mantém a reformulação visual isolada da lógica.
"""
from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QComboBox, QFrame, QGraphicsOpacityEffect,
                               QHBoxLayout, QLabel, QLineEdit, QListView, QPlainTextEdit,
                               QProgressBar, QSizePolicy, QSpinBox, QVBoxLayout, QWidget)
from qfluentwidgets import SmoothScrollArea

from . import icons, theme


# ============================================================== textos

def _label(text: str, font, object_name: str = "", parent=None,
           wrap: bool = False) -> QLabel:
    label = QLabel(text, parent)
    label.setFont(font)
    if object_name:
        label.setObjectName(object_name)
    if wrap:
        label.setWordWrap(True)
    return label


def LargeTitle(text: str = "", parent=None) -> QLabel:
    return _label(text, theme.large_title(), "largeTitle", parent)


def Title(text: str = "", parent=None) -> QLabel:
    return _label(text, theme.title(), "title", parent)


def Headline(text: str = "", parent=None, wrap: bool = False) -> QLabel:
    return _label(text, theme.headline(), "headline", parent, wrap)


def Body(text: str = "", parent=None, wrap: bool = False) -> QLabel:
    return _label(text, theme.body(), "body", parent, wrap)


def Callout(text: str = "", parent=None, wrap: bool = False) -> QLabel:
    return _label(text, theme.callout(), "body", parent, wrap)


def Muted(text: str = "", parent=None, wrap: bool = True) -> QLabel:
    return _label(text, theme.footnote(), "muted", parent, wrap)


def Hint(text: str = "", parent=None, wrap: bool = True) -> QLabel:
    return _label(text, theme.caption(), "hint", parent, wrap)


def SectionLabel(text: str = "", parent=None) -> QLabel:
    """Rótulo de seção em caixa alta — a assinatura tipográfica do Discord."""
    return _label(text.upper(), theme.section_label(), "sectionLabel", parent)


class Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rowSeparator")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


# ============================================================== botões

_VARIANTS = {
    "primary": ("btnPrimary", "on_accent"),
    "secondary": ("btnSecondary", "text"),
    "ghost": ("btnGhost", "text_secondary"),
    "danger": ("btnDanger", "on_accent"),
}


class Button(QAbstractButton):
    """Botão de texto com ícone opcional. O visual todo vem do QSS por objectName."""

    def __init__(self, text: str = "", icon_name: str = "", variant: str = "secondary",
                 parent=None):
        super().__init__(parent)
        object_name, tone = _VARIANTS.get(variant, _VARIANTS["secondary"])
        self._icon_name = icon_name
        self._tone = tone
        self.setObjectName(object_name)
        self.setText(text)
        self.setFont(theme.callout())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(theme.CONTROL_HEIGHT)
        # QAbstractButton nem sempre repinta sozinho ao mudar de estado pressionado.
        self.pressed.connect(self.update)
        self.released.connect(self.update)

    # O desenho é manual para que ícone e rótulo fiquem opticamente centrados,
    # o que o par QPushButton+QSS não garante quando há ícone.
    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        width = metrics.horizontalAdvance(self.text()) + 32
        if self._icon_name:
            width += 24
        return QSize(max(width, 76), theme.CONTROL_HEIGHT)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        fill, text_color = self._colors()
        if fill is not None:
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                    theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)
        if self._border_color() is not None:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(self._border_color(), 1))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5),
                                    theme.RADIUS_CONTROL, theme.RADIUS_CONTROL)

        metrics = QFontMetrics(self.font())
        text_width = metrics.horizontalAdvance(self.text())
        icon_size = 16
        gap = 8 if (self._icon_name and self.text()) else 0
        total = text_width + (icon_size + gap if self._icon_name else 0)
        left = (self.width() - total) / 2

        if self._icon_name:
            pixmap = icons.pixmap(self._icon_name, text_color.name(), icon_size)
            painter.drawPixmap(int(left), int((self.height() - icon_size) / 2), pixmap)
            left += icon_size + gap

        painter.setPen(QPen(text_color))
        painter.setFont(self.font())
        painter.drawText(QRectF(left, 0, text_width + 2, self.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.text())

    def _colors(self):
        name = self.objectName()
        enabled = self.isEnabled()
        hovered = self.underMouse() and enabled
        pressed = self.isDown() and enabled
        dark = theme.is_dark()

        if name == "btnPrimary":
            if not enabled:
                return (theme.qcolor("surface_active"), theme.qcolor("text_tertiary"))
            token = "accent_pressed" if pressed else ("accent_hover" if hovered else "accent")
            return (theme.qcolor(token), theme.qcolor("on_accent"))
        if name == "btnDanger":
            if not enabled:
                return (theme.qcolor("surface_active"), theme.qcolor("text_tertiary"))
            token = "danger_hover" if (hovered or pressed) else "danger"
            return (theme.qcolor(token), QColor("#FFFFFF"))
        if name == "btnSecondary":
            if not enabled:
                return (None, theme.qcolor("text_tertiary"))
            if pressed:
                return (theme.qcolor("surface_active"), theme.qcolor("text"))
            base = QColor("#383B42") if dark else QColor("#FFFFFF")
            if hovered:
                base = QColor("#41454E") if dark else QColor("#F4F5F9")
            return (base, theme.qcolor("text"))
        # ghost
        if not enabled:
            return (None, theme.qcolor("text_tertiary"))
        if pressed:
            return (theme.qcolor("surface_active"), theme.qcolor("text"))
        if hovered:
            return (theme.qcolor("surface_hover"), theme.qcolor("text"))
        return (None, theme.qcolor("text_secondary"))

    def _border_color(self):
        if self.objectName() != "btnSecondary":
            return None
        if not self.isEnabled():
            return theme.qcolor("border")
        return theme.qcolor("accent") if self.underMouse() else theme.qcolor("border_strong")

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


def PrimaryButton(text: str = "", icon_name: str = "", parent=None) -> Button:
    return Button(text, icon_name, "primary", parent)


class IconButton(QAbstractButton):
    """Botão quadrado só com ícone — usado nas ações das listas."""

    def __init__(self, icon_name: str, tooltip: str = "", parent=None,
                 size: int = 32, icon_size: int = 18, tone: str = "text_secondary"):
        super().__init__(parent)
        self.setObjectName("iconButton")
        self._icon_name = icon_name
        self._icon_size = icon_size
        self._tone = tone
        self.setFixedSize(size, size)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.pressed.connect(self.update)
        self.released.connect(self.update)
        if tooltip:
            self.setToolTip(tooltip)

    def set_icon_name(self, name: str) -> None:
        self._icon_name = name
        self.update()

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        self.update()

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        if self.isEnabled() and (self.underMouse() or self.isChecked()):
            token = "accent_soft" if self.isChecked() else (
                "surface_active" if self.isDown() else "surface_hover")
            painter.setBrush(theme.qcolor(token))
            painter.drawRoundedRect(QRectF(self.rect()), theme.RADIUS_SMALL,
                                    theme.RADIUS_SMALL)
        tone = self._tone if self.isEnabled() else "text_tertiary"
        if self.isEnabled() and self.underMouse():
            tone = "text" if self._tone == "text_secondary" else self._tone
        pixmap = icons.pixmap(self._icon_name, theme.color(tone), self._icon_size)
        offset = (self.width() - self._icon_size) / 2
        opacity = 1.0 if self.isEnabled() else 0.45
        painter.setOpacity(opacity)
        painter.drawPixmap(int(offset), int(offset), pixmap)

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


# ============================================================== controles

class Switch(QAbstractButton):
    """Interruptor em cápsula, no formato dos ajustes do iOS/macOS."""

    checkedChanged = Signal(bool)  # noqa: N815 - nome mantido para o resto da UI

    TRACK_W, TRACK_H, KNOB = 46, 26, 20

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setFixedSize(self.TRACK_W, self.TRACK_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._offset = 0.0
        self._animation = QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(170)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._on_toggled)

    def _get_offset(self) -> float:
        return self._offset

    def _set_offset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = Property(float, _get_offset, _set_offset)

    def _on_toggled(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._offset)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()
        self.checkedChanged.emit(checked)

    def sizeHint(self) -> QSize:
        return QSize(self.TRACK_W, self.TRACK_H)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        off_track = QColor("#4A4E57") if theme.is_dark() else QColor("#D5D8E0")
        on_track = theme.qcolor("accent")
        track = QColor(
            int(off_track.red() + (on_track.red() - off_track.red()) * self._offset),
            int(off_track.green() + (on_track.green() - off_track.green()) * self._offset),
            int(off_track.blue() + (on_track.blue() - off_track.blue()) * self._offset),
        )
        painter.setOpacity(1.0 if self.isEnabled() else 0.42)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, self.TRACK_W, self.TRACK_H),
                                self.TRACK_H / 2, self.TRACK_H / 2)

        margin = (self.TRACK_H - self.KNOB) / 2
        travel = self.TRACK_W - self.KNOB - margin * 2
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(margin + travel * self._offset, margin,
                                   self.KNOB, self.KNOB))

    # Aceitos por compatibilidade com o resto da UI; um interruptor Apple não
    # carrega rótulo interno, então os textos são deliberadamente ignorados.
    def setOnText(self, _text: str) -> None:  # noqa: N802
        return

    def setOffText(self, _text: str) -> None:  # noqa: N802
        return


class CheckBox(QAbstractButton):
    """Caixa de seleção arredondada, desenhada para casar com o interruptor."""

    BOX, GAP = 19, 10

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setText(text)
        self.setFont(theme.body())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(26)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        metrics = QFontMetrics(self.font())
        return QSize(self.BOX + self.GAP + metrics.horizontalAdvance(self.text()) + 4, 26)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)

        top = (self.height() - self.BOX) / 2
        box = QRectF(0.5, top + 0.5, self.BOX - 1, self.BOX - 1)
        if self.isChecked():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(theme.qcolor("accent"))
            painter.drawRoundedRect(box, 6, 6)
            path = QPainterPath()
            path.moveTo(box.left() + self.BOX * 0.26, box.top() + self.BOX * 0.52)
            path.lineTo(box.left() + self.BOX * 0.43, box.top() + self.BOX * 0.69)
            path.lineTo(box.left() + self.BOX * 0.75, box.top() + self.BOX * 0.32)
            pen = QPen(QColor("#FFFFFF"), 2.0)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)
        else:
            border = theme.qcolor("accent") if self.underMouse() else theme.qcolor("border_strong")
            painter.setPen(QPen(border, 1.6))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 6, 6)

        painter.setPen(QPen(theme.qcolor("text")))
        painter.setFont(self.font())
        painter.drawText(QRectF(self.BOX + self.GAP, 0, self.width(), self.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.text())

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class Select(QComboBox):
    """Lista suspensa com a seta desenhada por nós, no traço dos demais ícones."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("select")
        self.setFont(theme.body())
        self.setView(QListView(self))
        self.view().setFont(theme.body())
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(theme.FIELD_HEIGHT)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContentsOnFirstShow)

    def paintEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setOpacity(1.0 if self.isEnabled() else 0.45)
        pixmap = icons.pixmap("chevron-down", theme.color("text_tertiary"), 16)
        painter.drawPixmap(self.width() - 26, int((self.height() - 16) / 2), pixmap)


class TextField(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setFont(theme.body())
        self.setMinimumHeight(theme.FIELD_HEIGHT)
        if placeholder:
            self.setPlaceholderText(placeholder)


class Stepper(QWidget):
    """Campo numérico com − e + próprios, no lugar das setinhas do sistema."""

    valueChanged = Signal(int)  # noqa: N815 - espelha o QSpinBox

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("stepperHost")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.minus = IconButton("minus", "Diminuir", self, size=30, icon_size=16)
        self.plus = IconButton("plus", "Aumentar", self, size=30, icon_size=16)
        self.spin = QSpinBox(self)
        self.spin.setObjectName("innerSpin")
        self.spin.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.spin.setFont(theme.callout())
        self.spin.setFixedWidth(66)
        self.spin.setMinimumHeight(theme.FIELD_HEIGHT)

        self.minus.clicked.connect(lambda: self.spin.stepBy(-1))
        self.plus.clicked.connect(lambda: self.spin.stepBy(1))
        self.spin.valueChanged.connect(self.valueChanged)

        layout.addWidget(self.minus)
        layout.addWidget(self.spin)
        layout.addWidget(self.plus)

    def setRange(self, low: int, high: int) -> None:  # noqa: N802
        self.spin.setRange(low, high)

    def setValue(self, value: int) -> None:  # noqa: N802
        self.spin.setValue(value)

    def value(self) -> int:
        return self.spin.value()


class ProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTextVisible(False)
        self.setFixedHeight(8)
        self.setRange(0, 100)


class BusyBar(QWidget):
    """Indicador indeterminado: uma cápsula que atravessa a trilha em laço."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._position = 0.18
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def _tick(self) -> None:
        self._position = (self._position + 0.011) % 1.0
        self.update()

    def showEvent(self, event):  # noqa: N802 - assinatura do Qt
        self._timer.start()
        super().showEvent(event)

    def hideEvent(self, event):  # noqa: N802 - assinatura do Qt
        self._timer.stop()
        super().hideEvent(event)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)
        track = QColor(255, 255, 255, 22) if theme.is_dark() else QColor(0, 0, 0, 20)
        painter.setBrush(track)
        painter.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 3, 3)

        span = self.width() * 0.32
        left = -span + self._position * (self.width() + span)
        painter.setBrush(theme.qcolor("accent"))
        painter.drawRoundedRect(QRectF(left, 0, span, self.height()), 3, 3)


class Chip(QLabel):
    """Etiqueta compacta de estado. As cores saem sempre dos tokens do tema."""

    def __init__(self, text: str = "", tone: str = "neutral", parent=None):
        super().__init__(text, parent)
        self.setFont(theme.font(11, 700, 0.2))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(22)
        self.set_tone(tone)

    def set_tone(self, tone: str) -> None:
        self._tone = tone
        mapping = {
            "accent": ("accent", "accent_soft"),
            "success": ("success", None),
            "danger": ("danger", None),
            "warning": ("warning", None),
            "neutral": ("text_tertiary", None),
        }
        token, soft = mapping.get(tone, mapping["neutral"])
        foreground = theme.color(token)
        if soft:
            background = theme.color(soft)
        else:
            base = theme.qcolor(token)
            background = f"rgba({base.red()}, {base.green()}, {base.blue()}, 0.16)"
        self.setStyleSheet(
            f"color: {foreground}; background-color: {background};"
            f" border-radius: 11px; padding: 0 10px;"
        )


# ============================================================== estruturas

class Card(QFrame):
    """Superfície arredondada padrão. `flat=True` para um contorno sem preenchimento."""

    def __init__(self, parent=None, flat: bool = False, padding=(16, 14, 16, 14),
                 spacing: int = 10, horizontal: bool = False):
        super().__init__(parent)
        self.setObjectName("cardFlat" if flat else "card")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(spacing)


class ListRow(QFrame):
    """Linha destacável de uma lista (fila, histórico). Realça ao passar o mouse."""

    def __init__(self, parent=None, padding=(16, 12, 12, 12), spacing: int = 12,
                 horizontal: bool = True):
        super().__init__(parent)
        self.setObjectName("listRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.body = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        self.body.setContentsMargins(*padding)
        self.body.setSpacing(spacing)


class SettingRow(QWidget):
    """Linha de ajuste: título, explicação e o controle à direita."""

    def __init__(self, title: str, subtitle: str = "", control: QWidget | None = None,
                 parent=None):
        super().__init__(parent)
        self.setObjectName("settingRow")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(18)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = Headline(title, self, wrap=True)
        texts.addWidget(self.title)
        if subtitle:
            self.subtitle = Muted(subtitle, self)
            texts.addWidget(self.subtitle)
        layout.addLayout(texts, 1)
        if control is not None:
            layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)


class InsetGroup(QFrame):
    """Lista agrupada da Apple: um único bloco arredondado com linhas finas dentro.

    Substitui o padrão anterior de um cartão flutuante por opção, que empilhava
    dezenas de retângulos e deixava a página de Configurações ruidosa.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("insetGroup")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 0, 0, 0)
        self._column.setSpacing(0)
        self._rows = 0

    def add_row(self, row: QWidget) -> QWidget:
        if self._rows:
            holder = QWidget(self)
            inner = QHBoxLayout(holder)
            inner.setContentsMargins(16, 0, 0, 0)
            inner.addWidget(Divider(holder))
            self._column.addWidget(holder)
        self._column.addWidget(row)
        self._rows += 1
        return row


class PageHeader(QWidget):
    """Cabeçalho de página: título grande, subtítulo e ações alinhadas à direita."""

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        self.title = LargeTitle(title, self)
        texts.addWidget(self.title)
        self.subtitle = Muted(subtitle, self)
        self.subtitle.setObjectName("pageSubtitle")
        self.subtitle.setVisible(bool(subtitle))
        texts.addWidget(self.subtitle)
        layout.addLayout(texts, 1)

        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        layout.addLayout(self.actions, 0)

    def add_action(self, widget: QWidget) -> QWidget:
        self.actions.addWidget(widget, 0, Qt.AlignmentFlag.AlignVCenter)
        return widget


class EmptyState(QWidget):
    """Estado vazio com ícone em disco, título e uma frase de orientação."""

    def __init__(self, icon_name: str, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 40, 24, 40)
        layout.setSpacing(12)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        badge = QLabel(self)
        badge.setFixedSize(64, 64)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icons.pixmap(icon_name, theme.color("text_tertiary"), 28))
        badge.setStyleSheet(
            f"background-color: {theme.color('accent_soft')}; border-radius: 32px;")
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignHCenter)

        heading = Headline(title, self)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(heading)

        if subtitle:
            caption = Muted(subtitle, self)
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setMaximumWidth(420)
            layout.addWidget(caption, 0, Qt.AlignmentFlag.AlignHCenter)


class ScrollColumn(SmoothScrollArea):
    """Coluna rolável com fundo transparente — a base de quase todas as páginas."""

    def __init__(self, parent=None, spacing: int = 12, margins=(0, 4, 12, 8)):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.body = QWidget(self)
        self.body.setObjectName("page")
        self.column = QVBoxLayout(self.body)
        self.column.setContentsMargins(*margins)
        self.column.setSpacing(spacing)
        self.setWidget(self.body)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.column.addWidget(widget, stretch)
        return widget

    def add_layout(self, layout) -> None:
        self.column.addLayout(layout)

    def add_stretch(self) -> None:
        self.column.addStretch(1)


class LogView(QPlainTextEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("logView")
        self.setReadOnly(True)
        self.setFont(theme.mono())
        self.setMaximumBlockCount(500)
        self.setFrameShape(QFrame.Shape.NoFrame)
        if placeholder:
            self.setPlaceholderText(placeholder)


# ============================================================== avisos

class Toast(QFrame):
    """Aviso flutuante no canto superior direito.

    Empilha até quatro mensagens, some sozinho e nunca bloqueia a janela — no
    lugar do balão do Fluent, que trazia a paleta e os ícones da Microsoft.
    """

    MAX_VISIBLE = 4
    WIDTH = 372
    MARGIN = 18
    GAP = 10

    _TONES = {
        "success": ("success", "success"),
        "error": ("error", "danger"),
        "warning": ("warning", "warning"),
        "info": ("info", "accent"),
    }

    def __init__(self, kind: str, title: str, message: str, parent: QWidget,
                 duration: int = 5000):
        super().__init__(parent)
        icon_name, tone = self._TONES.get(kind, self._TONES["info"])
        self.setObjectName("toast")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(self.WIDTH)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 13, 10, 13)
        layout.setSpacing(12)

        badge = QLabel(self)
        badge.setFixedSize(22, 22)
        badge.setPixmap(icons.pixmap(icon_name, theme.color(tone), 20))
        layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignTop)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(Headline(title, self, wrap=True))
        if message:
            texts.addWidget(Muted(message, self))
        layout.addLayout(texts, 1)

        close = IconButton("close", "Fechar", self, size=26, icon_size=14)
        close.clicked.connect(self.dismiss)
        layout.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)

        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(0.0)
        self.setGraphicsEffect(self._effect)
        self._fade = QPropertyAnimation(self._effect, b"opacity", self)
        self._fade.setDuration(160)

        self._closing = False
        parent.installEventFilter(self)
        QTimer.singleShot(max(1200, duration), self.dismiss)

    # ---------------------------------------------------------- ciclo de vida
    @classmethod
    def _stack(cls, parent: QWidget) -> list:
        existing = getattr(parent, "_toast_stack", None)
        if existing is None:
            existing = []
            parent._toast_stack = existing
        return existing

    @classmethod
    def show_message(cls, kind: str, title: str, message: str = "",
                     parent: QWidget | None = None, duration: int = 5000):
        if parent is None:
            return None
        stack = cls._stack(parent)
        alive = [item for item in stack if not item._closing]
        for old in alive[:max(0, len(alive) - cls.MAX_VISIBLE + 1)]:
            old.dismiss()
        toast = cls(kind, title, message, parent, duration)
        stack.append(toast)
        toast.adjustSize()
        toast.show()
        toast.raise_()
        cls._relayout(parent)
        toast._fade.stop()
        toast._fade.setStartValue(0.0)
        toast._fade.setEndValue(1.0)
        toast._fade.start()
        return toast

    @classmethod
    def success(cls, title, message="", parent=None, duration=5000):
        return cls.show_message("success", title, message, parent, duration)

    @classmethod
    def error(cls, title, message="", parent=None, duration=8000):
        return cls.show_message("error", title, message, parent, duration)

    @classmethod
    def warning(cls, title, message="", parent=None, duration=5000):
        return cls.show_message("warning", title, message, parent, duration)

    @classmethod
    def info(cls, title, message="", parent=None, duration=5000):
        return cls.show_message("info", title, message, parent, duration)

    @classmethod
    def _relayout(cls, parent: QWidget) -> None:
        """Empilha no alto e ao centro do painel de conteúdo.

        O canto superior direito parecia o lugar óbvio, mas é justamente onde
        ficam as ações do cabeçalho ("Limpar concluídos", "Limpar tudo"): um
        aviso ali tapa o botão que a pessoa acabou de procurar. Centralizado, o
        aviso flutua sobre área vazia em todas as páginas.
        """
        left = theme.SIDEBAR_WIDTH + max(
            0, (parent.width() - theme.SIDEBAR_WIDTH - cls.WIDTH) // 2)
        top = theme.TITLEBAR_HEIGHT + cls.MARGIN
        for toast in list(cls._stack(parent)):
            if toast._closing:
                continue
            toast.adjustSize()
            toast.move(left, top)
            toast.raise_()
            top += toast.height() + cls.GAP

    def dismiss(self) -> None:
        if self._closing:
            return
        self._closing = True
        self._fade.stop()
        self._fade.setStartValue(self._effect.opacity())
        self._fade.setEndValue(0.0)
        self._fade.finished.connect(self._finalize)
        self._fade.start()

    def _finalize(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            stack = self._stack(parent)
            if self in stack:
                stack.remove(self)
            parent.removeEventFilter(self)
            self.__class__._relayout(parent)
        self.hide()
        self.deleteLater()

    def eventFilter(self, watched, event):  # noqa: N802 - assinatura do Qt
        if event.type() == QEvent.Type.Resize and watched is self.parentWidget():
            self.__class__._relayout(watched)
        return super().eventFilter(watched, event)
