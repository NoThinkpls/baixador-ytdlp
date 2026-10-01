"""Valida o site estático de web/ (publicado no GitHub Pages) sem navegador."""
from __future__ import annotations

import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.keys: set[str] = set()
        self.urls: list[str] = []
        self.inline_scripts = 0
        self.style_attrs = 0
        self._in_script = False

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        for name in ("data-i18n", "data-i18n-alt", "data-i18n-aria"):
            if attributes.get(name):
                self.keys.add(attributes[name])
        for name in ("src", "href"):
            if attributes.get(name):
                self.urls.append(attributes[name])
        if "style" in attributes:
            self.style_attrs += 1
        if tag == "script" and "src" not in attributes:
            self.inline_scripts += 1


class SiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (WEB / "index.html").read_text(encoding="utf-8")
        self.page = _Collector()
        self.page.feed(self.html)

    def test_toda_chave_i18n_tem_traducao_em_ingles(self) -> None:
        script = (WEB / "app.js").read_text(encoding="utf-8")
        block = script.split("const EN = {", 1)[1].split("\n};", 1)[0]
        english = set(re.findall(r'\b([a-z0-9_]+):\s*"', block))
        missing = sorted(k for k in self.page.keys if k not in english)
        self.assertEqual(missing, [], f"chaves sem tradução em app.js: {missing}")

    def test_arquivos_locais_referenciados_existem(self) -> None:
        for url in self.page.urls:
            if re.match(r"^(https?:|#|mailto:)", url):
                continue
            self.assertTrue((WEB / url).is_file(), f"web/{url} não existe")
        for name in ("styles.css", "app.js", "theme-init.js", ".nojekyll"):
            self.assertTrue((WEB / name).exists(), name)

    def test_links_de_download_batem_com_os_do_readme(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        wanted = set(re.findall(r"releases/latest/download/([\w.-]+)", readme))
        used = {m for u in self.page.urls for m in re.findall(r"releases/latest/download/([\w.-]+)", u)}
        self.assertEqual(used, wanted)
        sizes = set(re.findall(r'data-size="([\w.-]+)"', self.html))
        self.assertEqual(sizes, wanted)

    def test_politica_de_seguranca_sem_codigo_inline(self) -> None:
        self.assertIn("Content-Security-Policy", self.html)
        self.assertEqual(self.page.inline_scripts, 0)
        self.assertEqual(self.page.style_attrs, 0)

    def test_tokens_de_cor_espelham_o_tema_do_app(self) -> None:
        theme = (ROOT / "baixador_ytdlp" / "ui" / "theme.py").read_text(encoding="utf-8")
        css = (WEB / "styles.css").read_text(encoding="utf-8").upper()
        for token in ("#1F2023", "#26282C", "#2C2E33", "#5865F2", "#F2F3F5", "#ECEEF2", "#1C1D21"):
            self.assertIn(token, theme.upper(), f"{token} saiu do tema do app")
            self.assertIn(token, css, f"{token} falta no CSS do site")


if __name__ == "__main__":
    unittest.main()
