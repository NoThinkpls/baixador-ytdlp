"""Motor de download: monta a linha de comando do yt-dlp, executa e lê o progresso.

O progresso é lido por `--progress-template`, que emite campos separados por um
delimitador improvável em vez da barra colorida — parsing determinístico, sem regex
frágil em cima da saída humana.
"""
from __future__ import annotations

import re
import shlex
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable

from .config import IS_WINDOWS, Settings
from .cookies import cookie_args
from .processes import popen_isolated, terminate_process_tree
from .tools import CREATE_NO_WINDOW, Toolchain, decode_external_output, run_hidden
from .diagnostics import log_event
from .gpu import UPLOAD_FILTER, backend_of, device_args, quality_args
from .security import validate_media_url
from .sites import login_required_message, site_from_url

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
    transcribe_after: bool = False   # envia os arquivos concluídos para o Whisper
    embed_transcription: bool = False # incorpora a legenda como faixa, sem reencodar
    playlist_items: str = ""         # ex.: "1-3,7" — vazio = playlist inteira
    repeat_index: int = 0          # sufixo (2), (3)… em repetição confirmada
    media_duration: float = 0.0    # segundos, da análise; dá % a trecho sem fim definido
    section_selector: str = ""      # alternativa HLS equivalente para recortes


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


_RETRYABLE_FAILURES = (
    "timed out", "timeout", "connection reset", "connection aborted",
    "connection refused", "temporary failure", "temporarily unavailable",
    "network is unreachable", "name or service not known", "getaddrinfo",
    "urlopen error", "http error 408", "http error 429", "http error 500",
    "http error 502", "http error 503", "http error 504", "incomplete read",
    "unexpected eof", "remote end closed",
)
# SSL/TLS só como palavra: soltos, "tls" e "ssl" casavam com qualquer texto que
# os contivesse e faziam erros definitivos entrarem no ciclo de repetição.
_RETRYABLE_WORDS = re.compile(r"\b(?:ssl|tls)\b|ssleoferror|sslerror")


def is_retryable_error(message: str) -> bool:
    """Diz se uma nova execução tem chance real de resolver a falha.

    Erros de URL, permissão, conta, vídeo removido ou formato inexistente não
    entram nesta lista: repetir automaticamente esses casos só atrasa a fila e
    transmite a impressão errada de que o aplicativo está "travado".
    """
    text = (message or "").casefold()
    return (any(marker in text for marker in _RETRYABLE_FAILURES)
            or _RETRYABLE_WORDS.search(text) is not None)


def _output_template(opts: DownloadOptions, cfg: Settings) -> str:
    """Escolhe a nomenclatura final sem alterar a preferência base do usuário."""
    template = cfg.filename_template
    if opts.repeat_index >= 2:
        marker = ".%(ext)s"
        suffix = f" ({opts.repeat_index})"
        template = (template.replace(marker, suffix + marker, 1)
                    if marker in template else template + suffix)
    if opts.audio_only and cfg.organize_audio_by_uploader:
        # O próprio yt-dlp sanitiza o nome em cada sistema. A pasta vem antes do
        # template salvo, portanto o usuário ainda controla título, data e ID.
        return "%(uploader|Canal desconhecido)s/" + template
    return template


