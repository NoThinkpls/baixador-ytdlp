"""Operações locais de mídia construídas sobre o FFmpeg já gerenciado pelo aplicativo."""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tools import Toolchain

TIME_RE = re.compile(r"^(?:\d{1,2}:)?(?:[0-5]?\d:)?[0-5]?\d(?:\.\d+)?$")


class MediaToolError(RuntimeError):
    """Erro de validação ou de execução apresentado pela página de ferramentas."""


@dataclass(frozen=True)
class MediaToolOptions:
    source: Path
    destination: Path
    operation: str  # trim | audio | remux | compress | shorts | burn | soft_sub
    start: str = ""
    end: str = ""
    subtitles: Path | None = None


def default_destination(source: Path, operation: str) -> Path:
    if operation == "soft_sub":
        extension = ".mp4" if source.suffix.casefold() in {".mp4", ".m4v", ".mov"} else ".mkv"
        return available_destination(source.with_name(f"{source.stem}_legendado{extension}"))
    suffixes = {
        "trim": ("_trecho", ".mkv"),
        "audio": ("_audio", ".mp3"),
        "remux": ("_remux", ".mkv"),
        "compress": ("_compactado", ".mp4"),
        "shorts": ("_shorts", ".mp4"),
        "burn": ("_com_legendas", ".mp4"),
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
        )
        return max(0.0, float(result.stdout.strip())) if result.returncode == 0 else 0.0
    except (OSError, subprocess.SubprocessError, ValueError):
        return 0.0


def operation_duration(options: MediaToolOptions, toolchain: Toolchain) -> float:
    total = media_duration(options.source, toolchain)
    if options.operation != "trim":
        return total
    start = time_seconds(options.start) if options.start else 0.0
    end = time_seconds(options.end) if options.end else total
    return max(0.0, end - start)


def build_command(options: MediaToolOptions, toolchain: Toolchain) -> list[str]:
    """Monta uma invocação FFmpeg sem shell e sem nunca alterar o arquivo de origem."""
    if not options.source.is_file():
        raise MediaToolError("Selecione um arquivo de vídeo ou áudio existente.")
    if options.source.resolve() == options.destination.resolve():
        raise MediaToolError("Escolha outro nome de saída para preservar o arquivo original.")
    if options.operation == "trim":
        _validate_time_range(options.start, options.end)
    if options.operation in {"burn", "soft_sub"} and not (
            options.subtitles and options.subtitles.is_file()):
        raise MediaToolError("Selecione um arquivo de legenda .srt, .vtt ou .ass.")

    command = [str(toolchain.ffmpeg), "-hide_banner", "-n"]
    if options.operation == "trim" and options.start:
        command += ["-ss", options.start]
    if options.operation == "trim" and options.end:
        # Junto de -ss, antes da entrada, -to continua sendo o instante final
        # absoluto. Depois de -i ele virava duração e criava um trecho maior.
        command += ["-to", options.end]
    command += ["-i", str(options.source)]

    if options.operation == "trim":
        command += ["-map", "0", "-c", "copy"]
    elif options.operation == "audio":
        command += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
    elif options.operation == "remux":
        command += ["-map", "0", "-c", "copy"]
    elif options.operation == "compress":
        command += [
            "-map", "0:v:0", "-map", "0:a?", "-c:v", "libx264",
            "-preset", "medium", "-crf", "23",
            "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart",
        ]
    elif options.operation == "shorts":
        command += [
            "-map", "0:v:0", "-map", "0:a?",
            "-vf", (
                "scale=1080:1920:force_original_aspect_ratio=decrease,"
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black"
            ),
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
        command += ["-i", str(options.subtitles), "-map", "0", "-map", "1:0", "-c", "copy"]
        if options.destination.suffix.casefold() == ".mp4":
            command += ["-c:s", "mov_text", "-movflags", "+faststart"]
        else:
            command += ["-c:s", "srt"]
    else:
        raise MediaToolError("Ferramenta de mídia desconhecida.")

    command += ["-progress", "pipe:1", "-nostats", str(options.destination)]
    return command


def _validate_time_range(start: str, end: str) -> None:
    start, end = start.strip(), end.strip()
    if not start and not end:
        raise MediaToolError("Informe ao menos o início ou o fim do trecho.")
    for value in (start, end):
        if value and not TIME_RE.match(value):
            raise MediaToolError("Use mm:ss ou hh:mm:ss para definir o trecho.")


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
