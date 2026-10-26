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
        self.assertLess(max(path) - min(path), 0.005)      # parada, sem balançar junto
        self.assertTrue(all(abs(value - 0.5) < 0.03 for value in path))

    def test_balanco_parado_caminhada_suave_e_assenta(self) -> None:
        # 3 s balançando no lugar, 4 s andando para a direita, 3 s parado lá.
        targets = ([0.3 + (0.03 if i % 2 else -0.03) for i in range(18)]
                   + [0.3 + 0.1 * i / 6 for i in range(24)] + [0.7] * 18)
        path = reframe.camera_path(targets, rate=6.0, view=0.3164)
        self.assertLess(max(path[:12]) - min(path[:12]), 0.01)       # não acompanha o balanço
        self.assertGreater(path[-1], 0.66)                           # chegou
        self.assertLess(max(path[-6:]) - min(path[-6:]), 0.005)      # e assentou
        speeds = [b - a for a, b in zip(path, path[1:], strict=False)]
        accel = [abs(b - a) for a, b in zip(speeds, speeds[1:], strict=False)]
        self.assertLess(max(accel), 0.012)                           # sem trancos

    def test_velocidade_maxima_e_bordas(self) -> None:
        targets = [0.2] * 6 + [0.95] * 30
        path = reframe.camera_path(targets, rate=6.0, view=0.3)
        steps = [abs(b - a) for a, b in zip(path, path[1:], strict=False)]
        self.assertLessEqual(max(steps), reframe.MAX_SPEED / 6.0 + 1e-9)
        self.assertGreaterEqual(min(path), 0.15)       # janela nunca sai do quadro
        self.assertLessEqual(max(path), 0.85)
        self.assertGreater(path[-1], 0.75)             # e chega lá

    def test_troca_de_pessoa_corta_seco(self) -> None:
        targets = [0.25] * 30 + [0.75] * 30
        path = reframe.camera_path(targets, rate=10.0, view=0.3, cuts=[30])
        self.assertAlmostEqual(path[29], 0.25, places=3)
        self.assertAlmostEqual(path[30], 0.75, places=3)      # sem panorâmica no meio
        panned = reframe.camera_path(targets, rate=10.0, view=0.3)
        self.assertTrue(any(0.3 < value < 0.7 for value in panned))   # sem corte: atravessa

    def test_corte_seco_chega_ao_ffmpeg(self) -> None:
        samples = [(i / 10, 0.25 if i < 30 else 0.75) for i in range(60)]
        commands = reframe.crop_commands(samples, [(0.0, 6.0)], 3412, 1080, remap_time, 30.0,
                                         cuts=[3.0])
        xs = [x for _t, x in commands]
        left, right = round(0.25 * 3412 - 540), round(0.75 * 3412 - 540)
        jump = next(i for i, x in enumerate(xs) if x != left)
        self.assertEqual(xs[jump], right)                     # de um quadro para o outro
        self.assertAlmostEqual(jump / 30, 3.0, delta=0.04)

    def test_lacunas_repetem_o_ultimo_alvo(self) -> None:
        self.assertEqual(reframe.fill_gaps([None, 0.3, None, 0.6, None]),
                         [0.3, 0.3, 0.3, 0.6, 0.6])
        self.assertIsNone(reframe.fill_gaps([None, None]))

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


def _phrases(count: int, start: int = 0, talk: float = 2.0, pause: float = -2.5,
             period: int = 50) -> list[float]:
    """Nota do LR-ASD de quem fala: frases de 1,4 s e pausas de 0,6 s (a 25 quadros/s)."""
    return [talk if (start + i) % period < period * 0.7 else pause for i in range(count)]


