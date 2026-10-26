"""Enquadramento automático: a janela 9:16 acompanha quem está em cena.

Mesma ideia do AutoFlip (Google/MediaPipe) e do "reenquadrar" do CapCut, em versão leve
e com o que o app já leva: o PyAV decodifica alguns quadros por segundo, o detector de
rostos YuNet (OpenCV Zoo, MIT, 230 KB) roda no onnxruntime do Whisper e, quando não há
rosto (pessoa de costas, longe), o movimento entre quadros indica onde está a ação.

Com mais de um rosto em cena, quem fala é quem a câmera segue ("active speaker
detection" em versão leve): cada rosto é acompanhado entre os quadros, o movimento da
boca dele (descontado o da cabeça) vira uma curva no tempo e essa curva é comparada com
o volume da fala. A boca que abre e fecha junto com a voz é de quem está falando. Quando
a comparação não decide (boca coberta, rosto pequeno), vale quem mais falou no corte e,
por último, o maior rosto. Tudo em CPU, sem modelo extra.
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
from dataclasses import dataclass
from pathlib import Path

from .plataforma import pasta_do_executavel

MODEL_NAME = "face_detection_yunet_2023mar.onnx"
INPUT_SIZE = 640                 # o YuNet 2023mar tem entrada fixa de 640x640
SAMPLE_FPS = 10.0                # quadros analisados por segundo (a boca precisa disso)
FACE_SCORE = 0.6
MOTION_THRESHOLD = 24            # diferença de cinza que conta como movimento
MOTION_MIN_SHARE = 0.004         # fração mínima de pixels em movimento para confiar nele
DEAD_ZONE = 0.06                 # deslocamento (fração da largura) que a câmera ignora
MAX_SPEED = 0.35                 # fração da largura por segundo
SETTLE_SECONDS = 0.8             # parado por esse tempo = a câmera assenta
EASE_SECONDS = 0.45              # duração aproximada da aceleração e da frenagem
DEFAULT_FPS = 30.0               # quando o vídeo não informa a taxa de quadros
NMS_IOU = 0.3                    # caixas do mesmo rosto em âncoras vizinhas viram uma só
DETAIL_SIZE = 1280               # lado maior do quadro de onde sai o recorte da boca
MOUTH_PATCH = (24, 16)           # boca reduzida a 24x16 tons de cinza para comparar
MIN_MOUTH_PX = 6.0               # boca menor que isso no quadro não dá leitura confiável
TRACK_MEMORY = 2.0               # segundos que um rosto pode sumir e continuar o mesmo
SPEAKER_WINDOW = 4.0             # janela (s) em que se decide quem fala agora
SPEAKER_MIN_CORR = 0.15          # correlação mínima entre boca e voz para "está falando"
SPEAKER_MARGIN = 0.05            # vantagem sobre o segundo colocado para decidir
SWITCH_SECONDS = 0.8             # outro precisa vencer por esse tempo para a câmera trocar
MIN_SHOT_SECONDS = 2.0           # depois de trocar de pessoa, fica nela pelo menos isso


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


# ----------------------------------------------------------------- quem está falando

def patch(gray, cx: float, cy: float, half_w: float, half_h: float,
          size: tuple[int, int] = MOUTH_PATCH):
    """Recorte ``size`` (largura, altura) em torno de ``(cx, cy)`` em pixels, sem o brilho médio.

    Amostragem pelo vizinho mais próximo: barato e suficiente para medir o quanto mudou.
    """
    import numpy as np

    height, width = gray.shape[:2]
    xs = np.clip(np.linspace(cx - half_w, cx + half_w, size[0]).round().astype(int), 0, width - 1)
    ys = np.clip(np.linspace(cy - half_h, cy + half_h, size[1]).round().astype(int), 0, height - 1)
    values = gray[ys[:, None], xs[None, :]].astype(np.float32)
    return values - values.mean()


def mouth_patch(gray, face: Face):
    """Recorte da boca (lábios e queixo) num quadro cinza; ``None`` sem pontos ou boca pequena."""
    if len(face.points) < 5:
        return None
    height, width = gray.shape[:2]
    (rx, ry), (lx, ly) = face.points[3], face.points[4]
    rx, lx, ry, ly = rx * width, lx * width, ry * height, ly * height
    mouth = math.hypot(lx - rx, ly - ry)
    if mouth < MIN_MOUTH_PX:
        return None
    mx, my = (rx + lx) / 2, (ry + ly) / 2 + mouth * 0.15   # um pouco abaixo: lábio e queixo
    return patch(gray, mx, my, mouth * 0.75, mouth * 0.6)


def mouth_activity(before, after) -> float:
    """Quanto a boca mudou entre dois recortes.

    Descontar o movimento da cabeça (pelo nariz) foi testado e piorou: quem fala também
    mexe a cabeça no ritmo da fala, e isso ajuda a achar o orador.
    """
    import numpy as np

    return float(np.abs(after - before).mean())


@dataclass
class FaceTrack:
    """Um mesmo rosto ao longo dos quadros (para a boca de um não ser comparada à de outro)."""
    ident: int
    center: float
    width: float
    last_seen: float
    patches: object = None
    last_index: int = -1


class FaceTracker:
    def __init__(self) -> None:
        self.tracks: list[FaceTrack] = []

    def assign(self, faces: list[Face], moment: float) -> list[FaceTrack]:
        """A trilha de cada rosto: a mais próxima ainda viva e de tamanho parecido, ou nova."""
        alive = [track for track in self.tracks if moment - track.last_seen <= TRACK_MEMORY]
        taken: set[int] = set()
        result: dict[int, FaceTrack] = {}
        # Rostos maiores escolhem primeiro; a resposta volta na ordem de ``faces``.
        for position, face in sorted(enumerate(faces), key=lambda item: -item[1].area):
            best, distance = None, 0.0
            for track in alive:
                if track.ident in taken:
                    continue
                gap = abs(track.center - face.center)
                ratio = max(track.width, face.w) / max(1e-6, min(track.width, face.w))
                if gap <= max(track.width, face.w) * 1.5 and ratio <= 1.8 and (
                        best is None or gap < distance):
                    best, distance = track, gap
            if best is None:
                best = FaceTrack(len(self.tracks), face.center, face.w, moment)
                self.tracks.append(best)
            best.center, best.width, best.last_seen = face.center, face.w, moment
            taken.add(best.ident)
            result[position] = best
        return [result[position] for position in range(len(faces))]


def pearson(left: list[float], right: list[float]) -> float:
    count = len(left)
    if count < 3:
        return 0.0
    mean_l, mean_r = sum(left) / count, sum(right) / count
    cov = sum((a - mean_l) * (b - mean_r) for a, b in zip(left, right, strict=True))
    var_l = sum((a - mean_l) ** 2 for a in left)
    var_r = sum((b - mean_r) ** 2 for b in right)
    if var_l <= 1e-12 or var_r <= 1e-12:
        return 0.0
    return cov / math.sqrt(var_l * var_r)


def voice_envelope(samples, sample_rate: int, times: list[float], rate: float) -> list[float]:
    """Volume da voz (dB) em torno de cada instante analisado, na mesma cadência dos quadros."""
    import numpy as np

    half = max(1, int(sample_rate / rate / 2))
    levels = []
    for moment in times:
        center = int(moment * sample_rate)
        chunk = np.asarray(samples[max(0, center - half):center + half], dtype=np.float32)
        rms = float(np.sqrt(np.mean(chunk * chunk))) if chunk.size else 0.0
        levels.append(20 * math.log10(max(rms, 1e-5)))
    return levels


def _smooth3(values: list[float]) -> list[float]:
    return [sum(values[max(0, i - 1):i + 2]) / len(values[max(0, i - 1):i + 2])
            for i in range(len(values))]


def choose_speakers(observations: list[dict[int, tuple[float, float, float | None]]],
                    voice: list[float] | None, rate: float = SAMPLE_FPS,
                    ) -> tuple[list[float | None], list[int]]:
    """Centro x a seguir em cada amostra (o rosto de quem está falando) e onde há troca.

    ``observations[i]`` é ``{trilha: (centro x, área, movimento da boca ou None)}`` e
    ``voice`` é o volume da fala nos mesmos instantes. Sem rosto, a amostra fica ``None``
    (o movimento da cena decide).

    Cada rosto ganha uma nota: a correlação entre a boca dele e a voz no corte inteiro (quem
    mais falou: a pessoa principal) somada à dos segundos em volta (quem fala agora). A câmera só troca de pessoa quando outra vence
    com folga por ``SWITCH_SECONDS`` e nunca antes de ``MIN_SHOT_SECONDS`` na pessoa atual;
    sem decisão fica onde está e, sem ninguém escolhido, vai para quem mais falou ou para o
    maior rosto. As amostras em que a câmera passa de uma pessoa para outra voltam na
    segunda lista: ali o enquadramento corta seco, como um editor faria, em vez de
    atravessar o quadro numa panorâmica.
    """
    count = len(observations)
    if not count:
        return [], []
    tracks = sorted({ident for frame in observations for ident in frame})
    series: dict[int, list[float | None]] = {
        ident: _smooth_optional([frame[ident][2] if ident in frame else None
                                 for frame in observations]) for ident in tracks}
    radius = max(2, int(SPEAKER_WINDOW * rate / 2))
    voice_s = _smooth3(voice) if voice and len(voice) == count else None
    score = _speaker_scorer(series, voice_s, count, radius, rate)
    threshold, margin = SPEAKER_MIN_CORR, SPEAKER_MARGIN
    hold = max(1, int(SWITCH_SECONDS * rate))
    dwell = int(MIN_SHOT_SECONDS * rate)
    memory = rate * TRACK_MEMORY
    current: int | None = None
    shown: int | None = None             # pessoa que estava na tela na amostra anterior
    since = -10**9                       # amostra em que a pessoa atual entrou
    pending: int | None = None
    streak = 0
    last_seen: dict[int, int] = {}
    result: list[float | None] = []
    cuts: list[int] = []
    for index, frame in enumerate(observations):
        for ident in frame:
            last_seen[ident] = index
        if not frame:
            result.append(None)
            continue
        alive = [ident for ident, seen in last_seen.items() if index - seen <= memory]
        winner: int | None = None
        scores = sorted(((score(ident, index), ident) for ident in alive), reverse=True)
        if len(alive) == 1:
            winner = alive[0]
        elif scores[0][0] >= threshold and scores[0][0] - scores[1][0] >= margin:
            winner = scores[0][1]
        if current is not None and index - last_seen.get(current, -10**9) > memory:
            current = None
        if winner is not None and winner != current:
            streak = streak + 1 if pending == winner else 1
            pending = winner
            if current is None or (streak >= hold and index - since >= dwell):
                current, pending, streak = winner, None, 0
        elif winner == current:
            pending, streak = None, 0
        if current is None:
            present = [(value, ident) for value, ident in scores if ident in frame]
            if present and present[0][0] >= threshold:
                current = present[0][1]
            else:
                current = max(frame, key=lambda ident: frame[ident][1])
        if current != shown and current in frame:
            if shown is not None:
                cuts.append(index)
            shown, since = current, index
        # Rosto atual sumiu por um instante (virou, falhou a detecção): segura a posição.
        result.append(frame[current][0] if current in frame else None)
    return result, cuts


def _speaker_scorer(series: dict[int, list[float | None]], voice: list[float] | None,
                    count: int, radius: int, rate: float):
    """Nota de cada rosto num instante: corte inteiro + janela de ``SPEAKER_WINDOW``.

    Trilha curta tem nota encolhida, porque poucos pontos correlacionam por acaso.
    """
    trust = rate * 5                     # pontos para a nota valer metade do que mediu

    def correlation(ident: int, first: int, last: int) -> tuple[float, int]:
        if voice is None:
            return 0.0, 0
        mouth: list[float] = []
        sound: list[float] = []
        for j in range(first, last):
            value = series[ident][j]
            if value is not None:
                mouth.append(value)
                sound.append(voice[j])
        if len(mouth) < max(4, int(rate * 0.8)):
            return 0.0, 0
        return pearson(mouth, sound), len(mouth)

    overall: dict[int, float] = {}
    for ident in series:
        value, points = correlation(ident, 0, count)
        overall[ident] = value * points / (points + trust)

    def score(ident: int, index: int) -> float:
        local, points = correlation(ident, max(0, index - radius), min(count, index + radius + 1))
        return overall[ident] + local * points / (points + radius)
    return score


def _smooth_optional(values: list[float | None]) -> list[float | None]:
    """Média de 3 amostras só onde há leitura; buracos continuam buracos."""
    result: list[float | None] = []
    for index, value in enumerate(values):
        if value is None:
            result.append(None)
            continue
        near = [item for item in values[max(0, index - 1):index + 2] if item is not None]
        result.append(sum(near) / len(near))
    return result


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


def camera_path(targets: list[float], rate: float = SAMPLE_FPS, *, view: float = 0.3164,
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
    cuts: tuple[float, ...] = ()         # instantes (no corte) em que a câmera troca de pessoa

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


def analyze(source: Path, offset: float, length: float, *,
            voice: tuple | None = None,
            progress: Callable[[float], None] | None = None,
            cancelled: Callable[[], bool] | None = None) -> Track | None:
    """Caminho da câmera ao longo do corte; ``None`` = não há o que rastrear.

    ``voice`` é ``(amostras, taxa)`` do áudio do trecho (o mesmo que vai para o Whisper):
    com ele, havendo várias pessoas, a câmera segue quem está falando.
    """
    import av
    import numpy as np

    path = model_path()
    detector = FaceDetector(path) if path else None
    tracker = FaceTracker()
    times: list[float] = []
    observations: list[dict[int, tuple[float, float, float | None]]] = []
    motion: list[float | None] = []
    previous_gray = None
    with av.open(str(source)) as container:
        stream = container.streams.video[0]
        stream.thread_type = "AUTO"
        coded_w, coded_h = stream.codec_context.width, stream.codec_context.height
        rate = float(stream.average_rate or 0) or DEFAULT_FPS
        # Vídeo de celular costuma vir deitado com uma marca de rotação; o FFmpeg gira na
        # montagem, então a análise precisa ver o quadro já em pé, como ele.
        turns = quarter_turns(container, stream)
        width, height = (coded_h, coded_w) if turns % 2 else (coded_w, coded_h)
        if not width or not height or width / height <= 9 / 16 + 0.01:
            return None   # já é vertical: não há para onde mover a janela
        scale = INPUT_SIZE / max(width, height)
        small = (max(2, int(coded_w * scale) // 2 * 2), max(2, int(coded_h * scale) // 2 * 2))
        detail_scale = min(1.0, DETAIL_SIZE / max(width, height))
        detail = (max(2, int(coded_w * detail_scale) // 2 * 2),
                  max(2, int(coded_h * detail_scale) // 2 * 2))
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
            if turns:
                bgr = np.ascontiguousarray(np.rot90(bgr, turns))
            gray = bgr[::4, ::4].mean(axis=2).astype(np.uint8)
            seen: dict[int, tuple[float, float, float | None]] = {}
            faces = detector.detect(bgr) if detector else []
            if faces:
                # A boca sai de um quadro maior: no de 640 px ela teria poucos pixels.
                fine = _gray(frame, detail, turns)
                index = len(times)
                for face, track in zip(faces, tracker.assign(faces, moment), strict=True):
                    patch_now = mouth_patch(fine, face)
                    activity = None
                    if (patch_now is not None and track.patches is not None
                            and track.last_index == index - 1):
                        activity = mouth_activity(track.patches, patch_now)
                    track.patches, track.last_index = patch_now, index
                    seen[track.ident] = (face.center, face.area, activity)
            motion.append(motion_center(previous_gray, gray))
            previous_gray = gray
            times.append(max(0.0, moment))
            observations.append(seen)
            if progress and length:
                progress(min(1.0, max(0.0, moment) / length))
    envelope = None
    if voice is not None:
        try:
            envelope = voice_envelope(voice[0], int(voice[1]), times, SAMPLE_FPS)
        except Exception:  # noqa: BLE001 - sem áudio legível, decide pelo tamanho do rosto
            envelope = None
    speakers, cuts = choose_speakers(observations, envelope, SAMPLE_FPS)
    # Amostra sem nenhum rosto: o movimento da cena indica onde está a ação.
    targets = [x if x is not None or observations[i] else motion[i]
               for i, x in enumerate(speakers)]
    filled = fill_gaps(targets)
    if not filled:
        return None
    view = (height * 9 / 16) / width
    path = camera_path(filled, view=view, cuts=cuts)
    return Track(list(zip(times, path, strict=True)), width, height,
                 min(120.0, max(10.0, rate)), tuple(times[cut] for cut in cuts))


def _gray(frame, size: tuple[int, int], turns: int):
    """Quadro em cinza no tamanho de detalhe, já em pé."""
    import numpy as np

    gray = frame.to_ndarray(format="gray", width=size[0], height=size[1])
    return np.ascontiguousarray(np.rot90(gray, turns)) if turns else gray


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


def sendcmd_text(commands: list[tuple[float, int]], target: str = "crop@track") -> str:
    return "".join(f"{moment:.4f} {target} x {x};\n" for moment, x in commands)
