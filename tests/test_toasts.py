"""Avisos flutuantes: repetidos viram um só e não cobrem o rodapé."""
from __future__ import annotations

import importlib.util
import os
import unittest

HAS_QT = importlib.util.find_spec("PySide6") is not None

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QWidget

    from baixador_ytdlp.ui.components import Toast


@unittest.skipUnless(HAS_QT, "requer PySide6")
class ToastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.parent = QWidget()
        self.parent.resize(1000, 700)
        self.parent.show()

    def tearDown(self) -> None:
        self.parent.deleteLater()

    def _alive(self) -> list:
        return [toast for toast in Toast._stack(self.parent) if not toast._closing]

    def test_avisos_iguais_viram_um_com_contador(self) -> None:
        for _ in range(3):
            Toast.error("Falha no download", "O yt-dlp terminou com erro.", parent=self.parent)
        self.assertEqual(len(self._alive()), 1)
        self.assertEqual(self._alive()[0].title_label.text(), "Falha no download (3)")

    def test_limite_e_posicao_acima_do_rodape(self) -> None:
        for index in range(5):
            Toast.info(f"Aviso {index}", parent=self.parent)
        alive = self._alive()
        self.assertLessEqual(len(alive), Toast.MAX_VISIBLE)
        limit = self.parent.height() - Toast.FOOTER_CLEARANCE
        for toast in alive:
            self.assertLessEqual(toast.geometry().bottom(), limit)
            self.assertGreater(toast.x(), self.parent.width() // 2)


if __name__ == "__main__":
    unittest.main()
