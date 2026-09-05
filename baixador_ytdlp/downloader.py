"""Motor de download: monta a linha de comando do yt-dlp, executa e lê o progresso.

O progresso é lido por `--progress-template`, que emite campos separados por um
delimitador improvável em vez da barra colorida — parsing determinístico, sem regex
frágil em cima da saída humana.
"""
from __future__ import annotations

import shlex
import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import IS_WINDOWS, Settings
from .cookies import cookie_args
from .tools import CREATE_NO_WINDOW, Toolchain
from .diagnostics import log_event

SEP = "\x1f"  # unit separator: nunca aparece em título de vídeo
PROGRESS_TEMPLATE = (
    "download:" + SEP.join([
        "@P@", "%(progress.status)s", "%(progress.downloaded_bytes)s",
        "%(progress.total_bytes,progress.total_bytes_estimate)s",
        "%(progress.speed)s", "%(progress.eta)s",
        "%(info.playlist_index&{}|1)s", "%(info.n_entries&{}|1)s",
    ])
)
FILE_TEMPLATE = "after_move:@F@" + SEP + "%(filepath)s"

AUDIO_EXTS = {"mp3", "m4a", "opus", "flac", "wav", "vorbis", "alac"}


@dataclass
class DownloadOptions:
    url: str
    output_dir: str
    selector: str = "bv*+ba/b"      # seletor -f
    container: str = "mp4"          # mp4 | mkv | webm | original
    audio_only: bool = False
    audio_format: str = "mp3"
    playlist: bool = False
    title: str = ""
    section_start: str = ""         # "00:01:30" — vazio = do começo
    section_end: str = ""           # "00:04:00" — vazio = até o fim


@dataclass
class Progress:
    status: str = "queued"
    percent: float = 0.0
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0
    eta: int = 0
    index: int = 1
    count: int = 1
    stage: str = ""


class DownloadError(RuntimeError):
    pass


def build_args(opts: DownloadOptions, cfg: Settings, tc: Toolchain) -> list[str]:
    args: list[str] = [
        str(tc.ytdlp),
        "--ignore-config",
        "--ffmpeg-location", str(tc.bin_dir),
        "--no-colors", "--newline", "--progress", "--no-simulate",
        "--progress-template", PROGRESS_TEMPLATE,
        "--print", FILE_TEMPLATE,
        "--paths", opts.output_dir,
        "--output", cfg.filename_template,
        "--concurrent-fragments", str(max(1, cfg.concurrent_fragments)),
        "--retries", "10", "--fragment-retries", "10",
        "--no-overwrites", "--continue",
    ]
    if IS_WINDOWS:
        args.append("--windows-filenames")

    if opts.playlist:
        args += ["--yes-playlist"]
        args += ["--output", "%(playlist_title)s/%(playlist_index)03d - " + cfg.filename_template]
    else:
        args += ["--no-playlist"]

    if opts.audio_only:
        args += ["-f", "bestaudio/best", "-x",
                 "--audio-format", opts.audio_format, "--audio-quality", "0"]
    else:
        args += ["-f", opts.selector]
        if cfg.prefer_h264:
            args += ["-S", "vcodec:h264,res,fps,acodec:aac"]
        if opts.container in ("mp4", "mkv", "webm"):
            # --merge-output-format já resolve o caso vídeo+áudio separados.
            # --remux-video só entra para o arquivo único que veio em outro container:
            # o "container>container" faz o yt-dlp pular o remux quando já está certo.
            args += ["--merge-output-format", opts.container]
            args += ["--remux-video", f"{opts.container}>{opts.container}"]

    section = _section_range(opts)
    if section:
        # Recorte exige um único fluxo por vez; o yt-dlp baixa só o intervalo pedido.
        args += ["--download-sections", section, "--force-keyframes-at-cuts"]

    if cfg.embed_metadata:
        args.append("--embed-metadata")
    if cfg.embed_chapters:
        args.append("--embed-chapters")
    if cfg.embed_thumbnail and opts.container != "webm":
        args.append("--embed-thumbnail")
    if cfg.write_subs and not opts.audio_only:
        args += ["--write-subs", "--write-auto-subs", "--sub-langs", cfg.sub_langs]
        if cfg.embed_subs:
            args.append("--embed-subs")
    if cfg.sponsorblock:
        args += ["--sponsorblock-remove", "sponsor,selfpromo,interaction"]
    args += cookie_args(cfg)
    if cfg.extractor_args:
        args += ["--extractor-args", cfg.extractor_args]
    if cfg.limit_rate:
        args += ["--limit-rate", cfg.limit_rate]
    if cfg.proxy:
        args += ["--proxy", cfg.proxy]
    if cfg.archive_enabled:
        args += ["--download-archive", str(Path(opts.output_dir) / ".ytdl-archive.txt")]

    args.append(opts.url)
    return args


