"""Análise da mídia: roda `yt-dlp -J` e transforma os formatos em linhas legíveis."""
from __future__ import annotations

import json
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path

from .cookies import is_cookie_source_failure
from .processes import popen_isolated, terminate_process_tree
from .tools import decode_external_output
from .diagnostics import log_event
from .security import validate_media_url
from .ui.i18n import tr
import contextlib

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


def human_size(num: float | None) -> str:
    if not num:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.0f} {unit}" if unit in ("B", "KB") else f"{num:.2f} {unit}"
        num /= 1024
    return f"{num:.2f} TB"


def human_duration(seconds: float | None) -> str:
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
    estimated_size: int = 0
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
    audio_languages: list[str] = field(default_factory=list)
    subtitles: list[str] = field(default_factory=list)
    auto_subtitles: list[str] = field(default_factory=list)
    # Itens já listados na contagem da playlist; o seletor usa sem nova chamada.
    entries: list = field(default_factory=list)
    chapters: list[dict] = field(default_factory=list)

    @property
    def best_label(self) -> str:
        for row in self.rows:
            if not row.audio_only:
                return row.quality
        return "melhor disponível"

    @property
    def video_count(self) -> int:
        return sum(1 for row in self.rows if not row.audio_only)


class ProbeError(RuntimeError):
    def __init__(self, message: str, raw: str = ""):
        super().__init__(message)
        self.raw = raw  # stderr original, para decidir uma nova tentativa


@dataclass
class _Completed:
    """Resultado do subprocesso, no mesmo formato que subprocess.run devolvia."""
    returncode: int
    stdout: str
    stderr: str


# Processos de análise em andamento. Fechar o aplicativo precisa poder matá-los:
# uma QThread destruída enquanto ainda roda faz o Qt chamar qFatal, e o processo
# morre com fast-fail (0xc0000409) sem chance de gravar nada.
_RUNNING: set[subprocess.Popen] = set()
_RUNNING_LOCK = threading.Lock()


def _kill_tree(proc: subprocess.Popen) -> None:
    """Mata o processo E os filhos dele.

    Matar só o yt-dlp não basta: os filhos que ele criou (ffmpeg, deno) herdam as
    pipes de saída e as mantêm abertas, então o communicate() do pai continua
    bloqueado esperando um EOF que nunca chega. O aplicativo travava no
    fechamento em vez de encerrar.
    """
    terminate_process_tree(proc)


def _popen(args: list[str], env: dict | None) -> subprocess.Popen:
    """Popen com o grupo de processos isolado, para o kill alcançar os filhos."""
    return popen_isolated(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=False,
        env=env,
    )


def _drain(proc: subprocess.Popen) -> None:
    """Espera o processo morto liberar as pipes, sem bloquear para sempre."""
    with contextlib.suppress(subprocess.TimeoutExpired, ValueError, OSError):
        proc.communicate(timeout=5)


def kill_running() -> None:
    """Encerra as análises em andamento. Chamado ao fechar a janela."""
    with _RUNNING_LOCK:
        processes = list(_RUNNING)
    for proc in processes:
        _kill_tree(proc)


def _run_json(args: list[str], timeout: int, env: dict | None = None) -> dict:
    log_event("yt-dlp análise: %s", " ".join(args))
    proc = _popen(args, env)
    with _RUNNING_LOCK:
        _RUNNING.add(proc)
    try:
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            _kill_tree(proc)
            _drain(proc)
            raise ProbeError("A análise demorou demais. Verifique a conexão ou o link.") from exc
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(proc)

    proc = _Completed(proc.returncode, decode_external_output(out), decode_external_output(err))

    if proc.returncode != 0 or not proc.stdout.strip():
        log_event("yt-dlp análise falhou (código=%s): %s", proc.returncode,
                  (proc.stderr or "sem saída de erro")[-8000:])
        msg = (proc.stderr or "").strip().splitlines()
        detail = msg[-1] if msg else "erro desconhecido"
        raise ProbeError(friendly_error(detail), proc.stderr or "")

    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProbeError("Resposta inválida do yt-dlp.") from exc


def _cookie_args(cookies_browser: str, cookies_file: str) -> list[str]:
    if cookies_file and Path(cookies_file).is_file():
        return ["--cookies", cookies_file]
    if cookies_browser:
        return ["--cookies-from-browser", cookies_browser]
    return []


_COOKIE_FALLBACK_NOTE = (
    "\n\nOs cookies do navegador escolhido não puderam ser lidos (o Chrome e o Edge "
    "no Windows não liberam mais os cookies para outros programas). A análise seguiu "
    "sem cookies. Use o Firefox ou um arquivo cookies.txt em Configurações.")


