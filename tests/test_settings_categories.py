"""Navegação e estados reais da página de configurações."""
from __future__ import annotations

import importlib.util
import os
import unittest

HAS_QT = importlib.util.find_spec("PySide6") is not None
if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.ui.components import Switch
    from baixador_ytdlp.ui.settings_page import SettingsPage


@unittest.skipUnless(HAS_QT, "requer PySide6")
class SettingsCategoriesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_sections_are_reachable_and_keep_controls_when_switching(self) -> None:
        cfg = Settings()
        page = SettingsPage(cfg)
        page.resize(800, 600)
        page.show()
        self.app.processEvents()
        self.assertEqual(page.category_select.count(), 7)
        for index in range(page.category_select.count()):
            page.category_select.setCurrentIndex(index)
            self.app.processEvents()
            self.assertIs(page.pages.currentWidget(), page.pages.widget(index))
            self.assertTrue(page.category_description.text())
            self.assertGreater(page.pages.widget(index).column.count(), 2)

        page.category_select.setCurrentIndex(4)
        self.app.processEvents()
        switch = next(s for s in page.findChildren(Switch)
                      if s.accessibleName() == "Converter após baixar (GPU)")
        switch.setChecked(False)
        self.app.processEvents()
        self.assertFalse(page.conversion_group.isVisible())
        switch.setChecked(True)
        self.app.processEvents()
        self.assertTrue(page.conversion_group.isVisible())
        self.assertTrue(cfg.transcode_enabled)
        page.category_select.setCurrentIndex(0)
        page.category_select.setCurrentIndex(4)
        self.app.processEvents()
        self.assertTrue(page.conversion_group.isVisible())
        page._save_timer.stop()
        page.close()


if __name__ == "__main__":
    unittest.main()