def _section_range(opts: DownloadOptions) -> str:
    """Monta o argumento de --download-sections a partir do intervalo escolhido."""
    start, end = opts.section_start.strip(), opts.section_end.strip()
    if not start and not end:
        return ""
    return f"*{start or '0'}-{end or 'inf'}"


def preview_command(opts: DownloadOptions, cfg: Settings, tc: Toolchain) -> str:
    """Linha de comando equivalente — útil para auditoria e para reproduzir no terminal."""
    return " ".join(shlex.quote(a) for a in build_args(opts, cfg, tc))


class DownloadRunner:
    """Executa um download e emite atualizações de progresso via callback."""

    def __init__(self, opts: DownloadOptions, cfg: Settings, tc: Toolchain):
        self.opts, self.cfg, self.tc = opts, cfg, tc
        self.files: list[Path] = []
        # deque com teto: o log de erro não cresce sem limite em playlist longa.
        self.log: deque[str] = deque(maxlen=300)
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self, on_progress: Callable[[Progress], None]) -> list[Path]:
        args = build_args(self.opts, self.cfg, self.tc)
        log_event("yt-dlp download iniciado: %s", preview_command(self.opts, self.cfg, self.tc))
        prog = Progress(status="downloading")
        self._proc = subprocess.Popen(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
            creationflags=CREATE_NO_WINDOW, env=self.tc.env(),
        )
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            line = line.rstrip("\r\n")
            if not line:
                continue
            if line.startswith("@P@" + SEP):
                self._apply_progress(line, prog)
                on_progress(prog)
            elif line.startswith("@F@" + SEP):
                path = Path(line.split(SEP, 1)[1].strip())
                if path.name:
                    self.files.append(path)
            else:
                self.log.append(line)
                stage = _stage_from_line(line)
                if stage:
                    prog.stage = stage
                    prog.status = "processing"
                    on_progress(prog)

        code = self._proc.wait()
        if self._cancelled.is_set():
            prog.status = "cancelled"
            on_progress(prog)
            return []
        if code != 0:
            log_event("yt-dlp download falhou (código=%s): %s", code, self.tail(300))
            raise DownloadError(self._last_error())

        prog.status = "finished"
        prog.percent = 100.0
        prog.stage = ""
        on_progress(prog)
        return self.files

    def _apply_progress(self, line: str, prog: Progress) -> None:
        parts = line.split(SEP)
        if len(parts) < 8:
            return
        _, status, downloaded, total, speed, eta, index, count = parts[:8]
        prog.status = status or prog.status
        prog.downloaded = _to_int(downloaded)
        prog.total = _to_int(total)
        prog.speed = _to_float(speed)
        prog.eta = _to_int(eta)
        prog.index = _to_int(index) or 1
        prog.count = _to_int(count) or 1
        prog.percent = (prog.downloaded * 100 / prog.total) if prog.total else 0.0
        prog.stage = ""

    def _last_error(self) -> str:
        for line in reversed(self.log):
            if line.startswith("ERROR"):
                return line.replace("ERROR: ", "")
        return self.log[-1] if self.log else "O yt-dlp terminou com erro."

    def tail(self, lines: int = 40) -> str:
        """Últimas linhas da saída — alimenta o botão 'Ver detalhes' na fila."""
        return "\n".join(list(self.log)[-lines:])


_STAGES = {
    "Merger": "Juntando vídeo e áudio…",
    "ExtractAudio": "Extraindo o áudio…",
    "VideoRemuxer": "Remuxando o container…",
    "EmbedThumbnail": "Embutindo a capa…",
    "Metadata": "Gravando metadados…",
    "SponsorBlock": "Consultando o SponsorBlock…",
    "ModifyChapters": "Removendo trechos patrocinados…",
    "subtitles": "Baixando legendas…",
    "SplitChapters": "Separando capítulos…",
}