def _flat_entries(data: dict) -> list[PlaylistEntry]:
    result: list[PlaylistEntry] = []
    for position, entry in enumerate(data.get("entries") or [], start=1):
        if not isinstance(entry, dict):
            continue
        result.append(PlaylistEntry(
            index=position,
            title=str(entry.get("title") or entry.get("id") or f"Item {position}"),
            duration=human_duration(entry.get("duration")),
            entry_id=str(entry.get("id") or ""),
        ))
    return result


def _playlist_count(ytdlp: Path, base: list[str], url: str, timeout: int,
                    env: dict | None = None) -> tuple[int, list[PlaylistEntry]]:
    """Conta e lista os itens com --flat-playlist numa única requisição."""
    try:
        data = _run_json(base + ["-J", "--flat-playlist", "--", url], timeout, env)
    except ProbeError:
        return 0, []
    entries = _flat_entries(data)
    for key in ("playlist_count", "n_entries"):
        if isinstance(data.get(key), int):
            return data[key], entries
    return len(entries), entries


@dataclass
class PlaylistEntry:
    index: int          # posição 1-based, a mesma que o --playlist-items usa
    title: str
    duration: str
    entry_id: str


def compress_indices(indices: list[int]) -> str:
    """[1,2,3,5,8,9] → ``1-3,5,8-9`` (formato do --playlist-items)."""
    values = sorted(set(i for i in indices if i > 0))
    parts: list[str] = []
    start = previous = None
    for value in values:
        if start is None:
            start = previous = value
        elif value == previous + 1:
            previous = value
        else:
            parts.append(f"{start}-{previous}" if start != previous else str(start))
            start = previous = value
    if start is not None:
        parts.append(f"{start}-{previous}" if start != previous else str(start))
    return ",".join(parts)


def playlist_entries(url: str, ytdlp: Path, cookies_browser: str = "", cookies_file: str = "",
                     proxy: str = "", extractor_args: str = "", timeout: int = 180,
                     env: dict | None = None) -> list[PlaylistEntry]:
    """Lista os itens com --flat-playlist (uma requisição, sem formatos de cada vídeo)."""
    try:
        url = validate_media_url(url)
    except ValueError as exc:
        raise ProbeError(str(exc)) from exc
    args = [str(ytdlp), "--no-warnings", "--ignore-config", "--encoding", "utf-8",
            "--socket-timeout", "20"]
    if proxy:
        args += ["--proxy", proxy]
    if extractor_args:
        args += ["--extractor-args", extractor_args]
    args += _cookie_args(cookies_browser, cookies_file)
    data = _run_json(args + ["-J", "--flat-playlist", "--", url], timeout, env)
    return _flat_entries(data)


def probe(url: str, ytdlp: Path, cookies_browser: str = "", cookies_file: str = "",
          proxy: str = "", timeout: int = 120, extractor_args: str = "",
          env: dict | None = None) -> MediaInfo:
    try:
        url = validate_media_url(url)
    except ValueError as exc:
        raise ProbeError(str(exc)) from exc
    common = [str(ytdlp), "--no-warnings", "--ignore-config", "--encoding", "utf-8",
              "--socket-timeout", "20"]
    if proxy:
        common += ["--proxy", proxy]
    if extractor_args:
        common += ["--extractor-args", extractor_args]

    cookies = _cookie_args(cookies_browser, cookies_file)
    base, note = common + cookies, ""

    # --playlist-items 1: a análise extrai os formatos de UM vídeo, não dos N da
    # playlist. Sem isso, uma playlist de 200 itens levava minutos e centenas de
    # requisições só para montar a tabela de qualidades do primeiro vídeo.
    request = ["-J", "--playlist-items", "1", "--", url]
    try:
        data = _run_json(base + request, timeout, env)
    except ProbeError as exc:
        # Antes havia um --simulate extra só para testar os cookies, dobrando o
        # tempo de toda análise. Agora a análise vai direto e só repete sem
        # cookies quando a falha foi ler o navegador (App-Bound Encryption).
        if not cookies or not is_cookie_source_failure(exc.raw):
            raise
        log_event("Fonte de cookies indisponível, seguindo sem cookies: %s", exc.raw.strip()[-400:])
        base, note = common, _COOKIE_FALLBACK_NOTE
        try:
            data = _run_json(base + request, timeout, env)
        except ProbeError as retry:
            raise ProbeError(f"{retry}{note}", retry.raw) from retry

    is_playlist = data.get("_type") == "playlist"
    count = 0
    flat: list[PlaylistEntry] = []
    entry = data
    if is_playlist:
        entries = [e for e in (data.get("entries") or []) if e]
        if not entries:
            raise ProbeError("A playlist não retornou nenhum vídeo.")
        entry = entries[0]
        count = next((data[k] for k in ("playlist_count", "n_entries")
                      if isinstance(data.get(k), int) and data[k] > 1), 0)
        if count <= 1:
            count, flat = _playlist_count(ytdlp, base, url, timeout, env)
            count = count or len(entries)

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
        audio_languages=_audio_languages(entry),
        subtitles=_caption_languages(entry.get("subtitles")),
        auto_subtitles=_caption_languages(entry.get("automatic_captions")),
        entries=flat,
        chapters=[chapter for chapter in (entry.get("chapters") or [])
                  if isinstance(chapter, dict)
                  and isinstance(chapter.get("start_time"), (int, float))
                  and isinstance(chapter.get("end_time"), (int, float))
                  and chapter["end_time"] > chapter["start_time"]],
    )


