"""Casca da janela: barra de título unificada e navegação lateral recolhível."""
from __future__ import annotations

import sys

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QSizePolicy,
                               QStackedWidget, QVBoxLayout, QWidget)

from . import icons, theme
from .components import Chip, IconButton, SectionLabel

try:  # o qfluentwidgets já traz o qframelesswindow como dependência
    from qframelesswindow import FramelessWindow as _Base
except Exception:  # pragma: no cover - fallback defensivo
    _Base = QWidget


class CaptionButton(QAbstractButton):
    """Botão de moldura com os três glifos desenhados na mesma métrica.

    O qframelesswindow usa um SVG escalável para fechar e traços de tamanho
    fixo para minimizar/maximizar. Ao aumentar a barra de título, o ``X`` ficava
    visivelmente maior que os outros símbolos. Este componente substitui os
    três no Windows e mantém peso, dimensão e posição idênticos.
    """

    WIDTH = 46

    def __init__(self, action: str, parent=None):
        super().__init__(parent)
        self.action = action
        self.setFixedSize(self.WIDTH, theme.TITLEBAR_HEIGHT)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setToolTip({"minimize": "Minimizar", "maximize": "Maximizar", "close": "Fechar"}[action])
        self.pressed.connect(self.update)
        self.released.connect(self.update)
        self.clicked.connect(self._activate)

    def _activate(self) -> None:
        window = self.window()
        if self.action == "minimize":
            window.showMinimized()
        elif self.action == "maximize":
            window.showNormal() if window.isMaximized() else window.showMaximized()
            self.update()
        else:
            window.close()

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        hovered = self.underMouse()
        pressed = self.isDown()
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            if self.action == "close":
                painter.setBrush(theme.qcolor("danger_hover" if pressed else "danger"))
            else:
                painter.setBrush(theme.qcolor("surface_active" if pressed else "surface_hover"))
            painter.drawRect(self.rect())

        tone = QColor("#FFFFFF") if self.action == "close" and hovered else theme.qcolor("text_secondary")
        pen = QPen(tone, 1.35)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        pen.setCosmetic(True)
        painter.setPen(pen)
        center_x, center_y = self.width() / 2, self.height() / 2
        if self.action == "minimize":
            painter.drawLine(int(center_x - 5), int(center_y), int(center_x + 5), int(center_y))
        elif self.action == "maximize":
            if self.window().isMaximized():
                painter.drawRect(int(center_x - 4), int(center_y - 3), 8, 8)
                painter.drawLine(int(center_x - 2), int(center_y - 5), int(center_x + 5), int(center_y - 5))
                painter.drawLine(int(center_x + 5), int(center_y - 5), int(center_x + 5), int(center_y + 2))
            else:
                painter.drawRect(int(center_x - 5), int(center_y - 5), 10, 10)
        else:
            painter.drawLine(int(center_x - 5), int(center_y - 5), int(center_x + 5), int(center_y + 5))
            painter.drawLine(int(center_x + 5), int(center_y - 5), int(center_x - 5), int(center_y + 5))

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class CaptionControls(QWidget):
    """Grupo compacto de minimizar, maximizar/restaurar e fechar."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.buttons = [CaptionButton(action, self) for action in ("minimize", "maximize", "close")]
        for button in self.buttons:
            layout.addWidget(button)

    def refresh(self) -> None:
        for button in self.buttons:
            button.update()


class NavItem(QAbstractButton):
    """Item lateral com rótulo no modo amplo e ícone no modo compacto."""

    HEIGHT = 40

    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._compact = False
        self.setText(text)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self.HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggled.connect(self.update)
        self.pressed.connect(self.update)
        self.released.connect(self.update)

    def set_compact(self, compact: bool) -> None:
        self._compact = compact
        self.setToolTip(self.text() if compact else "")
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        width = theme.SIDEBAR_COLLAPSED_WIDTH if self._compact else theme.SIDEBAR_WIDTH
        return QSize(width, self.HEIGHT)

    def paintEvent(self, _event):  # noqa: N802 - assinatura do Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setPen(Qt.PenStyle.NoPen)

        active = self.isChecked()
        hovered = self.underMouse()
        pill = QRectF(8, 2, self.width() - 16, self.height() - 4)
        if active:
            painter.setBrush(theme.qcolor("accent_soft"))
            painter.drawRoundedRect(pill, 9, 9)
        elif hovered:
            painter.setBrush(theme.qcolor("surface_hover"))
            painter.drawRoundedRect(pill, 9, 9)

        if active:
            painter.setBrush(theme.qcolor("accent"))
            painter.drawRoundedRect(
                QRectF(0, (self.height() - 20) / 2, 3.5, 20), 2, 2)

        icon_tone = "accent" if active else ("text" if hovered else "text_secondary")
        icon_x = int((self.width() - 18) / 2) if self._compact else 20
        painter.drawPixmap(icon_x, int((self.height() - 18) / 2),
                           icons.pixmap(self._icon_name, theme.color(icon_tone), 18))

        if self._compact:
            return
        painter.setFont(theme.font(13, 600 if active else 500))
        painter.setPen(QPen(theme.qcolor(
            "text" if (active or hovered) else "text_secondary")))
        painter.drawText(QRectF(50, 0, self.width() - 60, self.height()),
                         int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                         self.text())

    def enterEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.update()
        super().leaveEvent(event)


class Sidebar(QWidget):
    """Navegação lateral que pode recolher sem ocultar páginas ou atalhos."""

    collapsedChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._collapsed = False
        self._sections: list[QLabel] = []
        self._items: list[NavItem] = []
        self.setFixedWidth(theme.SIDEBAR_WIDTH)

        self._column = QVBoxLayout(self)
        self._column.setContentsMargins(0, 8, 0, 12)
        self._column.setSpacing(2)

        header = QWidget(self)
        header.setFixedHeight(38)
        self._header_layout = QHBoxLayout(header)
        self._header_layout.setContentsMargins(14, 0, 14, 0)
        self._header_layout.setSpacing(0)
        self.toggle = IconButton("sidebar-collapse", "Recolher navegação", header,
                                 size=32, icon_size=18)
        self.toggle.clicked.connect(self.toggle_collapsed)
        self._header_layout.addWidget(self.toggle)
        self._header_layout.addStretch(1)
        self._column.addWidget(header)
        self._top_count = 1
        self._column.addStretch(1)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def set_collapsed(self, collapsed: bool, emit: bool = True) -> None:
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        width = theme.SIDEBAR_COLLAPSED_WIDTH if collapsed else theme.SIDEBAR_WIDTH
        self.setFixedWidth(width)
        margin = 16 if collapsed else 14
        self._header_layout.setContentsMargins(margin, 0, margin, 0)
        self.toggle.set_icon_name("sidebar-expand" if collapsed else "sidebar-collapse")
        self.toggle.setToolTip("Expandir navegação" if collapsed else "Recolher navegação")
        for label in self._sections:
            label.setVisible(not collapsed)
        for item in self._items:
            item.set_compact(collapsed)
        if emit:
            self.collapsedChanged.emit(collapsed)

    def add_section(self, text: str) -> QLabel:
        label = SectionLabel(text, self)
        label.setContentsMargins(20, 12, 20, 6)
        label.setVisible(not self._collapsed)
        self._column.insertWidget(self._top_count, label)
        self._top_count += 1
        self._sections.append(label)
        return label

    def add_item(self, item: NavItem, bottom: bool = False) -> NavItem:
        item.set_compact(self._collapsed)
        if bottom:
            self._column.addWidget(item)
        else:
            self._column.insertWidget(self._top_count, item)
            self._top_count += 1
        self._items.append(item)
        return item


class AppShell(_Base):
    """Janela sem moldura nativa com barra unificada e navegação lateral."""

    sidebar_collapsed_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("appShell")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._nav_items: dict[QWidget, NavItem] = {}
        self._sidebar_auto_compact = False
        self._sidebar_before_auto = False

        self._setup_title_bar()

        root = QHBoxLayout(self)
        root.setContentsMargins(0, theme.TITLEBAR_HEIGHT, 0, 0)
        root.setSpacing(0)

        self.sidebar = Sidebar(self)
        self.sidebar.collapsedChanged.connect(self.sidebar_collapsed_changed)
        self.sidebar.collapsedChanged.connect(self._remember_manual_sidebar_choice)
        root.addWidget(self.sidebar)

        self.contentArea = QWidget(self)
        self.contentArea.setObjectName("contentArea")
        self.contentArea.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.contentLayout = QVBoxLayout(self.contentArea)
        self.contentLayout.setContentsMargins(0, 0, 0, 0)
        self.contentLayout.setSpacing(0)

        self.stackedWidget = QStackedWidget(self.contentArea)
        self.contentLayout.addWidget(self.stackedWidget, 1)
        root.addWidget(self.contentArea, 1)

        title_bar = getattr(self, "titleBar", None)
        if title_bar is not None:
            title_bar.raise_()

    # ------------------------------------------------------------ barra de título
    def _setup_title_bar(self) -> None:
        title_bar = getattr(self, "titleBar", None)
        if title_bar is None:
            return
        title_bar.setFixedHeight(theme.TITLEBAR_HEIGHT)
        title_bar.setObjectName("titleBarHost")

        self.brand_icon = QLabel(title_bar)
        self.brand_icon.setFixedSize(20, 20)
        self.brand_name = QLabel(title_bar)
        self.brand_name.setFont(theme.font(13, 600))
        self.brand_version = Chip("", "neutral", title_bar)

        brand = QWidget(title_bar)
        brand.setObjectName("brandBlock")
        row = QHBoxLayout(brand)
        row.setContentsMargins(18, 0, 0, 0)
        row.setSpacing(9)
        row.addWidget(self.brand_icon)
        row.addWidget(self.brand_name)
        row.addWidget(self.brand_version)

        layout = getattr(title_bar, "hBoxLayout", None)
        if layout is not None:
            layout.insertWidget(0, brand, 0, Qt.AlignmentFlag.AlignVCenter)

        for name in ("minBtn", "maxBtn", "closeBtn"):
            button = getattr(title_bar, name, None)
            if button is not None:
                button.setFixedHeight(theme.TITLEBAR_HEIGHT)
                button.setFixedWidth(46)
                button.show()

        # Apenas no Windows: a versão do qframelesswindow presente na build
        # desenha o fechar via SVG escalado e os demais via linhas fixas. Isso
        # explica o X maior observado na barra personalizada.
        if sys.platform.startswith("win") and layout is not None:
            for name in ("minBtn", "maxBtn", "closeBtn"):
                button = getattr(title_bar, name, None)
                if button is not None:
                    button.hide()
            self.caption_controls = CaptionControls(title_bar)
            layout.addWidget(self.caption_controls, 0, Qt.AlignmentFlag.AlignRight)
        else:
            self.caption_controls = None
        self.refresh_title_bar_colors()

    def refresh_title_bar_colors(self) -> None:
        """Reaplica as cores dos botões da janela quando o tema muda."""
        title_bar = getattr(self, "titleBar", None)
        if title_bar is None:
            return
        # Faz o próprio qframelesswindow redesenhar os glifos de minimizar,
        # maximizar e fechar ao alternar o tema. Sem isso, algumas versões
        # deixam os ícones claros no tema claro (ou escuros no tema escuro).
        set_dark = getattr(title_bar, "setDarkTheme", None)
        if callable(set_dark):
            try:
                set_dark(theme.is_dark())
            except Exception:  # noqa: BLE001 - API varia entre versões
                pass
        normal = theme.qcolor("text_secondary")
        hover_background = theme.qcolor("surface_hover")
        for name in ("minBtn", "maxBtn"):
            button = getattr(title_bar, name, None)
            if button is None:
                continue
            for setter, value in (("setNormalColor", normal),
                                  ("setHoverColor", theme.qcolor("text")),
                                  ("setPressedColor", theme.qcolor("text")),
                                  ("setHoverBackgroundColor", hover_background),
                                  ("setPressedBackgroundColor",
                                   theme.qcolor("surface_active"))):
                function = getattr(button, setter, None)
                if callable(function):
                    try:
                        function(value)
                    except Exception:  # noqa: BLE001 - versões antigas do widget
                        pass
        close_button = getattr(title_bar, "closeBtn", None)
        if close_button is not None:
            for setter, value in (("setNormalColor", normal),
                                  ("setHoverColor", QColor("#FFFFFF")),
                                  ("setPressedColor", QColor("#FFFFFF")),
                                  ("setHoverBackgroundColor", theme.qcolor("danger")),
                                  ("setPressedBackgroundColor",
                                   theme.qcolor("danger_hover"))):
                function = getattr(close_button, setter, None)
                if callable(function):
                    try:
                        function(value)
                    except Exception:  # noqa: BLE001
                        pass
        if self.caption_controls is not None:
            self.caption_controls.refresh()

    def set_brand(self, name: str, version: str, icon=None) -> None:
        self.brand_name.setText(name)
        self.brand_version.setText(version)
        self.brand_version.set_tone("neutral")
        if icon is not None and not icon.isNull():
            self.brand_icon.setPixmap(icon.pixmap(QSize(20, 20)))
            self.brand_icon.show()
        else:
            self.brand_icon.hide()

    # ---------------------------------------------------------------- navegação
    def set_sidebar_collapsed(self, collapsed: bool) -> None:
        self.sidebar.set_collapsed(collapsed, emit=False)

    def _remember_manual_sidebar_choice(self, collapsed: bool) -> None:
        if self._sidebar_auto_compact:
            self._sidebar_before_auto = bool(collapsed)

    def resizeEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().resizeEvent(event)
        if not hasattr(self, "sidebar"):
            return
        # Quando a janela fica estreita, manter só os ícones da navegação deixa
        # a área principal utilizável. Ao voltar a ampliar, respeitamos a
        # preferência que a pessoa tinha antes da contração.
        compact = self.width() < 920
        if compact and not self._sidebar_auto_compact:
            self._sidebar_auto_compact = True
            self._sidebar_before_auto = self.sidebar.collapsed
            self.sidebar.set_collapsed(True, emit=False)
        elif not compact and self._sidebar_auto_compact:
            self._sidebar_auto_compact = False
            self.sidebar.set_collapsed(self._sidebar_before_auto, emit=False)
        if self.caption_controls is not None:
            self.caption_controls.refresh()

    def event(self, event):  # noqa: N802 - assinatura do Qt
        # Duplo clique na barra e atalhos do sistema também podem alternar o
        # estado maximizado. Nesse caso não há clique no nosso botão, então
        # redesenhamos o ícone de restaurar explicitamente.
        result = super().event(event)
        if event.type() == QEvent.Type.WindowStateChange and self.caption_controls is not None:
            self.caption_controls.refresh()
        return result

    def add_nav_section(self, text: str) -> None:
        self.sidebar.add_section(text)

    def addSubInterface(self, widget: QWidget, icon_name: str, text: str,
                        bottom: bool = False) -> NavItem:  # noqa: N802
        """Registra uma página e cria o item correspondente na barra lateral."""
        if not widget.objectName():
            widget.setObjectName(text)
        self.stackedWidget.addWidget(widget)
        item = NavItem(icon_name, text, self.sidebar)
        item.clicked.connect(lambda _checked=False, page=widget: self.switchTo(page))
        self.sidebar.add_item(item, bottom=bottom)
        self._nav_items[widget] = item
        if self.stackedWidget.count() == 1:
            self.switchTo(widget)
        return item

    def switchTo(self, widget: QWidget) -> None:  # noqa: N802
        self.stackedWidget.setCurrentWidget(widget)
        for page, item in self._nav_items.items():
            item.blockSignals(True)
            item.setChecked(page is widget)
            item.blockSignals(False)
            item.update()

    def add_footer_widget(self, widget: QWidget) -> None:
        """Faixa fixa abaixo do conteúdo — usada pelo aviso de atualização."""
        widget.setParent(self.contentArea)
        self.contentLayout.addWidget(widget, 0)

    # -------------------------------------------------------------------- efeitos
    def setMicaEffectEnabled(self, enabled: bool) -> None:  # noqa: N802
        """Mantém a opção do Windows 11 sem que o desenho dependa dela."""
        if not sys.platform.startswith("win"):
            return
        effect = getattr(self, "windowEffect", None)
        if effect is None:
            return
        try:
            if enabled:
                effect.setMicaEffect(self.winId(), theme.is_dark())
            else:
                effect.removeBackgroundEffect(self.winId())
        except Exception:  # noqa: BLE001 - build do Windows sem suporte a Mica
            pass
