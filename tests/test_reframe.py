"""Enquadramento que segue a pessoa: detector, câmera virtual e o ``sendcmd`` do FFmpeg."""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp import reframe
from baixador_ytdlp.clips import ClipOptions, ClipRange, remap_time
from baixador_ytdlp.tools import Toolchain

FFMPEG, FFPROBE = shutil.which("ffmpeg"), shutil.which("ffprobe")

try:
    import av  # noqa: F401
    import numpy as np
    import onnxruntime  # noqa: F401
    HAS_STACK = True
except ImportError:   # pragma: no cover - o app sempre leva os três
    HAS_STACK = False


def _moving_box(path: Path, seconds: int = 9) -> None:
    """Quadrado branco andando da esquerda para a direita num vídeo 16:9 preto."""
    subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", "color=black:s=640x360:r=25",
                    "-f", "lavfi", "-i", "color=white:s=60x60:r=25", "-f", "lavfi", "-i",
                    "sine=frequency=440:sample_rate=48000", "-filter_complex",
                    "[0:v][1:v]overlay=x='40+t*60':y=150:shortest=1[v]", "-map", "[v]",
                    "-map", "2:a", "-t", str(seconds), "-c:v", "libx264", "-preset",
                    "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)], check=True)


class CameraVirtualTests(unittest.TestCase):
    def test_zona_morta_segura_a_camera_parada(self) -> None:
        path = reframe.camera_path([0.5, 0.53, 0.48, 0.52, 0.5, 0.47] * 4, view=0.3)
        self.assertTrue(all(abs(value - 0.5) < 0.01 for value in path))

    def test_velocidade_maxima_e_bordas(self) -> None:
        targets = [0.2] * 6 + [0.95] * 30
        path = reframe.camera_path(targets, rate=6.0, view=0.3)
        steps = [abs(b - a) for a, b in zip(path, path[1:], strict=False)]
        self.assertLessEqual(max(steps), reframe.MAX_SPEED / 6.0 + 1e-9)
        self.assertGreaterEqual(min(path), 0.15)       # janela nunca sai do quadro
        self.assertLessEqual(max(path), 0.85)
        self.assertGreater(path[-1], 0.75)             # e chega lá

    def test_lacunas_repetem_o_ultimo_alvo(self) -> None:
        self.assertEqual(reframe.fill_gaps([None, 0.3, None, 0.6, None]),
                         [0.3, 0.3, 0.3, 0.6, 0.6])
        self.assertIsNone(reframe.fill_gaps([None, None]))

    def test_rosto_maior_e_continuidade(self) -> None:
        faces = [(0.2, 0.010), (0.7, 0.009), (0.5, 0.001)]
        self.assertEqual(reframe.pick_face(faces, None), 0.2)
        self.assertEqual(reframe.pick_face(faces, 0.65), 0.7)   # parecidos: fica perto
        self.assertIsNone(reframe.pick_face([], 0.5))

    @unittest.skipUnless(HAS_STACK, "numpy ausente")
    def test_centro_do_movimento(self) -> None:
        before = np.zeros((90, 160), dtype=np.uint8)
        after = before.copy()
        after[40:50, 120:130] = 255
        self.assertAlmostEqual(reframe.motion_center(before, after), 125 / 160, places=2)
        self.assertIsNone(reframe.motion_center(before, before))
        self.assertIsNone(reframe.motion_center(None, after))


