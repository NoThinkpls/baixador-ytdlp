"""A página Baixar só baixa o link que foi de fato analisado."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.probe import MediaInfo
    from baixador_ytdlp.ui.home_page import HomePage


def _info(url: str) -> "MediaInfo":
    return MediaInfo(title="Vídeo A", uploader="Canal", duration="1:00", thumbnail="",
                     webpage_url=url, is_playlist=False, playlist_count=0, rows=[], raw={})


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class HomeAnalysisTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.folder = tempfile.TemporaryDirectory()
        self.page = HomePage(Settings(download_dir=self.folder.name, history_enabled=False))
        self.page.toolchain = object()
        self.url_a = "https://example.com/watch?v=A"
        self.page.set_url(self.url_a)
        self.page._probing_url = self.url_a
        self.page._on_info(_info(self.url_a))

    def tearDown(self) -> None:
        self.page.deleteLater()
        self.folder.cleanup()

    def test_editar_o_link_descarta_a_analise(self) -> None:
        self.assertTrue(self.page.download_btn.isEnabled())
        self.page.set_url("https://example.com/watch?v=B")
        self.assertIsNone(self.page.info)
        self.assertFalse(self.page.download_btn.isEnabled())

    def test_download_usa_a_url_analisada(self) -> None:
        emitted = []
        self.page.enqueue.connect(emitted.append)
        # Espaços extras não mudam o link e não invalidam a análise.
        self.page.set_url(f"  {self.url_a} ")
        self.page._emit_job()
        self.assertEqual(len(emitted), 1)
        self.assertEqual(emitted[0].url, self.url_a)

    def test_resultado_atrasado_de_outro_link_e_ignorado(self) -> None:
        self.page.set_url("https://example.com/watch?v=B")
        self.page._probing_url = self.url_a
        self.page._on_info(_info(self.url_a))
        self.assertIsNone(self.page.info)
        self.assertFalse(self.page.download_btn.isEnabled())

    def test_opcoes_dependentes_so_aparecem_quando_valem(self) -> None:
        page = self.page
        self.assertTrue(page.audio_format_row.isHidden())
        self.assertTrue(page.embed_row.isHidden())
        page.audio_switch.setChecked(True)
        self.assertFalse(page.audio_format_row.isHidden())
        self.assertTrue(page.container_row.isHidden())
        page.transcribe_switch.setChecked(True)
        self.assertTrue(page.embed_row.isHidden())  # áudio puro não recebe faixa
        page.audio_switch.setChecked(False)
        self.assertFalse(page.embed_row.isHidden())
        page.set_url("https://example.com/watch?v=B")
        self.assertTrue(page.filename_row.isHidden())


if __name__ == "__main__":
    unittest.main()
