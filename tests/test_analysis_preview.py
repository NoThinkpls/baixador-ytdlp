"""Garante que a prévia visual continue expondo os dados importantes."""
from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication  # noqa: E402
    from baixador_ytdlp.config import Settings  # noqa: E402
    from baixador_ytdlp.probe import FormatRow, MediaInfo  # noqa: E402
    from baixador_ytdlp.ui.home_page import HomePage  # noqa: E402
except ModuleNotFoundError:  # ambiente mínimo de análise sem dependências de UI
    QApplication = None


@unittest.skipUnless(QApplication is not None, "PySide6 não está instalado neste ambiente")
class AnalysisPreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_preview_shows_formats_audio_and_subtitles_without_dense_columns(self) -> None:
        page = HomePage(Settings())
        info = MediaInfo(
            title="Vídeo de teste", uploader="Canal", duration="4:20", thumbnail="",
            webpage_url="https://example.invalid/video", is_playlist=False, playlist_count=0,
            rows=[FormatRow("137", "1080p", "60", "AV1", "—", "mp4", "240 MB",
                            "áudio separado", 240 * 1024 * 1024, 1080, video_only=True)],
            raw={}, audio_languages=["pt-BR", "en"], subtitles=["pt-BR"],
            auto_subtitles=["en", "es"],
        )

        page._on_info(info)

        self.assertFalse(page.info_card.isHidden())
        self.assertEqual(page.table.columnCount(), 6)
        self.assertIn("pt-BR", page.audio_stat.text())
        self.assertIn("Manuais", page.subtitles_stat.text())
        self.assertIn("Auto", page.subtitles_stat.text())
        self.assertIn("60 fps", page.table.item(1, 0).text())
        page.deleteLater()


if __name__ == "__main__":
    unittest.main()