def _stage_from_line(line: str) -> str:
    """Uma busca de dicionário por linha, em vez de varrer todos os prefixos."""
    if not line.startswith("["):
        return ""
    end = line.find("]")
    return _STAGES.get(line[1:end], "") if end > 1 else ""


def _to_int(value: str) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _to_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


# ------------------------------------------------------------- GPU encode
class Transcoder:
    """Reencoda via NVENC, AMD AMF ou VideoToolbox."""

    def __init__(self, tc: Toolchain, cfg: Settings):
        self.tc, self.cfg = tc, cfg
        self._proc: Optional[subprocess.Popen] = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()

    def duration(self, path: Path) -> float:
        try:
            out = subprocess.run(
                [str(self.tc.ffprobe), "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", str(path)],
                capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW,
            ).stdout.strip()
            return float(out)
        except Exception:
            return 0.0

    def build_args(self, src: Path, dst: Path, hwaccel: bool = True) -> list[str]:
        codec = self.cfg.transcode_codec
        args = [str(self.tc.ffmpeg), "-hide_banner", "-loglevel", "error", "-y"]
        is_nvenc = codec.endswith("_nvenc")
        is_amf = codec.endswith("_amf")
        is_videotoolbox = codec.endswith("_videotoolbox")
        if hwaccel and is_nvenc:
            args += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        elif hwaccel and is_videotoolbox:
            args += ["-hwaccel", "videotoolbox"]
        args += ["-i", str(src), "-c:v", codec]
        if is_nvenc:
            args += [
                "-preset", self.cfg.transcode_preset,
                "-rc", "vbr", "-cq", str(self.cfg.transcode_cq), "-b:v", "0",
            ]
        elif is_videotoolbox:
            quality = max(1, min(100, self.cfg.transcode_cq * 3))
            args += ["-q:v", str(quality), "-b:v", "0"]
        elif is_amf:
            # A codificação é feita na AMD. Não forçamos decodificação D3D11,
            # pois ela pode falhar com arquivos/driver específicos e não impede
            # que o AMF acelere a etapa mais cara: a codificação do vídeo.
            quality = max(1, min(51, self.cfg.transcode_cq))
            args += ["-quality", "balanced", "-rc", "cqp",
                     "-qp_i", str(quality), "-qp_p", str(quality)]
        else:
            raise DownloadError("O encoder acelerado selecionado não é suportado.")
        args += [
            "-c:a", "copy", "-c:s", "copy", "-map", "0",
            "-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(dst),
        ]
        return args

    def run(self, src: Path, on_progress: Callable[[float], None]) -> Path:
        total = self.duration(src)
        codec = self.cfg.transcode_codec
        suffix = {
            "h264_nvenc": "h264", "hevc_nvenc": "hevc", "av1_nvenc": "av1",
            "h264_videotoolbox": "h264", "hevc_videotoolbox": "hevc",
            "h264_amf": "h264", "hevc_amf": "hevc", "av1_amf": "av1",
        }
        dst = src.with_name(f"{src.stem} [{suffix.get(codec, 'acelerado')}]{src.suffix}")
        attempts = (True, False) if codec.endswith("_nvenc") else (True,)
        for attempt, hwaccel in enumerate(attempts):
            args = self.build_args(src, dst, hwaccel=hwaccel)
            self._proc = subprocess.Popen(
                args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", bufsize=1, creationflags=CREATE_NO_WINDOW,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                if line.startswith("out_time_us=") and total:
                    micros = _to_float(line.split("=", 1)[1])
                    on_progress(min(99.0, micros / 1_000_000 / total * 100))
            code = self._proc.wait()
            if code == 0:
                break
            if self._cancelled.is_set():
                dst.unlink(missing_ok=True)
                raise DownloadError("Conversão cancelada.")
            if attempt == len(attempts) - 1:
                err = (self._proc.stderr.read() if self._proc.stderr else "") or ""
                dst.unlink(missing_ok=True)
                raise DownloadError(f"Falha na conversão acelerada: {err.strip()[:300]}")
        on_progress(100.0)
        if self.cfg.transcode_replace:
            src.unlink(missing_ok=True)
            final = src
            dst.replace(final)
            return final
        return dst
