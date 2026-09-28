"""O modelo do Whisper sai da memória quando o Legendar fica ocioso."""
from __future__ import annotations

import importlib.util
import os
import unittest
from unittest.mock import MagicMock

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.ui.transcription_page import TranscriptionPage


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class WhisperIdleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = TranscriptionPage(Settings())
        self.worker = MagicMock()
        self.worker.is_busy.return_value = False
        self.page.worker = self.worker

    def test_ocioso_agenda_descarga_e_libera(self) -> None:
        self.page._finish_controls()
        self.assertTrue(self.page._idle_timer.isActive())
        self.assertFalse(self.page.release_btn.isHidden())
        self.page.release_engine()
        self.worker.shutdown.assert_called_once()
        self.assertIsNone(self.page.worker)
        self.assertTrue(self.page.release_btn.isHidden())

    def test_nao_descarrega_com_item_na_fila_ou_ocupado(self) -> None:
        self.worker.is_busy.return_value = True
        self.page.release_engine()
        self.worker.shutdown.assert_not_called()
        self.worker.is_busy.return_value = False
        self.page._pending.append((MagicMock(), False))
        self.page.release_engine()
        self.worker.shutdown.assert_not_called()


if __name__ == "__main__":
    unittest.main()