class QuemFalaTests(unittest.TestCase):
    """Várias pessoas em cena: a câmera vai para quem fala, não para o maior rosto."""

    def test_segue_quem_fala_mesmo_com_rosto_menor(self) -> None:
        notes = _phrases(250)
        observations = [{0: (0.25, 0.20, -3.0), 1: (0.75, 0.06, notes[i])} for i in range(250)]
        chosen, cuts, wide = reframe.choose_speakers(observations)
        self.assertEqual(set(chosen), {0.75})
        self.assertEqual((cuts, any(wide)), ([], False))

    def test_quem_esta_parado_atras_nao_rouba_a_camera(self) -> None:
        # O caso do corte "SANTO": a pregadora anda com o microfone e alguém fica parado
        # atrás, às vezes com o rosto maior que o dela. Antes a câmera ia e voltava.
        count = 500
        notes = _phrases(count)
        observations = []
        for i in range(count):
            frame = {0: (0.3 + 0.4 * i / count, 0.07, notes[i])}
            if i % 40 < 30:                       # o detector às vezes perde quem está atrás
                frame[1] = (0.55, 0.09, -2.0)
            observations.append(frame)
        chosen, cuts, _wide = reframe.choose_speakers(observations)
        self.assertEqual(cuts, [])
        self.assertTrue(all(x == observations[i][0][0] for i, x in enumerate(chosen)))

    def test_dialogo_troca_de_pessoa_sem_pingue_pongue(self) -> None:
        count, half = 600, 300
        left, right = _phrases(count), _phrases(count, start=17)
        observations = [{0: (0.25, 0.08, left[i] if i < half else -2.0),
                         1: (0.75, 0.08, -2.0 if i < half else right[i])} for i in range(count)]
        chosen, cuts, _wide = reframe.choose_speakers(observations)
        self.assertEqual(len(cuts), 1)             # uma troca, e ela é um corte seco
        self.assertEqual(chosen[cuts[0] - 1], 0.25)
        self.assertEqual(chosen[cuts[0]], 0.75)
        self.assertAlmostEqual(cuts[0], half, delta=reframe.SWITCH_SECONDS * 25 + 15)

    def test_conversa_rapida_respeita_tempo_minimo_na_pessoa(self) -> None:
        # Os dois se alternam a cada 0,6 s: a câmera não pode trocar nesse ritmo.
        count = 500
        observations = [{0: (0.25, 0.08, 2.0 if (i // 15) % 2 == 0 else -2.0),
                         1: (0.75, 0.08, -2.0 if (i // 15) % 2 == 0 else 2.0)}
                        for i in range(count)]
        _chosen, cuts, _wide = reframe.choose_speakers(observations)
        gaps = [b - a for a, b in zip([0, *cuts], cuts, strict=False)]
        self.assertTrue(all(gap >= reframe.MIN_SHOT_SECONDS * 25 for gap in gaps))

    def test_comeca_em_quem_vai_falar_primeiro(self) -> None:
        notes = [-2.0] * 50 + _phrases(200)
        observations = [{0: (0.25, 0.12, -3.0), 1: (0.75, 0.06, notes[i])} for i in range(250)]
        chosen, cuts, _wide = reframe.choose_speakers(observations)
        self.assertEqual((set(chosen), cuts), ({0.75}, []))

    def test_cena_nova_corta_seco_e_decide_de_novo(self) -> None:
        # Live com várias câmeras: a trilha 0 é de uma cena, a 1 de outra (rostos não
        # atravessam cortes); cada cena escolhe o seu orador.
        notes = _phrases(300)
        observations = ([{0: (0.3, 0.08, notes[i])} for i in range(150)]
                        + [{1: (0.7, 0.08, notes[i]), 2: (0.2, 0.08, -3.0)}
                           for i in range(150, 300)])
        chosen, cuts, _wide = reframe.choose_speakers(observations, shots=[150])
        self.assertEqual(cuts, [150])
        self.assertEqual(set(chosen[:150]), {0.3})
        self.assertEqual(set(chosen[150:]), {0.7})

    def test_ninguem_falando_com_pessoas_espalhadas_mostra_o_quadro_inteiro(self) -> None:
        # Plateia ou banda: seguir um rosto qualquer (o "tecladista") não faz sentido.
        crowd = [{0: (0.15, 0.06, -3.0), 1: (0.85, 0.05, -2.5)} for _ in range(100)]
        solo = [{2: (0.6, 0.1, -1.0)} for _ in range(100)]
        chosen, cuts, wide = reframe.choose_speakers(crowd + solo, shots=[100])
        self.assertEqual(wide, [True] * 100 + [False] * 100)
        self.assertEqual(cuts, [100])
        self.assertEqual(set(chosen[100:]), {0.6})          # um rosto só: segue ele

    def test_ninguem_falando_grupo_que_cabe_fica_junto(self) -> None:
        observations = [{0: (0.42, 0.06, -3.0), 1: (0.56, 0.06, -3.0)} for _ in range(100)]
        chosen, _cuts, wide = reframe.choose_speakers(observations)
        self.assertFalse(any(wide))
        self.assertTrue(all(abs(x - 0.49) < 1e-9 for x in chosen if x is not None))

    def test_rosto_relampago_nao_conta(self) -> None:
        # Nuca ou reflexo detectado por 4 quadros, com nota alta por acaso.
        observations = [{0: (0.3, 0.08, -2.0)} for _ in range(100)]
        for i in range(40, 44):
            observations[i][1] = (0.8, 0.2, 3.0)
        chosen, cuts, wide = reframe.choose_speakers(observations)
        self.assertEqual((set(chosen), cuts, any(wide)), ({0.3}, [], False))

    def test_sem_modelo_fica_no_maior_rosto(self) -> None:
        observations = [{0: (0.25, 0.2, None), 1: (0.75, 0.05, None)} for _ in range(100)]
        chosen, cuts, wide = reframe.choose_speakers(observations)
        self.assertEqual((set(chosen), cuts, any(wide)), ({0.25}, [], False))

    def test_rosto_que_falha_por_um_instante_segura_a_posicao(self) -> None:
        notes = _phrases(250)
        observations = [{0: (0.25, 0.2, -3.0), 1: (0.75, 0.06, notes[i])} for i in range(250)]
        for i in range(60, 64):
            del observations[i][1]               # o detector perdeu quem fala
        chosen, cuts, _wide = reframe.choose_speakers(observations)
        self.assertEqual(chosen[60:64], [None] * 4)   # None = repete a última posição
        self.assertEqual(cuts, [])

    def test_trechos_inteiros_vao_para_o_tempo_do_corte(self) -> None:
        windows = reframe.output_windows([(1.0, 5.0)], [(0.0, 2.0), (3.0, 6.0)], remap_time)
        self.assertEqual(windows, ((1.0, 4.0),))     # a pausa de 2 a 3 s sumiu na emenda
        self.assertEqual(reframe.output_windows([(2.2, 2.8)], [(0.0, 2.0), (3.0, 6.0)],
                                                remap_time), ())


@unittest.skipUnless(HAS_STACK, "numpy ausente")
class TrilhasECenasTests(unittest.TestCase):
    def test_trilhas_seguem_o_mesmo_rosto_na_ordem_recebida(self) -> None:
        tracker = reframe.FaceTracker()
        small = reframe.Face(0.70, 0.3, 0.08, 0.15)
        large = reframe.Face(0.20, 0.3, 0.15, 0.30)
        first = tracker.assign([small, large], 0)
        # O maior escolhe primeiro, mas a resposta vem na ordem dos rostos recebidos.
        moved = [reframe.Face(0.71, 0.3, 0.08, 0.15), reframe.Face(0.21, 0.3, 0.15, 0.30)]
        second = tracker.assign(moved, 2)
        self.assertEqual([t.ident for t in first], [t.ident for t in second])
        self.assertNotEqual(first[0].ident, first[1].ident)
        later = tracker.assign([moved[0]], 2 + reframe.TRACK_GAP + 1)
        self.assertNotIn(later[0].ident, {t.ident for t in first})   # sumiu demais: novo

    def test_rosto_nao_atravessa_corte_de_camera(self) -> None:
        tracker = reframe.FaceTracker()
        face = reframe.Face(0.4, 0.3, 0.1, 0.2)
        before = tracker.assign([face], 0)[0]
        tracker.new_shot()
        after = tracker.assign([face], 2)[0]       # mesma posição, outra cena: outra pessoa
        self.assertNotEqual(before.ident, after.ident)

    def test_caixa_suavizada_e_presenca(self) -> None:
        track = reframe.FaceTrack(0, 0)
        for index, x in [(0, 0.30), (2, 0.50), (4, 0.31), (6, 0.32)]:   # 2: detecção torta
            track.boxes[index] = (x, 0.2, 0.1, 0.2)
        box = track.box_at(3, aspect=0.5)
        assert box is not None
        cx, cy, side = box
        self.assertAlmostEqual(cx, 0.365, places=6)      # mediana: o pulo do quadro 2 some
        self.assertAlmostEqual(cy, 0.3, places=6)
        self.assertAlmostEqual(side, 0.1, places=6)      # max(0,1, 0,2 * 0,5)
        self.assertIsNotNone(track.box_at(7))            # quadro sem detecção logo depois
        self.assertIsNone(track.box_at(6 + reframe.DETECT_EVERY + 1))   # já saiu de cena

    def test_corte_de_camera_pelo_histograma(self) -> None:
        rng = np.random.default_rng(3)
        detector = reframe.ShotDetector()
        dark = np.zeros((90, 160, 3), dtype=np.uint8)
        bright = np.full((90, 160, 3), 200, dtype=np.uint8)
        found = []
        for index in range(60):
            base = dark if index < 30 else bright
            noise = rng.integers(0, 30, base.shape, dtype=np.uint8)   # gente mexendo, ruído
            if detector.feed(reframe.color_histogram(base + noise)):
                found.append(index)
        self.assertEqual(found, [30])

    def test_fusao_lenta_conta_um_corte_so(self) -> None:
        detector = reframe.ShotDetector()
        found = []
        for index in range(40):
            value = min(255, index * 40)      # 7 quadros mudando muito, um atrás do outro
            frame = np.full((90, 160, 3), value, dtype=np.uint8)
            if detector.feed(reframe.color_histogram(frame)):
                found.append(index)
        self.assertEqual(len(found), 1)


@unittest.skipUnless(HAS_STACK, "numpy ausente")
class DetectorTests(unittest.TestCase):
    def test_caixas_repetidas_viram_uma(self) -> None:
        faces = [(10, 10, 50, 60, 0.9), (12, 11, 50, 60, 0.8), (300, 10, 50, 60, 0.7)]
        kept = reframe.suppress(faces)
        self.assertEqual([face[4] for face in kept], [0.9, 0.7])

    def test_decodifica_pontos_do_rosto(self) -> None:
        outputs = {}
        for stride in (8, 16, 32):
            cells = (640 // stride) ** 2
            for name, size in (("cls", 1), ("obj", 1), ("bbox", 4), ("kps", 10)):
                outputs[f"{name}_{stride}"] = np.zeros((1, cells, size), dtype=np.float32)
        index = 5 * 20 + 10
        outputs["cls_32"][0, index, 0] = outputs["obj_32"][0, index, 0] = 0.9
        outputs["kps_32"][0, index] = [0.25, 0.5, 0.75, 0.5, 0.5, 0.75, 0.3, 1.0, 0.7, 1.0]
        face = reframe.decode_yunet(outputs, landmarks=True)[0]
        self.assertAlmostEqual(face[5][3][0], (10 + 0.3) * 32, places=3)   # canto da boca
        self.assertAlmostEqual(face[5][3][1], (5 + 1.0) * 32, places=3)


class SendcmdTests(unittest.TestCase):
    def test_posicoes_seguem_a_emenda_sem_pausas(self) -> None:
        samples = [(0.0, 0.2), (2.0, 0.2), (4.0, 0.95), (6.0, 0.95)]
        intervals = [(0.0, 2.0), (4.0, 6.0)]       # 2 s de pausa removidos
        commands = reframe.crop_commands(samples, intervals, 3412, 1080, remap_time, 30.0)
        self.assertEqual(commands[0], (0.0, 142))               # 0,2 * 3412 - 540
        self.assertEqual(len(commands), 121)                    # 4 s a 30 quadros/s
        self.assertEqual(commands[-1][1], 2332)                 # limite: 3412 - 1080

    def test_um_comando_por_quadro_antes_do_quadro(self) -> None:
        # Com 15 comandos/s num vídeo de 30 quadros/s a imagem andava num quadro e parava no
        # seguinte; e um tempo arredondado para cima (0,0667 > 2/30) atrasava o comando.
        samples = [(t / 6, 0.2 + t / 6 * 0.05) for t in range(0, 61)]
        commands = reframe.crop_commands(samples, [(0.0, 10.0)], 3412, 1080, remap_time, 30.0)
        for frame, (moment, _x) in enumerate(commands[1:], start=1):
            self.assertLess(moment, frame / 30)
            self.assertGreater(moment, (frame - 1) / 30)
        steps = [b[1] - a[1] for a, b in zip(commands, commands[1:], strict=False)]
        self.assertNotIn(0, steps[5:-5])           # panorâmica contínua: anda todo quadro
        self.assertLessEqual(max(steps) - min(steps[5:-5]), 2)

    def test_texto_do_sendcmd(self) -> None:
        self.assertEqual(reframe.sendcmd_text([(0.0, 10), (0.0583, 12)]),
                         "0.0000 crop@track x 10;\n0.0583 crop@track x 12;\n")

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

    def test_ffmpeg_aplica_a_posicao_em_cada_quadro(self) -> None:
        # Régua: o valor de cada coluna é x mod 256, então o pixel da esquerda do corte
        # diz onde a janela está em cada quadro.
        samples = [(t / 6, 0.2 + t / 6 * 0.08) for t in range(0, 19)]
        commands = reframe.crop_commands(samples, [(0.0, 3.0)], 3412, 1080, remap_time, 30.0)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cmd.txt").write_text(reframe.sendcmd_text(commands), encoding="utf-8")
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "color=black:s=3412x1920:r=30,format=gray,geq=lum=mod(X\\,256)",
                            "-t", "3", "-vf", f"format=yuv444p,sendcmd=f=cmd.txt,"
                            f"crop@track=1080:1920:{commands[0][1]}:0,format=gray",
                            "-c:v", "ffv1", "regua.mkv"], cwd=root, check=True)
            raw = subprocess.run([FFMPEG, "-v", "error", "-i", str(root / "regua.mkv"), "-vf",
                                  "crop=1:1:0:0", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                                 capture_output=True, check=True).stdout
        seen = list(raw)
        expected = [x % 256 for _t, x in commands][:len(seen)]
        off = [abs(a - b) for a, b in zip(seen, expected, strict=True)]
        self.assertGreater(len(seen), 85)
        self.assertLessEqual(max(off), 1)     # quadro certo; ±1 é o arredondamento da cor

    def test_trecho_sem_orador_mostra_o_quadro_inteiro(self) -> None:
        # Entre 1 e 2 s ninguém fala e as pessoas não cabem na janela: entra o quadro
        # inteiro com fundo desfocado. Fora dele, a janela que segue a pessoa.
        from baixador_ytdlp.clips import Tracking, filter_graph

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "cmd.txt").write_text("0.0000 crop@track x 0;\n", encoding="utf-8")
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=1280x720:rate=25", "-f", "lavfi", "-i",
                            "anullsrc=r=48000:cl=mono", "-t", "3", "-c:v", "libx264",
                            "-preset", "ultrafast", "-shortest", "fonte.mp4"],
                           cwd=root, check=True)
            tracking = Tracking(root / "cmd.txt", 0, ((1.0, 2.0),))
            graph = filter_graph([(0.0, 3.0)], "track", None, tracking)
            subprocess.run([FFMPEG, "-v", "error", "-i", "fonte.mp4", "-filter_complex", graph,
                            "-map", "[v]", "-map", "[ac]", "-c:v", "libx264", "-preset",
                            "ultrafast", "saida.mp4"], cwd=root, check=True)
            blue = []
            for moment in (0.5, 1.5, 2.5):
                raw = subprocess.run(
                    [FFMPEG, "-v", "error", "-ss", str(moment), "-i", str(root / "saida.mp4"),
                     "-frames:v", "1", "-vf", "scale=108:192", "-f", "rawvideo", "-pix_fmt",
                     "rgb24", "-"], capture_output=True, check=True).stdout
                row = np.frombuffer(raw, dtype=np.uint8).reshape(192, 108, 3)[90].astype(int)
                # A faixa azul do testsrc2 fica no meio do quadro: a janela presa à esquerda
                # não chega nela; o quadro inteiro mostra.
                blue.append(int(((row[:, 2] > 150) & (row[:, 0] < 100) & (row[:, 1] < 100)).sum()))
        self.assertEqual(blue[0], 0)
        self.assertGreater(blue[1], 8)
        self.assertEqual(blue[2], 0)

    def test_video_de_celular_girado_e_tratado_como_vertical(self) -> None:
        # Gravado deitado (1280x720) com marca de rotação: na tela, e no corte, é vertical.
        with tempfile.TemporaryDirectory() as tmp:
            plain, rotated = Path(tmp) / "deitado.mp4", Path(tmp) / "celular.mp4"
            subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=1280x720:rate=25", "-t", "2", "-c:v", "libx264",
                            "-preset", "ultrafast", str(plain)], check=True)
            subprocess.run([FFMPEG, "-v", "error", "-display_rotation", "90", "-i", str(plain),
                            "-c", "copy", str(rotated)], check=True)
            self.assertIsNone(reframe.analyze(rotated, 0.0, 2.0))

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
