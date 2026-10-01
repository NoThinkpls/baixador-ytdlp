"""Regressões da rodada 2 da caça a bugs (legendas, fila e lote de links)."""
from __future__ import annotations

import importlib.util
import os
import unittest

from baixador_ytdlp.transcription import Transcriber

HAS_QT = all(importlib.util.find_spec(m) is not None for m in ("PySide6", "qframelesswindow"))


def _transcriber(**kwargs) -> Transcriber:
    t = Transcriber(None, lambda _m: None, lambda _p: None, force_cpu=True)
    t.max_chars_per_line = kwargs.get("chars", 30)
    return t


def _palavras(textos: list[str]) -> list[dict]:
    return [{"text": t, "start": i * 0.5, "end": i * 0.5 + 0.4} for i, t in enumerate(textos)]


class LegendaSemPerderTextoTests(unittest.TestCase):
    def test_palavras_longas_nao_somem_do_texto_da_legenda(self) -> None:
        """O grupo cabia em 2×limite caracteres, mas o quebrador gerava 3 linhas e cortava a 3ª."""
        t = _transcriber(chars=30)
        palavras = ["responsabilidade", "constitucionalmente", "responsabilidade", "institucional"]
        segmento = {"start": 0.0, "end": 2.0, "text": " ".join(palavras), "words": _palavras(palavras)}
        blocos = t._split_word_segment(segmento)
        reunido = " ".join(b["text"].replace("\n", " ") for b in blocos).split()
        self.assertEqual(palavras, reunido)
        for bloco in blocos:
            self.assertLessEqual(len(bloco["text"].split("\n")), t.max_lines)

    def test_texto_normal_continua_agrupado_como_antes(self) -> None:
        t = _transcriber(chars=50)
        palavras = ["isto", "é", "uma", "frase", "curta", "e", "simples"]
        segmento = {"start": 0.0, "end": 4.0, "text": " ".join(palavras), "words": _palavras(palavras)}
        self.assertEqual(1, len(t._split_word_segment(segmento)))


class AlucinacaoPorPalavraTests(unittest.TestCase):
    def _item(self, texto: str) -> dict:
        return {"text": texto, "avg_logprob": -0.1, "no_speech_prob": 0.0}

    def test_palavra_que_apenas_contem_a_frase_nao_e_descartada(self) -> None:
        t = _transcriber()
        for texto in ("musical", "precisos", "compartilhei", "musicians"):
            self.assertFalse(t._is_hallucination(self._item(texto)), texto)

    def test_marcacoes_reais_continuam_descartadas(self) -> None:
        t = _transcriber()
        for texto in ("Música", "música", "Thank you for watching", "risos", "[Music]"):
            self.assertTrue(t._is_hallucination(self._item(texto)), texto)


@unittest.skipUnless(HAS_QT, "requer PySide6")
class FilaDuplicadaTests(unittest.TestCase):
    def test_video_e_playlist_do_mesmo_link_nao_sao_duplicados(self) -> None:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from baixador_ytdlp.downloader import DownloadOptions
        from baixador_ytdlp.ui.queue_page import QueuePage

        base = dict(url="https://www.youtube.com/watch?v=a&list=b", output_dir="/tmp")
        single = DownloadOptions(**base)
        playlist = DownloadOptions(**base, playlist=True)
        recorte_a = DownloadOptions(**base, playlist=True, playlist_items="1-3")
        recorte_b = DownloadOptions(**base, playlist=True, playlist_items="4-6")
        self.assertFalse(QueuePage._same_download(single, playlist))
        self.assertFalse(QueuePage._same_download(recorte_a, recorte_b))
        self.assertTrue(QueuePage._same_download(single, DownloadOptions(**base)))


class ExtracaoDeLinksTests(unittest.TestCase):
    def test_parenteses_balanceados_fazem_parte_do_link(self) -> None:
        from baixador_ytdlp.security import extract_urls

        texto = "veja https://pt.wikipedia.org/wiki/Foo_(bar). e (https://youtu.be/abc)."
        self.assertEqual(
            ["https://pt.wikipedia.org/wiki/Foo_(bar)", "https://youtu.be/abc"],
            extract_urls(texto))

    def test_pontuacao_final_sai_e_repeticao_e_ignorada(self) -> None:
        from baixador_ytdlp.security import extract_urls

        texto = "https://a.com/x, https://a.com/x; https://b.com/y>"
        self.assertEqual(["https://a.com/x", "https://b.com/y"], extract_urls(texto))

    def test_limite(self) -> None:
        from baixador_ytdlp.security import extract_urls

        texto = "\n".join(f"https://a.com/{i}" for i in range(10))
        self.assertEqual(3, len(extract_urls(texto, limit=3)))


if __name__ == "__main__":
    unittest.main()
