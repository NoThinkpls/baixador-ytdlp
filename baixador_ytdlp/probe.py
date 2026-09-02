"""Análise da mídia: roda `yt-dlp -J` e transforma os formatos em linhas legíveis."""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .tools import CREATE_NO_WINDOW

VCODEC_NAMES = {
    "avc1": "H.264", "h264": "H.264", "vp9": "VP9", "vp09": "VP9",
    "av01": "AV1", "vp8": "VP8", "hev1": "HEVC", "hvc1": "HEVC",
}
ACODEC_NAMES = {"mp4a": "AAC", "opus": "Opus", "vorbis": "Vorbis", "ec-3": "E-AC3", "ac-3": "AC3"}


def _codec_label(codec: str, table: dict[str, str]) -> str:
    if not codec or codec == "none":
        return "—"
    base = codec.split(".")[0].lower()
    return table.get(base, base.upper())


def human_size(num: Optional[float]) -> str:
    if not num:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"


def human_duration(seconds: Optional[float]) -> str:
    if not seconds:
        return "—"
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


@dataclass
class FormatRow:
    format_id: str
    quality: str
    fps: str
    vcodec: str
    acodec: str
    ext: str
    size: str
    note: str
    height: int = 0
    video_only: bool = False
    audio_only: bool = False

    @property
    def selector(self) -> str:
        """Seletor -f a ser passado ao yt-dlp."""
        if self.video_only:
            return f"{self.format_id}+bestaudio/{self.format_id}"
        return self.format_id


@dataclass
class MediaInfo:
    title: str
    uploader: str
    duration: str
    thumbnail: str
    webpage_url: str
    is_playlist: bool
    playlist_count: int
    rows: list[FormatRow]
    raw: dict

    @property
    def best_label(self) -> str:
        for row in self.rows:
            if not row.audio_only:
                return row.quality
        return "melhor disponível"


class ProbeError(RuntimeError):
    pass


def probe(url: str, ytdlp: Path, cookies_browser: str = "", proxy: str = "",
          timeout: int = 120) -> MediaInfo:
    args = [str(ytdlp), "-J", "--no-warnings", "--ignore-config"]
    if cookies_browser:
        args += ["--cookies-from-browser", cookies_browser]
    if proxy:
        args += ["--proxy", proxy]
    args.append(url)

    try:
        proc = subprocess.run(
            args, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, creationflags=CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProbeError("A análise demorou demais. Verifique a conexão ou o link.") from exc

    if proc.returncode != 0 or not proc.stdout.strip():
        msg = (proc.stderr or "").strip().splitlines()
        detail = msg[-1] if msg else "erro desconhecido"
        raise ProbeError(_friendly(detail))

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("Resposta inválida do yt-dlp.") from exc

    is_playlist = data.get("_type") == "playlist"
    count = 0
    entry = data
    if is_playlist:
        entries = [e for e in (data.get("entries") or []) if e]
        count = len(entries)
        if not entries:
            raise ProbeError("A playlist não retornou nenhum vídeo.")
        entry = entries[0]

    return MediaInfo(
        title=entry.get("title") or data.get("title") or "Sem título",
        uploader=entry.get("uploader") or entry.get("channel") or "",
        duration=human_duration(entry.get("duration")),
        thumbnail=entry.get("thumbnail") or "",
        webpage_url=data.get("webpage_url") or url,
        is_playlist=is_playlist,
        playlist_count=count,
        rows=build_rows(entry),
        raw=entry,
    )


def _friendly(detail: str) -> str:
    low = detail.lower()
    if "private" in low or "login" in low or "cookies" in low:
        return ("Conteúdo restrito. Ative os cookies do navegador em Configurações "
                "e tente novamente.")
    if "unsupported url" in low:
        return "Esse site não é suportado pelo yt-dlp."
    if "unavailable" in low:
        return "O vídeo está indisponível ou foi removido."
    return detail.replace("ERROR: ", "")


def build_rows(info: dict) -> list[FormatRow]:
    """Ordena os formatos do melhor para o pior e devolve linhas prontas para a tabela."""
    video: list[FormatRow] = []
    audio: list[FormatRow] = []

    for fmt in info.get("formats") or []:
        if fmt.get("format_note") == "storyboard" or fmt.get("ext") == "mhtml":
            continue
        vcodec, acodec = fmt.get("vcodec") or "none", fmt.get("acodec") or "none"
        size = fmt.get("filesize") or fmt.get("filesize_approx")
        tbr = fmt.get("tbr") or 0

        if vcodec != "none":
            height = fmt.get("height") or 0
            fps = fmt.get("fps") or 0
            notes = []
            if fmt.get("dynamic_range") and fmt["dynamic_range"] != "SDR":
                notes.append(fmt["dynamic_range"])
            if acodec == "none":
                notes.append("áudio separado")
            if tbr:
                notes.append(f"{tbr:.0f} kbps")
            video.append(FormatRow(
                format_id=fmt["format_id"],
                quality=f"{height}p" if height else (fmt.get("format_note") or "vídeo"),
                fps=f"{fps:g}" if fps else "—",
                vcodec=_codec_label(vcodec, VCODEC_NAMES),
                acodec=_codec_label(acodec, ACODEC_NAMES),
                ext=fmt.get("ext") or "?",
                size=human_size(size),
                note=" · ".join(notes),
                height=height,
                video_only=acodec == "none",
            ))
        elif acodec != "none":
            audio.append(FormatRow(
                format_id=fmt["format_id"],
                quality=f"{tbr:.0f} kbps" if tbr else "áudio",
                fps="—",
                vcodec="—",
                acodec=_codec_label(acodec, ACODEC_NAMES),
                ext=fmt.get("ext") or "?",
                size=human_size(size),
                note=fmt.get("format_note") or "",
                audio_only=True,
            ))

    def vkey(row: FormatRow):
        codec_rank = {"AV1": 3, "VP9": 2, "HEVC": 2, "H.264": 1}.get(row.vcodec, 0)
        fps = float(row.fps) if row.fps not in ("—", "") else 0
        return (row.height, fps, codec_rank)

    video.sort(key=vkey, reverse=True)
    audio.sort(key=lambda r: float(r.quality.split()[0]) if r.quality[0].isdigit() else 0,
               reverse=True)

    # Mantém no máximo 3 variantes por resolução para a lista não virar sopa.
    trimmed, seen = [], {}
    for row in video:
        key = (row.height, row.fps)
        seen[key] = seen.get(key, 0) + 1
        if seen[key] <= 3:
            trimmed.append(row)

    return trimmed + audio[:6]
