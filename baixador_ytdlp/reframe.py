"""Enquadramento automático: a janela 9:16 acompanha quem está em cena.

Mesma ideia do AutoFlip (Google/MediaPipe) e do "reenquadrar" do CapCut, em versão leve
e com o que o app já leva: o PyAV decodifica alguns quadros por segundo, o detector de
rostos YuNet (OpenCV Zoo, MIT, 230 KB) roda no onnxruntime do Whisper e, quando não há
rosto (pessoa de costas, longe), o movimento entre quadros indica onde está a ação.

Com mais de um rosto em cena, quem fala é quem a câmera segue: o LR-ASD (Liao et al.,
IJCV 2025, MIT, 3,4 MB), um modelo de "active speaker detection" treinado no AVA, olha a
boca de cada rosto junto com o áudio e diz quadro a quadro se aquela pessoa está falando
(ver ``speaker.py``). É o que o AutoClip e o TalkNet fazem, na CPU. Os cortes de câmera de
uma live com várias câmeras são achados pelo histograma de cor (como o PySceneDetect) e
cada cena é decidida sozinha: rosto não atravessa corte. Cena em que ninguém fala (plateia,
banda) mostra um rosto só, o grupo que cabe na janela ou o quadro inteiro com fundo
desfocado, como o AutoFlip.
Depois uma "câmera virtual" suaviza o caminho: zona morta para não tremer, velocidade
máxima para não chicotear e média móvel no fim. O FFmpeg recebe a posição do corte por
``sendcmd``, alguns valores por segundo.

Qualquer falha aqui (modelo ausente, vídeo estranho) devolve ``None`` e o corte segue
centralizado: o rastreamento é um extra, nunca motivo para o corte falhar.
"""
from __future__ import annotations

import math
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from . import speaker
from .plataforma import pasta_do_executavel

MODEL_NAME = "face_detection_yunet_2023mar.onnx"
INPUT_SIZE = 640                 # o YuNet 2023mar tem entrada fixa de 640x640
DETECT_EVERY = 2                 # detector de rostos a cada 2 quadros (12,5 por segundo)
FACE_SCORE = 0.6
MOTION_THRESHOLD = 24            # diferença de cinza que conta como movimento
MOTION_MIN_SHARE = 0.004         # fração mínima de pixels em movimento para confiar nele
MOTION_GAP = 3                   # quadros entre as duas imagens comparadas no movimento
DEAD_ZONE = 0.06                 # deslocamento (fração da largura) que a câmera ignora
MAX_SPEED = 0.35                 # fração da largura por segundo
SETTLE_SECONDS = 0.8             # parado por esse tempo = a câmera assenta
EASE_SECONDS = 0.45              # duração aproximada da aceleração e da frenagem
DEFAULT_FPS = 30.0               # quando o vídeo não informa a taxa de quadros
NMS_IOU = 0.3                    # caixas do mesmo rosto em âncoras vizinhas viram uma só
DETAIL_SIZE = 1280               # lado maior do quadro de onde sai o recorte do rosto
MIN_FACE_PX = 24                 # rosto menor que isso (no quadro de detalhe) não tem boca legível
TRACK_IOU = 0.3                  # sobreposição mínima para ser o mesmo rosto
TRACK_REACH = 1.0                # ou centro a até 1 largura de rosto (quem anda rápido)
TRACK_SIZE_RATIO = 1.5           # com tamanho parecido
TRACK_MEMORY = 0.5               # segundos que um rosto pode sumir e continuar o mesmo
TRACK_GAP = int(TRACK_MEMORY * speaker.VIDEO_FPS)
BOX_SMOOTH = 6                   # quadros de cada lado na mediana da caixa do rosto
MIN_TRACK_SECONDS = 0.5          # rosto que aparece menos que isso não conta
SCORE_WINDOW = 0.4               # segundos de cada lado na média da nota do LR-ASD
SPEAK_THRESHOLD = 0.0            # nota (logit) acima disso = falando
MIN_SPEECH_SECONDS = 0.4         # fala mínima para alguém ser "quem fala" na cena
SWITCH_SECONDS = 0.8             # outro precisa falar por esse tempo para a câmera trocar
MIN_SHOT_SECONDS = 2.0           # depois de trocar de pessoa, fica nela pelo menos isso
GROUP_SIZE = 0.6                 # rosto desse tamanho (relativo ao maior) conta no grupo
GROUP_PRESENCE = 0.3             # e precisa estar em pelo menos essa parte da cena
SHOT_DISTANCE = 0.5              # salto mínimo do histograma de cor para ser corte de câmera
SHOT_RATIO = 3.0                 # e quantas vezes maior que a variação normal da cena
MIN_SCENE_SECONDS = 0.5          # cortes mais próximos que isso (fusão) contam como um


