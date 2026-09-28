"""O arquivo de origem aparece antes das ferramentas e habilita a ação."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from baixador_ytdlp.config import Settings
from baixador_ytdlp.ui.media_tools_page import MediaToolsPage


class MediaToolsLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_source_first_and_action_requires_file(self) -> None:
        page = MediaToolsPage(Settings())
        page.resize(1100, 750)
        page.show()
        self.app.processEvents()
        self.assertFalse(page.run_button.isEnabled())
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"test")
            page.set_media(str(source))
            self.assertTrue(page.run_button.isEnabled())
            page.source_edit.setText("")
            self.assertFalse(page.run_button.isEnabled())
        self.assertLess(page.source_edit.mapTo(page, page.source_edit.rect().topLeft()).y(),
                        page._tool_cards["trim"].mapTo(page, page._tool_cards["trim"].rect().topLeft()).y())
        page.close()
        page.deleteLater()
