"""O cookies.txt vale para vários sites: detecção por domínio e mescla ao importar."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp import cookies

HEADER = "# Netscape HTTP Cookie File\n"
YOUTUBE = ".youtube.com\tTRUE\t/\tTRUE\t1820000000\tSID\tyt-antigo\n"
YOUTUBE_NOVO = ".youtube.com\tTRUE\t/\tTRUE\t1820000000\tSID\tyt-novo\n"
INSTAGRAM = "#HttpOnly_.instagram.com\tTRUE\t/\tTRUE\t1820000000\tsessionid\tig\n"


class CookieSitesTests(unittest.TestCase):
    def test_lista_os_sites_do_arquivo(self) -> None:
        text = HEADER + YOUTUBE + INSTAGRAM + ".google.com\tTRUE\t/\tTRUE\t1820000000\tNID\tx\n"
        self.assertEqual(cookies.cookie_sites(text), ["YouTube", "Instagram"])

    def test_arquivo_sem_site_conhecido_devolve_lista_vazia(self) -> None:
        self.assertEqual(cookies.cookie_sites(HEADER + ".exemplo.org\tTRUE\t/\tTRUE\t1\ta\tb\n"), [])

    def test_mescla_troca_o_dominio_reimportado_e_guarda_os_outros(self) -> None:
        merged = cookies.merge_cookie_text(HEADER + YOUTUBE, HEADER + INSTAGRAM + YOUTUBE_NOVO)
        self.assertEqual(merged.count("# Netscape HTTP Cookie File"), 1)
        self.assertIn("yt-novo", merged)
        self.assertNotIn("yt-antigo", merged)
        self.assertIn("sessionid", merged)

    def test_importar_instagram_nao_apaga_o_youtube(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "cookies"
            folder.mkdir()
            (folder / "cookies.txt").write_text(HEADER + YOUTUBE, encoding="utf-8")
            source = Path(tmp) / "instagram.txt"
            source.write_text(HEADER + INSTAGRAM, encoding="utf-8")
            with patch.object(cookies, "COOKIES_DIR", folder), \
                    patch.object(cookies, "IS_WINDOWS", False):
                destination, _ = cookies.import_cookie_file(source)
            self.assertEqual(cookies.cookie_sites(destination.read_text(encoding="utf-8")),
                             ["YouTube", "Instagram"])


if __name__ == "__main__":
    unittest.main()
