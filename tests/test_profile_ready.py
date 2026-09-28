"""O perfil pronto combina download de vídeo e legenda incorporada."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from baixador_ytdlp.config import Settings
from baixador_ytdlp.ui.home_page import CAPTION_EMBED_PROFILE, HomePage


class ReadyProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_perfil_pronto_liga_legenda_e_incorporacao(self) -> None:
        page = HomePage(Settings())
        page.audio_switch.setChecked(True)
        page._select_data(page.profile_combo, CAPTION_EMBED_PROFILE)
        self.assertFalse(page.audio_switch.isChecked())
        self.assertTrue(page.transcribe_switch.isChecked())
        self.assertTrue(page.embed_transcription_switch.isChecked())
        self.assertFalse(page.delete_profile_btn.isEnabled())
        page.deleteLater()