def friendly_error(detail: str) -> str:
    return tr(_friendly_error_pt(detail))


def _friendly_error_pt(detail: str) -> str:
    """Traduz o erro do yt-dlp para uma instrução que resolve o problema.

    A versão anterior mandava "ative os cookies do navegador" para qualquer erro
    que contivesse a palavra cookie — inclusive para o erro de bot do YouTube.
    Seguindo esse conselho no Windows, o usuário escolhia Chrome ou Edge e caía
    no erro de DPAPI. O aplicativo empurrava para o caminho quebrado.
    """
    low = detail.lower()

    # Falhas do disco e do sistema de arquivos valem para qualquer etapa (yt-dlp, FFmpeg,
    # conversão), por isso vêm antes das mensagens específicas de site.
    if any(marker in low for marker in (
            "no space left on device", "not enough space on the disk", "disk full",
            "winerror 112", "errno 28", "espaço insuficiente", "não há espaço")):
        return ("O disco ou a pasta de destino está sem espaço. Libere espaço ou escolha outra "
                "pasta em Configurações e tente de novo.")

    if any(marker in low for marker in (
            "file name too long", "filename too long", "path too long", "winerror 206",
            "errno 36", "the filename or extension is too long")):
        return ("O caminho do arquivo ficou longo demais para o sistema. Escolha uma pasta mais "
                "curta ou simplifique o modelo do nome do arquivo em Configurações.")

    if "permission denied" in low or "access is denied" in low or "winerror 5" in low:
        return ("Sem permissão para gravar na pasta de destino. Escolha outra pasta ou feche o "
                "programa que está usando o arquivo.")

    # FFmpeg: o yt-dlp repassa "ffmpeg exited with code N" com o código de saída sem sinal;
    # 3199971767 (0xBEBBB1B7) é o AVERROR_INVALIDDATA do FFmpeg.
    if ("invalid data found when processing input" in low or "moov atom not found" in low
            or re.search(r"ffmpeg exited with code (3199971767|-1094995529)", low)):
        return ("O FFmpeg encontrou dados inválidos no arquivo (parte danificada ou download "
                "incompleto). Baixe de novo ou escolha outro formato.")

    # Ferramentas de mídia num arquivo sem a faixa que precisam (vídeo num MP3, por exemplo).
    if "matches no streams" in low or "does not contain any stream" in low:
        return ("Este arquivo não tem a faixa que a ferramenta precisa (por exemplo, imagem em "
                "um arquivo só de áudio). Escolha outro arquivo ou outra ferramenta.")

    code = re.search(r"ffmpeg exited with code (-?\d+)", low)
    if code:
        return (f"O FFmpeg terminou com erro (código {code.group(1)}). Tente de novo; se repetir, "
                "exporte o diagnóstico em Configurações e anexe a uma issue.")

    if "dpapi" in low or ("decrypt" in low and "cookie" in low):
        return ("Não foi possível ler os cookies do Chrome ou do Edge. Desde o Chrome 127 "
                "esses navegadores criptografam os cookies de um jeito que só o próprio "
                "navegador consegue abrir, e isso não tem solução do lado do yt-dlp. "
                "Em Configurações, use o Firefox ou aponte um arquivo cookies.txt.")

    if "page needs to be reloaded" in low:
        return ("O YouTube exigiu um desafio JavaScript que o yt-dlp não conseguiu resolver. "
                "Isso acontece quando falta o runtime JavaScript (Deno) — apesar da mensagem, "
                "não é problema de cookies. Vá em Configurações → Dependências → Verificar "
                "agora para instalá-lo.")

    # Idade vem antes do robô: a mensagem do YouTube para vídeo com restrição de
    # idade também começa com "Sign in to confirm".
    if any(marker in low for marker in (
            "confirm your age", "age-restricted", "age restricted",
            "inappropriate for some users")):
        return "Vídeo com restrição de idade. É preciso fornecer cookies de uma conta logada."

    if "not a bot" in low or "sign in to confirm" in low:
        return ("O YouTube pediu confirmação de que você não é um robô. É preciso fornecer "
                "cookies de uma conta logada: em Configurações, aponte um arquivo cookies.txt "
                "exportado por uma janela anônima, ou selecione o Firefox.")

    if "private" in low or "members-only" in low or "join this channel" in low:
        return "Vídeo privado ou exclusivo para membros. Só com cookies de uma conta com acesso."

    if "unsupported url" in low:
        return "Esse site não é suportado pelo yt-dlp."

    # Antes de "unavailable": a mensagem de bloqueio regional começa com
    # "Video unavailable" e virava "removido".
    if ("geo" in low and "restrict" in low) or "in your country" in low:
        return "Vídeo bloqueado na sua região. Um proxy em outro país resolveria."

    if "live event will begin" in low:
        return "A transmissão ainda não começou. Tente novamente quando o evento estiver ao vivo."

    if "http error 429" in low or "too many requests" in low:
        return ("O YouTube limitou as requisições deste IP. Espere alguns minutos antes de "
                "tentar de novo, ou configure um proxy.")

    if ("temporarily unavailable" in low or "service unavailable" in low
            or any(f"http error {code}" in low for code in (500, 502, 503, 504))):
        return "O site está instável ou fora do ar agora. Tente novamente em alguns minutos."

    if "http error 403" in low:
        return ("O site recusou o acesso (HTTP 403). Verifique os componentes em "
                "Configurações e tente novamente; cookies só são necessários se o site "
                "pedir login ou confirmar que você não é um robô.")

    if "requested format is not available" in low:
        return "O formato escolhido não existe para este vídeo. Selecione Automático e tente novamente."

    if "unavailable" in low or "has been removed" in low or "terminated" in low:
        return "O vídeo está indisponível, foi removido ou o canal foi encerrado."

    if "urlopen error" in low or "getaddrinfo" in low or "connection" in low:
        return "Sem conexão com a internet, ou a rede bloqueou o acesso."

    return detail.replace("ERROR: ", "")