def build_args(
    opts: DownloadOptions,
    cfg: Settings,
    tc: Toolchain,
) -> list[str]:
    args: list[str] = [
        str(tc.ytdlp),
        "--ignore-config",
        # O executável standalone do yt-dlp pode seguir a página de código do
        # Windows ao escrever no pipe. Forçar UTF-8 impede nomes como "Mendon�a".
        "--encoding", "utf-8",
        "--ffmpeg-location", str(tc.bin_dir),
        "--no-colors", "--newline", "--progress", "--no-simulate",
        "--progress-template", PROGRESS_TEMPLATE,
        "--print", FILE_TEMPLATE,
        "--paths", opts.output_dir,
        "--output", _output_template(opts, cfg),
        "--concurrent-fragments", str(max(1, cfg.concurrent_fragments)),
        # Evita permanecer indefinidamente em "Iniciando" quando a conexão
        # aceita o processo, mas não entrega resposta alguma.
        "--socket-timeout", "30",
        # O yt-dlp lida com erros de fragmento; a fila aplica, além disso,
        # poucas novas execuções completas para quedas temporárias de rede.
        "--retries", "10", "--fragment-retries", "10", "--file-access-retries", "3",
        "--no-overwrites", "--continue",
    ]
    if IS_WINDOWS:
        args.append("--windows-filenames")
    if (site := site_from_url(opts.url)) and site.key == "facebook":
        # O título do Facebook começa com o contador ("122K views · 3.4K reactions | ").
        args += ["--replace-in-metadata", "title",
                 r"^[\d.,]+[KMB]? views?(?: · [\d.,]+[KMB]? reactions?)? \| ", ""]

    if opts.playlist:
        args += ["--yes-playlist"]
        items = opts.playlist_items.strip()
        if items and re.fullmatch(r"\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*", items):
            args += ["--playlist-items", items]
        args += ["--output", "%(playlist_title)s/%(playlist_index)03d - " + _output_template(opts, cfg)]
    else:
        args += ["--no-playlist"]

    if opts.audio_only:
        args += ["-f", "bestaudio/best", "-x",
                 "--audio-format", opts.audio_format, "--audio-quality", "0"]
    else:
        args += ["-f", opts.section_selector if _section_range(opts) and opts.section_selector
                 else opts.selector]
        # Uma única ordenação: dois -S seguidos deixam a prioridade ambígua.
        sort_keys: list[str] = []
        if _prefers_hls_section(opts):
            # Trecho no YouTube: o HLS é buscado por segmentos e chega a dezenas de
            # vezes o tempo real; o arquivo DASH comum sai numa conexão só, a ~2x.
            sort_keys.append("proto:m3u8")
        if cfg.prefer_h264:
            sort_keys.append("vcodec:h264,res,fps,acodec:aac")
        if sort_keys:
            args += ["-S", ",".join(sort_keys)]
        if opts.container in ("mp4", "mkv", "webm"):
            # --merge-output-format já resolve o caso vídeo+áudio separados.
            # --remux-video só entra para o arquivo único que veio em outro container:
            # o "container>container" faz o yt-dlp pular o remux quando já está certo.
            args += ["--merge-output-format", opts.container]
            args += ["--remux-video", f"{opts.container}>{opts.container}"]

    section = _section_range(opts)
    if section:
        # O downloader FFmpeg busca apenas o intervalo e copia os fluxos. Forçar
        # quadros-chave recodificaria todo o trecho, inclusive vídeos longos.
        args += ["--download-sections", section]
        if not opts.audio_only:
            # O FFmpeg usado como downloader não participa do progress-template
            # do yt-dlp. O canal -progress mantém a interface informada durante
            # recortes longos em vez de deixá-la parada em "Iniciando".
            args += ["--downloader-args", "ffmpeg_o:-progress pipe:1 -nostats"]

    if cfg.embed_metadata:
        args.append("--embed-metadata")
    if cfg.embed_chapters:
        args.append("--embed-chapters")
    if cfg.embed_thumbnail and (opts.audio_only or opts.container != "webm"):
        args.append("--embed-thumbnail")
        # Capas WebP nem sempre são aceitas por players e tags MP3. Converter
        # somente quando há capa a embutir deixa o áudio consistente sem custo
        # para quem optou por não baixar miniaturas.
        if opts.audio_only:
            args += ["--convert-thumbnails", "jpg"]
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
    # O histórico de IDs do yt-dlp não verifica se o arquivo ainda existe.
    # Um download solicitado de novo deve sempre chegar ao servidor.

    # ``--`` encerra as opções. Mesmo uma entrada malformada iniciada por hífen
    # nunca poderá virar --exec/--batch-file para o yt-dlp.
    args += ["--", validate_media_url(opts.url)]
    return args


