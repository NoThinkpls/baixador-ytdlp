"""Cortes verticais com legenda palavra a palavra, feitos só com FFmpeg e Whisper.

Cada corte passa por (ver ``workers.ClipWorker``):

1. o trecho do arquivo local, ou baixado do link com ``--download-sections``;
2. o áudio do trecho, transcrito pelo processo isolado do Whisper com o tempo de cada palavra;
3. as pausas longas, que viram cortes (``keep_intervals``) e deslocam os tempos das palavras;
4. uma legenda ASS de 2–3 palavras com a palavra falada em destaque e um título animado;
5. um único FFmpeg que recorta, emenda, enquadra em 1080x1920 e grava a legenda;
6. opcionalmente, os sons e o zoom rápido de ``effects`` (do plano da IA ou automáticos).

Tudo aqui é cálculo puro (sem Qt e sem subprocesso), para ser testado sem FFmpeg.
"""
from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from .effects import PUNCH, Effect, Marker
from .gpu import backend_of, quality_args
from .sfx import GAIN
from .media_tools import TIME_RE, _escape_filter_path, available_destination, time_seconds

WIDTH, HEIGHT = 1080, 1920
MAX_CLIP_SECONDS = 600       # acima de 10 min deixa de ser um corte e a transcrição pesa
MIN_CLIP_SECONDS = 1.0
DEFAULT_MIN_PAUSE = 0.6      # silêncio maior que isso entre duas palavras é removido
SPEECH_PAD = 0.12            # folga mantida antes da fala, para não comer a primeira sílaba
# O Whisper marca o fim da palavra cedo: a última sílaba, o "s" e a voz morrendo ficam
# depois do tempo dele. Por isso o fim de cada trecho ganha mais folga que o começo e,
# com o áudio em mãos, só corta quando o volume realmente cai.
TAIL_PAD = 0.28
MAX_TAIL = 0.7               # nunca segura mais que isso depois do fim marcado da palavra
MAX_LEAD = 0.2               # nem começa mais que isso antes do início marcado
RELEASE = 0.08               # depois que o volume cai, um respiro antes da emenda
SPLICE_FADE = 0.025          # rampa de volume em cada emenda, sem estalo
ENERGY_FRAME = 0.02          # janela (s) da medida de volume usada nas emendas
MIN_KEEP = 0.08              # pedaço menor que isso só gera um salto de imagem
CAPTION_HOLD = 0.35          # a última palavra do grupo fica na tela um pouco depois de dita
CAPTION_MAX_GAP = 0.6        # pausa que fecha um grupo mesmo antes de completar as palavras
HIGHLIGHT_HEX = "#FFD700"    # amarelo padrão da palavra falada
FRAMINGS = ("blur", "crop", "track")
# Como a palavra falada aparece: destaque (cor e maior), só cor, karaokê (preenche conforme
# fala), uma palavra por vez, grupo que entra com um pulo, ou legenda simples sem destaque.
ANIMATIONS = ("highlight", "color", "karaoke", "word", "pop", "none")
ZOOM = 1.08                  # aproximação nas emendas, para disfarçar o salto da pausa removida
PROGRESS_HEIGHT = 12         # barra de progresso do corte, em pixels
TITLE_HIGH, TITLE_LOW = 17, 83   # título automático: no alto, ou embaixo
TITLE_MIN, TITLE_MAX = 6, 94


class ClipError(RuntimeError):
    """Erro de validação ou de execução mostrado pela página de cortes."""


