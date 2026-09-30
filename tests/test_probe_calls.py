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

    def test_story_do_instagram_analisa_so_o_story_do_link(self) -> None:
        # A URL de story com id é uma playlist de todos os stories da pessoa; o
        # download usa --no-playlist e baixa o story do link. Analisar o item 1
        # mostrava formatos de outro story, e a linha escolhida não existia.
        story = "https://www.instagram.com/stories/fulano/3997102778119808536/"
        with patch.object(probe, "_run_json", return_value=VIDEO) as run:
            probe.probe(story, Path("yt-dlp"), cookies_browser="firefox")
        args = run.call_args.args[0]
        self.assertIn("--no-playlist", args)
        self.assertNotIn("--playlist-items", args)

    def test_story_sem_cookies_avisa_sem_chamar_o_yt_dlp(self) -> None:
        story = "https://www.instagram.com/stories/fulano/3997102778119808536/"
        with patch.object(probe, "_run_json") as run,                 self.assertRaises(probe.ProbeError) as caught:
            probe.probe(story, Path("yt-dlp"))
        self.assertIn("Instagram", str(caught.exception))
        run.assert_not_called()

    def test_stories_sem_id_continuam_playlist(self) -> None:
        with patch.object(probe, "_run_json", return_value=VIDEO) as run:
            probe.probe("https://www.instagram.com/stories/fulano/", Path("yt-dlp"),
                        cookies_browser="firefox")
        self.assertIn("--playlist-items", run.call_args.args[0])

    def test_playlist_guarda_os_itens_da_contagem(self) -> None:
        playlist = {"_type": "playlist", "title": "Lista", "entries": [VIDEO]}
        flat = {"entries": [{"id": "a", "title": "A"}, {"id": "b", "title": "B"}]}
        with patch.object(probe, "_run_json", side_effect=[playlist, flat]):
            info = probe.probe("https://www.youtube.com/playlist?list=PL1", Path("yt-dlp"))
        self.assertEqual(info.playlist_count, 2)
        self.assertEqual([entry.title for entry in info.entries], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
