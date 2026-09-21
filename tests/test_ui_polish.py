"""Contratos da rodada de acabamento visual.

Os testes Qt usam o backend offscreen na CI. Em ambientes de diagnóstico sem
PySide6, eles são pulados para que os testes de processos continuem úteis.
"""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import patch


HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qfluentwidgets"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.downloader import DownloadOptions
    from baixador_ytdlp.ui import theme
    from baixador_ytdlp.ui.queue_page import JobCard
    from baixador_ytdlp.ui.shell import Sidebar


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySide6-Fluent-Widgets")
class UiPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_font_is_native_hinted_and_has_valid_point_size(self) -> None:
        with patch("baixador_ytdlp.ui.theme.sys.platform", "win32"):
            ui_font = theme.font(13)
            families = theme.font_families()

        self.assertEqual(families[0], "Segoe UI Variable Text")
        self.assertGreater(ui_font.pointSizeF(), 0)
        self.assertEqual(ui_font.pixelSize(), -1)
        self.assertEqual(ui_font.hintingPreference(), QFont.HintingPreference.PreferFullHinting)

    def test_navigation_title_and_toggle_share_the_same_header(self) -> None:
        sidebar = Sidebar()
        section = sidebar.add_section("Navegação")

        self.assertIs(section, sidebar.header_section)
        self.assertEqual(section.text(), "NAVEGAÇÃO")
        self.assertEqual(sidebar._header_layout.indexOf(sidebar.toggle), 1)
        sidebar.set_collapsed(True)
        self.assertTrue(sidebar.header_section.isHidden())

    def test_job_state_and_actions_share_a_centered_group(self) -> None:
        card = JobCard(1, DownloadOptions("https://example.invalid/video", "."))
        layout = card.action_group.layout()

        self.assertIs(card.chip.parent(), card.action_group)
        self.assertEqual(layout.indexOf(card.chip), 0)
        self.assertGreater(layout.indexOf(card.cancel_btn), layout.indexOf(card.chip))


if __name__ == "__main__":
    unittest.main()
