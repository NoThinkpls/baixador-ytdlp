"""Identificação de plataformas além do YouTube e avisos específicos de cada uma."""
from __future__ import annotations

import unittest

from baixador_ytdlp.probe import friendly_error
from baixador_ytdlp.sites import login_required_message, site_from_error, site_from_url


class SiteDetectionTests(unittest.TestCase):
    def test_reconhece_pelo_dominio(self) -> None:
        casos = {
            "https://www.instagram.com/reel/abc/": "instagram",
            "https://x.com/user/status/1": "twitter",
            "https://mobile.twitter.com/u/status/1": "twitter",
            "https://vm.tiktok.com/ZM123/": "tiktok",
            "https://fb.watch/abc/": "facebook",
            "https://youtu.be/abc": "youtube",
        }
        for url, key in casos.items():
            site = site_from_url(url)
            self.assertIsNotNone(site, url)
            self.assertEqual(site.key, key, url)

    def test_dominio_parecido_nao_confunde(self) -> None:
        self.assertIsNone(site_from_url("https://notinstagram.com/x"))
        self.assertIsNone(site_from_url("https://instagram.com.evil.example/x"))
        self.assertIsNone(site_from_url("nao é url"))

    def test_reconhece_pela_etiqueta_do_erro(self) -> None:
        self.assertEqual(site_from_error("ERROR: [Instagram] abc: x").key, "instagram")
        self.assertEqual(site_from_error("ERROR: [twitter:broadcast] 1: x").key, "twitter")
        self.assertIsNone(site_from_error("ERROR: algo sem etiqueta"))


class LoginRequiredTests(unittest.TestCase):
    def test_story_do_instagram_pede_login_antes_de_consultar_o_site(self) -> None:
        story = "https://www.instagram.com/stories/fulano/3997102778119808536/"
        message = login_required_message(story)
        self.assertIn("Instagram", message)
        self.assertIn("cookies.txt", message)
        self.assertNotIn("YouTube", message)

    def test_reel_e_outros_sites_nao_bloqueiam(self) -> None:
        for url in ("https://www.instagram.com/reel/abc/", "https://x.com/u/status/1",
                    "https://www.youtube.com/watch?v=abc"):
            self.assertEqual(login_required_message(url), "", url)

    def test_download_de_story_sem_cookies_falha_antes_de_abrir_o_yt_dlp(self) -> None:
        from unittest.mock import MagicMock, patch

        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.downloader import DownloadError, DownloadOptions, DownloadRunner

        opts = DownloadOptions(
            url="https://www.instagram.com/stories/fulano/3997102778119808536/", output_dir=".")
        runner = DownloadRunner(opts, Settings(cookies_file="", cookies_browser=""), MagicMock())
        with patch("baixador_ytdlp.downloader.popen_isolated") as popen,                 self.assertRaises(DownloadError) as caught:
            runner.run(lambda progress: None)
        self.assertIn("Instagram", str(caught.exception))
        popen.assert_not_called()


class SiteErrorTests(unittest.TestCase):
    def test_login_no_instagram_nao_fala_de_youtube(self) -> None:
        message = friendly_error(
            "ERROR: [Instagram] abc: Requested content is not available, rate-limit reached "
            "or login required. Use --cookies-from-browser")
        self.assertIn("Instagram", message)
        self.assertIn("cookies", message)
        self.assertNotIn("YouTube", message)

    def test_limite_de_requisicoes_cita_o_site(self) -> None:
        message = friendly_error("ERROR: [tiktok] 1: HTTP Error 429: Too Many Requests")
        self.assertIn("TikTok", message)
        self.assertNotIn("YouTube", message)

    def test_youtube_mantem_os_avisos_antigos(self) -> None:
        self.assertIn("robô", friendly_error(
            "ERROR: [youtube] abc: Sign in to confirm you're not a bot."))
        self.assertIn("YouTube", friendly_error("ERROR: [youtube] abc: HTTP Error 429"))


if __name__ == "__main__":
    unittest.main()
