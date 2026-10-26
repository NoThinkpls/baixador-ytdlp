"""Título fixo no topo (faixa com cartão) e a página Cortes com escolhas visuais."""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp import clips
from baixador_ytdlp.clips import (BANNER_CAPTION_MIN, BANNER_CARD, BANNER_HEIGHT, BANNER_PADDING,
                                  CHAR_WIDTH, HEIGHT, WIDTH, CaptionStyle, ClipOptions,
                                  ClipRange, banner_label_size, banner_title_layout, build_ass,
                                  filter_graph)

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")
HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))
WORDS = [{"text": text, "start": start, "end": start + 0.4}
         for text, start in (("sei", 0.2), ("lá", 0.7), ("cara", 1.2))]
CARD_WIDTH = BANNER_CARD[2] - BANNER_CARD[0] - 2 * BANNER_PADDING


def _dialogues(ass: str, style: str) -> list[str]:
    return [line for line in ass.splitlines()
            if line.startswith("Dialogue:") and line.split(",")[3] == style]


class CartaoNoTopoTests(unittest.TestCase):
    def test_titulo_e_linha_de_cima_ficam_o_corte_inteiro(self) -> None:
        ass = build_ass(WORDS, 12.5, title='"Hard work beats talent"', banner=True,
                        banner_label="Paulo Muzy · Flow #594")
        rows = _dialogues(ass, "Banner")
        self.assertEqual(len(rows), 3)                       # cartão, linha de cima, título
        self.assertTrue(all(",0:00:00.00,0:00:12.50," in row for row in rows))
        self.assertIn("\\p1", rows[0])                        # cartão desenhado
        self.assertIn("PAULO MUZY · FLOW #594", rows[1])
        self.assertIn('"HARD WORK BEATS TALENT"', rows[2].replace("\\N", " "))
        self.assertEqual(_dialogues(ass, "Title"), [])        # sem o título animado
        self.assertIn("Style: Banner,", ass)

    def test_sem_titulo_nem_linha_fica_so_a_faixa(self) -> None:
        ass = build_ass(WORDS, 4.0, title="  ", banner=True)
        self.assertEqual(_dialogues(ass, "Banner"), [])

    def test_titulo_animado_continua_sem_a_faixa(self) -> None:
        ass = build_ass(WORDS, 4.0, title="Oi", banner_label="ignorada")
        self.assertEqual(_dialogues(ass, "Banner"), [])
        self.assertEqual(len(_dialogues(ass, "Title")), 1)

    def test_legenda_nao_sobe_para_dentro_da_faixa(self) -> None:
        style = CaptionStyle(position=20)
        ass = build_ass(WORDS, 4.0, title="Oi", banner=True, style=style)
        y = round(HEIGHT * BANNER_CAPTION_MIN / 100)
        self.assertTrue(all(f"\\pos({WIDTH // 2},{y})" in row
                            for row in _dialogues(ass, "Caption")))
        self.assertGreater(y, BANNER_HEIGHT)

    def test_titulo_curto_grande_e_longo_menor_em_ate_tres_linhas(self) -> None:
        short_size, short_lines = banner_title_layout("FOCO")
        long_title = "O DIA EM QUE EU QUASE DESISTI DE TUDO E COMECEI DO ZERO DE NOVO"
        long_size, long_lines = banner_title_layout(long_title)
        self.assertEqual(short_lines, ["FOCO"])
        self.assertGreater(short_size, long_size)
        self.assertLessEqual(len(long_lines), 3)
        self.assertEqual(" ".join(long_lines), long_title)
        self.assertTrue(all(len(line) * CHAR_WIDTH * long_size <= CARD_WIDTH
                            for line in long_lines))

    def test_linha_de_cima_comprida_diminui_para_caber(self) -> None:
        label = "PAULO MUZY + RAMIRES TIBANA + CONVIDADO ESPECIAL · FLOW PODCAST #594"
        size = banner_label_size(label)
        self.assertLess(size, banner_label_size("FLOW #594"))
        self.assertLessEqual(len(label) * CHAR_WIDTH * size, CARD_WIDTH)


