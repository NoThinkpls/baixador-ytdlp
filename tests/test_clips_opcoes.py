"""Opções novas dos cortes: animações da legenda, acabamento e os bugs da revisão."""
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

from baixador_ytdlp.clips import (CaptionStyle, ClipError, ClipOptions, ClipRange, build_ass,
                                  build_srt, clamp_range, filter_graph, require_video_and_audio,
                                  stream_kinds, zoom_windows)
from baixador_ytdlp.tools import Toolchain

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")


def _words(*items: tuple[str, float]) -> list[dict]:
    return [{"text": text, "start": start, "end": start + 0.4} for text, start in items]


WORDS = _words(("um", 0.0), ("dois", 0.5), ("três", 1.0))


def _captions(animation: str, **extra) -> list[str]:
    ass = build_ass(WORDS, 2.0, style=CaptionStyle(animation=animation, **extra))
    return [line for line in ass.splitlines() if line.startswith("Dialogue: 0,")]


class AnimacoesTests(unittest.TestCase):
    def test_sem_destaque_e_uma_linha_simples(self) -> None:
        rows = _captions("none")
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].endswith("UM DOIS TRÊS"))
        self.assertNotIn("\\1c", rows[0])

    def test_so_a_cor_nao_aumenta(self) -> None:
        rows = _captions("color")
        self.assertEqual(len(rows), 3)
        self.assertIn("{\\1c&H00D7FF&}DOIS{\\r}", rows[1])
        self.assertNotIn("fscx112", "".join(rows))

    def test_karaoke_preenche_cada_palavra_no_seu_tempo(self) -> None:
        rows = _captions("karaoke")
        self.assertEqual(len(rows), 1)
        self.assertIn("{\\kf50}UM {\\kf50}DOIS {\\kf40}TRÊS", rows[0])
        header = build_ass(WORDS, 2.0, style=CaptionStyle(animation="karaoke"))
        # Primária = já falado (destaque), secundária = ainda não falado (texto).
        self.assertIn("Style: Caption,Arial,88,&H0000D7FF,&H00FFFFFF,", header)

    def test_uma_palavra_por_vez(self) -> None:
        rows = _captions("word")
        self.assertEqual([row.rsplit("}", 1)[1] for row in rows], ["UM", "DOIS", "TRÊS"])
        self.assertIn("\\t(0,90,", rows[0])

    def test_grupo_entra_com_pulo(self) -> None:
        rows = _captions("pop")
        self.assertIn("\\fscx70", rows[0])
        self.assertNotIn("\\fscx70", rows[1])      # só na entrada do grupo

    def test_caixa_atras_da_legenda(self) -> None:
        header = build_ass(WORDS, 2.0, style=CaptionStyle(background=True))
        caption = next(line for line in header.splitlines() if line.startswith("Style: Caption"))
        self.assertIn(",3,17,0,5,", caption)       # BorderStyle 3, folga, sem sombra

    def test_animacao_desconhecida_volta_ao_destaque(self) -> None:
        self.assertEqual(CaptionStyle(animation="??").normalized().animation, "highlight")

    def test_titulo_desce_quando_a_legenda_esta_no_alto(self) -> None:
        low = build_ass([], 3.0, style=CaptionStyle(position=70))
        high = build_ass([], 3.0, style=CaptionStyle(position=20))
        self.assertIn(",3,22,0,8,90,90,300,1", low)
        self.assertIn(",3,22,0,2,90,90,300,1", high)

    def test_titulo_o_corte_inteiro(self) -> None:
        ass = build_ass(WORDS, 9.5, title="Oi", title_seconds=0)
        self.assertIn("Dialogue: 1,0:00:00.00,0:00:09.50,Title,", ass)

    def test_srt_com_os_mesmos_grupos(self) -> None:
        srt = build_srt(WORDS, 2.0, CaptionStyle(words=2))
        self.assertEqual(srt.split("\n\n")[0], "1\n00:00:00,000 --> 00:00:01,000\nUM DOIS")
        self.assertIn("2\n00:00:01,000 --> 00:00:02,000\nTRÊS", srt)


class AcabamentoTests(unittest.TestCase):
    def test_zoom_alterna_nas_emendas(self) -> None:
        intervals = [(0.0, 2.0), (4.0, 5.0), (7.0, 9.0), (10.0, 11.0)]
        self.assertEqual(zoom_windows(intervals), [(2.0, 3.0), (5.0, 6.0)])
        graph = filter_graph(intervals, "crop", None, zoom_cuts=True)
        self.assertIn("scale=1166:2074,crop=1080:1920", graph)
        self.assertIn("enable='between(t,2.000,2.999)+between(t,5.000,5.999)'", graph)
        self.assertNotIn("overlay=0:0", filter_graph([(0.0, 3.0)], "crop", None, zoom_cuts=True))

    def test_barra_de_progresso_e_volume(self) -> None:
        graph = filter_graph([(0.0, 4.0)], "blur", None, progress_colour="#00E5FF",
                             normalize_audio=True)
        self.assertIn("color=c=0x00E5FF:s=1080x12", graph)
        self.assertIn("overlay=x='-w+w*t/4.000':y=H-h", graph)
        self.assertIn("loudnorm=I=-14", graph)
        self.assertIn("[ac0]loudnorm", graph)
        self.assertTrue(graph.endswith("format=yuv420p[v]"))


