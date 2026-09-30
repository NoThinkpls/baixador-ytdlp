"""Modelos de nome de arquivo: plataforma, data e título; título limpo no Facebook."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, build_args
from baixador_ytdlp.filename_preview import FILENAME_PRESETS, render_filename_preview
from baixador_ytdlp.tools import Toolchain
from baixador_ytdlp.ui.settings_page import SettingsPage
from pathlib import Path

PLATAFORMA = next(template for label, template in FILENAME_PRESETS if "Plataforma" in label)


class FilenamePreviewTests(unittest.TestCase):
    def test_previa_do_modelo_com_plataforma_e_data(self) -> None:
        result = render_filename_preview(
            PLATAFORMA, {"extractor_key": "TikTok", "upload_date": "20260910",
                         "title": "Meu vídeo", "id": "768"}, "mp4")
        self.assertEqual(result, "TikTok - 2026-09-10 - Meu vídeo [768].mp4")

    def test_sem_data_usa_o_texto_de_reserva(self) -> None:
        result = render_filename_preview(
            PLATAFORMA, {"extractor_key": "Generic", "upload_date": ""}, "mp4")
        self.assertIn("Generic - sem data - ", result)

    def test_todos_os_modelos_renderizam_sem_sobras(self) -> None:
        for label, template in FILENAME_PRESETS:
            rendered = render_filename_preview(template, None, "mp4")
            self.assertNotIn("%(", rendered, label)
            self.assertTrue(rendered.endswith(".mp4"), label)


class FacebookTitleTests(unittest.TestCase):
    def _args(self, url: str) -> list[str]:
        tc = Toolchain(ytdlp=Path("yt-dlp"), ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"),
                       bin_dir=Path("."))
        return build_args(DownloadOptions(url=url, output_dir="."), Settings(), tc)

    def test_facebook_tira_o_contador_de_views_do_titulo(self) -> None:
        args = self._args("https://www.facebook.com/share/r/1BypECBh2t/")
        self.assertIn("--replace-in-metadata", args)
        pattern = args[args.index("--replace-in-metadata") + 2]
        import re

        self.assertEqual(
            re.sub(pattern, "", "122K views · 3.4K reactions | que lapada | Mylonzete"),
            "que lapada | Mylonzete")
        self.assertEqual(re.sub(pattern, "", "1 view | oi"), "oi")

    def test_outros_sites_nao_mexem_no_titulo(self) -> None:
        self.assertNotIn("--replace-in-metadata",
                         self._args("https://www.instagram.com/reel/abc/"))


class FilenamePresetUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_escolher_um_modelo_preenche_o_campo_e_salva(self) -> None:
        cfg = Settings()
        cfg.save = lambda *args, **kwargs: None
        page = SettingsPage(cfg)
        index = next(i for i in range(page.filename_presets.count())
                     if page.filename_presets.itemData(i) == PLATAFORMA)
        page.filename_presets.setCurrentIndex(index)
        self.assertEqual(page.filename_template_edit.text(), PLATAFORMA)
        self.assertEqual(cfg.filename_template, PLATAFORMA)
        self.assertIn("YouTube - ", page.filename_template_preview.text())


if __name__ == "__main__":
    unittest.main()
