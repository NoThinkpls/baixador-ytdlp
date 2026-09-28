"""Ajustes da página Configurações na terceira rodada."""
from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from baixador_ytdlp.config import Settings
from baixador_ytdlp.ui.settings_page import SettingsPage
from baixador_ytdlp.ui.main_window import MainWindow


class SettingsRound3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_singular_last_check_and_real_cuda_state(self) -> None:
        cfg = Settings(max_parallel_downloads=1, app_update_checked_at=0)
        page = SettingsPage(cfg)
        self.assertIn("Até 1 download ·", page._categories[1][2].summary.text())
        self.assertNotEqual(page._categories[1][2].icon_name,
                            page._categories[7][2].icon_name)
        self.assertIn("ainda não verificado", page.app_update_status.text())
        with patch("baixador_ytdlp.runtime.embedded_cuda_available", return_value=False):
            page.set_versions("2026.09.01", "9.0", "Whisper 1.1 · CTranslate2 4.8 (CUDA)")
        self.assertIn("(CPU)", page.versions.text())
        self.assertIn("CUDA indisponível", page.versions.text())
        page._save_timer.stop()
        page.deleteLater()

    def test_channel_change_waits_for_next_component_check(self) -> None:
        window = Mock()
        window.manager = SimpleNamespace(ytdlp_channel="stable")
        with patch("baixador_ytdlp.ui.main_window.Toast.info"):
            MainWindow._switch_ytdlp_channel(window, "nightly")
        self.assertEqual(window.manager.ytdlp_channel, "nightly")
        window.run_setup.assert_not_called()
