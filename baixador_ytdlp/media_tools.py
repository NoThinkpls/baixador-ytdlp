"""Operações locais de mídia construídas sobre o FFmpeg já gerenciado pelo aplicativo."""
from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, replace
from pathlib import Path

from .processes import CREATE_NO_WINDOW
from .gpu import UPLOAD_FILTER, backend_of, device_args, quality_args, select_section_encoder
from .tools import Toolchain

TIME_RE = re.compile(r"^(?:\d{1,2}:)?(?:[0-5]?\d:)?[0-5]?\d(?:\.\d+)?$")


class MediaToolError(RuntimeError):
    """Erro de validação ou de execução apresentado pela página de ferramentas."""


@dataclass(frozen=True)
class MediaToolOptions:
    source: Path
    destination: Path
    # trim | audio | remux | compress | target_size | shorts | burn | soft_sub | convert | speed |
    # rotate | mute | normalize | gif | frame | extract_subs | strip
    operation: str
    start: str = ""
    end: str = ""
    subtitles: Path | None = None
    subtitle_language: str = ""   # ISO 639-1 do Whisper (pt, en…); vazio = indefinido
    target_mb: int = 25           # "target_size": limite do arquivo final em MB
    shorts_blur: bool = True      # "shorts": fundo desfocado em vez de barras pretas
    fast_trim: bool = False       # "trim": cópia direta, sem reencodar (corta no quadro-chave)
    choice: str = ""              # escolha única da ferramenta (ver CHOICES); vazio = padrão
    stream_index: int = -1        # "extract_subs": faixa resolvida pelo ffprobe (-1 = a primeira)


# Operações que podem usar encoder de GPU. "Caber em um limite" fica na CPU: o
# x264 entrega mais qualidade por byte, que é o objetivo dessa ferramenta, e
# respeita melhor o teto de bitrate numa passada só.
GPU_VIDEO_OPERATIONS = frozenset({"trim", "compress", "shorts", "burn", "speed", "rotate",
                                  "convert"})

# Ferramentas com um recorte de tempo (início/fim) e as que só usam o início.
TIMED_OPERATIONS = frozenset({"trim", "gif"})
GIF_MAX_SECONDS = 30   # acima disso o GIF passa de centenas de MB sem ganho para quem assiste


def uses_gpu(options: MediaToolOptions) -> bool:
    if options.operation not in GPU_VIDEO_OPERATIONS:
        return False
    if options.operation == "trim":
        return not options.fast_trim
    if options.operation == "convert":
        return options.destination.suffix.casefold() != ".webm"   # VP9 não tem encoder de GPU
    return True


# Ferramentas com uma escolha única (a Select da página): valores válidos na ordem exibida e o
# padrão de cada uma. O que a escolha significa depende da ferramenta: em "audio", "convert",
# "frame" e "extract_subs" ela só sugere a extensão do arquivo (o codec vem da extensão final,
# então renomear o destino nunca gera um comando incoerente); nas demais é o parâmetro em si.
CHOICES: dict[str, tuple[str, ...]] = {
    "audio": ("mp3", "m4a", "opus", "flac", "wav"),
    "convert": ("mp4", "webm"),
    "speed": ("0.25", "0.5", "0.75", "1.25", "1.5", "2", "3", "4"),
    "rotate": ("cw", "ccw", "180", "flip_h", "flip_v"),
    "gif": ("480", "640", "800"),
    "normalize": ("-16", "-14", "-23"),
    "frame": ("png", "jpg", "webp"),
    "extract_subs": ("srt", "ass", "vtt"),
}
DEFAULT_CHOICE = {"audio": "mp3", "convert": "mp4", "speed": "2", "rotate": "cw", "gif": "640",
                  "normalize": "-16", "frame": "png", "extract_subs": "srt"}


def choice_of(operation: str, choice: str = "") -> str:
    """Escolha válida para ``operation``: valor desconhecido cai no padrão da ferramenta."""
    values = CHOICES.get(operation)
    if not values:
        return ""
    return choice if choice in values else DEFAULT_CHOICE[operation]


