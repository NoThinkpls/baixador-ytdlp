"""Análise da mídia: roda `yt-dlp -J` e transforma os formatos em linhas legíveis."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import IS_WINDOWS
from .cookies import is_cookie_source_failure
from .tools import CREATE_NO_WINDOW
from .diagnostics import log_event

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
    if proc.poll() is not None:
        return
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                           capture_output=True, timeout=10,
                           creationflags=CREATE_NO_WINDOW)
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        try:
            proc.kill()
        except OSError:
            pass


def _popen(args: list[str], env: dict | None) -> subprocess.Popen:
    """Popen com o grupo de processos isolado, para o kill alcançar os filhos."""
    extra = {} if IS_WINDOWS else {"start_new_session": True}
    return subprocess.Popen(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        creationflags=CREATE_NO_WINDOW, env=env, **extra,
    )


def _drain(proc: subprocess.Popen) -> None:
    """Espera o processo morto liberar as pipes, sem bloquear para sempre."""
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass


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

    proc = _Completed(proc.returncode, out, err)

    if proc.returncode != 0 or not proc.stdout.strip():
        log_event("yt-dlp análise falhou (código=%s): %s", proc.returncode,
                  (proc.stderr or "sem saída de erro")[-8000:])
        msg = (proc.stderr or "").strip().splitlines()
        detail = msg[-1] if msg else "erro desconhecido"
        raise ProbeError(_friendly(detail))

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


def _resolve_cookies(common: list[str], cookies: list[str], url: str,
                     timeout: int, env: dict | None = None) -> tuple[list[str], str]:
    """Confere se a fonte de cookies funciona antes de usá-la na análise real.

    O Chrome e o Edge no Windows não entregam mais os cookies para processos
    externos (App-Bound Encryption). Sem esta checagem, a análise inteira morria
    com "Failed to decrypt with DPAPI" — um erro sobre o navegador, exibido como
    se fosse um erro do vídeo. Agora a falha de leitura degrada para "sem
    cookies" e o motivo vai junto da mensagem final.
    """
    if not cookies:
        return common, ""
    probe_args = common + cookies + ["--simulate", "--skip-download",
                                     "--playlist-items", "1", "--quiet", url]
    proc = _popen(probe_args, env)
    with _RUNNING_LOCK:
        _RUNNING.add(proc)
    try:
        try:
            _, stderr = proc.communicate(timeout=min(timeout, 45))
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            _drain(proc)
            return common + cookies, ""
    finally:
        with _RUNNING_LOCK:
            _RUNNING.discard(proc)

    if proc.returncode == 0 or not is_cookie_source_failure(stderr or ""):
        return common + cookies, ""

    log_event("Fonte de cookies indisponível, seguindo sem cookies: %s",
              (stderr or "").strip()[-400:])
    return common, ("\n\nOs cookies do navegador escolhido não puderam ser lidos "
                    "(o Chrome e o Edge no Windows não liberam mais os cookies para "
                    "outros programas). A análise seguiu sem cookies. Use o Firefox "
                    "ou um arquivo cookies.txt em Configurações.")


def _playlist_count(ytdlp: Path, base: list[str], url: str, timeout: int,
                    env: dict | None = None) -> int:
    """Conta os itens com --flat-playlist: uma requisição, sem extrair formato de cada vídeo."""
    try:
        data = _run_json(base + ["-J", "--flat-playlist", url], timeout, env)
    except ProbeError:
        return 0
    for key in ("playlist_count", "n_entries"):
        if isinstance(data.get(key), int):
            return data[key]
    return len([e for e in (data.get("entries") or []) if e])


def probe(url: str, ytdlp: Path, cookies_browser: str = "", cookies_file: str = "",
          proxy: str = "", timeout: int = 120, extractor_args: str = "",
          env: dict | None = None) -> MediaInfo:
    common = [str(ytdlp), "--no-warnings", "--ignore-config", "--socket-timeout", "20"]
    if proxy:
        common += ["--proxy", proxy]
    if extractor_args:
        common += ["--extractor-args", extractor_args]

    cookies = _cookie_args(cookies_browser, cookies_file)
    base, note = _resolve_cookies(common, cookies, url, timeout, env)

    # --playlist-items 1: a análise extrai os formatos de UM vídeo, não dos N da
    # playlist. Sem isso, uma playlist de 200 itens levava minutos e centenas de
    # requisições só para montar a tabela de qualidades do primeiro vídeo.
    try:
        data = _run_json(base + ["-J", "--playlist-items", "1", url], timeout, env)
    except ProbeError as exc:
        raise ProbeError(f"{exc}{note}") from exc

    is_playlist = data.get("_type") == "playlist"
    count = 0
    entry = data
    if is_playlist:
        entries = [e for e in (data.get("entries") or []) if e]
        if not entries:
            raise ProbeError("A playlist não retornou nenhum vídeo.")
        entry = entries[0]
        count = next((data[k] for k in ("playlist_count", "n_entries")
                      if isinstance(data.get(k), int) and data[k] > 1), 0)
        if count <= 1:
            count = _playlist_count(ytdlp, base, url, timeout, env) or len(entries)

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
    """Traduz o erro do yt-dlp para uma instrução que resolve o problema.

    A versão anterior mandava "ative os cookies do navegador" para qualquer erro
    que contivesse a palavra cookie — inclusive para o erro de bot do YouTube.
    Seguindo esse conselho no Windows, o usuário escolhia Chrome ou Edge e caía
    no erro de DPAPI. O aplicativo empurrava para o caminho quebrado.
    """
    low = detail.lower()

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

    if "sign in to confirm" in low or "not a bot" in low:
        return ("O YouTube pediu confirmação de que você não é um robô. É preciso fornecer "
                "cookies de uma conta logada: em Configurações, aponte um arquivo cookies.txt "
                "exportado por uma janela anônima, ou selecione o Firefox.")

    if "age" in low and ("restrict" in low or "confirm" in low):
        return "Vídeo com restrição de idade. É preciso fornecer cookies de uma conta logada."

    if "private" in low or "members-only" in low or "join this channel" in low:
        return "Vídeo privado ou exclusivo para membros. Só com cookies de uma conta com acesso."

    if "unsupported url" in low:
        return "Esse site não é suportado pelo yt-dlp."

    if "unavailable" in low or "removed" in low or "terminated" in low:
        return "O vídeo está indisponível, foi removido ou o canal foi encerrado."

    if "http error 429" in low or "too many requests" in low:
        return ("O YouTube limitou as requisições deste IP. Espere alguns minutos antes de "
                "tentar de novo, ou configure um proxy.")

    if "geo" in low and "restrict" in low:
        return "Vídeo bloqueado na sua região. Um proxy em outro país resolveria."

    if "urlopen error" in low or "getaddrinfo" in low or "connection" in low:
        return "Sem conexão com a internet, ou a rede bloqueou o acesso."

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
