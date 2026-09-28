"""A análise chama o yt-dlp o mínimo de vezes."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp import probe

VIDEO = {"title": "Vídeo", "formats": [], "webpage_url": "https://www.youtube.com/watch?v=abc"}


class ProbeCallsTests(unittest.TestCase):
    def test_com_cookies_validos_e_uma_chamada_so(self) -> None:
        with patch.object(probe, "_run_json", return_value=VIDEO) as run:
            probe.probe("https://www.youtube.com/watch?v=abc", Path("yt-dlp"),
                        cookies_browser="firefox")
        self.assertEqual(run.call_count, 1)
        args = run.call_args.args[0]
        self.assertIn("--cookies-from-browser", args)
        self.assertNotIn("--simulate", args)

    def test_cookies_ilegiveis_repetem_sem_cookies(self) -> None:
        failure = probe.ProbeError("x", "ERROR: Failed to decrypt with DPAPI")
        with patch.object(probe, "_run_json", side_effect=[failure, VIDEO]) as run:
            info = probe.probe("https://www.youtube.com/watch?v=abc", Path("yt-dlp"),
                               cookies_browser="chrome")
        self.assertEqual(info.title, "Vídeo")
        self.assertEqual(run.call_count, 2)
        self.assertNotIn("--cookies-from-browser", run.call_args.args[0])

    def test_outros_erros_nao_repetem(self) -> None:
        failure = probe.ProbeError("Vídeo privado", "ERROR: Private video")
        with patch.object(probe, "_run_json", side_effect=[failure]) as run, \
                self.assertRaises(probe.ProbeError):
            probe.probe("https://www.youtube.com/watch?v=abc", Path("yt-dlp"),
                        cookies_browser="chrome")
        self.assertEqual(run.call_count, 1)

    def test_playlist_guarda_os_itens_da_contagem(self) -> None:
        playlist = {"_type": "playlist", "title": "Lista", "entries": [VIDEO]}
        flat = {"entries": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}
        with patch.object(probe, "_run_json", side_effect=[playlist, flat]):
            info = probe.probe("https://www.youtube.com/playlist?list=PL1", Path("yt-dlp"))
        self.assertEqual(info.playlist_count, 2)
        self.assertEqual([entry.title for entry in info.entries], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