# A extensão de saída manda no codec (ver CHOICES).
AUDIO_CODECS: dict[str, list[str]] = {
    ".mp3": ["-c:a", "libmp3lame", "-q:a", "2"],
    ".m4a": ["-c:a", "aac", "-b:a", "192k"],
    ".opus": ["-c:a", "libopus", "-b:a", "128k"],
    ".ogg": ["-c:a", "libvorbis", "-q:a", "5"],
    ".flac": ["-c:a", "flac"],
    ".wav": ["-c:a", "pcm_s16le"],
}
VIDEO_CONTAINERS = frozenset({".mp4", ".m4v", ".mov", ".mkv", ".webm"})
MP4_FAMILY = frozenset({".mp4", ".m4v", ".mov"})
IMAGE_ARGS: dict[str, list[str]] = {
    ".png": [], ".jpg": ["-q:v", "2"], ".jpeg": ["-q:v", "2"], ".webp": ["-q:v", "90"],
}
SUBTITLE_CODECS = {".srt": "srt", ".ass": "ass", ".vtt": "webvtt"}
# Legendas em texto (as únicas que viram .srt/.ass/.vtt); PGS, DVD e DVB são imagens.
TEXT_SUBTITLE_CODECS = frozenset({"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text",
                                  "subviewer", "microdvd", "mpl2", "realtext", "sami"})
ROTATE_FILTERS = {"cw": "transpose=1", "ccw": "transpose=2", "180": "hflip,vflip",
                  "flip_h": "hflip", "flip_v": "vflip"}
GIF_FPS = {"480": 12, "640": 15, "800": 20}


ISO_639_2 = {"pt": "por", "en": "eng", "es": "spa", "fr": "fra", "de": "deu",
             "it": "ita", "ja": "jpn", "ko": "kor", "zh": "zho", "ru": "rus",
             "nl": "nld", "pl": "pol", "tr": "tur", "ar": "ara", "hi": "hin"}


def _same_container(source: Path) -> str:
    """Contêiner de vídeo do arquivo de origem; formatos que o FFmpeg copia mal viram MKV."""
    suffix = source.suffix.casefold()
    return suffix if suffix in VIDEO_CONTAINERS else ".mkv"


def _normalized_extension(source: Path) -> str:
    suffix = source.suffix.casefold()
    if suffix in AUDIO_CODECS:
        return suffix
    return ".m4a" if suffix in {".aac", ".wma", ".ac3"} else _same_container(source)


def default_destination(source: Path, operation: str, subtitles: Path | None = None,
                        choice: str = "") -> Path:
    if operation == "soft_sub":
        ass = bool(subtitles and subtitles.suffix.casefold() in {".ass", ".ssa"})
        # Legenda ASS (inclusive karaokê) vai para MKV, que preserva o estilo.
        extension = ".mp4" if (source.suffix.casefold() in {".mp4", ".m4v", ".mov"}
                               and not ass) else ".mkv"
        return available_destination(source.with_name(f"{source.stem}_legendado{extension}"))
    choice = choice_of(operation, choice)
    if operation == "extract_subs":
        # Nome de legenda "ao lado": o player a encontra sozinho.
        return available_destination(source.with_name(f"{source.stem}.{choice}"))
    suffixes = {
        "trim": ("_trecho", ".mkv"),
        "audio": ("_audio", f".{choice}"),
        "convert": ("_convertido", f".{choice}"),
        "speed": ("_velocidade", ".mp4"),
        "rotate": ("_girado", ".mp4"),
        "mute": ("_sem_audio", _same_container(source)),
        "normalize": ("_normalizado", _normalized_extension(source)),
        "gif": ("_animado", ".gif"),
        "frame": ("_quadro", f".{choice}"),
        "strip": ("_limpo", _same_container(source)),
        "remux": ("_remux", ".mkv"),
        "compress": ("_compactado", ".mp4"),
        "shorts": ("_shorts", ".mp4"),
        "burn": ("_com_legendas", ".mp4"),
        "target_size": ("_tamanho_alvo", ".mp4"),
    }
    label, extension = suffixes.get(operation, ("_editado", ".mp4"))
    return available_destination(source.with_name(f"{source.stem}{label}{extension}"))


