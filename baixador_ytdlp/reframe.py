"""Enquadramento automático: a janela 9:16 acompanha quem está em cena.

Mesma ideia do AutoFlip (Google/MediaPipe) e do "reenquadrar" do CapCut, em versão leve
e com o que o app já leva: o PyAV decodifica alguns quadros por segundo, o detector de
rostos YuNet (OpenCV Zoo, MIT, 230 KB) roda no onnxruntime do Whisper e, quando não há
rosto (pessoa de costas, longe), o movimento entre quadros indica onde está a ação.
Depois uma "câmera virtual" suaviza o caminho: zona morta para não tremer, velocidade
máxima para não chicotear e média móvel no fim. O FFmpeg recebe a posição do corte por
``sendcmd``, alguns valores por segundo.

Qualquer falha aqui (modelo ausente, vídeo estranho) devolve ``None`` e o corte segue
centralizado: o rastreamento é um extra, nunca motivo para o corte falhar.
"""
from __future__ import annotations

import math
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .plataforma import pasta_do_executavel

MODEL_NAME = "face_detection_yunet_2023mar.onnx"
INPUT_SIZE = 640                 # o YuNet 2023mar tem entrada fixa de 640x640
SAMPLE_FPS = 6.0                 # quadros analisados por segundo de vídeo
FACE_SCORE = 0.6
MOTION_THRESHOLD = 24            # diferença de cinza que conta como movimento
MOTION_MIN_SHARE = 0.004         # fração mínima de pixels em movimento para confiar nele
DEAD_ZONE = 0.06                 # deslocamento (fração da largura) que a câmera ignora
MAX_SPEED = 0.35                 # fração da largura por segundo
SETTLE_SECONDS = 0.8             # parado por esse tempo = a câmera assenta
EASE_SECONDS = 0.45              # duração aproximada da aceleração e da frenagem
DEFAULT_FPS = 30.0               # quando o vídeo não informa a taxa de quadros


def model_path() -> Path | None:
    """O modelo fica em ``assets/models``; procura também onde o PyInstaller põe os dados."""
    candidates = [pasta_do_executavel() / "assets" / "models" / MODEL_NAME,
                  Path(__file__).resolve().parents[1] / "assets" / "models" / MODEL_NAME]
    frozen = getattr(sys, "_MEIPASS", "")
    if frozen:
        candidates.insert(0, Path(frozen) / "assets" / "models" / MODEL_NAME)
    return next((path for path in candidates if path.is_file()), None)


# ----------------------------------------------------------------- detecção

def decode_yunet(outputs: dict, score_threshold: float = FACE_SCORE) -> list[tuple[float, ...]]:
    """Rostos ``(x, y, w, h, score)`` em pixels da entrada 640x640 do YuNet 2023mar.

    Cada escala (8, 16, 32) é uma grade; a caixa vem relativa à célula e o tamanho em log,
    como no ``FaceDetectorYN`` do OpenCV.
    """
    import numpy as np

    faces: list[tuple[float, ...]] = []
    for stride in (8, 16, 32):
        cls = outputs[f"cls_{stride}"].reshape(-1)
        obj = outputs[f"obj_{stride}"].reshape(-1)
        box = outputs[f"bbox_{stride}"].reshape(-1, 4)
        score = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        cols = INPUT_SIZE // stride
        for index in np.nonzero(score >= score_threshold)[0]:
            row, col = divmod(int(index), cols)
            cx = (col + float(box[index, 0])) * stride
            cy = (row + float(box[index, 1])) * stride
            w = float(np.exp(box[index, 2])) * stride
            h = float(np.exp(box[index, 3])) * stride
            faces.append((cx - w / 2, cy - h / 2, w, h, float(score[index])))
    return faces


class FaceDetector:
    def __init__(self, path: Path):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2     # o Whisper e o FFmpeg também querem a CPU
        self.session = onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"])
        self.names = [output.name for output in self.session.get_outputs()]

    def centers(self, bgr) -> list[tuple[float, float]]:
        """``(centro x, área)`` normalizados de cada rosto num quadro BGR de até 640 px."""
        import numpy as np

        height, width = bgr.shape[:2]
        canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.float32)
        canvas[:height, :width] = bgr[:INPUT_SIZE, :INPUT_SIZE]
        blob = canvas.transpose(2, 0, 1)[None]
        values = self.session.run(self.names, {"input": blob})
        faces = decode_yunet(dict(zip(self.names, values, strict=True)))
        return [((x + w / 2) / width, (w * h) / (width * height)) for x, _y, w, h, _s in faces]


