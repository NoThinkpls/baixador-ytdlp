"""LR-ASD (quem está falando): MFCC igual ao do treino, recorte do rosto e o modelo em blocos."""
from __future__ import annotations

import unittest

try:
    import numpy as np
    import onnxruntime  # noqa: F401
    HAS_STACK = True
except ImportError:   # pragma: no cover - o app sempre leva os dois
    HAS_STACK = False

from baixador_ytdlp import speaker


def _tone():
    t = np.arange(16000) / 16000
    signal = 0.3 * np.sin(2 * np.pi * 220 * t) + 0.1 * np.sin(2 * np.pi * 1500 * t) * (t > 0.5)
    return np.round(signal * 32768).astype(np.int16) / 32768.0


@unittest.skipUnless(HAS_STACK, "numpy/onnxruntime ausentes")
class MfccTests(unittest.TestCase):
    def test_igual_ao_python_speech_features(self) -> None:
        # Valores de python_speech_features 0.6, ``mfcc(sinal_int16, 16000)``, o que os
        # autores usaram no treino. Escala diferente (float sem voltar a int16) mudaria o
        # coeficiente 0 e o modelo veria "silêncio".
        features = speaker.mfcc(_tone(), 16000)
        self.assertEqual(features.shape, (99, 13))
        np.testing.assert_allclose(features[0, :4], [18.1765, 21.5838, 12.2684, 6.2517],
                                   atol=2e-3)
        np.testing.assert_allclose(features[60, :4], [19.8811, 10.4293, -13.3926, 6.4506],
                                   atol=2e-3)


@unittest.skipUnless(HAS_STACK, "numpy ausente")
class RecorteTests(unittest.TestCase):
    def test_recorte_pega_o_rosto_inteiro_como_no_treino(self) -> None:
        # Imagem em que o valor do pixel diz a linha: dá para ver onde o recorte começou.
        rows = np.repeat(np.arange(400, dtype=np.float32)[:, None] % 256, 400, axis=1)
        crop = speaker.face_crop(rows.astype(np.uint8), 200.0, 120.0, 100.0)
        self.assertEqual(crop.shape, (speaker.FACE_SIZE, speaker.FACE_SIZE))
        # Caixa do YuNet de 100 px centrada em y=120: o recorte cobre 140 px, da testa
        # (y≈70) até abaixo do queixo (y≈210). Antes cobria só 70 px, da ponta do nariz ao
        # queixo, e o LR-ASD não reconhecia quem falava (nota -1,8 no exemplo do TalkNet).
        self.assertAlmostEqual(float(crop[0, 56]), 70, delta=1.5)
        self.assertAlmostEqual(float(crop[-1, 56]), 209, delta=1.5)

    def test_rosto_na_borda_nao_quebra(self) -> None:
        gray = np.full((90, 160), 77, dtype=np.uint8)
        crop = speaker.face_crop(gray, 2.0, 88.0, 60.0)
        self.assertEqual(crop.shape, (112, 112))
        self.assertTrue((crop == 77).all())


@unittest.skipUnless(HAS_STACK, "numpy/onnxruntime ausentes")
class ModeloTests(unittest.TestCase):
    def test_modelo_vai_junto_e_da_uma_nota_por_quadro(self) -> None:
        path = speaker.model_path()
        self.assertIsNotNone(path, "assets/models/lr_asd_ava.onnx sumiu")
        assert path is not None
        model = speaker.SpeakerModel(path)
        crops = [np.full((112, 112), 128, dtype=np.uint8)] * 205   # 100 + 105 (sobra junta)
        notes = model.scores(np.zeros((205 * 4, 13), dtype=np.float32), crops)
        self.assertEqual(len(notes), 205)
        self.assertTrue(all(note < 0 for note in notes))     # rosto liso não está falando
        self.assertEqual(len(model.scores(np.zeros((3, 13), dtype=np.float32), crops[:8])), 8)
        self.assertEqual(model.scores(np.zeros((0, 13), dtype=np.float32), []), [])


if __name__ == "__main__":
    unittest.main()
