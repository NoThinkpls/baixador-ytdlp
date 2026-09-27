"""Configurações: cartões, busca e estados preservados ao navegar."""
from __future__ import annotations

import importlib.util
import os
import unittest

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.ui.components import Switch
    from baixador_ytdlp.ui.settings_page import SettingsPage


@unittest.skipUnless(HAS_QT, "requer PySide6")
class SettingsCategoriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_cards_search_and_conversion_reveal(self) -> None:
        cfg = Settings()
        cfg.transcode_enabled = False
        page = SettingsPage(cfg)
        page.resize(1020, 650)
        page.show()
        self.app.processEvents()
        self.assertIs(page.pages.currentWidget(), page.landing)
        self.assertEqual(len(page._categories), 8)
        self.assertEqual(page.cards_layout.itemAtPosition(0, 0).widget().accessibleName(),
                         "Downloads")
        self.assertEqual(page.cards_layout.itemAtPosition(0, 1).widget().accessibleName(),
                         "Legendas e extras")
        QTest.mouseClick(page._categories[0][2], Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertIs(page.pages.currentWidget(), page.pages.widget(1))
        page._show_landing()
        page.search_edit.setText("próxy")
        self.app.processEvents()
        self.assertEqual(page.results_layout.count(), 1)
        self.assertIn("Proxy", page.results_layout.itemAt(0).widget().text())
        page.results_layout.itemAt(0).widget().click()
        self.app.processEvents()
        self.assertIs(page.pages.currentWidget(), page.pages.widget(2))

        page._show_landing()
        page.search_edit.setText("códec")
        self.app.processEvents()
        self.assertIn("ative a conversão", page.results_layout.itemAt(0).widget().text())
        page.results_layout.itemAt(0).widget().click()
        self.app.processEvents()
        self.assertFalse(cfg.transcode_enabled)
        self.assertIs(page.pages.currentWidget(), page.pages.widget(5))

        page._show_category(4)
        self.app.processEvents()
        switch = next(s for s in page.findChildren(Switch)
                      if s.accessibleName() == "Converter após baixar (GPU)")
        self.assertFalse(page.conversion_group.isVisible())
        switch.setChecked(True)
        self.app.processEvents()
        self.assertTrue(page.conversion_group.isVisible())
        self.assertTrue(cfg.transcode_enabled)
        page._show_landing()
        self.assertIn("Ligada", page._categories[4][2].summary.text())
        page.resize(600, 650)
        self.app.processEvents()
        self.assertEqual(page.cards_layout.itemAtPosition(1, 0).widget().accessibleName(),
                         "Legendas e extras")
        page._save_timer.stop()
        page.close()


if __name__ == "__main__":
    unittest.main()
