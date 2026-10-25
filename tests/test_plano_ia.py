"""Plano de cortes vindo da IA: uma linha de JSON que preenche cortes, títulos e efeitos."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp.clips import remap_time
from baixador_ytdlp.effects import Marker, find_word, place_markers, schedule
from baixador_ytdlp.plano_ia import PlanError, find_plan, parse_plan

LINHA = ('{"bx":1,"c":[["12:03","12:58.5","A GRAÇA QUE ALCANÇA",'
         '[["12:10","graça","i",1],["12:30","","w",0],["13:40","fora","p",0],["12:20","x","?",1]]],'
         '["1:02:00","1:02:40","",[]]]}')


class FormatoTests(unittest.TestCase):
    def test_linha_compacta_vira_cortes_com_efeitos(self) -> None:
        cuts = parse_plan(LINHA)
        self.assertEqual(len(cuts), 2)
        first = cuts[0]
        self.assertEqual((first.start, first.end, first.title), (723.0, 778.5, "A GRAÇA QUE ALCANÇA"))
        self.assertEqual(first.markers, (
            Marker(730.0, "impacto", "graça", True),
            Marker(750.0, "whoosh", "", False),
            Marker(740.0, "", "x", True),        # som desconhecido: fica só o zoom
        ))                                       # 13:40 está fora do corte e saiu
        self.assertEqual(cuts[1].start, 3720.0)

    def test_acha_a_linha_no_meio_da_resposta_inteira(self) -> None:
        resposta = ("1. ANÁLISE…\nTítulos…\n\n```json\n" + LINHA + "\n```\nBons cortes!")
        self.assertEqual(len(parse_plan(resposta)), 2)

    def test_nomes_inteiros_e_segundos_tambem_valem(self) -> None:
        cuts = parse_plan('{"bx":1,"c":[[10,25.5,"T",[[12,"oi","impacto",true]]]]}')
        self.assertEqual(cuts[0].markers, (Marker(12.0, "impacto", "oi", True),))

    def test_sem_plano_explica_o_que_colar(self) -> None:
        with self.assertRaisesRegex(PlanError, '"bx":1'):
            find_plan("só os títulos, sem a linha")

    def test_json_cortado_pede_para_copiar_de_novo(self) -> None:
        with self.assertRaisesRegex(PlanError, "incompleto"):
            parse_plan('{"bx":1,"c":[["12:03","12:58"')

    def test_corte_curto_ou_longo_demais(self) -> None:
        with self.assertRaisesRegex(PlanError, "corte 1"):
            parse_plan('{"bx":1,"c":[["12:03","12:03.5","",[]]]}')

    def test_tempo_invalido_num_efeito_nao_derruba_o_plano(self) -> None:
        cuts = parse_plan('{"bx":1,"c":[["0:10","0:30","",[["ontem","x","i",0],["0:12","","d",0]]]]}')
        self.assertEqual(cuts[0].markers, (Marker(12.0, "ding", "", False),))


def _words(*items: tuple[str, float]) -> list[dict]:
    return [{"text": text, "start": start, "end": start + 0.3} for text, start in items]


class EncaixeTests(unittest.TestCase):
    def test_palavra_procurada_perto_do_tempo_do_srt(self) -> None:
        words = _words(("A", 1.0), ("Graça,", 2.0), ("de", 2.4), ("Deus", 2.6), ("graça", 20.0))
        self.assertEqual(find_word(words, "graça", 4.0)["start"], 2.0)    # sem acento/pontuação
        self.assertEqual(find_word(words, "GRAÇA DE DEUS", 4.0)["start"], 2.0)
        self.assertIsNone(find_word(words, "graça", 12.0))                 # longe demais

    def test_som_cai_na_palavra_exata_no_tempo_final(self) -> None:
        # O SRT diz 12:10, mas "graça" foi dita em 12:12,4; uma pausa de 2 s saiu antes.
        words = _words(("começo", 0.5), ("graça", 9.4))
        intervals = [(0.0, 3.0), (5.0, 20.0)]
        effects, zooms = place_markers([Marker(730.0, "impacto", "graça", True)], 723.0, words,
                                       intervals, 18.0, remap_time)
        self.assertEqual([(e.time, e.kind) for e in effects], [(7.4, "impacto")])
        self.assertEqual(zooms, [(7.4, 8.0)])

    def test_whoosh_vai_para_a_emenda_mais_proxima(self) -> None:
        intervals = [(0.0, 3.0), (5.0, 20.0)]
        effects, _ = place_markers([Marker(726.5, "whoosh")], 723.0, [], intervals, 18.0,
                                   remap_time)
        self.assertEqual(effects[0].time, 3.0)       # a emenda, no tempo do vídeo final

    def test_ponto_fora_do_trecho_e_ignorado(self) -> None:
        effects, zooms = place_markers([Marker(800.0, "pop", "", True)], 723.0, [],
                                       [(0.0, 20.0)], 20.0, remap_time)
        self.assertEqual((effects, zooms), ([], []))

    def test_antecedencia_de_cada_som(self) -> None:
        planned, _ = place_markers([Marker(733.0, "subida"), Marker(733.0, "impacto")], 723.0,
                                   [], [(0.0, 20.0)], 20.0, remap_time)
        placed = schedule(planned, {"subida": 1.6, "impacto": 0.01})
        self.assertEqual(sorted((e.kind, e.time) for e in placed),
                         [("impacto", 9.99), ("subida", 8.4)])


class PaginaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _page(self):
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.ui.clips_page import ClipsPage
        cfg = Settings()
        with patch.object(cfg, "save"):
            page = ClipsPage(cfg)
        page.cfg.save = lambda *a, **k: None   # nunca grava no perfil
        return page

    def test_aplicar_plano_preenche_os_cortes_e_liga_os_efeitos(self) -> None:
        page = self._page()
        page.sfx_switch.setChecked(False)
        count = page.apply_plan_text("resposta…\n" + LINHA)
        self.assertEqual(count, 2)
        self.assertEqual([row.start.text() for row in page.rows], ["12:03", "1:02:00"])
        self.assertEqual(page.rows[0].end.text(), "12:58.5")
        self.assertEqual(page.rows[0].title.text(), "A GRAÇA QUE ALCANÇA")
        self.assertEqual(page.rows[0].plan_badge.text(), "✦ 3")
        self.assertTrue(page.sfx_switch.isChecked() and page.punch_switch.isChecked())
        page.source_edit.setText("https://www.youtube.com/watch?v=abc")
        page.output_edit.setText("/tmp")
        clip = page._options().ranges[0]
        self.assertEqual(len(clip.markers), 3)
        self.assertEqual(clip.end, 778.5)

    def test_plano_com_erro_mantem_a_lista(self) -> None:
        page = self._page()
        page.rows[0].start.setText("00:10")
        with self.assertRaises(PlanError):
            page.apply_plan_text("nada aqui")
        self.assertEqual(page.rows[0].start.text(), "00:10")

    def test_altura_do_titulo_vai_para_o_estilo(self) -> None:
        page = self._page()
        page.title_stepper.setValue(40)
        self.assertEqual(page.caption_style().title_position, 40)
        self.assertEqual(page.cfg.clips_title_position, 40)


if __name__ == "__main__":
    unittest.main()
