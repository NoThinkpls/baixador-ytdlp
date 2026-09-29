"""Acabamento da interface: foco inicial, texto das ferramentas, botões desabilitados, caminho."""
from __future__ import annotations

import importlib.util
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QFontMetrics
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.ui import theme
    from baixador_ytdlp.ui.components import (
        BreadcrumbChevron, BreadcrumbCurrent, BreadcrumbLink, Button,
    )
    from baixador_ytdlp.ui.media_tools_page import OPERATIONS, wrap_lines
    from baixador_ytdlp.ui.settings_page import SettingsPage
    from baixador_ytdlp.ui.shell import CaptionButton


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class InterfaceAcabamentoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_caption_buttons_never_take_keyboard_focus(self) -> None:
        for action in ("minimize", "maximize", "close"):
            self.assertEqual(CaptionButton(action).focusPolicy(), Qt.FocusPolicy.NoFocus)

    def test_tool_descriptions_are_never_cut_with_an_ellipsis(self) -> None:
        metrics = QFontMetrics(theme.footnote())
        for width in (260, 300, 360):
            for key, data in OPERATIONS.items():
                lines = wrap_lines(data["summary"], metrics, width, max_lines=3)
                self.assertFalse(any(line.endswith("…") for line in lines), (key, width))
                self.assertEqual(" ".join(lines), data["summary"], (key, width))

    def test_wrap_lines_elides_only_when_text_really_overflows(self) -> None:
        metrics = QFontMetrics(theme.footnote())
        lines = wrap_lines("palavra " * 40, metrics, 120, max_lines=2)
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[-1].endswith("…"))

    def test_disabled_button_looks_and_behaves_disabled(self) -> None:
        button = Button("Pausar tudo", "pause", "secondary")
        button.resize(button.sizeHint())
        button.setEnabled(False)
        self.assertEqual(button.cursor().shape(), Qt.CursorShape.ArrowCursor)
        button.setEnabled(True)
        self.assertEqual(button.cursor().shape(), Qt.CursorShape.PointingHandCursor)

    def test_settings_subpage_uses_a_windows_style_breadcrumb(self) -> None:
        page = SettingsPage(Settings())
        try:
            links = page.findChildren(BreadcrumbLink)
            self.assertTrue(links)
            self.assertTrue(page.findChildren(BreadcrumbChevron))
            current = page.findChildren(BreadcrumbCurrent)
            self.assertTrue(current)
            # o pai e o item atual têm o mesmo corpo; o atual é mais pesado
            self.assertEqual(links[0].font().pointSizeF(), current[0].font().pointSizeF())
            self.assertGreater(current[0].font().weight(), links[0].font().weight())
            self.assertEqual(links[0].focusPolicy(), Qt.FocusPolicy.TabFocus)
        finally:
            page._save_timer.stop()
            page.deleteLater()


if __name__ == "__main__":
    unittest.main()
