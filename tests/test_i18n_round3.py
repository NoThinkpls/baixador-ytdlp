"""Mensagens dinâmicas passam pelo catálogo inglês."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QWidget

from baixador_ytdlp.probe import friendly_error
from baixador_ytdlp.ui.components import Toast
from baixador_ytdlp.ui.i18n import set_language


class I18nRound3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def tearDown(self) -> None:
        set_language("pt-BR")

    def test_toast_and_friendly_error(self) -> None:
        set_language("en")
        self.assertEqual(friendly_error("ERROR: Unsupported URL"),
                         "This site is not supported by yt-dlp.")
        parent = QWidget()
        toast = Toast.info("Falha no download", "Você já está usando a versão mais recente.",
                           parent=parent)
        self.assertEqual(toast.title_label.text(), "Download failed")
        self.assertEqual(toast.message_label.text(), "You already have the latest version.")
        toast.dismiss()
        parent.deleteLater()
