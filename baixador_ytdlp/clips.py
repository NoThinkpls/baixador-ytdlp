"""Cortes verticais com legenda palavra a palavra, feitos só com FFmpeg e Whisper.

Cada corte passa por (ver ``workers.ClipWorker``):

1. o trecho do arquivo local, ou baixado do link com ``--download-sections``;
2. o áudio do trecho, transcrito pelo processo isolado do Whisper com o tempo de cada palavra;
3. as pausas longas, que viram cortes (``keep_intervals``) e deslocam os tempos das palavras;
4. uma legenda ASS de 2–3 palavras com a palavra falada em destaque e um título animado;
5. um único FFmpeg que recorta, emenda, enquadra em 1080x1920 e grava a legenda.

Tudo aqui é cálculo puro (sem Qt e sem subprocesso), para ser testado sem FFmpeg.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .gpu import backend_of, quality_args
from .media_tools import TIME_RE, _escape_filter_path, available_destination, time_seconds

WIDTH, HEIGHT = 1080, 1920
MAX_CLIP_SECONDS = 600       # acima de 10 min deixa de ser um corte e a transcrição pesa
MIN_CLIP_SECONDS = 1.0
DEFAULT_MIN_PAUSE = 0.6      # silêncio maior que isso entre duas palavras é removido
SPEECH_PAD = 0.12            # folga mantida antes e depois da fala, para não comer sílabas
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


class ClipError(RuntimeError):
    """Erro de validação ou de execução mostrado pela página de cortes."""


@dataclass(frozen=True)
class ClipRange:
    start: float
    end: float
    title: str = ""

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
    clamped = ClipRange(clip.start, min(clip.end, duration), clip.title)
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


def keep_intervals(words: list[dict], length: float, min_pause: float = DEFAULT_MIN_PAUSE,
                   pad: float = SPEECH_PAD) -> list[tuple[float, float]]:
    """Trechos ``(início, fim)`` com fala; pausas acima de ``min_pause`` ficam de fora.

    O começo e o fim do corte contam como pausas também: silêncio antes da primeira
    palavra e depois da última sai. Sem palavras (música, silêncio), o corte fica inteiro.
    """
    if length <= 0:
        return []
    if not words:
        return [(0.0, length)]
    intervals: list[list[float]] = []
    cursor_start = 0.0 if words[0]["start"] <= min_pause else max(0.0, words[0]["start"] - pad)
    cursor_end = words[0]["end"]
    for word in words[1:]:
        if word["start"] - cursor_end > min_pause:
            intervals.append([cursor_start, cursor_end + pad])
            cursor_start = word["start"] - pad
        cursor_end = max(cursor_end, word["end"])
    finish = length if length - cursor_end <= min_pause else cursor_end + pad
    intervals.append([cursor_start, finish])

    merged: list[list[float]] = []
    for start, end in intervals:
        start, end = max(0.0, start), min(length, end)
        if end - start < MIN_KEEP:
            continue
        if merged and start <= merged[-1][1]:
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
        result.append({"text": word["text"], "start": start, "end": end})
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

    def normalized(self) -> CaptionStyle:
        # Vírgula separaria os campos da linha "Style:" do ASS.
        font = re.sub(r"[,\r\n{}]", "", self.font or "").strip() or "Arial"
        return CaptionStyle(
            font=font[:64], size=max(40, min(160, int(self.size))),
            text_color=self.text_color, highlight_color=self.highlight_color,
            position=max(8, min(92, int(self.position))), words=max(1, min(4, int(self.words))),
            uppercase=bool(self.uppercase),
            animation=self.animation if self.animation in ANIMATIONS else "highlight",
            background=bool(self.background))

    @property
    def y(self) -> int:
        return round(HEIGHT * self.normalized().position / 100)


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
    # Título no topo; se a legenda estiver lá em cima, ele vai para baixo para não encostar.
    title_alignment = 2 if style.position < 35 else 8
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
        # Título: caixa na cor de destaque (BorderStyle 3), texto que contrasta.
        f"Style: Title,{style.font},{round(style.size * 0.84)},{title_text},&H000000FF,"
        f"{highlight},&H00000000,-1,0,0,0,"
        f"100,100,0,0,3,22,0,{title_alignment},90,90,300,1\n\n"
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


def title_event(title: str, seconds: float, total: float) -> str:
    """Título que entra crescendo, dá um leve "pulo" e some em fade."""
    text = ass_text(title)
    end = min(max(0.5, seconds), total) if total else max(0.5, seconds)
    animation = ("{\\fad(120,280)\\fscx40\\fscy40"
                 "\\t(0,220,\\fscx108\\fscy108)\\t(220,360,\\fscx100\\fscy100)}")
    return f"Dialogue: 1,{ass_time(0)},{ass_time(end)},Title,,0,0,0,,{animation}{text}"


def build_ass(words: list[dict], total: float, *, title: str = "", title_seconds: float = 2.0,
              style: CaptionStyle = CaptionStyle()) -> str:
    style = style.normalized()
    rows = caption_events(caption_groups(words, style.words), total, style)
    if title.strip():
        rows.insert(0, title_event(title, title_seconds if title_seconds > 0 else total, total))
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


def _framing_graph(framing: str, tracking: Tracking | None = None) -> str:
    """De ``[vc]`` (o corte emendado) até um quadro 1080x1920 rotulado ``[vf]``."""
    if framing == "track" and tracking is not None:
        # Altura em 1920 e janela de 1080 que anda na horizontal conforme a análise.
        # yuv444p antes do crop: em 4:2:0 o x só anda de 2 em 2 pixels.
        return (f"[vc]scale=-2:{HEIGHT},format=yuv444p,"
                f"sendcmd=f={_escape_filter_path(tracking.commands)},"
                f"crop@track={WIDTH}:{HEIGHT}:{tracking.first_x}:0,setsar=1[vf]")
    if framing in {"crop", "track"}:
        return (f"[vc]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
                f"crop={WIDTH}:{HEIGHT},setsar=1[vf]")
    # Mesmo visual de "Criar versão vertical" nas Ferramentas.
    return (f"[vc]split=2[bg][fg];"
            f"[bg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},"
            "boxblur=luma_radius=24:luma_power=2,eq=brightness=-0.08[bgb];"
            f"[fg]scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease[fgs];"
            "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,setsar=1[vf]")


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
                 progress_colour: str = "", normalize_audio: bool = False) -> str:
    """Recorta cada trecho com fala, emenda vídeo e áudio juntos, enquadra e grava a legenda."""
    if not intervals:
        raise ClipError("Não sobrou nenhum trecho para montar o corte.")
    parts: list[str] = []
    pads: list[str] = []
    for index, (start, end) in enumerate(intervals):
        parts.append(f"[0:v:0]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{index}]")
        parts.append(f"[0:a:0]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{index}]")
        pads.append(f"[v{index}][a{index}]")
    audio = "[ac0]" if normalize_audio else "[ac]"
    parts.append(f"{''.join(pads)}concat=n={len(intervals)}:v=1:a=1[vc]{audio}")
    if normalize_audio:
        # -14 LUFS é o alvo do YouTube, TikTok e Reels; uma passada só, sem arquivo extra.
        parts.append("[ac0]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[ac]")
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
                   tracking: Tracking | None = None, **extras) -> list[str]:
    """Um FFmpeg só, sem shell: o arquivo de origem nunca é alterado."""
    if source.resolve() == destination.resolve():
        raise ClipError("Escolha outra pasta de saída para preservar o arquivo original.")
    return [
        str(ffmpeg), "-hide_banner", "-n",
        "-ss", f"{max(0.0, offset):.3f}", "-t", f"{length:.3f}", "-i", str(source),
        "-filter_complex", filter_graph(intervals, framing, subtitles, tracking, **extras),
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
