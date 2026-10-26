"""Cortes verticais: pausas, legenda palavra a palavra, título e o FFmpeg do render."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp.clips import (MAX_TAIL, TAIL_PAD, CaptionStyle, ClipError, ClipOptions,
                                  ClipRange, Loudness, Tracking,
                                  ass_colour, ass_header, ass_text, build_ass,
                                  caption_groups, clamp_range, clip_filename, display_word,
                                  filter_graph, keep_intervals, make_range, output_length,
                                  remap_time, remap_words, render_command, section_offset,
                                  video_codec_args, words_from_transcript)
from baixador_ytdlp.tools import Toolchain

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def _words(*items: tuple[str, float]) -> list[dict]:
    return [{"text": text, "start": start, "end": start + 0.4} for text, start in items]


class IntervalosTests(unittest.TestCase):
    def test_pausa_longa_vira_corte_e_curta_fica(self) -> None:
        words = _words(("um", 0.2), ("dois", 0.8), ("três", 3.0), ("quatro", 3.5))
        intervals = keep_intervals(words, 4.0, min_pause=0.6, pad=0.1)
        # 1,2 s → 3,0 s é silêncio de 1,8 s: sai. 0,6 → 0,8 é curto: fica. O fim da fala
        # ganha mais folga que o começo (TAIL_PAD), para a palavra terminar antes do corte.
        self.assertEqual(intervals, [(0.0, round(1.2 + TAIL_PAD, 3)), (2.9, 4.0)])

    def test_silencio_no_comeco_e_no_fim_sai(self) -> None:
        words = _words(("olá", 2.0), ("mundo", 2.5))
        self.assertEqual(keep_intervals(words, 6.0, min_pause=0.6, pad=0.1),
                         [(1.9, round(2.9 + TAIL_PAD, 3))])

    def test_sem_palavras_mantem_o_corte_inteiro(self) -> None:
        self.assertEqual(keep_intervals([], 12.5), [(0.0, 12.5)])

    def test_trechos_nunca_passam_da_duracao(self) -> None:
        words = _words(("fim", 9.8))
        start, end = keep_intervals(words, 10.0)[-1]
        self.assertLessEqual(end, 10.0)
        self.assertGreaterEqual(start, 0.0)

    def test_corte_espera_a_voz_cair(self) -> None:
        """O Whisper marca o fim da palavra cedo; a emenda só vem depois que a voz cai."""
        import numpy as np

        rate = 16000
        samples = np.zeros(rate * 4, dtype=np.float32)
        rng = np.random.default_rng(1)
        samples += rng.normal(0, 0.001, samples.size).astype(np.float32)   # ruído da sala
        # Fala de 0,5 s a 1,55 s (o "s" final vai até 1,55), outra de 3,0 s a 3,6 s.
        for start, end in ((0.5, 1.55), (3.0, 3.6)):
            span = slice(int(start * rate), int(end * rate))
            samples[span] += (0.2 * np.sin(np.arange(span.stop - span.start) * 0.3)).astype(
                np.float32)
        loud = Loudness(samples, rate)
        # Whisper disse que "mundo" acaba em 1,1 s: 0,45 s antes de a voz realmente parar.
        words = [{"text": "olá", "start": 0.5, "end": 0.9},
                 {"text": "mundo", "start": 0.95, "end": 1.1},
                 {"text": "tudo", "start": 3.0, "end": 3.5}]
        first_end = keep_intervals(words, 4.0, min_pause=0.6, loudness=loud)[0][1]
        self.assertGreaterEqual(first_end, 1.55)              # o fim da palavra fica
        self.assertLessEqual(first_end, 1.1 + MAX_TAIL + 0.1)   # e não segura demais
        without = keep_intervals(words, 4.0, min_pause=0.6)[0][1]
        self.assertLess(without, first_end)

    def test_folgas_nao_invadem_a_fala_seguinte(self) -> None:
        words = _words(("um", 0.0), ("dois", 1.05))   # "um" acaba em 0,4: pausa de 0,65 s
        intervals = keep_intervals(words, 2.0, min_pause=0.6)
        # Sai só o miolo do silêncio: folga longa depois de "um", curta antes de "dois".
        self.assertEqual(intervals, [(0.0, round(0.4 + TAIL_PAD, 3)), (0.93, 2.0)])
        # Som alto atravessando a pausa (música, eco): o fim segura até o meio da pausa e
        # não passa dele; o começo da fala seguinte não volta antes desse meio.
        loud = Loudness([0.3] * 28800 + [0.0] * 3200, 16000)
        first, second = keep_intervals(words, 2.0, min_pause=0.6, loudness=loud)
        self.assertEqual(first[1], 0.725)
        self.assertGreaterEqual(second[0], 0.725)

    def test_emendas_tem_rampa_de_volume(self) -> None:
        graph = filter_graph([(0.0, 1.0), (2.5, 4.0)], "crop", None)
        self.assertIn("afade=t=in:d=0.025", graph)
        self.assertIn("afade=t=out:st=0.975:d=0.025", graph)
        self.assertNotIn("afade", filter_graph([(0.0, 1.0)], "crop", None))   # sem emenda

    def test_remapeia_tempos_pela_emenda(self) -> None:
        intervals = [(0.0, 1.0), (3.0, 4.0)]
        self.assertAlmostEqual(remap_time(0.5, intervals), 0.5)
        self.assertAlmostEqual(remap_time(3.5, intervals), 1.5)
        self.assertAlmostEqual(remap_time(2.0, intervals), 1.0)   # dentro da pausa: na emenda
        self.assertAlmostEqual(output_length(intervals), 2.0)

    def test_palavra_dentro_de_trecho_removido_some(self) -> None:
        words = [{"text": "eco", "start": 1.5, "end": 1.9}]
        self.assertEqual(remap_words(words, [(0.0, 1.0), (3.0, 4.0)]), [])


class LegendaTests(unittest.TestCase):
    def test_grupos_respeitam_tamanho_e_fim_de_frase(self) -> None:
        words = _words(("Oi,", 0.0), ("gente.", 0.4), ("Hoje", 0.8), ("vamos", 1.2),
                       ("falar", 1.6), ("disso", 2.0))
        groups = caption_groups(words, 3)
        self.assertEqual([[w["text"] for w in g] for g in groups],
                         [["Oi,", "gente."], ["Hoje", "vamos", "falar"], ["disso"]])
        self.assertEqual(len(caption_groups(words, 2)[1]), 2)

    def test_pausa_fecha_o_grupo(self) -> None:
        words = _words(("antes", 0.0), ("depois", 2.0))
        self.assertEqual(len(caption_groups(words, 3)), 2)

    def test_destaque_na_palavra_falada_e_linhas_encostadas(self) -> None:
        words = _words(("um", 0.0), ("dois", 0.5), ("três", 1.0))
        ass = build_ass(words, 2.0)
        rows = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
        self.assertEqual(len(rows), 3)
        self.assertIn("{\\1c&H00D7FF&\\fscx112\\fscy112}DOIS{\\r}", rows[1])
        self.assertTrue(rows[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,"))
        self.assertTrue(rows[1].startswith("Dialogue: 0,0:00:00.50,0:00:01.00,"))
        self.assertIn("PlayResX: 1080", ass)
        self.assertIn("PlayResY: 1920", ass)

    def test_titulo_animado_nos_primeiros_segundos(self) -> None:
        ass = build_ass(_words(("oi", 0.0)), 10.0, title="Meu {corte}", title_seconds=2.0)
        title = next(line for line in ass.splitlines() if line.startswith("Dialogue: 1,"))
        self.assertTrue(title.startswith("Dialogue: 1,0:00:00.00,0:00:02.00,Title,"))
        self.assertIn("\\fad(", title)
        self.assertIn("\\t(0,220,", title)
        self.assertTrue(title.endswith("Meu (corte)"))   # chave abriria uma tag do ASS

    def test_titulo_nao_passa_do_fim_do_corte(self) -> None:
        ass = build_ass([], 1.2, title="Curto", title_seconds=2.0)
        self.assertIn("Dialogue: 1,0:00:00.00,0:00:01.20,", ass)

    def test_sem_titulo_nao_cria_linha(self) -> None:
        self.assertNotIn("Dialogue: 1,", build_ass(_words(("oi", 0.0)), 1.0, title="  "))

    def test_texto_da_palavra(self) -> None:
        self.assertEqual(display_word("mundo,", True), "MUNDO")
        self.assertEqual(display_word("sério?", False), "sério?")
        self.assertEqual(display_word("...", False), "...")
        self.assertEqual(ass_text("a\\N{b}"), "a/N(b)")


class EstiloDaLegendaTests(unittest.TestCase):
    """Posição, fonte, tamanho e cores escolhidos na página chegam ao ASS."""

    def test_posicao_fonte_tamanho_e_cores(self) -> None:
        style = CaptionStyle(font="Impact", size=100, text_color="#ff0000",
                             highlight_color="#00E5FF", position=50, words=2, uppercase=False)
        ass = build_ass(_words(("um", 0.0), ("dois", 0.5), ("três", 1.0)), 2.0, style=style)
        self.assertIn("Style: Caption,Impact,100,&H000000FF,", ass)
        rows = [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]
        self.assertTrue(all("{\\an5\\pos(540,960)}" in row for row in rows))
        self.assertIn("{\\1c&HFFE500&\\fscx112\\fscy112}dois{\\r}", rows[1])
        self.assertIn("três", rows[2])            # 2 palavras por legenda: "três" sozinha
        self.assertNotIn("um", rows[2])

    def test_legenda_mais_para_cima(self) -> None:
        ass = build_ass(_words(("oi", 0.0)), 1.0, style=CaptionStyle(position=20))
        self.assertIn("\\pos(540,384)", ass)

    def test_valores_fora_da_faixa_e_fonte_que_quebraria_o_ass(self) -> None:
        style = CaptionStyle(font="Ar,ial{x}\n", size=999, position=0, words=9).normalized()
        self.assertEqual(style.font, "Arialx")
        self.assertEqual((style.size, style.position, style.words), (160, 8, 4))
        self.assertNotIn(",", style.font)
        self.assertEqual(ass_colour("nada", "#FFD700"), "&H0000D7FF")

    def test_titulo_contrasta_com_a_cor_de_destaque(self) -> None:
        light = ass_header(CaptionStyle(highlight_color="#FFD700"))
        dark = ass_header(CaptionStyle(highlight_color="#202060"))
        self.assertIn("Style: Title,Arial,74,&H00141414,", light)
        self.assertIn("Style: Title,Arial,74,&H00FFFFFF,", dark)
        self.assertIn(",&H00602020,", dark)       # caixa do título na cor de destaque


class ValidacaoTests(unittest.TestCase):
    def test_intervalos_validos_e_invalidos(self) -> None:
        clip = make_range("1:30", "2:15,5", "  Título   bom ")
        self.assertEqual((clip.start, clip.end, clip.title), (90.0, 135.5, "Título bom"))
        for start, end in (("2:00", "1:00"), ("abc", "1:00"), ("0:00", "0:00.5"),
                           ("0:00", "11:00")):
            with self.subTest(start=start, end=end), self.assertRaises(ClipError):
                make_range(start, end)

    def test_ajusta_a_duracao_do_arquivo(self) -> None:
        self.assertEqual(clamp_range(ClipRange(10, 50), 30.0).end, 30.0)
        with self.assertRaises(ClipError):
            clamp_range(ClipRange(40, 50), 30.0)
        self.assertEqual(clamp_range(ClipRange(40, 50), 0.0).end, 50)

    def test_nome_do_arquivo_sem_caracteres_proibidos(self) -> None:
        self.assertEqual(clip_filename("Live: parte 1", 3, 'Por que "isso"? / sim'),
                         "Por que isso sim - Live parte 1 - corte03.mp4")
        self.assertEqual(clip_filename("video", 1, ""), "video - corte01.mp4")
        # O título vem primeiro: é por ele que se procura o corte na pasta.
        self.assertEqual(clip_filename("2026-10-25 10-54-15", 1, '"ISSO É MEDO?"'),
                         "ISSO É MEDO - 2026-10-25 10-54-15 - corte01.mp4")

    def test_sobra_do_trecho_baixado(self) -> None:
        self.assertAlmostEqual(section_offset(33.2, 30.0), 3.2)
        self.assertEqual(section_offset(30.1, 30.0), 0.0)

    def test_transcricao_sem_palavras_e_dividida(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.json"
            path.write_text(json.dumps({"segments": [
                {"start": 0.0, "end": 2.0, "text": "a b", "words": []},
                {"start": 3.0, "end": 3.5, "text": "c",
                 "words": [{"text": "c", "start": 3.0, "end": 3.4}]},
            ]}), encoding="utf-8")
            words = words_from_transcript(path)
        self.assertEqual([(w["text"], w["start"], w["end"]) for w in words],
                         [("a", 0.0, 1.0), ("b", 1.0, 2.0), ("c", 3.0, 3.4)])


class ComandoTests(unittest.TestCase):
    def test_grafo_emenda_trechos_e_grava_legenda(self) -> None:
        graph = filter_graph([(0.0, 1.0), (2.5, 4.0)], "crop", Path("/tmp/l.ass"))
        self.assertIn("[0:v:0]trim=start=2.500:end=4.000,setpts=PTS-STARTPTS[v1]", graph)
        self.assertIn("[v0][a0][v1][a1]concat=n=2:v=1:a=1[vc][ac]", graph)
        self.assertIn("crop=1080:1920", graph)
        self.assertNotIn("boxblur", graph)
        self.assertIn("subtitles=filename=", graph)
        self.assertIn("boxblur", filter_graph([(0.0, 1.0)], "blur", None))

    def test_grafo_que_segue_a_pessoa(self) -> None:
        tracking = Tracking(Path("/tmp/cmd.txt"), 420)
        graph = filter_graph([(0.0, 1.0)], "track", None, tracking)
        self.assertIn("[vc]scale=-2:1920,format=yuv444p,sendcmd=f=", graph)   # x de 1 em 1 px
        self.assertIn("crop@track=1080:1920:420:0", graph)
        self.assertNotIn("boxblur", graph)
        # Sem caminho calculado (falha, vídeo vertical): corte centralizado.
        self.assertIn("crop=1080:1920", filter_graph([(0.0, 1.0)], "track", None))

    def test_render_usa_trecho_e_encoder(self) -> None:
        command = render_command(Path("ffmpeg"), Path("/v/a.mp4"), 90.0, 30.0, [(0.0, 30.0)],
                                 "blur", None, Path("/v/out.mp4"), video_encoder="h264_nvenc")
        self.assertEqual(command[command.index("-ss") + 1], "90.000")
        self.assertEqual(command[command.index("-t") + 1], "30.000")
        self.assertEqual(command[command.index("-c:v") + 1], "h264_nvenc")
        self.assertIn("-cq", command)
        self.assertIn("-n", command)   # nunca sobrescreve
        with self.assertRaises(ClipError):
            render_command(Path("ffmpeg"), Path("/v/a.mp4"), 0, 1, [(0.0, 1.0)], "blur", None,
                           Path("/v/a.mp4"))

    def test_vaapi_fica_na_cpu(self) -> None:
        # O grafo complexo roda na CPU; mandar o resultado ao VAAPI exigiria hwupload.
        self.assertEqual(video_codec_args("h264_vaapi")[1], "libx264")
        self.assertEqual(video_codec_args("")[1], "libx264")


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg não instalado")
class ClipWorkerRealTests(unittest.TestCase):
    """O worker inteiro com o FFmpeg de verdade; só o Whisper é simulado."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_gera_corte_vertical_sem_as_pausas(self) -> None:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.workers import ClipWorker, TranscriptionWorker

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "origem.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i",
                            "sine=frequency=440:sample_rate=48000", "-t", "20",
                            "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                            str(source)], check=True)
            transcript = {"segments": [{"start": 0.2, "end": 7.0, "text": "", "words": [
                {"text": "Olá", "start": 0.2, "end": 0.6}, {"text": "pessoal.", "start": 0.7, "end": 1.2},
                {"text": "Voltei", "start": 5.0, "end": 5.5}, {"text": "aqui.", "start": 5.6, "end": 6.0},
            ]}]}

            def fake_run(worker: TranscriptionWorker) -> None:
                worker.opts.output_path.write_text(json.dumps(transcript), encoding="utf-8")
                worker.progress.emit(100)
                worker.finished_ok.emit(str(worker.opts.output_path))

            tc = Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                           bin_dir=root)
            options = ClipOptions(source=str(source), ranges=(ClipRange(2.0, 10.0, "Título"),),
                                  output_dir=root / "saida", framing="blur")
            worker = ClipWorker(options, tc, Settings())
            results: dict = {}
            worker.finished_ok.connect(lambda paths: results.update(ok=paths))
            worker.failed.connect(lambda message: results.update(error=message))
            with patch.object(TranscriptionWorker, "run", fake_run), \
                    patch("baixador_ytdlp.workers.preferred_video_encoder", return_value=""):
                worker.run()
            self.assertNotIn("error", results, results.get("error"))
            output = Path(results["ok"][0])
            self.assertEqual(output.name, "Título - origem - corte01.mp4")
            probe = subprocess.run(
                [FFPROBE, "-v", "error", "-show_entries", "stream=width,height:format=duration",
                 "-of", "json", str(output)], capture_output=True, text=True, check=True)
            info = json.loads(probe.stdout)
            video = next(s for s in info["streams"] if "width" in s)
            self.assertEqual((video["width"], video["height"]), (1080, 1920))
            # 8 s de trecho; sem os silêncios sobram ~2,6 s de fala.
            self.assertLess(float(info["format"]["duration"]), 3.5)

    def test_link_baixa_so_o_trecho(self) -> None:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.workers import ClipWorker

        options = ClipOptions(source="https://www.youtube.com/watch?v=abc",
                              ranges=(ClipRange(60.0, 90.0),), output_dir=Path("/tmp"))
        tc = Toolchain(ytdlp=Path("yt-dlp"), ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                       bin_dir=Path("/tmp"))
        worker = ClipWorker(options, tc, Settings())
        captured = {}

        class FakeRunner:
            def __init__(self, opts, cfg, tc):
                captured["opts"] = opts

            def run(self, _cb):
                return []

            def cancel(self):
                pass

            def tail(self, _lines=40):
                return ""

        with tempfile.TemporaryDirectory() as tmp, \
                patch("baixador_ytdlp.workers.create_runner", FakeRunner), \
                self.assertRaises(ClipError):
            worker._download(options.ranges[0], Path(tmp))
        self.assertEqual((captured["opts"].section_start, captured["opts"].section_end),
                         ("60.000", "90.000"))


if __name__ == "__main__":
    unittest.main()