class PlanoComVisualTests(unittest.TestCase):
    def test_plano_traz_tipo_de_titulo_e_linha_de_cima(self) -> None:
        from baixador_ytdlp.plano_ia import parse_look
        look = parse_look('Resposta… {"bx":1,"t":"f","l":"  PR. JOÃO ·  CULTO DE DOMINGO ",'
                          '"c":[["1:00","1:40","X",[]]]}')
        self.assertEqual((look.title_mode, look.label), ("banner", "PR. JOÃO · CULTO DE DOMINGO"))
        self.assertEqual(parse_look('{"bx":1,"t":"a","c":[]}').title_mode, "animated")

    def test_plano_antigo_ou_estranho_nao_muda_a_pagina(self) -> None:
        from baixador_ytdlp.plano_ia import parse_look
        look = parse_look('{"bx":1,"c":[["1:00","1:40","X",[]]]}')
        self.assertEqual((look.title_mode, look.label), ("", None))
        look = parse_look('{"bx":1,"t":"qualquer","l":42,"c":[]}')
        self.assertEqual((look.title_mode, look.label), ("", None))


class MontagemComFaixaTests(unittest.TestCase):
    def test_video_vai_para_baixo_da_faixa(self) -> None:
        area = HEIGHT - BANNER_HEIGHT
        graph = filter_graph([(0.0, 3.0), (4.0, 6.0)], "crop", None, banner=True,
                             zoom_cuts=True, punch=[(1.0, 1.5)])
        self.assertIn(f"crop={WIDTH}:{area},setsar=1[vf]", graph)
        self.assertIn(f"pad={WIDTH}:{HEIGHT}:0:{BANNER_HEIGHT}", graph)
        # Os zooms mexem só no vídeo: a faixa e o cartão ficam parados.
        self.assertIn(f"[vz]scale=1166:1452,crop={WIDTH}:{area}", graph)
        self.assertLess(graph.index("[vpm]"), graph.index("pad="))

    def test_seguir_a_pessoa_usa_a_altura_da_area(self) -> None:
        tracking = clips.Tracking(Path("cmd.txt"), 120, wide=((1.0, 2.0),))
        graph = filter_graph([(0.0, 3.0)], "track", None, tracking, banner=True)
        area = HEIGHT - BANNER_HEIGHT
        self.assertIn(f"scale=-2:{area},format=yuv444p", graph)
        self.assertIn(f"crop@track={WIDTH}:{area}:120:0", graph)
        self.assertIn(f"[bgw]scale={WIDTH}:{area}", graph)

    def test_sem_faixa_nada_muda(self) -> None:
        graph = filter_graph([(0.0, 3.0)], "blur", None)
        self.assertNotIn("pad=", graph)
        self.assertIn(f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease", graph)


class JanelaDaPessoaTests(unittest.TestCase):
    def test_analise_e_largura_seguem_a_area_do_video(self) -> None:
        from PySide6.QtWidgets import QApplication

        from baixador_ytdlp import reframe
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.tools import Toolchain
        from baixador_ytdlp.workers import ClipWorker

        QApplication.instance() or QApplication([])
        options = ClipOptions(source="x.mp4", ranges=(ClipRange(0, 5),), output_dir=Path("."),
                              framing="track", banner=True)
        worker = ClipWorker(options, Toolchain(ytdlp=Path("y"), ffmpeg=Path("f"),
                                               ffprobe=Path("p"), bin_dir=Path(".")),
                            Settings())
        track = reframe.Track([(0.0, 0.5), (5.0, 0.5)], 1920, 1080)
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(reframe, "analyze", return_value=track) as analyze, \
                patch.object(reframe, "crop_commands", return_value=[(0.0, 10)]) as commands:
            result = worker._track(Path("x.mp4"), 0.0, 5.0, [(0.0, 5.0)], Path(tmp))
        area = HEIGHT - BANNER_HEIGHT
        self.assertAlmostEqual(analyze.call_args.kwargs["aspect"], WIDTH / area)
        self.assertEqual(commands.call_args.args[2], track.scaled_width(area))
        self.assertIsNotNone(result)


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg ausente")
class CorteRealComFaixaTests(unittest.TestCase):
    def test_corte_sai_com_faixa_escura_e_cartao_amarelo(self) -> None:
        from PySide6.QtWidgets import QApplication

        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.tools import Toolchain
        from baixador_ytdlp.workers import ClipWorker, TranscriptionWorker

        QApplication.instance() or QApplication([])

        def fake_run(worker: TranscriptionWorker) -> None:
            worker.opts.output_path.write_text(json.dumps(
                {"segments": [{"start": 0, "end": 3, "text": "", "words": WORDS}]}),
                encoding="utf-8")
            worker.finished_ok.emit(str(worker.opts.output_path))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "origem.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i",
                            "sine=sample_rate=48000", "-t", "3", "-c:v", "libx264", "-preset",
                            "ultrafast", "-c:a", "aac", str(source)], check=True)
            tc = Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                           bin_dir=root)
            options = ClipOptions(source=str(source), ranges=(ClipRange(0.0, 3.0, "Foco"),),
                                  output_dir=root / "saida", framing="crop", banner=True,
                                  banner_label="Canal", remove_pauses=False)
            worker = ClipWorker(options, tc, Settings())
            results: dict = {}
            worker.finished_ok.connect(lambda paths: results.update(ok=paths))
            worker.failed.connect(lambda message: results.update(error=message))
            with patch.object(TranscriptionWorker, "run", fake_run), \
                    patch("baixador_ytdlp.workers.preferred_video_encoder", return_value=""):
                worker.run()
            self.assertNotIn("error", results, results.get("error"))
            raw = subprocess.run([FFMPEG, "-v", "error", "-ss", "1", "-i", results["ok"][0],
                                  "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                                 capture_output=True, check=True).stdout
        self.assertEqual(len(raw), WIDTH * HEIGHT * 3)

        def pixel(x: int, y: int) -> tuple[int, ...]:
            index = (y * WIDTH + x) * 3
            return tuple(raw[index:index + 3])

        self.assertTrue(all(value < 40 for value in pixel(540, 30)))      # faixa escura
        red, green, blue = pixel(80, BANNER_CARD[3] - 20)                 # canto do cartão
        self.assertGreater(red, 200)
        self.assertGreater(green, 170)
        self.assertLess(blue, 80)


@unittest.skipUnless(HAS_QT, "Qt ausente")
class PaginaVisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _page(self, **values):
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.ui.clips_page import ClipsPage
        cfg = Settings(**values)
        cfg.save = MagicMock()   # nunca grava no perfil de quem roda os testes
        return ClipsPage(cfg), cfg

    def test_escolher_titulo_fixo_vale_para_o_corte_e_fica_salvo(self) -> None:
        page, cfg = self._page(clips_position=20)
        page.title_picker.set_value("banner")
        page.label_edit.setText("Flow #594")
        page.label_edit.editingFinished.emit()
        self.assertTrue(cfg.clips_banner)
        self.assertEqual(cfg.clips_banner_label, "Flow #594")
        self.assertEqual(page.position_stepper.value(), BANNER_CAPTION_MIN)
        self.assertTrue(page.preview.state.banner)
        self.assertEqual(page.preview.state.label, "Flow #594")
        self.assertIn("cartão", page.rows[0].title.placeholderText())
        with tempfile.TemporaryDirectory() as tmp:
            page.source_edit.setText("https://www.youtube.com/watch?v=abc")
            page.output_edit.setText(tmp)
            page.rows[0].start.setText("00:10")
            page.rows[0].end.setText("00:40")
            options = page._options()
        self.assertTrue(options.banner)
        self.assertEqual(options.banner_label, "Flow #594")

    def test_plano_da_ia_escolhe_titulo_fixo_e_linha_de_cima(self) -> None:
        page, cfg = self._page()
        page.apply_plan_text('{"bx":1,"t":"f","l":"Pr. João · Culto",'
                             '"c":[["1:00","1:40","\\"DEUS NÃO TE ESQUECEU\\"",[]]]}')
        self.assertEqual(page.title_picker.value(), "banner")
        self.assertEqual(page.label_edit.text(), "Pr. João · Culto")
        self.assertTrue(cfg.clips_banner)
        self.assertEqual(cfg.clips_banner_label, "Pr. João · Culto")
        self.assertEqual(page.preview.state.title, '"DEUS NÃO TE ESQUECEU"')
        # Plano sem "t" e "l" (o formato antigo) não mexe no que a pessoa escolheu.
        page.apply_plan_text('{"bx":1,"c":[["2:00","2:40","OUTRO",[]]]}')
        self.assertEqual((page.title_picker.value(), page.label_edit.text()),
                         ("banner", "Pr. João · Culto"))

    def test_titulo_fixo_salvo_volta_na_abertura(self) -> None:
        page, _cfg = self._page(clips_banner=True, clips_banner_label="Canal",
                                clips_framing="crop")
        self.assertEqual((page.title_picker.value(), page.framing_picker.value()),
                         ("banner", "crop"))
        self.assertEqual(page.label_edit.text(), "Canal")

    def test_campos_de_cada_tipo_de_titulo(self) -> None:
        page, _cfg = self._page()
        page.resize(900, 2400)
        page.show()
        self.assertTrue(page.title_combo.isVisible())
        self.assertFalse(page.label_edit.isVisible())
        page.title_picker.set_value("banner")
        self.assertFalse(page.title_combo.isVisible())
        self.assertFalse(page.title_stepper.isVisible())
        self.assertTrue(page.label_edit.isVisible())
        page.hide()

    def test_previa_mostra_o_titulo_do_primeiro_corte(self) -> None:
        page, _cfg = self._page()
        self.assertEqual(page.preview.state.title, "")
        page.rows[0].title.setText("Trabalho duro vence")
        self.assertEqual(page.preview.state.title, "Trabalho duro vence")
        page.rows[0].title.clear()
        self.assertEqual(page.preview.state.title, "")

    def test_cartao_de_enquadramento_troca_com_clique_e_setas(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        page, cfg = self._page(clips_framing="track")
        cards = page.framing_picker.cards
        QTest.mouseClick(cards[1], Qt.MouseButton.LeftButton)
        self.assertEqual((cfg.clips_framing, page.preview.framing), ("blur", "blur"))
        QTest.keyClick(cards[1], Qt.Key.Key_Right)
        self.assertEqual(cfg.clips_framing, "crop")
        QTest.keyClick(cards[2], Qt.Key.Key_Right)
        self.assertEqual(cfg.clips_framing, "track")       # dá a volta

    def test_miniaturas_desenham_sem_erro(self) -> None:
        from PySide6.QtGui import QImage
        page, _cfg = self._page()
        page.preview.set_frame(QImage(64, 36, QImage.Format.Format_RGB32))
        for picker in (page.framing_picker, page.title_picker):
            for card in picker.cards:
                self.assertFalse(card.grab().isNull())
        page.title_picker.set_value("banner")
        self.assertFalse(page.preview.grab().isNull())

    def test_previa_acompanha_a_rolagem(self) -> None:
        page, _cfg = self._page()
        page.resize(900, 700)
        page.show()
        self.app.processEvents()
        rail = page.preview_rail
        bar = page.page.verticalScrollBar()
        top = rail.mapTo(page.page.widget(), rail.rect().topLeft()).y()
        bar.setValue(top + 200)
        self.app.processEvents()
        self.assertGreater(rail.content.y(), 0)
        self.assertLessEqual(rail.content.y() + rail.content.height(), rail.height())
        bar.setValue(0)
        self.app.processEvents()
        self.assertEqual(rail.content.y(), 0)
        page.hide()

    def test_sem_remover_pausas_some_a_pausa_minima(self) -> None:
        page, _cfg = self._page()
        page.show()
        page.pauses_switch.setChecked(False)
        self.assertFalse(page.pause_row.isVisible())
        page.pauses_switch.setChecked(True)
        self.assertTrue(page.pause_row.isVisible())
        page.hide()


if __name__ == "__main__":
    unittest.main()
