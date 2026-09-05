"""Sistema de design do baixador-ytdlp: tokens, tipografia e folha de estilo.

A linguagem visual combina duas referências, e nenhuma delas é o Fluent Design:

* **Apple (Human Interface Guidelines)** — hierarquia tipográfica explícita,
  cantos generosos, listas agrupadas com separadores finos em vez de um cartão
  flutuante por linha, muito respiro e cor usada com parcimônia.
* **Discord** — superfícies escuras em camadas, rótulos de seção em caixa alta,
  indicador do item ativo na lateral e o azul-violeta como única cor de ação.

Este módulo é a única fonte de verdade de cor, raio, espaçamento e tipografia.
Nenhuma tela deve escrever cor literal: tudo sai de `palette()`.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication
from PySide6.QtWidgets import QApplication

from . import icons

# --------------------------------------------------------------------- tokens

RADIUS_PANEL = 12
RADIUS_CARD = 14
RADIUS_CONTROL = 10
RADIUS_SMALL = 8
RADIUS_PILL = 999

SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6 = 4, 8, 12, 16, 20, 24
SPACE_7, SPACE_8 = 32, 40

SIDEBAR_WIDTH = 236
SIDEBAR_COLLAPSED_WIDTH = 64
TITLEBAR_HEIGHT = 44
CONTROL_HEIGHT = 36
FIELD_HEIGHT = 38


@dataclass(frozen=True)
class Palette:
    """Cores de um tema. Os nomes descrevem a função, nunca o tom."""

    base: str            # atrás de tudo
    sidebar: str         # coluna de navegação
    content: str         # painel onde a página vive
    surface: str         # cartões sobre o conteúdo
    surface_hover: str
    surface_active: str
    field: str           # fundo de campos editáveis
    border: str
    border_strong: str
    separator: str
    text: str
    text_secondary: str
    text_tertiary: str
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str     # fundo tênue do item ativo / seleção
    on_accent: str
    success: str
    danger: str
    danger_hover: str
    warning: str
    scrim: str           # sombra e véus


DARK = Palette(
    base="#1F2023",
    sidebar="#1F2023",
    content="#26282C",
    surface="#2C2E33",
    surface_hover="#33363C",
    surface_active="#3A3D45",
    field="#1B1C1F",
    border="#34373D",
    border_strong="#454952",
    separator="#31343A",
    text="#F2F3F5",
    text_secondary="#B7BCC4",
    text_tertiary="#878C95",
    accent="#5865F2",
    accent_hover="#6C77F5",
    accent_pressed="#4752C4",
    accent_soft="rgba(88, 101, 242, 0.18)",
    on_accent="#FFFFFF",
    success="#2BB673",
    danger="#F04A4E",
    danger_hover="#F76C6F",
    warning="#F0B232",
    scrim="rgba(0, 0, 0, 0.45)",
)

LIGHT = Palette(
    base="#ECEEF2",
    sidebar="#ECEEF2",
    content="#FFFFFF",
    surface="#FFFFFF",
    surface_hover="#F5F6F9",
    surface_active="#EBEDF3",
    field="#FFFFFF",
    border="#E2E4EA",
    border_strong="#CED2DB",
    separator="#ECEEF3",
    text="#1C1D21",
    text_secondary="#4E5058",
    text_tertiary="#868B95",
    accent="#5865F2",
    accent_hover="#4752C4",
    accent_pressed="#3C45A5",
    accent_soft="rgba(88, 101, 242, 0.12)",
    on_accent="#FFFFFF",
    success="#1A9B57",
    danger="#D93B3F",
    danger_hover="#C1282C",
    warning="#B5810E",
    scrim="rgba(15, 18, 25, 0.14)",
)

_mode = "auto"


# ------------------------------------------------------------------ tema ativo

def _system_prefers_dark() -> bool:
    """Lê a preferência do sistema; cai no brilho da paleta se não houver API."""
    app = QGuiApplication.instance()
    if app is not None:
        hints = app.styleHints()
        scheme = getattr(hints, "colorScheme", None)
        if callable(scheme):
            try:
                return scheme() == Qt.ColorScheme.Dark
            except Exception:  # noqa: BLE001 - Qt antigo sem colorScheme
                pass
        window = app.palette().window().color()
        return window.lightness() < 128
    return False


def set_mode(mode: str) -> None:
    """Define claro, escuro ou 'auto' (segue o sistema)."""
    global _mode
    _mode = mode if mode in {"light", "dark", "auto"} else "auto"


def is_dark() -> bool:
    if _mode == "dark":
        return True
    if _mode == "light":
        return False
    return _system_prefers_dark()


def palette() -> Palette:
    return DARK if is_dark() else LIGHT


def color(name: str) -> str:
    return getattr(palette(), name)


def qcolor(name: str) -> QColor:
    """Versão QColor, inclusive para tokens escritos como rgba()."""
    value = getattr(palette(), name)
    if value.startswith("rgba"):
        parts = value[value.index("(") + 1: value.index(")")].split(",")
        red, green, blue = (int(float(p)) for p in parts[:3])
        alpha = int(float(parts[3]) * 255) if len(parts) > 3 else 255
        return QColor(red, green, blue, alpha)
    return QColor(value)


# ------------------------------------------------------------------ tipografia

def font_families() -> list[str]:
    """SF Pro quando existir na máquina; nunca distribuímos a fonte."""
    if sys.platform == "darwin":
        return ["SF Pro Text", "SF Pro Display", ".AppleSystemUIFont", "Helvetica Neue"]
    if sys.platform.startswith("win"):
        return ["SF Pro Text", "SF Pro Display", "Inter", "Segoe UI Variable Text", "Segoe UI"]
    return ["SF Pro Text", "SF Pro Display", "Inter", "Noto Sans", "DejaVu Sans"]


def mono_families() -> list[str]:
    return ["SF Mono", "JetBrains Mono", "Cascadia Mono", "Consolas", "Menlo", "monospace"]


def font(size: int = 13, weight: int = 400, tracking: float = 0.0,
         mono: bool = False) -> QFont:
    """Fonte da escala tipográfica. Tamanhos em pixels lógicos, como no iOS."""
    result = QFont()
    result.setFamilies(mono_families() if mono else font_families())
    result.setPixelSize(size)
    result.setWeight(QFont.Weight(weight))
    if tracking:
        result.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, tracking)
    result.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return result


# Escala tipográfica — os nomes seguem a nomenclatura da Apple.
def large_title() -> QFont:  return font(26, 700, -0.4)
def title() -> QFont:        return font(19, 700, -0.2)
def headline() -> QFont:     return font(14, 600)
def callout() -> QFont:      return font(13, 500)
def body() -> QFont:         return font(13, 400)
def subhead() -> QFont:      return font(12, 500)
def footnote() -> QFont:     return font(12, 400)
def caption() -> QFont:      return font(11, 400)
def section_label() -> QFont: return font(11, 800, 0.7)
def mono() -> QFont:         return font(12, 400, mono=True)


# -------------------------------------------------------------- folha de estilo

def stylesheet() -> str:
    """QSS global. Só cuida de superfície, borda e cor — o resto é código."""
    p = palette()
    dark = is_dark()
    # No claro, o campo precisa de borda visível; no escuro, o próprio fundo
    # rebaixado já separa o campo do cartão.
    return f"""
    /* ------------------------------------------------------ estrutura */
    QWidget {{
        color: {p.text};
        outline: none;
    }}
    QMainWindow, #appShell {{ background-color: {p.base}; }}
    #sidebar {{ background-color: {p.sidebar}; border: none; }}
    #contentArea {{
        background-color: {p.content};
        border-top-left-radius: {RADIUS_PANEL}px;
    }}
    #titleBarHost {{ background-color: transparent; }}
    #page {{ background-color: transparent; }}

    /* --------------------------------------------------------- textos */
    QLabel {{ background: transparent; color: {p.text}; }}
    QLabel#muted, QLabel#caption {{ color: {p.text_secondary}; }}
    QLabel#hint {{ color: {p.text_tertiary}; }}
    QLabel#sectionLabel {{ color: {p.text_tertiary}; }}
    QLabel#pageSubtitle {{ color: {p.text_secondary}; }}
    QLabel#danger {{ color: {p.danger}; }}
    QLabel#success {{ color: {p.success}; }}
    QLabel#warning {{ color: {p.warning}; }}

    /* -------------------------------------------------------- cartões */
    #card, #panel, #insetGroup {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS_CARD}px;
    }}
    #cardFlat {{
        background-color: transparent;
        border: 1px solid {p.border};
        border-radius: {RADIUS_CARD}px;
    }}
    #appUpdateBanner {{
        background-color: {p.accent_soft};
        border: none;
        border-top: 1px solid {p.accent};
    }}
    #rowSeparator {{ background-color: {p.separator}; border: none; }}
    #settingRow {{ background: transparent; border: none; }}
    #listRow {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: {RADIUS_CARD}px;
    }}
    #listRow:hover {{
        background-color: {p.surface_hover};
        border-color: {p.border_strong};
    }}

    /* --------------------------------------------------------- botões */
    QPushButton {{
        border-radius: {RADIUS_CONTROL}px;
        padding: 0 14px;
        min-height: {CONTROL_HEIGHT}px;
        border: 1px solid transparent;
        background-color: transparent;
    }}
    QPushButton#btnPrimary {{
        background-color: {p.accent};
        color: {p.on_accent};
    }}
    QPushButton#btnPrimary:hover {{ background-color: {p.accent_hover}; }}
    QPushButton#btnPrimary:pressed {{ background-color: {p.accent_pressed}; }}
    QPushButton#btnPrimary:disabled {{
        background-color: {'#3A3D48' if dark else '#D3D6E4'};
        color: {p.text_tertiary};
    }}

    QPushButton#btnSecondary {{
        background-color: {'#383B42' if dark else '#FFFFFF'};
        border: 1px solid {p.border_strong};
        color: {p.text};
    }}
    QPushButton#btnSecondary:hover {{
        background-color: {'#41454E' if dark else '#F4F5F9'};
        border-color: {p.accent};
    }}
    QPushButton#btnSecondary:pressed {{ background-color: {p.surface_active}; }}
    QPushButton#btnSecondary:disabled {{
        color: {p.text_tertiary};
        border-color: {p.border};
        background-color: transparent;
    }}

    QPushButton#btnGhost {{ color: {p.text_secondary}; }}
    QPushButton#btnGhost:hover {{
        background-color: {p.surface_hover};
        color: {p.text};
    }}
    QPushButton#btnGhost:pressed {{ background-color: {p.surface_active}; }}
    QPushButton#btnGhost:disabled {{ color: {p.text_tertiary}; }}

    QPushButton#btnDanger {{ background-color: {p.danger}; color: #FFFFFF; }}
    QPushButton#btnDanger:hover {{ background-color: {p.danger_hover}; }}

    QPushButton#iconButton {{
        min-height: 32px; max-height: 32px;
        min-width: 32px; max-width: 32px;
        padding: 0; border-radius: {RADIUS_SMALL}px;
    }}
    QPushButton#iconButton:hover {{ background-color: {p.surface_hover}; }}
    QPushButton#iconButton:pressed {{ background-color: {p.surface_active}; }}
    QPushButton#iconButton:checked {{ background-color: {p.accent_soft}; }}

    /* --------------------------------------------------------- campos */
    QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QTextEdit {{
        background-color: {p.field};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_CONTROL}px;
        padding: 0 12px;
        min-height: {FIELD_HEIGHT}px;
        color: {p.text};
        selection-background-color: {p.accent};
        selection-color: #FFFFFF;
    }}
    QPlainTextEdit, QTextEdit {{ padding: 10px 12px; }}
    QLineEdit:hover, QSpinBox:hover, QComboBox:hover {{ border-color: {p.accent}; }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus,
    QPlainTextEdit:focus, QTextEdit:focus {{
        border-color: {p.accent};
        background-color: {p.field};
    }}
    QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
        color: {p.text_tertiary};
        border-color: {p.border};
        background-color: {'rgba(255,255,255,0.02)' if dark else 'rgba(0,0,0,0.02)'};
    }}
    QLineEdit[placeholderText] {{ color: {p.text}; }}

    QComboBox::drop-down {{ border: none; width: 30px; }}
    QComboBox::down-arrow {{ image: none; width: 0; height: 0; }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_CONTROL}px;
        padding: 6px;
        outline: none;
        selection-background-color: {p.accent};
        selection-color: #FFFFFF;
    }}
    QComboBox QAbstractItemView::item {{
        min-height: 30px;
        border-radius: {RADIUS_SMALL - 2}px;
        padding: 2px 8px;
        color: {p.text};
    }}
    QComboBox QAbstractItemView::item:hover {{ background-color: {p.surface_hover}; }}
    QComboBox QAbstractItemView::item:selected {{
        background-color: {p.accent};
        color: #FFFFFF;
    }}
    /* Espaço à direita para a seta que o próprio Select desenha. */
    QComboBox {{ padding-left: 12px; padding-right: 32px; }}
    QSpinBox {{ padding: 0 8px; }}
    QSpinBox#innerSpin {{
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_CONTROL}px;
        padding: 0 4px;
    }}

    /* ------------------------------------------------------- progresso */
    QProgressBar {{
        background-color: {'rgba(255,255,255,0.08)' if dark else 'rgba(0,0,0,0.07)'};
        border: none;
        border-radius: 4px;
        max-height: 8px;
        min-height: 8px;
        text-align: center;
        color: transparent;
    }}
    QProgressBar::chunk {{
        background-color: {p.accent};
        border-radius: 4px;
    }}

    /* ---------------------------------------------------------- tabela */
    QTableWidget, QTableView {{
        background-color: {p.field};
        alternate-background-color: {'rgba(255,255,255,0.025)' if dark else 'rgba(0,0,0,0.018)'};
        border: 1px solid {p.border};
        border-radius: {RADIUS_CARD}px;
        gridline-color: transparent;
        padding: 4px;
        color: {p.text};
        selection-background-color: {p.accent_soft};
        selection-color: {p.text};
    }}
    QTableWidget::item, QTableView::item {{
        padding: 7px 10px;
        border: none;
        border-radius: {RADIUS_SMALL - 2}px;
    }}
    QTableWidget::item:selected, QTableView::item:selected {{
        background-color: {p.accent_soft};
        color: {p.text};
    }}
    QHeaderView {{ background: transparent; }}
    QHeaderView::section {{
        background-color: transparent;
        color: {p.text_tertiary};
        border: none;
        border-bottom: 1px solid {p.separator};
        padding: 8px 10px;
        font-weight: 700;
    }}
    QTableCornerButton::section {{ background: transparent; border: none; }}

    /* ------------------------------------------------------- rolagem */
    QScrollArea {{ background: transparent; border: none; }}
    QScrollBar:vertical {{
        background: transparent; width: 10px; margin: 2px 2px 2px 0;
    }}
    QScrollBar::handle:vertical {{
        background: {'rgba(255,255,255,0.16)' if dark else 'rgba(0,0,0,0.18)'};
        border-radius: 4px; min-height: 34px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {'rgba(255,255,255,0.28)' if dark else 'rgba(0,0,0,0.3)'};
    }}
    QScrollBar:horizontal {{
        background: transparent; height: 10px; margin: 0 2px 2px 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {'rgba(255,255,255,0.16)' if dark else 'rgba(0,0,0,0.18)'};
        border-radius: 4px; min-width: 34px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* --------------------------------------------------------- diversos */
    QToolTip {{
        background-color: {'#111214' if dark else '#1C1D21'};
        color: #FFFFFF;
        border: 1px solid {'#2C2E33' if dark else '#34373D'};
        border-radius: {RADIUS_SMALL}px;
        padding: 6px 9px;
    }}
    QDialog {{ background-color: {p.base}; }}
    QMenu {{
        background-color: {p.surface};
        border: 1px solid {p.border_strong};
        border-radius: {RADIUS_CONTROL}px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 7px 14px; border-radius: {RADIUS_SMALL - 2}px; color: {p.text};
    }}
    QMenu::item:selected {{ background-color: {p.accent}; color: #FFFFFF; }}
    /* Um degrau acima dos cartões: o aviso flutua sobre a página. */
    #toast {{
        background-color: {'#383B42' if dark else '#FFFFFF'};
        border: 1px solid {'#4B4F58' if dark else '#D5D9E2'};
        border-radius: {RADIUS_CARD}px;
    }}
    #logView {{
        background-color: {p.field};
        border: 1px solid {p.border};
        border-radius: {RADIUS_CARD}px;
    }}
    """


def apply(app: QApplication | None = None) -> None:
    """Aplica fonte e folha de estilo. Chamado na abertura e a cada troca de tema."""
    app = app or QApplication.instance()
    if app is None:
        return
    icons.clear_cache()
    app.setFont(body())
    app.setStyleSheet(stylesheet())


# Nome histórico mantido para não quebrar chamadas externas ao pacote de UI.
apply_appearance = apply