def model_path() -> Path | None:
    """O modelo fica em ``assets/models``; procura também onde o PyInstaller põe os dados."""
    candidates = [pasta_do_executavel() / "assets" / "models" / MODEL_NAME,
                  Path(__file__).resolve().parents[1] / "assets" / "models" / MODEL_NAME]
    frozen = getattr(sys, "_MEIPASS", "")
    if frozen:
        candidates.insert(0, Path(frozen) / "assets" / "models" / MODEL_NAME)
    return next((path for path in candidates if path.is_file()), None)


# ----------------------------------------------------------------- detecção

def decode_yunet(outputs: dict, score_threshold: float = FACE_SCORE, *,
                 landmarks: bool = False) -> list[tuple]:
    """Rostos ``(x, y, w, h, score)`` em pixels da entrada 640x640 do YuNet 2023mar.

    Cada escala (8, 16, 32) é uma grade; a caixa vem relativa à célula e o tamanho em log,
    como no ``FaceDetectorYN`` do OpenCV. Com ``landmarks``, cada rosto ganha no fim os
    5 pontos ``((x, y), …)``: olho direito, olho esquerdo, nariz, canto direito e canto
    esquerdo da boca.
    """
    import numpy as np

    faces: list[tuple] = []
    for stride in (8, 16, 32):
        cls = outputs[f"cls_{stride}"].reshape(-1)
        obj = outputs[f"obj_{stride}"].reshape(-1)
        box = outputs[f"bbox_{stride}"].reshape(-1, 4)
        kps = outputs[f"kps_{stride}"].reshape(-1, 10) if landmarks else None
        score = np.sqrt(np.clip(cls, 0, 1) * np.clip(obj, 0, 1))
        cols = INPUT_SIZE // stride
        for index in np.nonzero(score >= score_threshold)[0]:
            row, col = divmod(int(index), cols)
            cx = (col + float(box[index, 0])) * stride
            cy = (row + float(box[index, 1])) * stride
            w = float(np.exp(box[index, 2])) * stride
            h = float(np.exp(box[index, 3])) * stride
            face: tuple = (cx - w / 2, cy - h / 2, w, h, float(score[index]))
            if kps is not None:
                face += (tuple(((col + float(kps[index, 2 * k])) * stride,
                                (row + float(kps[index, 2 * k + 1])) * stride)
                               for k in range(5)),)
            faces.append(face)
    return faces


def suppress(faces: list[tuple], iou: float = NMS_IOU) -> list[tuple]:
    """Uma caixa por rosto: o YuNet acende várias âncoras vizinhas para a mesma pessoa."""
    kept: list[tuple] = []
    for face in sorted(faces, key=lambda item: -item[4]):
        x, y, w, h = face[:4]
        overlaps = False
        for other in kept:
            ox, oy, ow, oh = other[:4]
            inter_w = max(0.0, min(x + w, ox + ow) - max(x, ox))
            inter_h = max(0.0, min(y + h, oy + oh) - max(y, oy))
            inter = inter_w * inter_h
            if inter / max(1e-6, w * h + ow * oh - inter) > iou:
                overlaps = True
                break
        if not overlaps:
            kept.append(face)
    return kept


@dataclass(frozen=True)
class Face:
    """Rosto num quadro, em fração da largura e da altura (0 a 1)."""
    x: float
    y: float
    w: float
    h: float
    points: tuple[tuple[float, float], ...] = ()

    @property
    def center(self) -> float:
        return self.x + self.w / 2

    @property
    def area(self) -> float:
        return self.w * self.h


class FaceDetector:
    def __init__(self, path: Path):
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.intra_op_num_threads = 2     # o Whisper e o FFmpeg também querem a CPU
        self.session = onnxruntime.InferenceSession(
            str(path), sess_options=options, providers=["CPUExecutionProvider"])
        self.names = [output.name for output in self.session.get_outputs()]

    def detect(self, bgr) -> list[Face]:
        """Rostos de um quadro BGR de até 640 px, já sem caixas repetidas."""
        import numpy as np

        height, width = bgr.shape[:2]
        canvas = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.float32)
        canvas[:height, :width] = bgr[:INPUT_SIZE, :INPUT_SIZE]
        blob = canvas.transpose(2, 0, 1)[None]
        values = self.session.run(self.names, {"input": blob})
        outputs = dict(zip(self.names, values, strict=True))
        faces = suppress(decode_yunet(outputs, landmarks="kps_8" in outputs))
        return [Face(x / width, y / height, w / width, h / height,
                     tuple((px / width, py / height) for px, py in (face[5] if len(face) > 5 else ())))
                for face in faces for x, y, w, h in [face[:4]]]

    def centers(self, bgr) -> list[tuple[float, float]]:
        """``(centro x, área)`` normalizados de cada rosto num quadro BGR de até 640 px."""
        return [(face.center, face.area) for face in self.detect(bgr)]


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