def available_destination(path: Path) -> Path:
    """Preserva resultados existentes escolhendo automaticamente ``(2)``, ``(3)``…"""
    if not path.exists():
        return path
    for index in range(2, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise MediaToolError("Há arquivos demais com o mesmo nome na pasta de destino.")


def time_seconds(value: str) -> float:
    parts = [float(part) for part in value.strip().split(":") if part != ""]
    if not parts:
        return 0.0
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def media_duration(source: Path, toolchain: Toolchain) -> float:
    """Lê a duração fora da UI; falha apenas torna o progresso indeterminado."""
    try:
        result = subprocess.run(
            [str(toolchain.ffprobe), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=nokey=1:noprint_wrappers=1", str(source)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            creationflags=CREATE_NO_WINDOW,  # sem janela de console piscando no Windows
        )
        return max(0.0, float(result.stdout.strip())) if result.returncode == 0 else 0.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def operation_duration(options: MediaToolOptions, toolchain: Toolchain) -> float:
    """Duração da *saída*, que é o que o progresso do FFmpeg mede (0 = indeterminado)."""
    total = media_duration(options.source, toolchain)
    operation = options.operation
    if operation == "speed":
        return total / float(choice_of("speed", options.choice))
    if operation == "frame":
        start = time_seconds(options.start) if options.start else 0.0
        if total and start >= total:
            raise MediaToolError("O momento escolhido precisa estar dentro da duração do arquivo.")
        return 0.0
    if operation not in TIMED_OPERATIONS:
        return total
    start = time_seconds(options.start) if options.start else 0.0
    if total and start >= total:
        raise MediaToolError("O início do trecho precisa estar dentro da duração do arquivo.")
    if operation == "gif" and not options.end and not total:
        raise MediaToolError("Não foi possível ler a duração do arquivo; informe o fim do trecho.")
    end = time_seconds(options.end) if options.end else total
    if total:
        end = min(end, total)
    length = max(0.0, end - start)
    if operation == "gif" and length > GIF_MAX_SECONDS:
        raise MediaToolError(
            f"GIFs acima de {GIF_MAX_SECONDS} s ficam enormes. Informe início e fim com "
            f"até {GIF_MAX_SECONDS} s (o trecho atual tem {length:.0f} s).")
    return length


def subtitle_streams(source: Path, toolchain: Toolchain) -> list[dict]:
    """Faixas de legenda do arquivo: ``[{"index": 2, "codec_name": "subrip", ...}]``."""
    try:
        result = subprocess.run(
            [str(toolchain.ffprobe), "-v", "error", "-select_streams", "s",
             "-show_entries", "stream=index,codec_name:stream_tags=language,title",
             "-of", "json", str(source)],
            capture_output=True, text=True, timeout=30, check=False,
            creationflags=CREATE_NO_WINDOW,
        )
        streams = json.loads(result.stdout or "{}").get("streams", []) if result.returncode == 0 else []
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    return [item for item in streams if isinstance(item, dict) and isinstance(item.get("index"), int)]


def resolve_options(options: MediaToolOptions, toolchain: Toolchain) -> MediaToolOptions:
    """Completa o que só o ffprobe sabe (fora da UI) e recusa cedo o que não tem como dar certo."""
    if options.operation != "extract_subs":
        return options
    streams = subtitle_streams(options.source, toolchain)
    if not streams:
        raise MediaToolError("Este arquivo não tem legendas embutidas.")
    text = [item for item in streams if str(item.get("codec_name", "")).casefold()
            in TEXT_SUBTITLE_CODECS]
    if not text:
        raise MediaToolError(
            "As legendas deste arquivo são imagens (PGS/DVD) e não podem virar texto.")
    return replace(options, stream_index=int(text[0]["index"]))


# Fundo: o próprio vídeo ampliado para 9:16, cortado e desfocado; frente: o
# vídeo inteiro centralizado. Evita as barras pretas das versões anteriores.
SHORTS_BLUR_FILTER = (
    "[0:v:0]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
    "boxblur=luma_radius=24:luma_power=2,eq=brightness=-0.08[bgb];"
    "[fg]scale=1080:1920:force_original_aspect_ratio=decrease[fgs];"
    "[bgb][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]"
)
TARGET_AUDIO_KBPS = 128
TARGET_SAFETY = 0.94   # sobra para o contêiner e para a variação do codificador


def target_video_kbps(target_mb: int, duration: float, audio_kbps: int = TARGET_AUDIO_KBPS) -> int:
    """Bitrate de vídeo que faz o arquivo caber em ``target_mb`` (MB decimais)."""
    if duration <= 0:
        raise MediaToolError("Não foi possível ler a duração do arquivo para calcular o tamanho.")
    total_kbps = target_mb * 8_000 * TARGET_SAFETY / duration
    video = int(total_kbps - audio_kbps)
    if video < 150:
        raise MediaToolError(
            f"{target_mb} MB é pouco para {duration / 60:.1f} min de vídeo; "
            "aumente o limite ou recorte um trecho antes.")
    return video


def _target_size_args(options: MediaToolOptions, toolchain: Toolchain) -> list[str]:
    """Uma passada com VBV limitado: o resultado fica abaixo do alvo (Discord, WhatsApp…)."""
    duration = media_duration(options.source, toolchain)
    video = target_video_kbps(max(1, int(options.target_mb)), duration)
    # Resolução acompanha o orçamento: 1080p abaixo de ~2,5 Mbps só produz blocos.
    height = 1080 if video >= 2500 else 720 if video >= 1200 else 480
    return [
        "-map", "0:v:0", "-map", "0:a:0?",
        "-vf", f"scale=-2:'min({height},ih)'",
        "-c:v", "libx264", "-preset", "medium",
        "-b:v", f"{video}k", "-maxrate", f"{video}k", "-bufsize", f"{video * 2}k",
        "-c:a", "aac", "-b:a", f"{TARGET_AUDIO_KBPS}k", "-movflags", "+faststart",
    ]


def _audio_args(destination: Path) -> list[str]:
    args = AUDIO_CODECS.get(destination.suffix.casefold())
    if args is None:
        raise MediaToolError("Use .mp3, .m4a, .opus, .flac ou .wav como extensão de saída.")
    return list(args)


def _convert_args(destination: Path) -> list[str]:
    suffix = destination.suffix.casefold()
    if suffix == ".webm":
        return ["-map", "0:v:0", "-map", "0:a?", "-pix_fmt", "yuv420p",
                "-c:v", "libvpx-vp9", "-crf", "32", "-b:v", "0", "-row-mt", "1",
                "-deadline", "good", "-cpu-used", "3",
                "-c:a", "libopus", "-b:a", "128k"]
    if suffix in VIDEO_CONTAINERS:
        return ["-map", "0:v:0", "-map", "0:a?", "-pix_fmt", "yuv420p",
                "-c:v", "libx264", "-preset", "medium", "-crf", "20",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]
    raise MediaToolError("Use .mp4, .mkv ou .webm como extensão de saída.")


def _atempo_chain(factor: float) -> str:
    """O atempo só aceita 0,5–2: fora disso encadeia (4x = 2x duas vezes)."""
    parts: list[float] = []
    while factor > 2.0:
        parts.append(2.0)
        factor /= 2.0
    while factor < 0.5:
        parts.append(0.5)
        factor /= 0.5
    parts.append(factor)
    return ",".join(f"atempo={part:g}" for part in parts)


def _speed_args(factor: float) -> list[str]:
    args = ["-map", "0:v:0", "-map", "0:a?", "-vf", f"setpts=PTS/{factor:g}",
            "-af", _atempo_chain(factor)]
    if factor > 1:
        args += ["-fpsmax", "60"]   # 4x de um vídeo de 60 fps não vira 240 fps
    return args + ["-c:v", "libx264", "-preset", "medium", "-crf", "20",
                   "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart"]


def _gif_args(width: str) -> list[str]:
    """Paleta própria do trecho e dither por bloco: o GIF fica bem menor e sem faixas de cor."""
    graph = (f"fps={GIF_FPS[width]},scale='min({width},iw)':-2:flags=lanczos,split[a][b];"
             "[a]palettegen=stats_mode=diff[p];"
             "[b][p]paletteuse=dither=bayer:bayer_scale=5:diff_mode=rectangle")
    return ["-map", "0:v:0", "-an", "-vf", graph, "-loop", "0"]


def _normalize_args(destination: Path, loudness: str) -> list[str]:
    # Análise única (dinâmica): boa o bastante para nivelar sem ler o arquivo duas vezes.
    # loudnorm devolve 192 kHz; -ar 48000 evita arquivos de áudio inchados e incompatíveis.
    audio = ["-af", f"loudnorm=I={loudness}:TP=-1.5:LRA=11", "-ar", "48000"]
    suffix = destination.suffix.casefold()
    if suffix in AUDIO_CODECS:
        return ["-vn", "-map", "0:a:0", *audio, *AUDIO_CODECS[suffix]]
    codec = ["-c:a", "libopus", "-b:a", "160k"] if suffix == ".webm" else ["-c:a", "aac", "-b:a", "192k"]
    args = ["-map", "0:v?", "-map", "0:a?", "-c:v", "copy", *audio, *codec]
    if suffix in MP4_FAMILY:
        args += ["-movflags", "+faststart"]
    return args


def _frame_args(destination: Path) -> list[str]:
    quality = IMAGE_ARGS.get(destination.suffix.casefold())
    if quality is None:
        raise MediaToolError("Use .png, .jpg ou .webp como extensão de saída.")
    return ["-map", "0:v:0", "-frames:v", "1", "-update", "1", *quality]


def _subtitle_args(options: MediaToolOptions) -> list[str]:
    codec = SUBTITLE_CODECS.get(options.destination.suffix.casefold())
    if codec is None:
        raise MediaToolError("Use .srt, .ass ou .vtt como extensão de saída.")
    stream = f"0:{options.stream_index}" if options.stream_index >= 0 else "0:s:0"
    return ["-map", stream, "-c:s", codec]


def _strip_args(destination: Path) -> list[str]:
    """Copia as faixas sem reencodar e sem nenhuma etiqueta: GPS, título, câmera, software."""
    args = ["-map", "0:v?", "-map", "0:a?"]
    if destination.suffix.casefold() not in MP4_FAMILY:
        args += ["-map", "0:s?"]   # MP4 só aceita legenda de texto simples; MKV/WebM guardam qualquer uma
    return args + ["-c", "copy", "-map_metadata", "-1", "-map_chapters", "-1",
                   "-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1", "-map_metadata:s:s", "-1",
                   "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact"]


def build_command(options: MediaToolOptions, toolchain: Toolchain, *, video_encoder: str = "") -> list[str]:
    """Monta uma invocação FFmpeg sem shell e sem nunca alterar o arquivo de origem."""
    if not options.source.is_file():
        raise MediaToolError("Selecione um arquivo de vídeo ou áudio existente.")
    if options.source.resolve() == options.destination.resolve():
        raise MediaToolError("Escolha outro nome de saída para preservar o arquivo original.")
    if options.operation == "trim":
        _validate_time_range(options.start, options.end)
    elif options.operation == "gif":
        _validate_time_range(options.start, options.end, required=False)
    elif options.operation == "frame":
        _validate_time_range(options.start, "", required=False)
    if options.operation in {"burn", "soft_sub"} and not (
            options.subtitles and options.subtitles.is_file()):
        raise MediaToolError("Selecione um arquivo de legenda .srt, .vtt ou .ass.")

    command = [str(toolchain.ffmpeg), "-hide_banner", "-n"]
    if options.operation in TIMED_OPERATIONS | {"frame"} and options.start:
        command += ["-ss", options.start]
    command += ["-i", str(options.source)]

    # Buscar antes da entrada é rápido; ao reencodar, o FFmpeg decodifica
    # desde o quadro-chave anterior e descarta os quadros antes de -ss.
    # Stream copy deixava esses quadros no arquivo e podia congelar o começo.
    if options.operation in TIMED_OPERATIONS and options.end:
        length = time_seconds(options.end) - time_seconds(options.start)
        command += ["-t", f"{length:.6f}"]
    if options.operation == "gif":
        command += _gif_args(choice_of("gif", options.choice))
    elif options.operation == "trim":
        if options.fast_trim:
            # Corte rápido: nada é reencodado, então é instantâneo e sem perda,
            # mas o início cai no quadro-chave anterior ao ponto escolhido.
            command += ["-map", "0", "-map_chapters", "-1", "-c", "copy",
                        "-avoid_negative_ts", "make_zero"]
        else:
            command += [
                "-map", "0:v:0?", "-map", "0:a?", "-map_chapters", "-1",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "192k",
            ]
    elif options.operation == "audio":
        command += ["-vn", *_audio_args(options.destination)]
    elif options.operation == "remux":
        command += ["-map", "0", "-c", "copy"]
    elif options.operation == "compress":
        command += [
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
            "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        ]
    elif options.operation == "shorts":
        video = (["-filter_complex", SHORTS_BLUR_FILTER, "-map", "[v]"] if options.shorts_blur
                 else ["-map", "0:v:0", "-vf",
                       "scale=1080:1920:force_original_aspect_ratio=decrease,"
                       "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"])
        command += [
            *video, "-map", "0:a?",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        ]
    elif options.operation == "burn":
        # Não copie todas as faixas de entrada: arquivos MP4 podem ter dados ou
        # legendas internas que não são aceitos pelo contêiner de saída. A
        # legenda escolhida já entra na imagem pelo filtro abaixo.
        command += [
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", f"subtitles=filename='{_escape_filter_path(options.subtitles)}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            # Reencodar o áudio evita uma segunda fonte de falhas ao salvar MP4
            # quando a mídia de entrada traz Opus, DTS ou outro codec que o
            # contêiner não aceita.
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        ]
    elif options.operation == "soft_sub":
        # A legenda nova entra como PRIMEIRA faixa de legenda (s:0), para que o
        # idioma e a marcação "padrão" apontem para ela e não para uma antiga.
        mp4 = options.destination.suffix.casefold() in {".mp4", ".m4v", ".mov"}
        command += ["-i", str(options.subtitles),
                    "-map", "0:v?", "-map", "0:a?", "-map", "1:0", "-map", "0:s?"]
        if not mp4:
            command += ["-map", "0:t?"]  # fontes/capas anexadas só existem em MKV
        command += ["-c", "copy"]
        subtitle_suffix = options.subtitles.suffix.casefold() if options.subtitles else ""
        if mp4:
            # MP4 só aceita texto simples (mov_text): estilo ASS/karaokê se perde.
            command += ["-c:s", "mov_text", "-movflags", "+faststart"]
        elif subtitle_suffix in {".ass", ".ssa", ".srt"}:
            command += ["-c:s:0", "copy"]   # MKV guarda ASS nativo: karaokê preservado
        else:
            command += ["-c:s:0", "srt"]    # VTT/JSON/TXT viram SRT dentro do MKV
        language = ISO_639_2.get((options.subtitle_language or "").casefold(), "und")
        command += ["-metadata:s:s:0", f"language={language}",
                    "-metadata:s:s:0", "title=Whisper",
                    "-disposition:s:0", "default"]
    elif options.operation == "target_size":
        command += _target_size_args(options, toolchain)
    elif options.operation == "convert":
        command += _convert_args(options.destination)
    elif options.operation == "speed":
        command += _speed_args(float(choice_of("speed", options.choice)))
    elif options.operation == "rotate":
        command += [
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", ROTATE_FILTERS[choice_of("rotate", options.choice)],
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        ]
    elif options.operation == "mute":
        command += ["-map", "0:v", "-c", "copy"]
        if options.destination.suffix.casefold() in MP4_FAMILY:
            command += ["-movflags", "+faststart"]
    elif options.operation == "normalize":
        command += _normalize_args(options.destination, choice_of("normalize", options.choice))
    elif options.operation == "frame":
        command += _frame_args(options.destination)
    elif options.operation == "extract_subs":
        command += _subtitle_args(options)
    elif options.operation == "strip":
        command += _strip_args(options.destination)
    else:
        raise MediaToolError("Ferramenta de mídia desconhecida.")

    if video_encoder and uses_gpu(options) and "-c:v" in command:
        # Filtros permanecem na CPU; o encoder de hardware recebe os quadros
        # prontos. Isso funciona também com subtitles/libass e fundos desfocados.
        if backend_of(video_encoder) == "vaapi" and "-filter_complex" in command:
            # Fundo desfocado usa um grafo complexo; enviar o resultado à GPU exigiria
            # reescrevê-lo. Fica na CPU (x264), que já é o comportamento de segurança.
            return _finish(command, options)
        index = command.index("-c:v")
        command[index + 1] = video_encoder
        if "-crf" in command:
            crf = command.index("-crf")
            command[crf:crf + 2] = quality_args(video_encoder, int(command[crf + 1]))
        if "-preset" in command:
            preset = command.index("-preset")
            if video_encoder.endswith("_nvenc"):
                command[preset + 1] = "p5"
            else:
                del command[preset:preset + 2]
        if backend_of(video_encoder) == "vaapi":
            # O VAAPI só aceita quadros na GPU: os filtros rodam na CPU e o resultado sobe no fim.
            if "-vf" in command:
                vf = command.index("-vf") + 1
                command[vf] = f"{command[vf]},{UPLOAD_FILTER}"
            else:
                command[command.index("-c:v"):command.index("-c:v")] = ["-vf", UPLOAD_FILTER]
            command[command.index("-i"):command.index("-i")] = device_args(video_encoder)
    return _finish(command, options)


def _finish(command: list[str], options: MediaToolOptions) -> list[str]:
    command += ["-progress", "pipe:1", "-nostats", str(options.destination)]
    return command


def preferred_video_encoder(toolchain: Toolchain) -> str:
    """Detecta um encoder anunciado; a execução real decide se ele funciona."""
    return select_section_encoder(toolchain.ffmpeg)


def _validate_time_range(start: str, end: str, *, required: bool = True) -> None:
    start, end = start.strip(), end.strip()
    if required and not start and not end:
        raise MediaToolError("Informe ao menos o início ou o fim do trecho.")
    for value in (start, end):
        if value and not TIME_RE.match(value):
            raise MediaToolError("Use mm:ss ou hh:mm:ss para definir o trecho.")
    if end and time_seconds(end) <= time_seconds(start):
        raise MediaToolError("O fim do trecho precisa ser posterior ao início.")


def _escape_filter_path(path: Path | None) -> str:
    if path is None:
        return ""
    # O filtro subtitles recebe uma string própria do FFmpeg, não um argumento de shell.
    value = str(path.resolve()).replace("\\", "/")
    # Aqui cada caractere precisa de *uma* barra. Duas barras antes de `:`
    # fazem o parser do FFmpeg interpretar `C\\:` como uma opção separada,
    # gerando "Error opening output files: Invalid argument" no Windows.
    return (value.replace("'", r"\'")
                 .replace(":", r"\:")
                 .replace(",", r"\,")
                 .replace("[", r"\[")
                 .replace("]", r"\]")
                 .replace(";", r"\;")
                 .replace("|", r"\|"))
