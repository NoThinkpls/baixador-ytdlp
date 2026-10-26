"""Quem está falando: o LR-ASD olha a boca de um rosto e ouve o áudio junto.

LR-ASD (Liao et al., IJCV 2025, MIT) é um modelo de "active speaker detection": recebe 25
recortes por segundo de um rosto (112x112, cinza) e o MFCC do áudio no mesmo trecho e diz,
quadro a quadro, se aquela pessoa está falando. É o mesmo modelo que o AutoClip usa para
reenquadrar vídeos. São 3,4 MB em ONNX, no onnxruntime que o Whisper já leva, na CPU. O
arquivo sai de ``scripts/export_lr_asd.py`` a partir dos pesos publicados pelos autores.

Este módulo só faz as contas: MFCC igual ao ``python_speech_features`` do treino, recorte do
rosto igual ao do script dos autores e a chamada do modelo em blocos.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

from .plataforma import pasta_do_executavel

MODEL_NAME = "lr_asd_ava.onnx"
VIDEO_FPS = 25                   # o modelo foi treinado com 25 quadros por segundo
AUDIO_STEPS = 4                  # 4 linhas de MFCC (10 ms) por quadro de vídeo
FACE_SIZE = 112
CROP_SCALE = 0.40                # folga em volta da caixa do rosto, como no treino
BOX_SCALE = 2.0                  # a caixa do S3FD (treino) tem ~2x o lado da do YuNet
BOX_RAISE = 0.2                  # e o centro dela fica mais alto (pega testa e cabelo)
CHUNK_FRAMES = 100               # blocos de 4 s: contexto suficiente e memória baixa
MIN_CHUNK_FRAMES = 6             # sobra menor que isso vai junto com o bloco anterior


def model_path() -> Path | None:
    candidates = [pasta_do_executavel() / "assets" / "models" / MODEL_NAME,
                  Path(__file__).resolve().parents[1] / "assets" / "models" / MODEL_NAME]
    frozen = getattr(sys, "_MEIPASS", "")
    if frozen:
        candidates.insert(0, Path(frozen) / "assets" / "models" / MODEL_NAME)
    return next((path for path in candidates if path.is_file()), None)


# ----------------------------------------------------------------- áudio

def _mel_filters(count: int, nfft: int, rate: int):
    import numpy as np

    def hz2mel(hz):
        return 2595 * np.log10(1 + hz / 700.0)

    def mel2hz(mel):
        return 700 * (10 ** (mel / 2595.0) - 1)

    points = np.linspace(hz2mel(0), hz2mel(rate / 2), count + 2)
    bins = np.floor((nfft + 1) * mel2hz(points) / rate)
    filters = np.zeros((count, nfft // 2 + 1))
    for j in range(count):
        for i in range(int(bins[j]), int(bins[j + 1])):
            filters[j, i] = (i - bins[j]) / (bins[j + 1] - bins[j])
        for i in range(int(bins[j + 1]), int(bins[j + 2])):
            filters[j, i] = (bins[j + 2] - i) / (bins[j + 2] - bins[j + 1])
    return filters


def mfcc(samples, rate: int = 16000):
    """MFCC (13 coeficientes, 100 por segundo) igual ao ``python_speech_features.mfcc``.

    ``samples`` em float de -1 a 1; o treino usou o WAV em inteiros de 16 bits, então a
    escala volta para lá (a energia do coeficiente 0 depende disso).
    """
    import numpy as np

    signal = np.asarray(samples, dtype=np.float64) * 32768.0
    signal = np.append(signal[:1], signal[1:] - 0.97 * signal[:-1])
    frame_len, step, nfft = int(round(0.025 * rate)), int(round(0.010 * rate)), 512
    count = 1 if len(signal) <= frame_len else 1 + math.ceil((len(signal) - frame_len) / step)
    padded = np.concatenate((signal, np.zeros((count - 1) * step + frame_len - len(signal))))
    power = np.empty((count, nfft // 2 + 1))
    for first in range(0, count, 4096):          # em blocos: corte de 10 min sem estourar RAM
        rows = np.arange(first, min(count, first + 4096))
        index = np.arange(frame_len)[None, :] + (rows * step)[:, None]
        power[rows] = np.square(np.abs(np.fft.rfft(padded[index], nfft))) / nfft
    eps = np.finfo(float).eps
    energy = np.maximum(power.sum(axis=1), eps)
    logs = np.log(np.maximum(power @ _mel_filters(26, nfft, rate).T, eps))
    # DCT-II ortonormal, só os 13 primeiros coeficientes, e o "lifter" de 22.
    n = np.arange(26)
    basis = np.cos(np.pi * np.arange(13)[:, None] * (2 * n[None, :] + 1) / 52)
    scale = np.full(13, math.sqrt(2 / 26))
    scale[0] = math.sqrt(1 / 26)
    cepstra = (logs @ basis.T) * scale
    cepstra *= 1 + 11 * np.sin(np.pi * np.arange(13) / 22)
    cepstra[:, 0] = np.log(energy)
    return cepstra.astype(np.float32)


# ----------------------------------------------------------------- rosto

def face_crop(gray, cx: float, cy: float, size: float):
    """Recorte 112x112 do rosto como no treino; ``size`` é o maior lado da caixa do YuNet.

    O script dos autores recorta, a partir da caixa do S3FD, um quadrado de lado
    ``2s(1+0,4)`` (``s`` = meio lado da caixa) um pouco abaixo do centro, reduz para 224 e
    fica com o miolo de 112: aqui isso vira direto o miolo, com interpolação bilinear. A
    caixa do YuNet é mais justa (sobrancelha ao queixo); convertida com ``BOX_SCALE`` e
    ``BOX_RAISE`` o recorte volta a mostrar o rosto como no treino. Medido no vídeo de
    exemplo do TalkNet: quem fala passou de nota -1,8 (recorte só da boca) para +3,0, e os
    outros rostos ficaram abaixo de -3.
    """
    import numpy as np

    half = size * BOX_SCALE / 2
    center_y = cy - size * BOX_RAISE + half * CROP_SCALE
    reach = half * (1 + CROP_SCALE) / 2
    height, width = gray.shape[:2]
    steps = (np.arange(FACE_SIZE) + 0.5) / FACE_SIZE * 2 * reach - reach
    xs = np.clip(cx + steps - 0.5, 0, width - 1)
    ys = np.clip(center_y + steps - 0.5, 0, height - 1)
    x0, y0 = np.floor(xs).astype(int), np.floor(ys).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (xs - x0)[None, :], (ys - y0)[:, None]
    image = gray.astype(np.float32)
    top = image[y0[:, None], x0[None, :]] * (1 - fx) + image[y0[:, None], x1[None, :]] * fx
    bottom = image[y1[:, None], x0[None, :]] * (1 - fx) + image[y1[:, None], x1[None, :]] * fx
    return (top * (1 - fy) + bottom * fy).astype(np.uint8)


# ----------------------------------------------------------------- modelo

class SpeakerModel:
    def __init__(self, path: Path):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2     # o Whisper e o FFmpeg também querem a CPU
        self.session = onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"])

    def scores(self, features, crops: list) -> list[float]:
        """Nota (logit; acima de 0 = falando) de cada recorte de uma sequência contínua.

        ``features`` é o MFCC a partir do primeiro recorte: ``4 x len(crops)`` linhas
        (faltando, repete a última). A sequência vai em blocos de ``CHUNK_FRAMES``.
        """
        import numpy as np

        total = len(crops)
        if total == 0:
            return []
        if len(features) < total * AUDIO_STEPS:
            filler = features[-1:] if len(features) else np.zeros((1, 13), dtype=np.float32)
            features = np.concatenate(
                [features, np.repeat(filler, total * AUDIO_STEPS - len(features), axis=0)])
        result: list[float] = []
        start = 0
        while start < total:
            end = min(total, start + CHUNK_FRAMES)
            if total - end < MIN_CHUNK_FRAMES:
                end = total
            video = np.stack(crops[start:end]).astype(np.float32)[None]
            audio = np.ascontiguousarray(
                features[start * AUDIO_STEPS:end * AUDIO_STEPS], dtype=np.float32)[None]
            values = self.session.run(None, {"audio": audio, "video": video})[0]
            result.extend(float(value) for value in np.asarray(values).reshape(-1)[:end - start])
            start = end
        return result