# ----------------------------------------------------------------- troca de cena

def color_histogram(bgr):
    """Histograma de cor (8x8x8) normalizado de um quadro BGR pequeno."""
    import numpy as np

    pixels = bgr[::4, ::4].reshape(-1, 3).astype(np.int32) // 32
    codes = pixels[:, 0] * 64 + pixels[:, 1] * 8 + pixels[:, 2]
    counts = np.bincount(codes, minlength=512).astype(np.float32)
    return counts / max(1.0, float(counts.sum()))


class ShotDetector:
    """Acha os cortes de câmera, como o ``ContentDetector`` do PySceneDetect e o AutoFlip.

    Live com várias câmeras troca de plano o tempo todo: a pessoa que estava à esquerda
    agora pode ser outra, e trilha de rosto ou câmera virtual que atravessa o corte mistura
    as duas cenas. Um corte é um salto grande na distribuição de cores entre dois quadros
    seguidos, bem maior que a variação normal da cena (gente andando, luz piscando).
    """

    def __init__(self, rate: float = speaker.VIDEO_FPS) -> None:
        self.previous = None
        self.recent: list[float] = []
        self.window = max(4, int(rate))
        self.min_gap = max(1, int(MIN_SCENE_SECONDS * rate))
        self.since = 10**9

    def feed(self, histogram) -> bool:
        import numpy as np

        self.since += 1
        if self.previous is None:
            self.previous = histogram
            return False
        distance = float(np.abs(histogram - self.previous).sum())
        self.previous = histogram
        typical = sorted(self.recent)[len(self.recent) // 2] if self.recent else 0.0
        self.recent = [*self.recent[-self.window + 1:], distance]
        if (distance > SHOT_DISTANCE and distance > SHOT_RATIO * typical
                and self.since >= self.min_gap):
            self.since = 0
            self.recent = []
            return True
        return False


# ----------------------------------------------------------------- quem está falando

def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """Sobreposição de duas caixas ``(x, y, w, h)``."""
    inter_w = max(0.0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    inter_h = max(0.0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    inter = inter_w * inter_h
    return inter / max(1e-9, a[2] * a[3] + b[2] * b[3] - inter)


@dataclass
class FaceTrack:
    """Um mesmo rosto dentro de uma cena: caixas detectadas e notas do LR-ASD por quadro."""
    ident: int
    shot: int
    boxes: dict[int, tuple[float, float, float, float]] = field(default_factory=dict)
    last: int = -1                                   # último quadro com detecção
    scores: dict[int, float] = field(default_factory=dict)
    pending: list = field(default_factory=list)       # (quadro, recorte) ainda sem nota

    def box_at(self, index: int, aspect: float = 9 / 16) -> tuple[float, float, float] | None:
        """``(centro x, centro y, lado)`` suavizado no quadro; ``None`` se o rosto não está lá.

        Centro em fração da largura e da altura; lado (o maior da caixa) em fração da
        largura, sendo ``aspect`` a altura do quadro sobre a largura. É a mediana das
        detecções em volta, como o ``medfilt`` do script dos autores: a caixa do detector
        treme alguns pixels de um quadro para outro, e o recorte da boca tremeria junto.
        """
        near = [frame for frame in range(index - TRACK_GAP, index + TRACK_GAP + 1)
                if frame in self.boxes]
        before = [frame for frame in near if frame <= index]
        after = [frame for frame in near if frame >= index]
        bridged = bool(before and after)        # detectado antes e depois, sem buraco longo
        if not bridged and min((abs(frame - index) for frame in near),
                               default=TRACK_GAP + 1) > DETECT_EVERY:
            return None
        window = [self.boxes[frame] for frame in near if abs(frame - index) <= BOX_SMOOTH]
        if not window:
            window = [self.boxes[before[-1] if before else after[0]]]
        return (_median([x + w / 2 for x, _y, w, _h in window]),
                _median([y + h / 2 for _x, y, _w, h in window]),
                _median([max(w, h * aspect) for _x, _y, w, h in window]))


def _box_distance(old: tuple[float, float, float, float],
                  new: tuple[float, float, float, float]) -> float | None:
    """Distância entre os centros (em larguras de rosto) se puder ser o mesmo rosto.

    Sobreposição sozinha falha com quem anda rápido ou com rosto pequeno: entre duas
    detecções a caixa já saiu de cima da anterior. Vale também o centro perto, com tamanho
    parecido.
    """
    width = max(old[2], new[2])
    distance = math.hypot(old[0] + old[2] / 2 - new[0] - new[2] / 2,
                          old[1] + old[3] / 2 - new[1] - new[3] / 2) / max(1e-9, width)
    similar = width / max(1e-9, min(old[2], new[2])) <= TRACK_SIZE_RATIO
    if iou(old, new) > TRACK_IOU or (similar and distance <= TRACK_REACH):
        return distance
    return None


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


class FaceTracker:
    """Liga as detecções de um mesmo rosto entre quadros pela sobreposição das caixas."""

    def __init__(self) -> None:
        self.tracks: list[FaceTrack] = []
        self.shot = 0

    def new_shot(self) -> None:
        self.shot += 1                        # nenhum rosto atravessa um corte de câmera

    def assign(self, faces: list[Face], index: int) -> list[FaceTrack]:
        """A trilha de cada rosto, na ordem recebida: a de maior sobreposição ou uma nova."""
        alive = [track for track in self.tracks
                 if track.shot == self.shot and index - track.last <= TRACK_GAP]
        taken: set[int] = set()
        result: dict[int, FaceTrack] = {}
        for position, face in sorted(enumerate(faces), key=lambda item: -item[1].area):
            box = (face.x, face.y, face.w, face.h)
            best, closest = None, 0.0
            for track in alive:
                if track.ident not in taken:
                    distance = _box_distance(track.boxes[track.last], box)
                    if distance is not None and (best is None or distance < closest):
                        best, closest = track, distance
            if best is None:
                best = FaceTrack(len(self.tracks), self.shot)
                self.tracks.append(best)
            best.boxes[index] = box
            best.last = index
            taken.add(best.ident)
            result[position] = best
        return [result[position] for position in range(len(faces))]


def smooth_scores(values: list[float | None], radius: int) -> list[float | None]:
    """Média das notas em volta de cada quadro (só onde o rosto está)."""
    result: list[float | None] = []
    for index, value in enumerate(values):
        if value is None:
            result.append(None)
            continue
        near = [item for item in values[max(0, index - radius):index + radius + 1]
                if item is not None]
        result.append(sum(near) / len(near))
    return result


Observation = dict[int, tuple[float, float, float | None]]


def choose_speakers(observations: list[Observation], shots: Sequence[int] = (),
                    rate: float = speaker.VIDEO_FPS, view: float = 0.3164,
                    ) -> tuple[list[float | None], list[int], list[bool]]:
    """Centro x a seguir em cada quadro, onde a câmera corta seco e onde mostra tudo.

    ``observations[i]`` é ``{trilha: (centro x, largura do rosto, nota do LR-ASD ou None)}``
    e ``shots`` são os quadros em que começa uma cena nova. Cada cena é decidida sozinha:

    - alguém fala nela: a câmera segue quem fala; troca de pessoa só quando outra fala por
      ``SWITCH_SECONDS`` e nunca antes de ``MIN_SHOT_SECONDS`` na atual (sem pingue-pongue);
      nas pausas fica em quem falou por último;
    - ninguém fala (plateia, banda, a câmera longe demais para ler a boca): um rosto só é
      seguido; vários que cabem na janela ficam juntos; vários espalhados viram o quadro
      inteiro com fundo desfocado (terceira lista), como o AutoFlip e o OpusClip fazem.

    Rosto que aparece por menos de ``MIN_TRACK_SECONDS`` (nuca, reflexo, detecção falsa)
    não conta. Sem rosto, a amostra fica ``None`` e o movimento da cena decide.
    """
    count = len(observations)
    bounds = [0, *sorted(shot for shot in set(shots) if 0 < shot < count), count]
    targets: list[float | None] = []
    cuts: list[int] = []
    wide: list[bool] = []
    for first, last in zip(bounds, bounds[1:], strict=False):
        local, switches, spread = _choose_in_shot(observations[first:last], rate, view)
        if first > 0:
            cuts.append(first)
        cuts += [first + index for index in switches]
        targets += local
        wide += [spread] * (last - first)
    return targets, cuts, wide


def _choose_in_shot(frames: list[Observation], rate: float, view: float,
                    ) -> tuple[list[float | None], list[int], bool]:
    count = len(frames)
    presence: dict[int, int] = {}
    for frame in frames:
        for ident in frame:
            presence[ident] = presence.get(ident, 0) + 1
    minimum = min(int(MIN_TRACK_SECONDS * rate), max(1, count // 2))
    real = {ident for ident, seen in presence.items() if seen >= minimum}
    frames = [{ident: value for ident, value in frame.items() if ident in real}
              for frame in frames]
    radius = max(1, int(SCORE_WINDOW * rate))
    smooth = {ident: smooth_scores([frame[ident][2] if ident in frame else None
                                    for frame in frames], radius) for ident in real}
    talking = {ident: sum(1 for value in values if value is not None and value > SPEAK_THRESHOLD)
               for ident, values in smooth.items()}
    speakers = {ident for ident, seen in talking.items() if seen >= MIN_SPEECH_SECONDS * rate}
    if speakers:
        targets, switches = _follow_speakers(frames, smooth, speakers, rate)
        return targets, switches, False
    return _frame_people(frames, view)


def _follow_speakers(frames: list[Observation], smooth: dict[int, list[float | None]],
                     speakers: set[int], rate: float) -> tuple[list[float | None], list[int]]:
    def speaking(ident: int, index: int) -> float | None:
        value = smooth[ident][index]
        return value if value is not None and value > SPEAK_THRESHOLD else None

    # Antes de alguém abrir a boca, a câmera já está em quem vai falar primeiro.
    current = min(speakers, key=lambda ident: next(
        index for index in range(len(frames)) if speaking(ident, index) is not None))
    hold = max(1, int(SWITCH_SECONDS * rate))
    memory = int(TRACK_MEMORY * rate)
    dwell = int(MIN_SHOT_SECONDS * rate)
    shown: int | None = None
    since = 0
    pending: int | None = None
    streak = arrived = 0
    last_seen: dict[int, int] = {}
    targets: list[float | None] = []
    switches: list[int] = []
    for index, frame in enumerate(frames):
        for ident in frame:
            last_seen[ident] = index
        live = [(value, ident) for ident in frame if ident in speakers
                for value in [speaking(ident, index)] if value is not None]
        winner = max(live)[1] if live else None
        gone = current not in frame and index - last_seen.get(current, -10**9) > memory
        if gone and winner is not None:
            current, pending, streak = winner, None, 0      # saiu de cena: vai para quem fala
        elif winner is not None and winner != current:
            if pending != winner:
                pending, streak, arrived = winner, 0, index
            streak += 1
            if streak >= hold and index - since >= dwell:
                # Confirmado: o corte volta para quando a pessoa começou a falar, como um
                # editor faria, e não fica atrasado o tempo da confirmação.
                start = max(arrived, since + dwell)
                current, pending, streak = winner, None, 0
                for back in range(start, index):
                    targets[back] = frames[back][current][0] if current in frames[back] else None
                if any(current in frames[back] for back in range(start, index)):
                    switches.append(start)
                    shown, since = current, start
        elif winner == current:
            pending, streak = None, 0       # a pessoa atual voltou a falar: fica nela
        # Ninguém falando (respiração entre frases) não zera a vez de quem estava chegando.
        if current != shown and current in frame:
            if shown is not None:
                switches.append(index)
            shown, since = current, index
        # Quem fala sumiu por um instante (virou, falhou a detecção): segura a posição.
        targets.append(frame[current][0] if current in frame else None)
    return targets, switches


def _frame_people(frames: list[Observation], view: float) -> tuple[list[float | None], list[int], bool]:
    """Cena sem ninguém falando: um rosto, um grupo que cabe na janela ou o quadro inteiro."""
    totals: dict[int, list[float]] = {}
    for frame in frames:
        for ident, (center, width, _score) in frame.items():
            entry = totals.setdefault(ident, [0, 0.0, 0.0])
            entry[0] += 1
            entry[1] += center
            entry[2] += width
    if not totals:
        return [None] * len(frames), [], False
    stats = {ident: (seen, center / seen, width / seen)
             for ident, (seen, center, width) in totals.items()}
    main = max(stats, key=lambda ident: stats[ident][0] * stats[ident][2] ** 2)
    group = [ident for ident, (seen, _center, width) in stats.items()
             if ident == main or (width >= GROUP_SIZE * stats[main][2]
                                  and seen >= GROUP_PRESENCE * len(frames))]
    left = min(stats[ident][1] - stats[ident][2] / 2 for ident in group)
    right = max(stats[ident][1] + stats[ident][2] / 2 for ident in group)
    if len(group) > 1 and right - left > view * 0.9:
        return [0.5] * len(frames), [], True
    targets: list[float | None] = []
    for frame in frames:
        present = [frame[ident] for ident in group if ident in frame]
        if not present:
            targets.append(None)
            continue
        low = min(center - width / 2 for center, width, _score in present)
        high = max(center + width / 2 for center, width, _score in present)
        targets.append((low + high) / 2)
    return targets, [], False


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


def camera_path(targets: list[float], rate: float = speaker.VIDEO_FPS, *, view: float = 0.3164,
                cuts: Sequence[int] = ()) -> list[float]:
    """Caminho suave do centro da janela, em fração da largura do vídeo.

    Como um operador de câmera: parado enquanto a pessoa fica perto do centro; quando ela sai
    da zona morta, a câmera acompanha até ela parar de novo. As retomadas e paradas viram
    curvas suaves (gaussiana sem atraso, ~0,5 s), a velocidade tem teto e uma segunda passada
    tira qualquer quina que o teto tenha deixado. ``view`` é a largura da janela 9:16 em
    relação ao quadro (0,316 num 16:9): a câmera não passa das bordas. Em cada ``cuts``
    (troca de pessoa) o caminho recomeça: a câmera corta seco para a outra pessoa.
    """
    if not targets:
        return []
    bounds = [0, *sorted(cut for cut in set(cuts) if 0 < cut < len(targets)), len(targets)]
    if len(bounds) > 2:
        path: list[float] = []
        for first, last in zip(bounds, bounds[1:], strict=False):
            path += camera_path(targets[first:last], rate, view=view)
        return path
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
    cuts: tuple[float, ...] = ()         # instantes (no corte) em que a câmera corta seco
    wide: tuple[tuple[float, float], ...] = ()   # trechos (no corte) com o quadro inteiro

    def scaled_width(self, height: int) -> int:
        """Largura depois do ``scale=-2:altura`` do FFmpeg."""
        return int(self.width * height / self.height) // 2 * 2


def quarter_turns(container, stream) -> int:
    """Quartos de volta (anti-horário) que o player aplica ao exibir; 0 sem rotação."""
    try:
        for frame in container.decode(stream):
            return round(float(getattr(frame, "rotation", 0) or 0) / 90) % 4
    except Exception:  # noqa: BLE001 - sem rotação legível, segue como está
        return 0
    return 0


class _Analysis:
    """Estado da leitura quadro a quadro (25 por segundo, a cadência do LR-ASD)."""

    def __init__(self, detector: FaceDetector | None, model, features) -> None:
        self.detector = detector
        self.model = model
        self.features = features
        self.tracker = FaceTracker()
        self.shots = ShotDetector()
        self.shot_starts: list[int] = []
        self.buffer: dict[int, object] = {}       # quadros cinza esperando as caixas
        self.observations: list[dict[int, tuple[float, float]]] = []
        self.motion: list[float | None] = []
        self.grays: dict[int, object] = {}
        self.size = (1, 1)

    def feed(self, index: int, bgr, fine) -> None:
        cut = self.shots.feed(color_histogram(bgr))
        if cut:
            self.tracker.new_shot()
            self.shot_starts.append(index)
        gray = bgr[::4, ::4].mean(axis=2).astype("uint8")
        if index % DETECT_EVERY == 0 or cut:
            if self.detector is not None:
                self.tracker.assign(self.detector.detect(bgr), index)
            earlier = self.grays.get(index - MOTION_GAP)
            self.motion.append(None if cut else motion_center(earlier, gray))
        else:
            self.motion.append(None)
        self.grays = {key: value for key, value in self.grays.items()
                      if key > index - MOTION_GAP}
        self.grays[index] = gray
        self.size = (fine.shape[1], fine.shape[0])
        self.buffer[index] = fine
        self._settle(index - TRACK_GAP)

    def finish(self, last: int) -> None:
        for index in range(max(0, last - TRACK_GAP + 1), last + 1):
            self._settle(index)
        for track in self.tracker.tracks:
            self._score(track)

    def _settle(self, index: int) -> None:
        """Fecha o quadro ``index``: as caixas em volta já são conhecidas."""
        fine = self.buffer.pop(index, None)
        if fine is None:
            return
        width, height = self.size
        seen: dict[int, tuple[float, float]] = {}
        shot = sum(1 for start in self.shot_starts if start <= index)
        for track in self.tracker.tracks:
            if track.shot != shot or track.last < index - TRACK_GAP:
                if track.pending:
                    self._score(track)
                continue
            box = track.box_at(index, height / width)
            if box is None:
                continue
            cx, cy, side = box
            seen[track.ident] = (cx, side)
            if self.model is not None and side * width >= MIN_FACE_PX:
                if track.pending and track.pending[-1][0] != index - 1:
                    self._score(track)
                track.pending.append((index, speaker.face_crop(
                    fine, cx * width, cy * height, side * width)))
                if len(track.pending) >= speaker.CHUNK_FRAMES:
                    self._score(track)
        while len(self.observations) <= index:
            self.observations.append({})
        self.observations[index] = seen

    def _score(self, track: FaceTrack) -> None:
        """Nota do LR-ASD para os recortes acumulados (uma sequência contínua)."""
        pending, track.pending = track.pending, []
        first = pending[0][0] if pending else 0
        if len(pending) < speaker.MIN_CHUNK_FRAMES or first * speaker.AUDIO_STEPS >= len(
                self.features):
            return
        values = self.model.scores(self.features[first * speaker.AUDIO_STEPS:],
                                   [crop for _index, crop in pending])
        for (index, _crop), value in zip(pending, values, strict=True):
            track.scores[index] = value


def analyze(source: Path, offset: float, length: float, *,
            voice: tuple | None = None,
            progress: Callable[[float], None] | None = None,
            cancelled: Callable[[], bool] | None = None,
            aspect: float = 9 / 16) -> Track | None:
    """Caminho da câmera ao longo do corte; ``None`` = não há o que rastrear.

    ``voice`` é ``(amostras, taxa)`` do áudio do trecho (o mesmo que vai para o Whisper):
    com ele, havendo várias pessoas, a câmera segue quem está falando. ``aspect`` é
    largura/altura da janela (mais larga que 9:16 com o título fixo no topo).
    """
    import av
    import numpy as np

    path = model_path()
    detector = FaceDetector(path) if path else None
    model, features = None, None
    asd = speaker.model_path()
    if voice is not None and asd is not None and detector is not None:
        try:
            features = speaker.mfcc(voice[0], int(voice[1]))
            model = speaker.SpeakerModel(asd)
        except Exception:  # noqa: BLE001 - sem o modelo, decide pelo tamanho dos rostos
            model, features = None, None
    state = _Analysis(detector, model, features)
    rate_grid = speaker.VIDEO_FPS
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        coded_w, coded_h = stream.codec_context.width, stream.codec_context.height
        rate = float(stream.average_rate or 0) or DEFAULT_FPS
        # Vídeo de celular costuma vir deitado com uma marca de rotação; o FFmpeg gira na
        # montagem, então a análise precisa ver o quadro já em pé, como ele.
        turns = quarter_turns(container, stream)
        width, height = (coded_h, coded_w) if turns % 2 else (coded_w, coded_h)
        if not width or not height or width / height <= aspect + 0.01:
            return None   # já cabe na janela: não há para onde movê-la
        scale = INPUT_SIZE / max(width, height)
        small = (max(2, int(coded_w * scale) // 2 * 2), max(2, int(coded_h * scale) // 2 * 2))
        detail_scale = min(1.0, DETAIL_SIZE / max(width, height))
        detail = (max(2, int(coded_w * detail_scale) // 2 * 2),
                  max(2, int(coded_h * detail_scale) // 2 * 2))
        container.seek(int(max(0.0, offset - 1.0) * av.time_base), any_frame=False, backward=True)
        next_index = 0
        last_index = int(length * rate_grid)
        for frame in container.decode(stream):
            if cancelled and cancelled():
                return None
            if frame.time is None:
                continue
            moment = float(frame.time) - offset
            index = min(last_index, round(moment * rate_grid))
            if index < next_index:
                continue
            bgr = frame.to_ndarray(format="bgr24", width=small[0], height=small[1])
            fine = frame.to_ndarray(format="gray", width=detail[0], height=detail[1])
            if turns:
                bgr = np.ascontiguousarray(np.rot90(bgr, turns))
                fine = np.ascontiguousarray(np.rot90(fine, turns))
            # Vídeo com menos de 25 quadros por segundo: repete o quadro, como o FFmpeg -r 25.
            for missing in range(next_index, index + 1):
                state.feed(missing, bgr, fine)
            next_index = index + 1
            if progress and length:
                progress(min(1.0, max(0.0, moment) / length))
            if index >= last_index:
                break
    if not next_index:
        return None
    state.finish(next_index - 1)
    scores = {track.ident: track.scores for track in state.tracker.tracks}
    observations: list[Observation] = [
        {ident: (center, side, scores[ident].get(index))
         for ident, (center, side) in frame.items()}
        for index, frame in enumerate(state.observations)]
    view = (height * aspect) / width
    speakers, cuts, wide = choose_speakers(observations, state.shot_starts, rate_grid, view)
    # Quadro sem nenhum rosto: o movimento da cena indica onde está a ação.
    targets = [x if x is not None or observations[i] else state.motion[i]
               for i, x in enumerate(speakers)]
    filled = fill_gaps(targets)
    if not filled:
        return None
    path = camera_path(filled, rate_grid, view=view, cuts=cuts)
    times = [index / rate_grid for index in range(len(path))]
    spans = []
    for index, flag in enumerate(wide):
        if flag and (not spans or spans[-1][1] != index):
            spans.append([index, index + 1])
        elif flag:
            spans[-1][1] = index + 1
    return Track(list(zip(times, path, strict=True)), width, height,
                 min(120.0, max(10.0, rate)), tuple(times[cut] for cut in cuts),
                 tuple((start / rate_grid, end / rate_grid) for start, end in spans))


# ----------------------------------------------------------------- FFmpeg

def crop_commands(samples: list[tuple[float, float]], intervals: list[tuple[float, float]],
                  scaled_width: int, crop_width: int,
                  remap: Callable[[float, list[tuple[float, float]]], float],
                  rate: float = DEFAULT_FPS,
                  cuts: Sequence[float] = ()) -> list[tuple[float, int]]:
    """Posição ``x`` do ``crop`` em cada quadro do corte já sem as pausas.

    Um comando por quadro e passo de 1 pixel: com menos comandos que quadros a imagem anda
    num quadro e para no seguinte, o "travado" que se vê em panorâmicas lentas. Nos
    ``cuts`` (troca de pessoa, no tempo da origem) a posição salta de um quadro para o outro.
    """
    kept = [(remap(time, intervals), center) for time, center in samples
            if any(start <= time <= end for start, end in intervals)]
    jumps = sorted(remap(time, intervals) for time in cuts)
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
            if any(time_a < jump <= time_b + 1e-6 for jump in jumps):
                centers.append(center_a)       # corte seco: só muda na amostra seguinte
                frame += 1
                continue
            share = min(1.0, (moment - time_a) / max(1e-6, time_b - time_a))
            share = share * share * (3 - 2 * share)     # sem quina entre as amostras
            centers.append(center_a + (center_b - center_a) * share)
        else:
            centers.append(center_a)
        frame += 1
    # As emendas das pausas aproximam amostras distantes: uma passada leve evita degraus
    # (sem atravessar um corte seco, que precisa continuar seco).
    edges = [0, *sorted({min(len(centers), max(0, math.ceil(jump * rate - 1e-6)))
                         for jump in jumps}), len(centers)]
    centers = [value for first, last in zip(edges, edges[1:], strict=False)
               for value in gaussian(centers[first:last], 0.08 * rate)]
    commands = []
    for frame, center in enumerate(centers):
        x = int(round(center * scaled_width - crop_width / 2))
        # Um quarto de quadro antes: arredondado para cima (2/30 = 0,0667 > 0,06667), o
        # comando só valeria no quadro seguinte e a imagem daria um tranco.
        moment = max(0.0, (frame - 0.25) / rate)
        commands.append((round(moment, 4), max(0, min(limit, x))))
    return commands


def output_windows(windows: Sequence[tuple[float, float]], intervals: list[tuple[float, float]],
                   remap: Callable[[float, list[tuple[float, float]]], float],
                   ) -> tuple[tuple[float, float], ...]:
    """Trechos da origem levados para o tempo do corte já sem as pausas (e emendados)."""
    result: list[list[float]] = []
    for start, end in windows:
        for first, last in intervals:
            low, high = max(start, first), min(end, last)
            if high - low <= 1e-6:
                continue
            begin, finish = remap(low, intervals), remap(high, intervals)
            if result and begin - result[-1][1] <= 1e-3:
                result[-1][1] = finish
            else:
                result.append([begin, finish])
    return tuple((round(begin, 3), round(finish, 3)) for begin, finish in result)


def sendcmd_text(commands: list[tuple[float, int]], target: str = "crop@track") -> str:
    return "".join(f"{moment:.4f} {target} x {x};\n" for moment, x in commands)