def pick_face(faces: list[tuple[float, float]], previous: float | None) -> float | None:
    """O maior rosto; entre rostos de tamanho parecido, o mais perto de onde a câmera está."""
    if not faces:
        return None
    largest = max(area for _x, area in faces)
    candidates = [x for x, area in faces if area >= largest * 0.6]
    if previous is None:
        return max(faces, key=lambda face: face[1])[0]
    return min(candidates, key=lambda x: abs(x - previous))


def motion_center(previous_gray, gray) -> float | None:
    """Centro horizontal do que mudou entre dois quadros (quem anda, gesticula)."""
    import numpy as np

    if previous_gray is None or previous_gray.shape != gray.shape:
        return None
    moving = np.abs(gray.astype(np.int16) - previous_gray.astype(np.int16)) > MOTION_THRESHOLD
    columns = moving.sum(axis=0)
    total = float(columns.sum())
    if total < moving.size * MOTION_MIN_SHARE:
        return None
    positions = (np.arange(columns.size) + 0.5) / columns.size
    return float((columns * positions).sum() / total)


# ----------------------------------------------------------------- câmera virtual

def fill_gaps(points: list[float | None]) -> list[float] | None:
    """Repete o último alvo conhecido (e o primeiro para trás); ``None`` se não houve nenhum."""
    known = [value for value in points if value is not None]
    if not known:
        return None
    filled, last = [], known[0]
    for value in points:
        last = value if value is not None else last
        filled.append(last)
    return filled


