"""Identidade visual Apple + Discord, sem distribuir fontes proprietárias."""
from __future__ import annotations

import sys

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication
from qfluentwidgets import isDarkTheme


def _system_font() -> QFont:
    """Prefere a tipografia nativa de cada sistema, com fallback seguro."""
    font = QFont()
    # A mesma hierarquia tipográfica é solicitada nos dois sistemas. A SF Pro
    # é usada quando já existe na máquina; ela não é distribuída pelo projeto.
    if sys.platform == "darwin":
        font.setFamilies(["SF Pro Text", "SF Pro Display", ".AppleSystemUIFont", "Helvetica Neue"])
    elif sys.platform.startswith("win"):
        font.setFamilies(["SF Pro Text", "SF Pro Display", "Segoe UI Variable Text", "Segoe UI", "Arial"])
    else:
        font.setFamilies(["SF Pro Text", "SF Pro Display", "Inter", "Noto Sans", "Sans Serif"])
    font.setPointSize(10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return font


def _style_sheet(dark: bool) -> str:
    """Combina superfícies arredondadas Apple com contraste e destaque Discord."""
    if dark:
        surface, elevated, field = "#313338", "#2B2D31", "#1E1F22"
        text, muted, border, hover = "#F2F3F5", "#B5BAC1", "#3F4147", "#3A3C43"
    else:
        surface, elevated, field = "#FFFFFF", "#F6F7FB", "#FFFFFF"
        text, muted, border, hover = "#1D1D1F", "#5F6368", "#E2E5EC", "#F0F2F8"
    return f"""
        QWidget#homePage, QWidget#queuePage, QWidget#transcriptionPage,
        QWidget#mediaToolsPage, QWidget#historyPage, QWidget#settingsPage {{
            background: transparent; color: {text};
        }}
        CardWidget {{
            background-color: {surface}; border: 1px solid {border}; border-radius: 16px;
        }}
        CardWidget:hover {{ background-color: {hover}; border-color: #5865F2; }}
        CardWidget#appUpdateBanner {{
            background-color: {elevated}; border: 1px solid #5865F2; border-radius: 14px;
            margin: 8px 14px 12px 14px;
        }}
        QLabel {{ color: {text}; }}
        CaptionLabel {{ color: {muted}; }}
        QPushButton, PrimaryPushButton {{ min-height: 34px; padding: 0 14px; border-radius: 10px; }}
        QPushButton {{ background-color: {elevated}; border: 1px solid {border}; color: {text}; }}
        QPushButton:hover {{ background-color: {hover}; border-color: #5865F2; }}
        PrimaryPushButton {{ background-color: #5865F2; border: 1px solid #5865F2; color: white; font-weight: 600; }}
        PrimaryPushButton:hover {{ background-color: #4752C4; border-color: #4752C4; }}
        QLineEdit, ComboBox, SpinBox {{
            min-height: 34px; padding: 0 10px; border: 1px solid {border}; border-radius: 10px;
            background-color: {field}; color: {text}; selection-background-color: #5865F2;
        }}
        QLineEdit:focus, ComboBox:focus, SpinBox:focus {{ border: 2px solid #5865F2; }}
        QScrollBar:vertical {{ width: 10px; background: transparent; margin: 4px; }}
        QScrollBar::handle:vertical {{ min-height: 30px; border-radius: 5px; background: #5865F2; }}
    """


def apply_apple_discord_appearance(app: QApplication) -> None:
    """Aplica tipografia e acabamento; o tema Fluent define claro/escuro antes."""
    app.setFont(_system_font())
    app.setStyleSheet(f"{app.styleSheet()}\n{_style_sheet(isDarkTheme())}")