@unittest.skipUnless(HAS_STACK, "numpy ausente")
class YuNetTests(unittest.TestCase):
    def test_decodifica_caixa_da_grade(self) -> None:
        outputs = {}
        for stride in (8, 16, 32):
            cells = (640 // stride) ** 2
            outputs[f"cls_{stride}"] = np.zeros((1, cells, 1), dtype=np.float32)
            outputs[f"obj_{stride}"] = np.zeros((1, cells, 1), dtype=np.float32)
            outputs[f"bbox_{stride}"] = np.zeros((1, cells, 4), dtype=np.float32)
        index = 5 * 20 + 10                       # linha 5, coluna 10 da grade de 32 px
        outputs["cls_32"][0, index, 0] = 0.9
        outputs["obj_32"][0, index, 0] = 0.9
        outputs["bbox_32"][0, index] = [0.5, 0.5, math.log(2), math.log(3)]
        faces = reframe.decode_yunet(outputs)
        self.assertEqual(len(faces), 1)
        x, y, w, h, score = faces[0]
        self.assertAlmostEqual(x + w / 2, 336.0, places=3)
        self.assertAlmostEqual(y + h / 2, 176.0, places=3)
        self.assertAlmostEqual(w, 64.0, places=3)
        self.assertAlmostEqual(h, 96.0, places=3)
        self.assertAlmostEqual(score, 0.9, places=5)

    def test_modelo_vai_junto_e_carrega(self) -> None:
        path = reframe.model_path()
        self.assertIsNotNone(path, "assets/models/face_detection_yunet_2023mar.onnx sumiu")
        assert path is not None
        detector = reframe.FaceDetector(path)
        self.assertEqual(detector.centers(np.zeros((360, 640, 3), dtype=np.uint8)), [])


class SendcmdTests(unittest.TestCase):
    def test_posicoes_seguem_a_emenda_sem_pausas(self) -> None:
        samples = [(0.0, 0.2), (2.0, 0.2), (4.0, 0.95), (6.0, 0.95)]
        intervals = [(0.0, 2.0), (4.0, 6.0)]       # 2 s de pausa removidos
        commands = reframe.crop_commands(samples, intervals, 3412, 1080, remap_time)
        self.assertEqual(commands[0], (0.0, 142))               # 0,2 * 3412 - 540
        self.assertAlmostEqual(commands[-1][0], 4.0, places=2)  # 4 s de vídeo final
        self.assertEqual(commands[-1][1], 2332)                 # limite: 3412 - 1080
        self.assertTrue(all(x % 2 == 0 for _t, x in commands))
        gaps = [b[0] - a[0] for a, b in zip(commands, commands[1:], strict=False)]
        self.assertAlmostEqual(max(gaps), 1 / reframe.COMMAND_RATE, places=3)

    def test_texto_do_sendcmd(self) -> None:
        self.assertEqual(reframe.sendcmd_text([(0.0, 10), (0.0667, 12)]),
                         "0.000 crop@track x 10;\n0.067 crop@track x 12;\n")

    def test_largura_depois_da_escala(self) -> None:
        self.assertEqual(reframe.Track([], 1920, 1080).scaled_width(1920), 3412)


@unittest.skipUnless(FFMPEG and FFPROBE and HAS_STACK, "FFmpeg/PyAV ausentes")
class SeguirPessoaRealTests(unittest.TestCase):
    """Corte de verdade: a janela 9:16 precisa acompanhar o objeto que anda."""

    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtCore import QCoreApplication
        cls.app = QCoreApplication.instance() or QCoreApplication([])

    def test_analise_acompanha_o_movimento(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "caixa.mp4"
            _moving_box(source)
            track = reframe.analyze(source, 0.5, 8.0)
        assert track is not None
        centers = [center for _t, center in track.samples]
        self.assertLess(centers[0], 0.25)
        self.assertGreater(centers[-1], 0.7)
        self.assertEqual(centers, sorted(centers))      # sempre para o mesmo lado, sem tremer

    def test_video_vertical_nao_e_rastreado(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "vertical.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=360x640:rate=25", "-t", "2", "-c:v", "libx264",
                            "-preset", "ultrafast", str(source)], check=True)
            self.assertIsNone(reframe.analyze(source, 0.0, 2.0))

    def test_corte_final_mostra_o_objeto_no_fim(self) -> None:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.workers import ClipWorker, TranscriptionWorker

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "caixa.mp4"
            _moving_box(source)
            transcript = {"segments": [{"start": 0.0, "end": 8.0, "text": "", "words": [
                {"text": f"p{i}", "start": i * 0.5, "end": i * 0.5 + 0.4} for i in range(16)]}]}

            def fake_run(worker: TranscriptionWorker) -> None:
                worker.opts.output_path.write_text(json.dumps(transcript), encoding="utf-8")
                worker.finished_ok.emit(str(worker.opts.output_path))

            tc = Toolchain(ytdlp=root / "yt-dlp", ffmpeg=Path(FFMPEG), ffprobe=Path(FFPROBE),
                           bin_dir=root)
            options = ClipOptions(source=str(source), ranges=(ClipRange(0.5, 8.5),),
                                  output_dir=root / "saida", framing="track",
                                  remove_pauses=False)
            worker = ClipWorker(options, tc, Settings())
            results: dict = {}
            worker.finished_ok.connect(lambda paths: results.update(ok=paths))
            worker.failed.connect(lambda message: results.update(error=message))
            with patch.object(TranscriptionWorker, "run", fake_run), \
                    patch("baixador_ytdlp.workers.preferred_video_encoder", return_value=""):
                worker.run()
            self.assertNotIn("error", results, results.get("error"))
            output = Path(results["ok"][0])
            # Último quadro em 108x192 tons de cinza: o quadrado tem de estar dentro dele.
            # (Centralizado, sem seguir, ele estaria fora da janela a essa altura.)
            raw = subprocess.run(
                [FFMPEG, "-v", "error", "-sseof", "-0.3", "-i", str(output), "-frames:v", "1",
                 "-vf", "scale=108:192", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                capture_output=True, check=True).stdout
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(192, 108)
            # A faixa do quadrado (y 150–210 de 360) fica longe da legenda (70% da altura).
            band = frame[80:118]
            columns = np.nonzero((band > 200).sum(axis=0))[0]
            self.assertGreater(columns.size, 5, "o quadrado não aparece no corte")


if __name__ == "__main__":
    unittest.main()