class RevisaoDeBugsTests(unittest.TestCase):
    def test_capa_de_mp3_nao_conta_como_video(self) -> None:
        probe = json.dumps({"streams": [
            {"codec_type": "audio", "disposition": {"attached_pic": 0}},
            {"codec_type": "video", "disposition": {"attached_pic": 1}}]})
        self.assertEqual(stream_kinds(probe), {"audio"})
        with self.assertRaisesRegex(ClipError, "só tem áudio"):
            require_video_and_audio(stream_kinds(probe))
        with self.assertRaisesRegex(ClipError, "não tem som"):
            require_video_and_audio({"video"})
        require_video_and_audio({"video", "audio"})
        self.assertEqual(stream_kinds("lixo"), set())

    def test_corte_que_sobra_com_menos_de_um_segundo(self) -> None:
        with self.assertRaisesRegex(ClipError, "menos de 1 segundo"):
            clamp_range(ClipRange(59.5, 70.0), 60.0)
        self.assertEqual(clamp_range(ClipRange(50.0, 70.0), 60.0).end, 60.0)


@unittest.skipUnless(FFMPEG and FFPROBE, "FFmpeg não instalado")
class WorkerRealTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def _run(self, source: Path, root: Path, **options) -> dict:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.workers import ClipWorker, TranscriptionWorker

        words = ([{"text": "oi", "start": 0.2, "end": 0.6}, {"text": "gente", "start": 0.7, "end": 1.1}]
                 + [{"text": "voltei", "start": 3.0, "end": 3.4}])

        def fake_run(worker: TranscriptionWorker) -> None:
            worker.opts.output_path.write_text(
                json.dumps({"segments": [{"start": 0, "end": 4, "text": "", "words": words}]}),
                encoding="utf-8")
            worker.finished_ok.emit(str(worker.opts.output_path))

        tc = Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                       bin_dir=root)
        clip_options = ClipOptions(source=str(source), ranges=(ClipRange(0.0, 4.0, "T"),),
                                   output_dir=root / "saida", framing="crop", **options)
        worker = ClipWorker(clip_options, tc, Settings())
        results: dict = {}
        worker.finished_ok.connect(lambda paths: results.update(ok=paths))
        worker.failed.connect(lambda message: results.update(error=message))
        transcribed = []
        with patch.object(TranscriptionWorker, "run",
                          lambda w: (transcribed.append(1), fake_run(w))), \
                patch("baixador_ytdlp.workers.preferred_video_encoder", return_value=""):
            worker.run()
        results["transcribed"] = bool(transcribed)
        return results

    def test_so_audio_e_recusado_antes_de_transcrever(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "podcast.mp3"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i", "sine=sample_rate=44100",
                            "-t", "5", str(source)], check=True)
            results = self._run(source, root)
        self.assertIn("só tem áudio", results["error"])
        self.assertFalse(results["transcribed"])     # antes: minutos de Whisper e erro do FFmpeg

    def test_todas_as_opcoes_juntas_geram_o_corte_e_o_srt(self) -> None:
        from baixador_ytdlp.clips import CaptionStyle as Style
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "origem.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i",
                            "sine=sample_rate=48000", "-t", "6", "-c:v", "libx264", "-preset",
                            "ultrafast", "-c:a", "aac", str(source)], check=True)
            results = self._run(source, root, zoom_cuts=True, progress_bar=True,
                                normalize_audio=True, save_srt=True,
                                style=Style(animation="karaoke", background=True))
            self.assertNotIn("error", results, results.get("error"))
            output = Path(results["ok"][0])
            self.assertTrue(output.with_suffix(".srt").is_file())

    def test_cancelado_nao_deixa_mp4_pela_metade(self) -> None:
        from baixador_ytdlp.workers import ClipWorker
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "origem.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=25", "-f", "lavfi", "-i",
                            "sine=sample_rate=48000", "-t", "6", "-c:v", "libx264", "-preset",
                            "ultrafast", "-c:a", "aac", str(source)], check=True)

            def render_and_cancel(self, source, offset, length, intervals, subtitles,
                                  destination, tracking=None, *_efeitos):
                destination.write_bytes(b"metade")
                self._cancelled.set()
                self._check()

            with patch.object(ClipWorker, "_render", render_and_cancel):
                results = self._run(source, root)
            self.assertIn("cancelados", results["error"])
            self.assertEqual(list((root / "saida").glob("*.mp4")), [])


if __name__ == "__main__":
    unittest.main()