def vp9_mp4_to_mkv(path: Path, tc: Toolchain) -> Path:
    """Troca o contêiner de um MP4 com vídeo VP9 por MKV, sem recodificar.

    Medido em 29/09/2026 no DaVinci Resolve: o mesmo VP9 1440p abre com partes
    "Media Offline" dentro do MP4 e abre inteiro em MKV (H.264 e AV1 em MP4 também
    abrem). Devolve o caminho novo, ou o original se não for o caso ou se falhar.
    """
    if path.suffix.lower() != ".mp4" or not path.is_file():
        return path
    try:
        probe = run_hidden([str(tc.ffprobe), "-v", "error", "-select_streams", "v:0",
                            "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                            str(path)], timeout=60)
        if probe.stdout.strip().split(",")[0] != "vp9":
            return path
        target = path.with_suffix(".mkv")
        for index in range(2, 10_000):
            if not target.exists():
                break
            target = path.with_name(f"{path.stem} ({index}).mkv")
        # Capa embutida (imagem anexada) não cabe como faixa de vídeo do MKV: fica de fora.
        result = run_hidden([
            str(tc.ffmpeg), "-hide_banner", "-loglevel", "error", "-y", "-i", str(path),
            "-map", "0:v:0", "-map", "0:a?", "-map", "0:s?", "-map_chapters", "0",
            "-c", "copy", "-c:s", "srt", str(target)], timeout=3600)
        if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
            target.unlink(missing_ok=True)
            log_event("Troca de MP4 para MKV falhou: %s", (result.stderr or "").strip()[-300:])
            return path
        path.unlink(missing_ok=True)
        log_event("VP9 em MP4 trocado para MKV: %s", target.name)
        return target
    except Exception as exc:  # noqa: BLE001 - o arquivo original continua válido
        log_event("Troca de MP4 para MKV falhou: %s", exc)
        return path


def _prefers_hls_section(opts: DownloadOptions) -> bool:
    """Trecho sem escolha explícita de formato, em vídeo do YouTube."""
    return (bool(_section_range(opts)) and not opts.audio_only
            and not opts.section_selector and opts.selector == "bv*+ba/b"
            and _is_youtube_url(opts.url))


def _is_youtube_url(url: str) -> bool:
    from urllib.parse import urlsplit

    host = (urlsplit(url).hostname or "").lower()
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def _section_range(opts: DownloadOptions) -> str:
    """Monta o argumento de --download-sections a partir do intervalo escolhido."""
    start, end = opts.section_start.strip(), opts.section_end.strip()
    if not start and not end:
        return ""
    return f"*{start or '0'}-{end or 'inf'}"


def _time_seconds(value: str) -> float:
    """Aceita segundos, mm:ss ou hh:mm:ss sem depender da localidade."""
    try:
        parts = [float(part) for part in value.strip().split(":")]
    except (TypeError, ValueError):
        return 0.0
    if not 1 <= len(parts) <= 3:
        return 0.0
    seconds = 0.0
    for part in parts:
        seconds = seconds * 60 + part
    return seconds


def _section_duration(opts: DownloadOptions) -> float:
    start = _time_seconds(opts.section_start) if opts.section_start.strip() else 0.0
    if opts.section_end.strip():
        end = _time_seconds(opts.section_end)
    elif opts.media_duration > 0:
        end = opts.media_duration  # "até o fim": usa a duração vinda da análise
    else:
        return 0.0
    return max(0.0, end - start)


def preview_command(
    opts: DownloadOptions,
    cfg: Settings,
    tc: Toolchain,
) -> str:
    """Linha de comando equivalente — útil para auditoria e para reproduzir no terminal."""
    return " ".join(
        shlex.quote(a) for a in build_args(opts, cfg, tc)
    )


class DownloadRunner:
    """Executa um download e emite atualizações de progresso via callback."""

    def __init__(self, opts: DownloadOptions, cfg: Settings, tc: Toolchain):
        self.opts, self.cfg, self.tc = opts, cfg, tc
        self.files: list[Path] = []
        # deque com teto: o log de erro não cresce sem limite em playlist longa.
        self.log: deque[str] = deque(maxlen=300)
        self._proc: subprocess.Popen | None = None
        self._cancelled = threading.Event()
        self._last_progress_emit = 0.0
        self._last_progress_state: tuple[str, str] | None = None
        # Vídeo e áudio separados (bv*+ba) passam duas vezes pelo FFmpeg no
        # recorte; sem isto a barra voltava a 0% no meio do trabalho.
        self._section_pass = 0
        self._section_elapsed = 0.0

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            terminate_process_tree(self._proc)

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def run(self, on_progress: Callable[[Progress], None]) -> list[Path]:
        # O clique em remover pode chegar antes de a thread realmente começar.
        # Nesse caso não devemos abrir um novo yt-dlp depois do cancelamento.
        if self._cancelled.is_set():
            return []

        return self._run_once(on_progress)

    def _run_once(
        self,
        on_progress: Callable[[Progress], None],
    ) -> list[Path]:
        if (message := login_required_message(self.opts.url)) and not cookie_args(self.cfg):
            raise DownloadError(message)
        args = build_args(self.opts, self.cfg, self.tc)
        log_event(
            "yt-dlp download iniciado%s: %s",
            " (recorte via FFmpeg)" if _section_range(self.opts) else "",
            preview_command(self.opts, self.cfg, self.tc),
        )
        prog = Progress(status="downloading")
        if _section_range(self.opts):
            prog.status = "processing"
            prog.stage = "Baixando e recortando com FFmpeg…"
        else:
            prog.stage = "Conectando ao servidor…"
        self._emit_progress(on_progress, prog, force=True)
        self._proc = popen_isolated(
            args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            # Ler bytes permite reconhecer de forma segura uma versão antiga
            # do yt-dlp que imprima na página de código do Windows.
            text=False, bufsize=0,
            env=self.tc.env(),
        )
        # Fecha a janela de corrida entre a verificação acima e a atribuição de
        # _proc: se o cancelamento aconteceu durante o Popen, encerra o processo
        # recém-criado antes de começar a leitura bloqueante de stdout.
        if self._cancelled.is_set():
            terminate_process_tree(self._proc)
            return []
        assert self._proc.stdout is not None
        for raw_line in self._proc.stdout:
            line = decode_external_output(raw_line).rstrip("\r\n")
            if not line:
                continue
            if line.startswith("@P@" + SEP):
                self._apply_progress(line, prog)
                self._emit_progress(on_progress, prog)
            elif line.startswith("@F@" + SEP):
                path = Path(line.split(SEP, 1)[1].strip())
                if path.name:
                    self.files.append(path)
            elif self._apply_ffmpeg_progress(line, prog):
                self._emit_progress(on_progress, prog)
            else:
                self.log.append(line)
                stage = _stage_from_line(line)
                if stage:
                    prog.stage = stage
                    prog.status = "processing"
                    self._emit_progress(on_progress, prog, force=True)

        code = self._proc.wait()
        self._proc = None
        if self._cancelled.is_set():
            prog.status = "cancelled"
            self._emit_progress(on_progress, prog, force=True)
            return []
        if code != 0:
            log_event("yt-dlp download falhou (código=%s): %s", code, self.tail(300))
            raise DownloadError(self._last_error())
        if not self.files:
            raise DownloadError(
                "O yt-dlp terminou sem informar um arquivo baixado. Confira os detalhes da tarefa."
            )

        prog.status = "finished"
        prog.percent = 100.0
        prog.stage = ""
        self._emit_progress(on_progress, prog, force=True)
        return self.files

    def _apply_ffmpeg_progress(self, line: str, prog: Progress) -> bool:
        """Converte ``-progress pipe:1`` do FFmpeg em avanço do recorte."""
        key, separator, value = line.partition("=")
        if not separator or key not in _FFMPEG_PROGRESS_KEYS:
            return False
        prog.status = "processing"
        prog.stage = prog.stage or "Processando o trecho com FFmpeg…"
        duration = _section_duration(self.opts)
        if key == "out_time_us":
            elapsed = _to_float(value) / 1_000_000
        elif key == "out_time":
            elapsed = _time_seconds(value)
        else:
            return True
        if not duration or elapsed < 0:
            return True
        if elapsed + 1.0 < self._section_elapsed:
            self._section_pass += 1  # nova execução do FFmpeg (a faixa de áudio)
        self._section_elapsed = elapsed
        fraction = min(1.0, elapsed / duration)
        split = "+" in self.opts.selector and not self.opts.audio_only
        if not split:
            percent = fraction * 100
        elif self._section_pass == 0:
            percent = fraction * 85  # o vídeo é quase todo o trabalho
        else:
            percent = 85 + fraction * 14
        prog.percent = min(99.0, max(prog.percent if self._section_pass else 0.0, percent))
        return True

    def _emit_progress(
        self,
        on_progress: Callable[[Progress], None],
        prog: Progress,
        *,
        force: bool = False,
    ) -> None:
        """Limita repaints sem esconder transições importantes de estado.

        O yt-dlp pode produzir dezenas de linhas por segundo. Enfileirar todas
        como sinais Qt consome CPU e deixa a interface atrasada, principalmente
        quando há downloads paralelos. O último estado continua chegando em no
        máximo 120 ms e toda mudança de etapa chega imediatamente.
        """
        now = time.monotonic()
        state = (prog.status, prog.stage)
        if (not force and state == self._last_progress_state
                and now - self._last_progress_emit < 0.12):
            return
        self._last_progress_emit = now
        self._last_progress_state = state
        # O callback pode cruzar threads; a cópia impede que a UI veja um
        # objeto alterado novamente antes de processar o sinal enfileirado.
        on_progress(Progress(**vars(prog)))

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
        from .probe import friendly_error

        for line in reversed(self.log):
            if line.startswith("ERROR"):
                return friendly_error(line)
        return friendly_error(self.log[-1]) if self.log else "O yt-dlp terminou com erro."

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

_FFMPEG_PROGRESS_KEYS = frozenset({
    "frame", "fps", "stream_0_0_q", "bitrate", "total_size", "out_time_us",
    "out_time_ms", "out_time", "dup_frames", "drop_frames", "speed", "progress",
})


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
    """Reencoda via NVENC, AMD AMF, Intel Quick Sync, VAAPI ou VideoToolbox."""

    def __init__(self, tc: Toolchain, cfg: Settings):
        self.tc, self.cfg = tc, cfg
        self._proc: subprocess.Popen | None = None
        self._cancelled = threading.Event()

    def cancel(self) -> None:
        self._cancelled.set()
        if self._proc and self._proc.poll() is None:
            terminate_process_tree(self._proc)

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
        backend = backend_of(codec)
        is_nvenc = backend == "nvenc"
        is_amf = backend == "amf"
        is_videotoolbox = backend == "videotoolbox"
        is_qsv = backend == "qsv"
        is_vaapi = backend == "vaapi"
        if hwaccel and is_nvenc:
            args += ["-hwaccel", "cuda", "-hwaccel_output_format", "cuda"]
        elif hwaccel and is_videotoolbox:
            args += ["-hwaccel", "videotoolbox"]
        elif hwaccel and is_qsv:
            # Decodifica na iGPU/Arc; os quadros voltam à memória e o encoder QSV os recebe.
            args += ["-hwaccel", "qsv"]
        elif is_vaapi:
            args += device_args(codec)
            if hwaccel:
                # Decodificar e codificar na GPU, sem passar os quadros pela CPU.
                args += ["-hwaccel", "vaapi", "-hwaccel_output_format", "vaapi"]
        args += ["-i", str(src)]
        if is_vaapi and not hwaccel:
            args += ["-vf", UPLOAD_FILTER]   # sem decodificação por GPU, os quadros sobem aqui
        args += ["-c:v", codec]
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
        elif is_qsv or is_vaapi:
            args += quality_args(codec, max(1, min(51, self.cfg.transcode_cq)))
        else:
            raise DownloadError("O encoder acelerado selecionado não é suportado.")
        # Containers MP4 rejeitam PGS/ASS/WebVTT, anexos e streams de dados.
        # O vídeo e o áudio são sempre preservados; MKV também mantém legendas.
        args += ["-map", "0:v?", "-map", "0:a?", "-c:a", "copy"]
        if dst.suffix.casefold() == ".mkv":
            args += ["-map", "0:s?", "-c:s", "copy"]
        args += ["-map", "-0:d?", "-map", "-0:t?"]
        if dst.suffix.casefold() in {".mp4", ".mov", ".m4v"}:
            args += ["-movflags", "+faststart"]
        args += ["-progress", "pipe:1", "-nostats", str(dst)]
        return args

    def _has_video(self, path: Path) -> bool:
        try:
            result = subprocess.run(
                [str(self.tc.ffprobe), "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=30, creationflags=CREATE_NO_WINDOW,
            )
            return result.returncode == 0 and result.stdout.strip() == "video"
        except Exception:
            return False

    def run(self, src: Path, on_progress: Callable[[float], None]) -> Path:
        total = self.duration(src)
        codec = self.cfg.transcode_codec
        suffix = {
            "h264_nvenc": "h264", "hevc_nvenc": "hevc", "av1_nvenc": "av1",
            "h264_videotoolbox": "h264", "hevc_videotoolbox": "hevc",
            "h264_amf": "h264", "hevc_amf": "hevc", "av1_amf": "av1",
            "h264_qsv": "h264", "hevc_qsv": "hevc", "av1_qsv": "av1",
            "h264_vaapi": "h264", "hevc_vaapi": "hevc", "av1_vaapi": "av1",
        }
        dst = src.with_name(f"{src.stem} [{suffix.get(codec, 'acelerado')}]{src.suffix}")
        # NVENC, QSV e VAAPI tentam primeiro com decodificação por GPU e repetem sem ela.
        attempts = (True, False) if backend_of(codec) in {"nvenc", "qsv", "vaapi"} else (True,)
        for attempt, hwaccel in enumerate(attempts):
            if self._cancelled.is_set():
                raise DownloadError("Conversão cancelada.")
            args = self.build_args(src, dst, hwaccel=hwaccel)
            self._proc = popen_isolated(
                # Mesclar stderr evita o deadlock clássico: o FFmpeg pode
                # encher a pipe de erro antes de o processo principal chegar a
                # lê-la. Mantemos somente o final para a mensagem ao usuário.
                args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=False,
                bufsize=0,
            )
            if self._cancelled.is_set():
                terminate_process_tree(self._proc)
            assert self._proc.stdout is not None
            errors: deque[str] = deque(maxlen=40)
            for raw_line in self._proc.stdout:
                line = decode_external_output(raw_line).rstrip("\r\n")
                if line.startswith("out_time_us=") and total:
                    micros = _to_float(line.split("=", 1)[1])
                    on_progress(min(99.0, micros / 1_000_000 / total * 100))
                elif line:
                    errors.append(line)
            code = self._proc.wait()
            self._proc = None
            if code == 0:
                break
            if self._cancelled.is_set():
                dst.unlink(missing_ok=True)
                raise DownloadError("Conversão cancelada.")
            if attempt == len(attempts) - 1:
                from .probe import friendly_error

                err = "\n".join(errors)
                dst.unlink(missing_ok=True)
                raise DownloadError(
                    f"Falha na conversão acelerada: {friendly_error(err.strip()[:300])}")
        on_progress(100.0)
        output_duration = self.duration(dst)
        tolerance = max(1.0, total * 0.02)
        if (not dst.is_file() or not self._has_video(dst) or output_duration <= 0
                or (total > 0 and abs(output_duration - total) > tolerance)):
            raise DownloadError(
                "A conversão terminou, mas o arquivo resultante não passou na validação. "
                "O original foi preservado."
            )
        if self.cfg.transcode_replace:
            try:
                from send2trash import send2trash
                send2trash(str(src))
            except Exception as exc:
                raise DownloadError(
                    "A conversão foi validada, mas o original não pôde ser enviado à Lixeira; "
                    f"os dois arquivos foram preservados ({exc})."
                ) from exc
            final = src
            dst.replace(final)
            return final
        return dst