def median(values: list[float], radius: int = 2) -> list[float]:
    result = []
    for index in range(len(values)):
        window = sorted(values[max(0, index - radius):index + radius + 1])
        result.append(window[len(window) // 2])
    return result


def gaussian(values: list[float], sigma: float) -> list[float]:
    """Suavização gaussiana sem atraso (olha para trás e para frente); bordas repetidas."""
    if sigma <= 0 or len(values) < 2:
        return list(values)
    radius = max(1, int(sigma * 3))
    weights = [math.exp(-(k * k) / (2 * sigma * sigma)) for k in range(-radius, radius + 1)]
    last = len(values) - 1
    result = []
    for index in range(len(values)):
        total = sum(w * values[min(last, max(0, index + k - radius))]
                    for k, w in enumerate(weights))
        result.append(total / sum(weights))
    return result


def camera_path(targets: list[float], rate: float = SAMPLE_FPS, *, view: float = 0.3164) -> list[float]:
    """Caminho suave do centro da janela, em fração da largura do vídeo.

    Como um operador de câmera: parado enquanto a pessoa fica perto do centro; quando ela sai
    da zona morta, a câmera acompanha até ela parar de novo. As retomadas e paradas viram
    curvas suaves (gaussiana sem atraso, ~0,5 s), a velocidade tem teto e uma segunda passada
    tira qualquer quina que o teto tenha deixado. ``view`` é a largura da janela 9:16 em
    relação ao quadro (0,316 num 16:9): a câmera não passa das bordas.
    """
    if not targets:
        return []
    low, high = view / 2, 1 - view / 2
    clean = [min(high, max(low, value)) for value in median(targets, radius=max(2, int(rate // 2)))]
    settle = max(2, int(rate * SETTLE_SECONDS))
    position, moving = clean[0], False
    setpoints = []
    for index, target in enumerate(clean):
        if not moving and abs(target - position) > DEAD_ZONE:
            moving = True
        if moving:
            position = target
            recent = clean[max(0, index - settle + 1):index + 1]
            if index >= settle - 1 and max(recent) - min(recent) < DEAD_ZONE / 2:
                moving = False          # a pessoa parou: a câmera assenta onde ela está
                position = sum(recent) / len(recent)
        setpoints.append(position)
    smooth = gaussian(setpoints, EASE_SECONDS * rate)
    step_limit = MAX_SPEED / rate
    limited = [smooth[0]]
    for value in smooth[1:]:
        limited.append(limited[-1] + max(-step_limit, min(step_limit, value - limited[-1])))
    final = gaussian(limited, 0.25 * rate)
    return [min(high, max(low, value)) for value in final]


@dataclass(frozen=True)
class Track:
    samples: list[tuple[float, float]]   # (tempo no corte, centro x de 0 a 1)
    width: int                           # dimensões do vídeo de origem
    height: int
    fps: float = DEFAULT_FPS             # um comando de posição por quadro do corte

    def scaled_width(self, height: int) -> int:
        """Largura depois do ``scale=-2:altura`` do FFmpeg."""
        return int(self.width * height / self.height) // 2 * 2


def analyze(source: Path, offset: float, length: float, *,
            progress: Callable[[float], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> Track | None:
    """Caminho da câmera ao longo do corte; ``None`` = não há o que rastrear."""
    import av
    import numpy as np

    path = model_path()
    detector = FaceDetector(path) if path else None
    times: list[float] = []
    targets: list[float | None] = []
    previous_face: float | None = None
    previous_gray = None
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        width, height = stream.codec_context.width, stream.codec_context.height
        rate = float(stream.average_rate or 0) or DEFAULT_FPS
        if not width or not height or width / height <= 9 / 16 + 0.01:
            return None   # já é vertical: não há para onde mover a janela
        scale = INPUT_SIZE / max(width, height)
        small = (max(2, int(width * scale) // 2 * 2), max(2, int(height * scale) // 2 * 2))
        container.seek(int(max(0.0, offset - 1.0) * av.time_base), any_frame=False, backward=True)
        next_sample = 0.0
        for frame in container.decode(stream):
            if cancelled and cancelled():
                return None
            if frame.time is None:
                continue
            moment = float(frame.time) - offset
            if moment < next_sample - 0.25 / SAMPLE_FPS:
                continue
            if moment > length:
                break
            next_sample = max(next_sample + 1 / SAMPLE_FPS, moment + 0.5 / SAMPLE_FPS)
            bgr = frame.to_ndarray(format="bgr24", width=small[0], height=small[1])
            gray = bgr[::4, ::4].mean(axis=2).astype(np.uint8)
            face = pick_face(detector.centers(bgr), previous_face) if detector else None
            if face is not None:
                previous_face = face
            target = face if face is not None else motion_center(previous_gray, gray)
            previous_gray = gray
            times.append(max(0.0, moment))
            targets.append(target)
            if progress and length:
                progress(min(1.0, moment / length))
    filled = fill_gaps(targets)
    if not filled:
        return None
    view = (height * 9 / 16) / width
    return Track(list(zip(times, camera_path(filled, view=view), strict=True)), width, height,
                 min(120.0, max(10.0, rate)))


# ----------------------------------------------------------------- FFmpeg

def crop_commands(samples: list[tuple[float, float]], intervals: list[tuple[float, float]],
                  scaled_width: int, crop_width: int,
                  remap: Callable[[float, list[tuple[float, float]]], float],
                  rate: float = DEFAULT_FPS) -> list[tuple[float, int]]:
    """Posição ``x`` do ``crop`` em cada quadro do corte já sem as pausas.

    Um comando por quadro e passo de 1 pixel: com menos comandos que quadros a imagem anda
    num quadro e para no seguinte, o "travado" que se vê em panorâmicas lentas.
    """
    kept = [(remap(time, intervals), center) for time, center in samples
            if any(start <= time <= end for start, end in intervals)]
    if not kept:
        return []
    total = sum(end - start for start, end in intervals)
    limit = max(0, scaled_width - crop_width)
    centers: list[float] = []
    index, frame = 0, 0
    while frame / rate <= total + 1e-6:
        moment = frame / rate
        while index + 1 < len(kept) and kept[index + 1][0] <= moment:
            index += 1
        time_a, center_a = kept[index]
        if index + 1 < len(kept) and moment > time_a:
            time_b, center_b = kept[index + 1]
            share = min(1.0, (moment - time_a) / max(1e-6, time_b - time_a))
            share = share * share * (3 - 2 * share)     # sem quina entre as amostras
            centers.append(center_a + (center_b - center_a) * share)
        else:
            centers.append(center_a)
        frame += 1
    # As emendas das pausas aproximam amostras distantes: uma passada leve evita degraus.
    centers = gaussian(centers, 0.08 * rate)
    commands = []
    for frame, center in enumerate(centers):
        x = int(round(center * scaled_width - crop_width / 2))
        # Um quarto de quadro antes: arredondado para cima (2/30 = 0,0667 > 0,06667), o
        # comando só valeria no quadro seguinte e a imagem daria um tranco.
        moment = max(0.0, (frame - 0.25) / rate)
        commands.append((round(moment, 4), max(0, min(limit, x))))
    return commands


def sendcmd_text(commands: list[tuple[float, int]], target: str = "crop@track") -> str:
    return "".join(f"{moment:.4f} {target} x {x};\n" for moment, x in commands)
