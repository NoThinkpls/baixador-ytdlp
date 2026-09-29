"""Fila: conversão opcional que falha não derruba o download; ações por item."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.downloader import DownloadError, DownloadOptions
    from baixador_ytdlp.ui.queue_page import QueuePage
    from baixador_ytdlp.workers import DownloadWorker


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class TranscodeFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_falha_na_conversao_mantem_o_download(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            video = Path(folder) / "video.mp4"
            video.write_bytes(b"x")
            runner = MagicMock(cancelled=False)
            runner.run.return_value = [video]
            runner.tail.return_value = ""
            transcoder = MagicMock()
            transcoder.run.side_effect = DownloadError("Falha na conversão acelerada: driver")
            cfg = Settings(transcode_enabled=True, auto_retry_attempts=0)
            with patch("baixador_ytdlp.workers.create_runner", return_value=runner), \
                    patch("baixador_ytdlp.workers.Transcoder", return_value=transcoder):
                worker = DownloadWorker(1, DownloadOptions("https://x", folder), cfg, MagicMock())
                done, failed, warnings = [], [], []
                worker.finished_ok.connect(lambda _id, files: done.append(files))
                worker.failed.connect(lambda *args: failed.append(args))
                worker.warning.connect(lambda _id, message: warnings.append(message))
                worker.run()
            self.assertEqual(failed, [])
            self.assertEqual(done, [[video]])
            self.assertEqual(len(warnings), 1)
            self.assertIn("original foi mantido", warnings[0])


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class QueueActionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.page = QueuePage(Settings(resume_queue=False))
        self.page._persist = MagicMock()   # nunca grava a fila real
        self.page._pump = lambda: self.page._refresh_summary()
        for index in range(3):
            self.page.add(DownloadOptions(f"https://x/{index}", "/tmp/Videos",
                                          title=f"Item {index}"))

    def test_cartoes_seguem_a_ordem_de_chegada(self) -> None:
        cards = [self.page.cards.itemAt(i).widget() for i in range(self.page.cards.count() - 1)]
        self.assertEqual([card.title.text() for card in cards], ["Item 0", "Item 1", "Item 2"])
        self.assertIn("Vídeo MP4 · Videos", cards[0].status.text())

    def test_falha_libera_acoes_de_repeticao_e_remocao(self) -> None:
        self.assertFalse(self.page.clear_btn.isEnabled())
        job_id = self.page.pending.pop(0)
        self.page.jobs[job_id].active = True
        self.page._on_failed(job_id, "O yt-dlp terminou com erro.")
        card = self.page.jobs[job_id].card
        self.assertFalse(card.cancel_btn.isHidden())
        self.assertTrue(card.bar.isHidden())
        self.assertTrue(self.page.clear_btn.isEnabled())
        self.assertFalse(self.page.retry_failed_btn.isHidden())

        self.page.retry_failed()
        self.assertIn(job_id, self.page.pending)
        self.assertFalse(card.bar.isHidden())
        self.assertTrue(self.page.retry_failed_btn.isHidden())


if __name__ == "__main__":
    unittest.main()
