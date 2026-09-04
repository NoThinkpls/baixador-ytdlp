"""Operações locais de mídia construídas sobre o FFmpeg já gerenciado pelo aplicativo."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .tools import Toolchain

TIME_RE = __import__("re").compile(r"^(?:\d{1,2}:)?(?:[0-5]?\d:)?[0-5]?\d(?:\.\d+)?$")


class MediaToolError(RuntimeError):
    """Erro de validação ou de execução apresentado pela página de ferramentas."""


@dataclass(frozen=True)
class MediaToolOptions:
    source: Path
    destination: Path
    operation: str  # trim | audio | remux | compress | shorts | burn
    start: str = ""
    end: str = ""
    subtitles: Path | None = None


def default_destination(source: Path, operation: str) -> Path:
    suffixes = {
        "trim": ("_trecho", ".mkv"),
        "audio": ("_audio", ".mp3"),
        "remux": ("_remux", ".mkv"),
        "compress": ("_compactado", ".mp4"),
        "shorts": ("_shorts", ".mp4"),
        "burn": ("_legendado", ".mp4"),
    }
    label, extension = suffixes.get(operation, ("_editado", ".mp4"))
    return source.with_name(f"{source.stem}{label}{extension}")


def build_command(options: MediaToolOptions, toolchain: Toolchain) -> list[str]:
    """Monta uma invocação FFmpeg sem shell e sem nunca alterar o arquivo de origem."""
    if not options.source.is_file():
        raise MediaToolError("Selecione um arquivo de vídeo ou áudio existente.")
    if options.source.resolve() == options.destination.resolve():
        raise MediaToolError("Escolha outro nome de saída para preservar o arquivo original.")
    if options.operation == "trim":
        _validate_time_range(options.start, options.end)
    if options.operation == "burn" and not (options.subtitles and options.subtitles.is_file()):
        raise MediaToolError("Selecione um arquivo de legenda .srt, .vtt ou .ass.")

    command = [str(toolchain.ffmpeg), "-hide_banner", "-y"]
    if options.operation == "trim" and options.start:
        command += ["-ss", options.start]
    command += ["-i", str(options.source)]

    if options.operation == "trim":
        if options.end:
            command += ["-to", options.end]
        command += ["-map", "0", "-c", "copy"]
    elif options.operation == "audio":
        command += ["-vn", "-c:a", "libmp3lame", "-q:a", "2"]
    elif options.operation == "remux":
        command += ["-map", "0", "-c", "copy"]
    elif options.operation == "compress":
        command += [
            "-map", "0", "-c:v", "libx264", "-preset", "medium", "-crf", "23",
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
        command += [
            "-map", "0", "-vf", f"subtitles=filename='{_escape_filter_path(options.subtitles)}'",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "copy", "-movflags", "+faststart",
        ]
    else:
        raise MediaToolError("Ferramenta de mídia desconhecida.")

    command.append(str(options.destination))
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
    return (value.replace("\\", "\\\\")
                 .replace(":", r"\\:")
                 .replace("'", r"\\'")
                 .replace(",", r"\\,")
                 .replace("[", r"\\[")
                 .replace("]", r"\\]"))