@dataclass(frozen=True)
class ClipRange:
    start: float
    end: float
    title: str = ""
    markers: tuple[Marker, ...] = ()     # pontos do plano da IA (tempo do vídeo original)

    @property
    def length(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class ClipOptions:
    source: str                          # caminho local ou link http(s)
    ranges: tuple[ClipRange, ...]
    output_dir: Path
    # blur = vídeo inteiro com fundo desfocado; crop = centro; track = segue quem está em cena
    framing: str = "blur"
    remove_pauses: bool = True
    min_pause: float = DEFAULT_MIN_PAUSE
    style: CaptionStyle = field(default_factory=lambda: CaptionStyle())
    title_seconds: float = 2.0       # 0 = o corte inteiro
    language: str = "pt"
    model_size: str = "medium"
    zoom_cuts: bool = False          # alterna aproximação a cada emenda das pausas removidas
    progress_bar: bool = False       # barra fina na cor de destaque mostrando o andamento
    normalize_audio: bool = False    # volume equilibrado em -14 LUFS (padrão das redes)
    save_srt: bool = False           # grava também a legenda .srt ao lado do vídeo
    sound_effects: bool = False      # whoosh nas trocas de assunto e pop nas ênfases
    emphasis_zoom: bool = False      # zoom rápido na palavra dita com mais força
    sounds_folder: Path | None = None   # sons da pessoa (whoosh.wav, impacto.mp3…)


def is_url(source: str) -> bool:
    return bool(re.match(r"^https?://", source.strip(), re.IGNORECASE))


def parse_time(value: str) -> float:
    """``mm:ss``, ``hh:mm:ss`` ou segundos; vírgula decimal do teclado brasileiro vale."""
    text = value.strip().replace(",", ".")
    if not text or not TIME_RE.match(text):
        raise ClipError("Use mm:ss ou hh:mm:ss para o início e o fim de cada corte.")
    return time_seconds(text)


def make_range(start: str, end: str, title: str = "") -> ClipRange:
    begin, finish = parse_time(start), parse_time(end)
    if finish <= begin:
        raise ClipError("O fim de cada corte precisa ser posterior ao início.")
    length = finish - begin
    if length < MIN_CLIP_SECONDS:
        raise ClipError("Cada corte precisa ter pelo menos 1 segundo.")
    if length > MAX_CLIP_SECONDS:
        raise ClipError(f"Cada corte pode ter até {MAX_CLIP_SECONDS // 60} minutos.")
    return ClipRange(begin, finish, " ".join(title.split()))


def stream_kinds(probe_json: str) -> set[str]:
    """``{"video", "audio"}`` presentes num ``ffprobe -of json``; capa de MP3 não é vídeo."""
    try:
        streams = json.loads(probe_json or "{}").get("streams") or []
    except (ValueError, AttributeError):
        return set()
    kinds = set()
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if (stream.get("disposition") or {}).get("attached_pic"):
            continue
        if stream.get("codec_type") in {"video", "audio"}:
            kinds.add(stream["codec_type"])
    return kinds


def require_video_and_audio(kinds: set[str]) -> None:
    if "video" not in kinds and "audio" in kinds:
        raise ClipError("Este arquivo só tem áudio. Os cortes verticais precisam de vídeo; para "
                        "legendar só o áudio, use a aba Legendar.")
    if "video" in kinds and "audio" not in kinds:
        raise ClipError("Este vídeo não tem som: sem fala não há legenda nem pausas para tirar. "
                        "Para só deixá-lo vertical, use Ferramentas → Criar versão vertical.")
    if not kinds:
        raise ClipError("Não foi possível ler este arquivo como vídeo.")


def clamp_range(clip: ClipRange, duration: float) -> ClipRange:
    """Ajusta o corte à duração real do arquivo (0 = desconhecida, nada a ajustar)."""
    if not duration:
        return clip
    if clip.start >= duration:
        raise ClipError(
            f"O corte que começa em {format_clock(clip.start)} está depois do fim do vídeo "
            f"({format_clock(duration)}).")
    clamped = replace(clip, end=min(clip.end, duration))
    if clamped.length < MIN_CLIP_SECONDS:
        raise ClipError(
            f"O corte que começa em {format_clock(clip.start)} fica com menos de 1 segundo: o "
            f"vídeo acaba em {format_clock(duration)}.")
    return clamped


def format_clock(seconds: float) -> str:
    whole = max(0, int(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes:02}:{secs:02}"


def clip_filename(stem: str, index: int, title: str) -> str:
    """``video_corte01_titulo.mp4`` sem caracteres que o Windows recusa."""
    slug = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", title).strip().rstrip(".")
    slug = re.sub(r"\s+", "_", slug)[:60]
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", stem).strip().rstrip(".")[:80] or "corte"
    return f"{base}_corte{index:02d}{'_' + slug if slug else ''}.mp4"


def clip_destination(output_dir: Path, stem: str, index: int, title: str) -> Path:
    return available_destination(output_dir / clip_filename(stem, index, title))


# ----------------------------------------------------------------- palavras

def words_from_transcript(path: Path) -> list[dict]:
    """Palavras ``{"text", "start", "end"}`` do JSON gerado pelo legendador.

    Segmento sem tempo por palavra (raro: o motor sempre pede ``word_timestamps``) é
    dividido em partes iguais, para a legenda não sumir naquele trecho.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    words: list[dict] = []
    for segment in data.get("segments") or ():
        start, end = float(segment.get("start", 0.0)), float(segment.get("end", 0.0))
        items = segment.get("words") or []
        if items:
            for item in items:
                text = str(item.get("text") or "").strip()
                if text:
                    words.append({"text": text, "start": float(item.get("start", start)),
                                  "end": float(item.get("end", end))})
            continue
        tokens = str(segment.get("text") or "").split()
        step = (end - start) / len(tokens) if tokens else 0.0
        for position, token in enumerate(tokens):
            words.append({"text": token, "start": start + position * step,
                          "end": start + (position + 1) * step})
    words.sort(key=lambda word: word["start"])
    return words


class Loudness:
    """Volume do trecho em janelas de 20 ms, para achar onde a fala acaba de verdade."""

    def __init__(self, samples, rate: int):
        import numpy as np

        step = max(1, int(rate * ENERGY_FRAME))
        count = len(samples) // step
        frames = np.asarray(samples[:count * step], dtype=np.float32).reshape(count, step)
        self.db = 20 * np.log10(np.maximum(np.sqrt((frames * frames).mean(axis=1)), 1e-6))
        if count:
            floor, loud = np.percentile(self.db, 10), np.percentile(self.db, 90)
            # Um quarto do caminho entre o ruído de fundo e a voz: o fim da palavra
            # ("s", "r", voz morrendo) ainda está acima disso; o silêncio da sala, não.
            self.threshold = float(floor + max(6.0, (loud - floor) * 0.25))
        else:
            self.threshold = 0.0

    def _voiced(self, index: int) -> bool:
        return 0 <= index < len(self.db) and float(self.db[index]) >= self.threshold

    def speech_end(self, after: float, limit: float) -> float:
        """Primeiro instante depois de ``after`` em que o volume cai e fica caído (40 ms)."""
        index = int(after / ENERGY_FRAME)
        last = int(limit / ENERGY_FRAME)
        while index < last and (self._voiced(index) or self._voiced(index + 1)):
            index += 1
        return min(limit, index * ENERGY_FRAME)

    def speech_start(self, before: float, limit: float) -> float:
        """O mesmo para trás: onde a voz começa antes do início marcado da palavra."""
        index = int(before / ENERGY_FRAME) - 1
        first = int(limit / ENERGY_FRAME)
        while index > first and (self._voiced(index) or self._voiced(index - 1)):
            index -= 1
        return max(limit, (index + 1) * ENERGY_FRAME)


def keep_intervals(words: list[dict], length: float, min_pause: float = DEFAULT_MIN_PAUSE,
                   pad: float = SPEECH_PAD, tail: float = TAIL_PAD,
                   loudness: Loudness | None = None) -> list[tuple[float, float]]:
    """Trechos ``(início, fim)`` com fala; pausas acima de ``min_pause`` ficam de fora.

    O começo e o fim do corte contam como pausas também: silêncio antes da primeira
    palavra e depois da última sai. Sem palavras (música, silêncio), o corte fica inteiro.
    Com ``loudness`` (o áudio do trecho), a emenda só acontece depois que a voz cai, até
    ``MAX_TAIL`` além do fim marcado: assim a palavra termina antes do corte.
    """
    if length <= 0:
        return []
    if not words:
        return [(0.0, length)]

    def finish_of(end: float, following: float) -> float:
        cut = end + tail
        if loudness is not None:
            cut = max(cut, loudness.speech_end(end, end + MAX_TAIL) + RELEASE)
        return min(cut, following)

    def start_of(begin: float, preceding: float) -> float:
        cut = begin - pad
        if loudness is not None:
            cut = min(cut, loudness.speech_start(begin, begin - MAX_LEAD) - RELEASE / 2)
        return max(cut, preceding)

    intervals: list[list[float]] = []
    cursor_start = (0.0 if words[0]["start"] <= min_pause
                    else start_of(words[0]["start"], 0.0))
    cursor_end = words[0]["end"]
    for word in words[1:]:
        if word["start"] - cursor_end > min_pause:
            # Folgas de uma fala e da outra não se cruzam: metade da pausa para cada lado.
            middle = (cursor_end + word["start"]) / 2
            intervals.append([cursor_start, finish_of(cursor_end, middle)])
            cursor_start = start_of(word["start"], middle)
        cursor_end = max(cursor_end, word["end"])
    finish = length if length - cursor_end <= min_pause else finish_of(cursor_end, length)
    intervals.append([cursor_start, finish])

    merged: list[list[float]] = []
    for start, end in intervals:
        start, end = max(0.0, start), min(length, end)
        if end - start < MIN_KEEP:
            continue
        # Sobra de pausa curta demais para valer a emenda: junta os dois trechos.
        if merged and start - merged[-1][1] < MIN_KEEP:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(round(start, 3), round(end, 3)) for start, end in merged] or [(0.0, length)]


def remap_time(value: float, intervals: list[tuple[float, float]]) -> float:
    """Tempo no vídeo final; um instante dentro de uma pausa removida vai para a emenda."""
    elapsed = 0.0
    for start, end in intervals:
        if value < start:
            return elapsed
        if value <= end:
            return elapsed + value - start
        elapsed += end - start
    return elapsed


def remap_words(words: list[dict], intervals: list[tuple[float, float]]) -> list[dict]:
    result = []
    for word in words:
        start, end = remap_time(word["start"], intervals), remap_time(word["end"], intervals)
        if end - start < 0.01:
            continue   # palavra inteira dentro de um trecho removido
        # Só o tempo muda: o resto (volume medido para os efeitos) acompanha a palavra.
        result.append({**word, "start": start, "end": end})
    return result


def output_length(intervals: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in intervals)


def display_word(text: str, uppercase: bool) -> str:
    """Tira vírgula e ponto do fim (a legenda curta não precisa deles); ? e ! ficam."""
    cleaned = text.strip().rstrip(",.;:")
    cleaned = cleaned or text.strip()
    return cleaned.upper() if uppercase else cleaned


def caption_groups(words: list[dict], size: int = 3,
                   max_gap: float = CAPTION_MAX_GAP) -> list[list[dict]]:
    """Grupos de até ``size`` palavras; fim de frase ou pausa fecham o grupo antes."""
    size = max(1, min(4, int(size)))
    groups: list[list[dict]] = []
    current: list[dict] = []
    for word in words:
        if current and (len(current) >= size
                        or word["start"] - current[-1]["end"] > max_gap
                        or current[-1]["text"].rstrip().endswith((".", "!", "?", "…"))):
            groups.append(current)
            current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


# ----------------------------------------------------------------- ASS

def ass_time(value: float) -> str:
    hundredths = max(0, round(value * 100))
    hours, rest = divmod(hundredths, 360000)
    minutes, rest = divmod(rest, 6000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def ass_text(value: str) -> str:
    """Texto literal no ASS: chaves abririam uma tag e a barra invertida, um comando."""
    value = value.replace("\\", "/").replace("{", "(").replace("}", ")")
    return " ".join(value.split())


def ass_colour(value: str, fallback: str = "#FFFFFF") -> str:
    """``#RRGGBB`` da interface para ``&H00BBGGRR`` do ASS (que guarda azul-verde-vermelho)."""
    text = value.strip().lstrip("#") if isinstance(value, str) else ""
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        text = fallback.lstrip("#")
    red, green, blue = text[0:2], text[2:4], text[4:6]
    return f"&H00{blue}{green}{red}".upper()


def is_light(value: str) -> bool:
    text = value.lstrip("#")
    if not re.fullmatch(r"[0-9A-Fa-f]{6}", text):
        return True
    red, green, blue = (int(text[index:index + 2], 16) for index in (0, 2, 4))
    return 0.299 * red + 0.587 * green + 0.114 * blue > 150


@dataclass(frozen=True)
class CaptionStyle:
    """Aparência da legenda; os valores vêm da página e ficam salvos nas Configurações."""
    font: str = "Arial"
    size: int = 88                   # em pixels de um quadro 1080x1920
    text_color: str = "#FFFFFF"
    highlight_color: str = HIGHLIGHT_HEX
    position: int = 70               # centro da legenda, em % da altura (0 = topo)
    words: int = 3
    uppercase: bool = True
    animation: str = "highlight"     # ver ANIMATIONS
    background: bool = False         # caixa escura atrás da legenda
    # Centro do título, em % da altura; 0 = automático (no alto, ou embaixo se a
    # legenda estiver lá em cima, para não encostar).
    title_position: int = 0

    def normalized(self) -> CaptionStyle:
        # Vírgula separaria os campos da linha "Style:" do ASS.
        font = re.sub(r"[,\r\n{}]", "", self.font or "").strip() or "Arial"
        return CaptionStyle(
            font=font[:64], size=max(40, min(160, int(self.size))),
            text_color=self.text_color, highlight_color=self.highlight_color,
            position=max(8, min(92, int(self.position))), words=max(1, min(4, int(self.words))),
            uppercase=bool(self.uppercase),
            animation=self.animation if self.animation in ANIMATIONS else "highlight",
            background=bool(self.background), title_position=self.resolved_title_position())

    def resolved_title_position(self) -> int:
        value = int(self.title_position or 0)
        if value <= 0:
            return TITLE_LOW if int(self.position) < 35 else TITLE_HIGH
        return max(TITLE_MIN, min(TITLE_MAX, value))

    @property
    def y(self) -> int:
        return round(HEIGHT * self.normalized().position / 100)

    @property
    def title_y(self) -> int:
        return round(HEIGHT * self.resolved_title_position() / 100)


def ass_header(style: CaptionStyle) -> str:
    style = style.normalized()
    title_text = "&H00141414" if is_light(style.highlight_color) else "&H00FFFFFF"
    text, highlight = ass_colour(style.text_color), ass_colour(style.highlight_color, HIGHLIGHT_HEX)
    if style.animation == "karaoke":
        # No \kf o ASS pinta com a cor primária o que já foi dito e com a secundária o resto.
        primary, secondary = highlight, text
    else:
        primary, secondary = text, "&H000000FF"
    if style.background:
        # BorderStyle 3: caixa (na cor do contorno) atrás do texto, sem sombra.
        border, outline, shadow, outline_colour = 3, max(10, style.size // 5), 0, "&H60000000"
    else:
        border, outline, shadow, outline_colour = 1, max(4, style.size // 12), 3, "&H00000000"
    return (
        "[Script Info]\n"
        "Title: Baixador YT-DLP - corte vertical\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {WIDTH}\nPlayResY: {HEIGHT}\n"
        "WrapStyle: 0\nScaledBorderAndShadow: yes\n\n"
        "[V4+ Styles]\n"
        "Format: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,"
        "Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,"
        "Alignment,MarginL,MarginR,MarginV,Encoding\n"
        # Legenda: a altura vem do \\pos de cada linha (posição escolhida).
        f"Style: Caption,{style.font},{style.size},{primary},{secondary},"
        f"{outline_colour},&H78000000,-1,0,0,0,100,100,0,0,{border},{outline},{shadow},"
        "5,80,80,0,1\n"
        # Título: caixa na cor de destaque (BorderStyle 3), texto que contrasta. A altura
        # vem do \\pos do evento (``title_position``).
        f"Style: Title,{style.font},{round(style.size * 0.84)},{title_text},&H000000FF,"
        f"{highlight},&H00000000,-1,0,0,0,"
        "100,100,0,0,3,22,0,5,90,90,0,1\n\n"
        "[Events]\n"
        "Format: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n"
    )


def _caption_line(words: list[str], active: int, style: CaptionStyle) -> str:
    """Grupo com a palavra ``active`` em destaque (-1 = nenhuma), conforme a animação."""
    highlight = ass_colour(style.highlight_color, HIGHLIGHT_HEX)[4:]   # BBGGRR
    grow = style.animation in {"highlight", "pop"}
    parts = []
    for index, word in enumerate(words):
        if index == active and style.animation != "none":
            scale = "\\fscx112\\fscy112" if grow else ""
            parts.append(f"{{\\1c&H{highlight}&{scale}}}{word}{{\\r}}")
        else:
            parts.append(word)
    return f"{{\\an5\\pos({WIDTH // 2},{style.y})}}" + " ".join(parts)


def _group_end(groups: list[list[dict]], index: int, total: float) -> float:
    group = groups[index]
    following = groups[index + 1][0]["start"] if index + 1 < len(groups) else total
    end = min(total, following, group[-1]["end"] + CAPTION_HOLD)
    if following - end < CAPTION_HOLD:
        end = min(total, following)
    return max(end, group[0]["start"] + 0.05)


def caption_events(groups: list[list[dict]], total: float,
                   style: CaptionStyle = CaptionStyle()) -> list[str]:
    """Linhas ``Dialogue`` da legenda, conforme a animação escolhida.

    No destaque, uma linha por palavra: o grupo inteiro na tela e só a palavra falada
    marcada. Linhas encostadas umas nas outras (sem intervalo) evitam o "pisca".
    """
    style = style.normalized()
    rows: list[str] = []
    pop = "{\\fscx70\\fscy70\\t(0,90,\\fscx106\\fscy106)\\t(90,160,\\fscx100\\fscy100)}"
    for group_index, group in enumerate(groups):
        texts = [ass_text(display_word(word["text"], style.uppercase)) for word in group]
        group_end = _group_end(groups, group_index, total)
        head = "Dialogue: 0,{start},{end},Caption,,0,0,0,,"
        if style.animation == "none":
            rows.append(head.format(start=ass_time(group[0]["start"]), end=ass_time(group_end))
                        + _caption_line(texts, -1, style))
            continue
        if style.animation == "karaoke":
            # Uma linha por grupo; \kf preenche cada palavra durante a sua fala.
            parts, cursor = [], group[0]["start"]
            for index, word in enumerate(group):
                until = group[index + 1]["start"] if index + 1 < len(group) else word["end"]
                lead = max(0, round((word["start"] - cursor) * 100))
                fill = max(1, round((max(until, word["start"] + 0.05) - word["start"]) * 100))
                parts.append((f"{{\\k{lead}}}" if lead else "") + f"{{\\kf{fill}}}{texts[index]}")
                cursor = max(until, word["start"] + 0.05)
            position = f"{{\\an5\\pos({WIDTH // 2},{style.y})}}"
            rows.append(head.format(start=ass_time(group[0]["start"]), end=ass_time(group_end))
                        + position + " ".join(parts))
            continue
        for index, word in enumerate(group):
            start = word["start"]
            end = group[index + 1]["start"] if index + 1 < len(group) else group_end
            end = max(end, start + 0.05)
            if style.animation == "word":
                # Só a palavra falada, entrando com um pulo.
                line = f"{{\\an5\\pos({WIDTH // 2},{style.y})}}{pop}{texts[index]}"
            else:
                line = _caption_line(texts, index, style)
                if style.animation == "pop" and index == 0:
                    line = line.replace("}", "}" + pop, 1)
            rows.append(head.format(start=ass_time(start), end=ass_time(end)) + line)
    return rows


def title_event(title: str, seconds: float, total: float, y: int | None = None) -> str:
    """Título que entra crescendo, dá um leve "pulo" e some em fade."""
    text = ass_text(title)
    end = min(max(0.5, seconds), total) if total else max(0.5, seconds)
    y = round(HEIGHT * TITLE_HIGH / 100) if y is None else y
    animation = (f"{{\\pos({WIDTH // 2},{y})\\fad(120,280)\\fscx40\\fscy40"
                 "\\t(0,220,\\fscx108\\fscy108)\\t(220,360,\\fscx100\\fscy100)}")
    return f"Dialogue: 1,{ass_time(0)},{ass_time(end)},Title,,0,0,0,,{animation}{text}"


def build_ass(words: list[dict], total: float, *, title: str = "", title_seconds: float = 2.0,
              style: CaptionStyle = CaptionStyle()) -> str:
    style = style.normalized()
    rows = caption_events(caption_groups(words, style.words), total, style)
    if title.strip():
        rows.insert(0, title_event(title, title_seconds if title_seconds > 0 else total, total,
                                   style.title_y))
    return ass_header(style) + "\n".join(rows) + ("\n" if rows else "")


def srt_time(value: float) -> str:
    millis = max(0, round(value * 1000))
    hours, rest = divmod(millis, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    secs, ms = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{ms:03}"


def build_srt(words: list[dict], total: float, style: CaptionStyle = CaptionStyle()) -> str:
    """Mesmos grupos da legenda gravada, em SRT, para enviar junto ao YouTube/TikTok."""
    style = style.normalized()
    groups = caption_groups(words, style.words)
    blocks = []
    for index, group in enumerate(groups):
        text = " ".join(display_word(word["text"], style.uppercase) for word in group)
        blocks.append(f"{index + 1}\n{srt_time(group[0]['start'])} --> "
                      f"{srt_time(_group_end(groups, index, total))}\n{text}\n")
    return "\n".join(blocks)


# ----------------------------------------------------------------- FFmpeg

@dataclass(frozen=True)
class Tracking:
    """Janela que acompanha a pessoa: posições enviadas ao ``crop`` por ``sendcmd``."""
    commands: Path          # arquivo do sendcmd (``tempo crop@track x valor;``)
    first_x: int            # posição no primeiro quadro, antes do primeiro comando
    # Trechos (no tempo do corte final) em que ninguém fala e as pessoas não cabem na
    # janela: ali entra o quadro inteiro com fundo desfocado, como no enquadramento "blur".
    wide: tuple[tuple[float, float], ...] = ()


def _framing_graph(framing: str, tracking: Tracking | None = None) -> str:
    """De ``[vc]`` (o corte emendado) até um quadro 1080x1920 rotulado ``[vf]``."""
    if framing == "track" and tracking is not None:
        # Altura em 1920 e janela de 1080 que anda na horizontal conforme a análise.
        # yuv444p antes do crop: em 4:2:0 o x só anda de 2 em 2 pixels.
        follow = (f"scale=-2:{HEIGHT},format=yuv444p,"
                  f"sendcmd=f={_escape_filter_path(tracking.commands)},"
                  f"crop@track={WIDTH}:{HEIGHT}:{tracking.first_x}:0,setsar=1")
        if not tracking.wide:
            return f"[vc]{follow}[vf]"
        enable = "+".join(f"between(t,{start:.3f},{end - 0.001:.3f})"
                          for start, end in tracking.wide)
        return (f"[vc]split=2[vtr][vwi];[vtr]{follow}[vtf];"
                + _blur_fit("[vwi]", "[vwf]", "w") +
                f";[vtf][vwf]overlay=0:0:enable='{enable}',setsar=1[vf]")
    if framing in {"crop", "track"}:
        return (f"[vc]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setsar=1[vf]")
    # Mesmo visual de "Criar versão vertical" nas Ferramentas.
    return _blur_fit("[vc]", "[vf]")


def _blur_fit(source: str, output: str, tag: str = "") -> str:
    """Quadro inteiro no meio, com o próprio vídeo ampliado e desfocado atrás."""
    return (f"{source}split=2[bg{tag}][fg{tag}];"
            f"[bg{tag}]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},boxblur=luma_radius=24:luma_power=2,eq=brightness=-0.08"
            f"[bgb{tag}];"
            f"[fg{tag}]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fgs{tag}];"
            f"[bgb{tag}][fgs{tag}]overlay=(W-w)/2:(H-h)/2,setsar=1{output}")


def zoom_windows(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Trechos (no tempo do corte final) que entram aproximados: um sim, outro não."""
    windows, cursor = [], 0.0
    for index, (start, end) in enumerate(intervals):
        if index % 2:
            windows.append((cursor, cursor + end - start))
        cursor += end - start
    return windows


def filter_graph(intervals: list[tuple[float, float]], framing: str, subtitles: Path | None,
                 tracking: Tracking | None = None, *, zoom_cuts: bool = False,
                 progress_colour: str = "", normalize_audio: bool = False,
                 effects: Sequence[Effect] = (), effect_inputs: dict[str, int] | None = None,
                 punch: Sequence[tuple[float, float]] = (),
                 effect_gains: dict[str, float] | None = None) -> str:
    """Recorta cada trecho com fala, emenda vídeo e áudio juntos, enquadra e grava a legenda.

    ``effects`` são os sons automáticos; ``effect_inputs`` diz em qual entrada do
    FFmpeg está o WAV de cada tipo e ``effect_gains`` o volume de cada um (acertado pela
    voz em ``sfx.matched_gains``). ``punch`` são as janelas do zoom rápido na ênfase.
    """
    if not intervals:
        raise ClipError("Não sobrou nenhum trecho para montar o corte.")
    parts: list[str] = []
    pads: list[str] = []
    for index, (start, end) in enumerate(intervals):
        parts.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]")
        fade = ""
        if len(intervals) > 1 and end - start > 4 * SPLICE_FADE:
            # Rampa curta nas pontas: emenda seca dá estalo e soa como palavra cortada.
            fade = (f",afade=t=in:d={SPLICE_FADE}"
                    f",afade=t=out:st={end - start - SPLICE_FADE:.3f}:d={SPLICE_FADE}")
        parts.append(f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS"
                     f"{fade}[a{index}]")
        pads.append(f"[v{index}][a{index}]")
    inputs = effect_inputs or {}
    effects = [effect for effect in effects if effect.kind in inputs]
    audio = "[ac0]" if normalize_audio or effects else "[ac]"
    parts.append(f"{''.join(pads)}concat=n={len(intervals)}:v=1:a=1[vc]{audio}")
    if effects:
        mixed = "[ac1]" if normalize_audio else "[ac]"
        parts.append(_effects_graph(effects, inputs, "[ac0]", mixed, effect_gains or {}))
        audio = mixed
    if normalize_audio:
        # -14 LUFS é o alvo do YouTube, TikTok e Reels; uma passada só, sem arquivo extra.
        parts.append(f"{audio}loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[ac]")
    parts.append(_framing_graph(framing if framing in FRAMINGS else "blur", tracking))
    video = "[vf]"
    windows = zoom_windows(intervals) if zoom_cuts else []
    if windows:
        # A cada emenda alterna 100% e 108%: o salto de imagem da pausa removida vira um
        # "corte de câmera", como fazem os editores de vídeos curtos.
        enable = "+".join(f"between(t,{start:.3f},{end - 0.001:.3f})" for start, end in windows)
        zoomed = f"{round(WIDTH * ZOOM / 2) * 2}:{round(HEIGHT * ZOOM / 2) * 2}"
        parts.append(f"[vf]split=2[vn][vz];[vz]scale={zoomed},crop={WIDTH}:{HEIGHT}[vzc];"
                     f"[vn][vzc]overlay=0:0:enable='{enable}'[vzm]")
        video = "[vzm]"
    if punch:
        # Zoom rápido (e mais forte) na palavra enfatizada, por cima do zoom das emendas.
        enable = "+".join(f"between(t,{start:.3f},{end - 0.001:.3f})" for start, end in punch)
        zoomed = f"{round(WIDTH * PUNCH / 2) * 2}:{round(HEIGHT * PUNCH / 2) * 2}"
        parts.append(f"{video}split=2[pn][pz];[pz]scale={zoomed},crop={WIDTH}:{HEIGHT}[pzc];"
                     f"[pn][pzc]overlay=0:0:enable='{enable}'[vpm]")
        video = "[vpm]"
    tail = f"subtitles=filename={_escape_filter_path(subtitles)}," if subtitles else ""
    if progress_colour:
        total = max(0.1, output_length(intervals))
        colour = "0x" + progress_colour.lstrip("#")
        parts.append(f"{video}{tail}setsar=1[vs];"
                     f"color=c={colour}:s={WIDTH}x{PROGRESS_HEIGHT}[bar];"
                     f"[vs][bar]overlay=x='-w+w*t/{total:.3f}':y=H-h:shortest=1,format=yuv420p[v]")
    else:
        parts.append(f"{video}{tail}format=yuv420p[v]")
    return ";".join(parts)


def _effects_graph(effects: Sequence[Effect], inputs: dict[str, int], speech: str,
                   output: str, gains: dict[str, float] | None = None) -> str:
    """Cada som entra atrasado até o seu instante e é somado à voz, sem mudar o volume dela."""
    parts, labels = [], []
    for kind, index in sorted(inputs.items()):
        times = [effect.time for effect in effects if effect.kind == kind]
        if not times:
            continue
        names = [f"[sx{kind}{number}]" for number in range(len(times))]
        parts.append(f"[{index}:a]asplit=outputs={len(times)}{''.join(names)}")
        for name, time in zip(names, times, strict=True):
            delayed = name.replace("[sx", "[sd")
            parts.append(f"{name}adelay=delays={round(time * 1000)}:all=1,"
                         f"volume={(gains or {}).get(kind, GAIN.get(kind, 0.3))}{delayed}")
            labels.append(delayed)
    parts.append(f"{speech}{''.join(labels)}amix=inputs={len(labels) + 1}:duration=first:"
                 f"normalize=0{output}")
    return ";".join(parts)


def video_codec_args(encoder: str = "") -> list[str]:
    """x264 por padrão; encoder de GPU (NVENC, AMF, QSV…) quando a detecção confirmou um."""
    if encoder and backend_of(encoder) and backend_of(encoder) != "vaapi":
        args = ["-c:v", encoder, *quality_args(encoder, 20)]
        if encoder.endswith("_nvenc"):
            args += ["-preset", "p5"]
        return args
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "20"]


def render_command(ffmpeg: Path, source: Path, offset: float, length: float,
                   intervals: list[tuple[float, float]], framing: str, subtitles: Path | None,
                   destination: Path, *, video_encoder: str = "",
                   tracking: Tracking | None = None, sounds: dict[str, Path] | None = None,
                   **extras) -> list[str]:
    """Um FFmpeg só, sem shell: o arquivo de origem nunca é alterado."""
    if source.resolve() == destination.resolve():
        raise ClipError("Escolha outra pasta de saída para preservar o arquivo original.")
    sound_inputs: list[str] = []
    effect_inputs: dict[str, int] = {}
    for kind, path in sorted((sounds or {}).items()):
        effect_inputs[kind] = 1 + len(effect_inputs)
        sound_inputs += ["-i", str(path)]
    return [
        str(ffmpeg), "-hide_banner", "-n",
        "-ss", f"{max(0.0, offset):.3f}", "-t", f"{length:.3f}", "-i", str(source),
        *sound_inputs,
        "-filter_complex", filter_graph(intervals, framing, subtitles, tracking,
                                        effect_inputs=effect_inputs, **extras),
        "-map", "[v]", "-map", "[ac]",
        *video_codec_args(video_encoder),
        "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
        "-movflags", "+faststart",
        "-progress", "pipe:1", "-nostats", str(destination),
    ]


def audio_command(ffmpeg: Path, source: Path, offset: float, length: float,
                  destination: Path) -> list[str]:
    """Áudio do trecho em 16 kHz mono, o formato que o Whisper usa."""
    return [str(ffmpeg), "-hide_banner", "-y", "-ss", f"{max(0.0, offset):.3f}",
            "-t", f"{length:.3f}", "-i", str(source), "-vn", "-ac", "1", "-ar", "16000",
            "-c:a", "pcm_s16le", "-progress", "pipe:1", "-nostats", str(destination)]


def section_offset(actual: float, expected: float) -> float:
    """Quanto sobrou antes do início num trecho baixado sem reencodar.

    O yt-dlp corta no quadro-chave anterior ao início pedido; o fim sai no ponto certo.
    A sobra no começo é a diferença entre a duração real e a pedida.
    """
    extra = actual - expected
    return extra if extra > 0.25 else 0.0
