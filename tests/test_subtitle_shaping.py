"""Formatação das legendas: limites de duração e limpeza de texto."""
from __future__ import annotations

import unittest

from baixador_ytdlp.transcription import Transcriber


def _transcriber() -> Transcriber:
    # force_cpu evita consultar CTranslate2/CUDA; só a formatação é exercitada.
    return Transcriber(None, lambda _message: None, lambda _percent: None, force_cpu=True)


def _slow_segment(words: int, step: float = 0.9) -> dict:
    items = [{"text": f"palavra{i}", "start": i * step, "end": i * step + 0.6}
             for i in range(words)]
    return {"start": 0.0, "end": items[-1]["end"], "text": " ".join(w["text"] for w in items),
            "words": items}


class SubtitleShapingTests(unittest.TestCase):
    def test_bloco_por_palavra_respeita_a_duracao_maxima(self) -> None:
        engine = _transcriber()
        engine.max_chars_per_line = 100  # isola o limite de tempo do de caracteres
        engine.max_duration = 4.5
        blocks = engine._split_word_segment(_slow_segment(12))
        self.assertGreater(len(blocks), 1)
        for block in blocks:
            self.assertLessEqual(block["end"] - block["start"], engine.max_duration + 1e-6)

    def test_duracao_maxima_nao_cria_flashes_curtos(self) -> None:
        engine = _transcriber()
        engine.max_chars_per_line = 100
        engine.max_duration = 1.0
        engine.min_duration = 0.8
        blocks = engine._split_word_segment(_slow_segment(6, step=1.2))
        # Uma palavra de 0,6 s sozinha seria um flash abaixo do mínimo; o limite
        # máximo só corta quando o bloco já cumpriu a duração mínima.
        self.assertGreater(len(blocks), 1)
        for block in blocks[:-1]:
            self.assertGreaterEqual(block["end"] - block["start"], engine.min_duration)

    def test_texto_preserva_simbolos_da_fala(self) -> None:
        engine = _transcriber()
        cases = {
            "Custa R$ 50, ou 50% a menos": "Custa R$ 50, ou 50% a menos",
            "Atendimento 24/7 em C++": "Atendimento 24/7 em C++",
            "fale@empresa.com.br #dica": "fale@empresa.com.br #dica",
            "«Olá» — disse ele…": "«Olá» — disse ele…",
            "Música ♪ tocando 🎵": "Música tocando",
            "<i>tag</i> {\\an8}": "itag/i an8",
        }
        for raw, expected in cases.items():
            self.assertEqual(engine._normalize_text(raw), expected, raw)


if __name__ == "__main__":
    unittest.main()