def playlist_selector(row: FormatRow) -> str:
    """Traduz uma escolha do primeiro item em atributos válidos para toda a playlist."""
    if row.audio_only:
        return "bestaudio/best"
    height = max(1, int(row.height or 1080))
    return f"bv*[height<={height}]+ba/b[height<={height}]/bv*+ba/b"


def hls_section_selector(info: MediaInfo, row: FormatRow) -> str:
    """Encontra o fluxo HLS equivalente ao formato escolhido, quando existir."""
    formats = info.raw.get("formats") or []
    selected = next((fmt for fmt in formats
                     if str(fmt.get("format_id")) == row.format_id), None)
    if not selected or row.audio_only:
        return ""
    has_hls_audio = any(
        str(fmt.get("protocol", "")).startswith("m3u8")
        and fmt.get("acodec") not in (None, "none")
        and fmt.get("vcodec") in (None, "none")
        for fmt in formats
    )
    if not has_hls_audio:
        return ""
    codec = str(selected.get("vcodec") or "").split(".", 1)[0]
    candidates = [fmt for fmt in formats
                  if str(fmt.get("protocol", "")).startswith("m3u8")
                  and fmt.get("height") == selected.get("height")
                  and fmt.get("fps") == selected.get("fps")
                  and fmt.get("dynamic_range") == selected.get("dynamic_range")
                  and str(fmt.get("vcodec") or "").split(".", 1)[0] == codec]
    if not candidates:
        return ""
    original_rate = float(selected.get("tbr") or 0)
    match = min(candidates, key=lambda fmt: abs(float(fmt.get("tbr") or 0) - original_rate))
    return f"{match['format_id']}+ba[protocol=m3u8_native]/{row.selector}"


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
                estimated_size=int(size or 0),
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
                estimated_size=int(size or 0),
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


def _caption_languages(source: object) -> list[str]:
    """Converte o mapa cru do yt-dlp numa lista curta, estável e exibível."""
    if not isinstance(source, dict):
        return []
    return sorted(
        {str(language).strip() for language, formats in source.items()
         if language and isinstance(formats, list) and formats},
        key=str.casefold,
    )


def _audio_languages(info: dict) -> list[str]:
    languages: set[str] = set()
    for fmt in info.get("formats") or []:
        if (fmt.get("acodec") or "none") == "none":
            continue
        language = str(fmt.get("language") or "").strip()
        if language and language.casefold() not in {"und", "none"}:
            languages.add(language)
    # Alguns extratores não colocam idioma por formato, mas informam o original.
    fallback = str(info.get("language") or "").strip()
    if not languages and fallback and fallback.casefold() not in {"und", "none"}:
        languages.add(fallback)
    return sorted(languages, key=str.casefold)
