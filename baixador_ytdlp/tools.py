"""Gerenciamento das dependências externas (yt-dlp e FFmpeg).

Os binários ficam em %LOCALAPPDATA%\\BaixadorYtdlp\\bin, fora de Program Files,
para que a atualização automática não precise de elevação.

Integridade: o yt-dlp é conferido contra o arquivo SHA2-256SUMS publicado no
release. Para FFmpeg, usamos o digest SHA-256 retornado pela API de Releases
quando o fornecedor o disponibiliza; o id do asset também é gravado no estado
local para detectar atualizações futuras.
"""
from __future__ import annotations

import hashlib
import json
import locale
import os
import platform
import re
import shutil
import ssl
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

try:
    import certifi
except ImportError:  # pragma: no cover - só ocorre fora das builds oficiais
    certifi = None

from .config import APP_NAME, APP_VERSION, BIN_DIR, DATA_DIR, IS_WINDOWS, STATE_PATH, ensure_dirs
from .diagnostics import get_logger
from .runtime import RuntimeInfo, RuntimeManager

YTDLP_EXE = "yt-dlp.exe" if IS_WINDOWS else "yt-dlp"
FFMPEG_EXE = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
FFPROBE_EXE = "ffprobe.exe" if IS_WINDOWS else "ffprobe"
YTDLP_ASSET = "yt-dlp.exe" if IS_WINDOWS else ("yt-dlp_macos" if sys.platform == "darwin" else "yt-dlp")

# O yt-dlp precisa de um runtime JavaScript para resolver o desafio JS do YouTube.
# Sem ele, a resposta do player volta UNPLAYABLE e o erro exibido é
# "The page needs to be reloaded" — que não tem nada a ver com cookies.
# Versões mínimas aceitas pelo yt-dlp (utils/_jsruntime.py): deno 2.3, bun 1.2.11,
# node 22, quickjs 2023-12-09. O Deno é um executável único, então é o que baixamos.
DENO_EXE = "deno.exe" if IS_WINDOWS else "deno"
DENO_MIN_VERSION = (2, 3, 0)
DENO_RELEASES_API = "https://api.github.com/repos/denoland/deno/releases?per_page=30"
DENO_SUPPORTED_MAJOR = 2

YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
# Quando o YouTube muda algo, a correção sai no nightly dias antes do estável.
# O repositório de nightly publica o mesmo SHA2-256SUMS, então a verificação
# de integridade é idêntica.
YTDLP_NIGHTLY_API = "https://api.github.com/repos/yt-dlp/yt-dlp-nightly-builds/releases/latest"
YTDLP_CHANNELS = {"stable": YTDLP_RELEASE_API, "nightly": YTDLP_NIGHTLY_API}
FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
# O BtbN publica somente os ramos de release mais recentes (ex.: n8.1 e n9.0) e
# remove os antigos. Fixar um nome quebrava instalações novas quando o ramo
# saía da release; agora escolhemos sempre o maior ramo estável publicado.
FFMPEG_BTBN_PLATFORMS = {
    "win64": ("win64", "zip"),
    "x86_64": ("linux64", "tar.xz"),
    "amd64": ("linux64", "tar.xz"),
    "aarch64": ("linuxarm64", "tar.xz"),
    "arm64": ("linuxarm64", "tar.xz"),
}
# Build estática macOS publicada em um único ZIP com FFmpeg e ffprobe. A API de
# Releases expõe o SHA-256 do próprio artefato, então uma publicação sem digest
# é recusada em vez de ser instalada no escuro.
MAC_FFMPEG_RELEASE_API = "https://api.github.com/repos/Tyrrrz/FFmpegBin/releases/latest"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://github.com/yt-dlp/yt-dlp)"
HTTP_CACHE_PATH = DATA_DIR / "http_cache.json"
INTEGRITY_FULL_CHECK_HOURS = 24

# Esconde a janela preta do console em cada subprocesso no Windows.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

ProgressCB = Callable[[str, int], None]  # (mensagem, percentual 0-100 ou -1 = indeterminado)


def _verified_ssl_context() -> ssl.SSLContext:
    """Cria TLS verificado mesmo quando o Python do .app não vê o Keychain.

    O bundle de CAs do ``certifi`` viaja dentro do aplicativo PyInstaller e
    evita depender do caminho de certificados da instalação local do Python.
    """
    if certifi is not None:
        return ssl.create_default_context(cafile=certifi.where())
    return ssl.create_default_context()


def require_https(url: str) -> str:
    """URLs de download vêm de APIs remotas; ``file:``/``ftp:`` nunca são aceitos."""
    if not str(url).lower().startswith("https://"):
        raise ValueError(f"Somente HTTPS é aceito para downloads: {url[:60]}")
    return url


class IntegrityError(RuntimeError):
    """O fornecedor não publicou uma prova de integridade utilizável."""


def pick_btbn_asset(assets: list[dict], platform_key: str) -> dict:
    """Escolhe o maior ramo estável ``nX.Y`` do BtbN para a plataforma."""
    target, extension = FFMPEG_BTBN_PLATFORMS[platform_key]
    pattern = re.compile(
        rf"^ffmpeg-n(\d+)\.(\d+)-latest-{re.escape(target)}-gpl-\1\.\2\.{re.escape(extension)}$"
    )
    candidates = []
    for asset in assets:
        match = pattern.match(str(asset.get("name") or ""))
        if match:
            candidates.append(((int(match.group(1)), int(match.group(2))), asset))
    if not candidates:
        raise RuntimeError(f"Nenhuma build estável do FFmpeg para {target} foi publicada.")
    return max(candidates, key=lambda item: item[0])[1]


def pick_deno_release(releases: list[dict], major: int = DENO_SUPPORTED_MAJOR) -> dict:
    """Maior release estável do Deno dentro da versão maior homologada."""
    best: tuple[tuple[int, ...], dict] | None = None
    for release in releases:
        if release.get("draft") or release.get("prerelease"):
            continue
        tag = str(release.get("tag_name") or "").lstrip("v")
        try:
            version = tuple(int(part) for part in tag.split(".")[:3])
        except ValueError:
            continue
        if len(version) == 3 and version[0] == major and (best is None or version > best[0]):
            best = (version, release)
    if best is None:
        raise RuntimeError(f"Nenhuma release estável do Deno {major}.x foi encontrada.")
    return best[1]


def _quiet_unlink(path: Path) -> None:
    """Remove sem propagar erro — arquivo em uso não é motivo para abortar."""
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def run_hidden(args: list[str], timeout: int = 60) -> subprocess.CompletedProcess:
    """Executa um comando sem abrir console, devolvendo texto decodificado."""
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=CREATE_NO_WINDOW,
    )


def decode_external_output(output: bytes | str | None) -> str:
    """Decodifica a saída de ferramentas externas sem perder acentos no Windows.

    Os executáveis *standalone* do yt-dlp mais antigos podem escrever na página
    de código ativa do Windows quando a saída está redirecionada para um pipe.
    Decodificar diretamente como UTF-8 transformava cada ``ã``/``ç`` em ``�``
    antes que a interface recebesse o nome final do arquivo. UTF-8 continua
    sendo a primeira escolha; só recorremos à página de código local quando os
    bytes realmente não formam UTF-8 válido.
    """
    if output is None:
        return ""
    if isinstance(output, str):
        return output
    try:
        return output.decode("utf-8")
    except UnicodeDecodeError:
        pass

    encodings = ("mbcs", "cp1252") if IS_WINDOWS else (
        locale.getpreferredencoding(False) or "utf-8", "utf-8")
    for encoding in encodings:
        try:
            return output.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return output.decode("utf-8", errors="replace")


@dataclass
class Toolchain:
    ytdlp: Path
    ffmpeg: Path
    ffprobe: Path
    bin_dir: Path
    ytdlp_version: str = ""
    ffmpeg_version: str = ""
    deno: Path | None = None
    deno_version: str = ""

    @property
    def ok(self) -> bool:
        return self.ytdlp.exists() and self.ffmpeg.exists()

    @property
    def has_js_runtime(self) -> bool:
        return bool(self.deno and self.deno.exists())

    def env(self) -> dict:
        """Ambiente para os subprocessos do yt-dlp, com o runtime JS no PATH.

        O yt-dlp procura deno/node/bun no PATH. Como o Deno fica na pasta de
        binários do aplicativo, ela precisa entrar no PATH do processo filho —
        sem poluir o PATH do sistema.
        """
        env = os.environ.copy()
        env["PATH"] = str(self.bin_dir) + os.pathsep + env.get("PATH", "")
        if IS_WINDOWS:
            # Mantém stdout/stderr do yt-dlp em UTF-8 inclusive na edição
            # standalone. A leitura binária com fallback em downloader.py ainda
            # cobre versões antigas que não respeitam esta variável.
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
        return env


class ToolManager:
    """Verifica, instala e atualiza yt-dlp e FFmpeg."""

    def __init__(self, bin_dir: Path = BIN_DIR, runtime_check_hours: int = 24,
                 allow_system_tools: bool = False, ytdlp_channel: str = "stable"):
        self.bin_dir = bin_dir
        self.ytdlp_channel = ytdlp_channel if ytdlp_channel in YTDLP_CHANNELS else "stable"
        self.allow_system_tools = bool(allow_system_tools)
        self.state = self._load_state()
        self.runtime = RuntimeManager(check_hours=runtime_check_hours)
        self.runtime_info = RuntimeInfo({}, False)
        # (caminho, mtime, tamanho) -> versão. Evita repetir `--version`, que
        # custa de 100 ms a 1 s por binário em disco lento ou com antivírus ativo.
        self._version_cache: dict[tuple[str, int, int], str] = {}
        # O mesmo cache é persistido no estado. Na abertura seguinte não há
        # motivo para iniciar três processos só para descobrir versões de
        # executáveis que não mudaram desde a última sessão.
        self._state_dirty = False
        self._http_cache_data: dict | None = None

    # ---------------------------------------------------------------- estado
    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = STATE_PATH.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
        temporary.replace(STATE_PATH)
        self._state_dirty = False

    # ------------------------------------------------------- cache de versão
    def _cached_version(self, path: Path, reader: Callable[[Path], str]) -> str:
        try:
            stat = path.stat()
        except OSError:
            return ""
        identity = str(path.resolve())
        mtime_ns = stat.st_mtime_ns
        key = (identity, mtime_ns, stat.st_size)
        cached = self._version_cache.get(key)
        if cached is not None:
            return cached

        persistent = self.state.get("tool_version_cache")
        if not isinstance(persistent, dict):
            persistent = {}
            self.state["tool_version_cache"] = persistent
            self._state_dirty = True
        entry = persistent.get(identity)
        if isinstance(entry, dict) and (
            entry.get("mtime_ns") == mtime_ns
            and entry.get("size") == stat.st_size
            and isinstance(entry.get("version"), str)
            and entry["version"]
        ):
            version = entry["version"]
        else:
            if entry is not None:
                persistent.pop(identity, None)
                self._state_dirty = True
            version = reader(path)
            # Não persiste uma falha temporária: uma próxima abertura deve poder
            # consultar o executável novamente em vez de esconder o problema.
            if version:
                persistent[identity] = {
                    "mtime_ns": mtime_ns,
                    "size": stat.st_size,
                    "version": version,
                }
                self._state_dirty = True
        self._version_cache[key] = version
        return version

    # --------------------------------------------------------------- caminhos
    def _resolve(self, name: str) -> Path:
        local = self.bin_dir / name
        if local.exists():
            if not self._integrity_ok(name, local):
                get_logger().error("Integridade local divergente para %s; reinstalação exigida", name)
                return self.bin_dir / f"{name}.integrity-failed"
            return local
        # Um binário que já vem na aplicação congelada tem precedência sobre o
        # PATH do sistema, mas nunca é alterado em lugar: atualizações vão para
        # a pasta de dados do usuário.
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "bin" / name
            if bundled.is_file():
                return bundled
        found = shutil.which(name) if self.allow_system_tools else None
        return Path(found) if found else local

    def toolchain(self) -> Toolchain:
        tc = Toolchain(
            ytdlp=self._resolve(YTDLP_EXE),
            ffmpeg=self._resolve(FFMPEG_EXE),
            ffprobe=self._resolve(FFPROBE_EXE),
            bin_dir=self.bin_dir,
        )
        tc.ytdlp_version = self.local_ytdlp_version(tc.ytdlp)
        tc.ffmpeg_version = self.local_ffmpeg_version(tc.ffmpeg)
        deno = self._resolve(DENO_EXE)
        tc.deno_version = self.local_deno_version(deno)
        tc.deno = deno if tc.deno_version else None
        return tc

    # ------------------------------------------------------------- utilidades
    @staticmethod
    def _request(url: str, accept: str = "application/vnd.github+json"):
        req = urllib.request.Request(require_https(url),
                                     headers={"User-Agent": USER_AGENT, "Accept": accept})
        return urllib.request.urlopen(req, timeout=30, context=_verified_ssl_context())  # noqa: S310

    def _download(self, url: str, dest: Path, progress: ProgressCB, label: str) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        try:
            with self._request(url, accept="application/octet-stream") as resp, open(tmp, "wb") as fh:
                total = int(resp.headers.get("Content-Length") or 0)
                done = 0
                while chunk := resp.read(256 * 1024):
                    fh.write(chunk)
                    done += len(chunk)
                    pct = int(done * 100 / total) if total else -1
                    mb = done / 1_048_576
                    suffix = (f"{mb:.1f} MB" if not total
                              else f"{mb:.1f} / {total / 1_048_576:.1f} MB")
                    progress(f"{label} — {suffix}", pct)
        except Exception:
            _quiet_unlink(tmp)
            raise
        tmp.replace(dest)
        return dest

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as fh:
            while chunk := fh.read(1 << 20):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _asset_sha256(asset: dict) -> str:
        """Lê o digest SHA-256 exposto pela API de assets do GitHub."""
        digest = str(asset.get("digest") or "").strip().lower()
        if digest.startswith("sha256:"):
            digest = digest.split(":", 1)[1]
        return digest if re.fullmatch(r"[0-9a-f]{64}", digest) else ""

    @staticmethod
    def require_sha256(path: Path, expected: str, label: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", (expected or "").casefold()):
            _quiet_unlink(path)
            raise IntegrityError(
                f"{label}: o fornecedor não publicou um SHA-256 verificável; "
                "o arquivo atual foi preservado."
            )
        actual = ToolManager._sha256(path)
        if actual.casefold() != expected.casefold():
            _quiet_unlink(path)
            raise IntegrityError(f"{label}: SHA-256 não confere. Download descartado.")
        return actual.casefold()

    def _record_integrity(self, name: str, path: Path) -> None:
        hashes = self.state.setdefault("tool_sha256", {})
        if isinstance(hashes, dict):
            hashes[name] = self._sha256(path)
            self._remember_verified_stat(name, path)

    def _remember_verified_stat(self, name: str, path: Path) -> None:
        try:
            stat = path.stat()
        except OSError:
            return
        verified = self.state.setdefault("tool_sha256_verified", {})
        if isinstance(verified, dict):
            verified[name] = {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size,
                              "at": time.time()}
            self._state_dirty = True

    def _integrity_ok(self, name: str, path: Path, *, full: bool = False) -> bool:
        """Confere o binário contra a linha de base gravada na instalação.

        O SHA-256 completo de FFmpeg/ffprobe/Deno soma centenas de MB. Ele só é
        recalculado quando mtime/tamanho mudam ou a última verificação completa
        tem mais de ``INTEGRITY_FULL_CHECK_HOURS``; no resto, basta o ``stat``.
        """
        expected = str((self.state.get("tool_sha256") or {}).get(name) or "")
        if not expected:
            return True  # instalação anterior à 1.7: sem linha de base ainda
        try:
            stat = path.stat()
        except OSError:
            return False
        verified = (self.state.get("tool_sha256_verified") or {}).get(name) or {}
        same_stat = (verified.get("mtime_ns") == stat.st_mtime_ns
                     and verified.get("size") == stat.st_size)
        fresh = (time.time() - float(verified.get("at") or 0)) < INTEGRITY_FULL_CHECK_HOURS * 3600
        if same_stat and fresh and not full:
            return True
        if not same_stat or full or not fresh:
            if self._sha256(path) != expected:
                return False
            self._remember_verified_stat(name, path)
        return True

    def repair_tampered_tools(self, progress: ProgressCB) -> list[str]:
        """Remove binários adulterados e zera o estado para forçar novo download.

        Antes, a divergência devolvia um caminho inexistente e a preparação
        terminava em erro genérico — em laço, porque a versão lida do próprio
        arquivo adulterado coincidia com a tag e nada era baixado de novo.
        """
        repaired: list[str] = []
        groups = {
            YTDLP_EXE: ("ytdlp", (YTDLP_EXE,)),
            FFMPEG_EXE: ("ffmpeg", (FFMPEG_EXE, FFPROBE_EXE)),
            FFPROBE_EXE: ("ffmpeg", (FFMPEG_EXE, FFPROBE_EXE)),
            DENO_EXE: ("deno", (DENO_EXE,)),
        }
        for name, (key, members) in groups.items():
            path = self.bin_dir / name
            if not path.exists() or self._integrity_ok(name, path):
                continue
            get_logger().error("Binário %s foi alterado fora do aplicativo; reinstalando", name)
            progress(f"O arquivo {name} foi alterado fora do aplicativo e será baixado novamente…", -1)
            for member in members:
                _quiet_unlink(self.bin_dir / member)
                for bucket in ("tool_sha256", "tool_sha256_verified"):
                    (self.state.get(bucket) or {}).pop(member, None)
            self.state.pop(f"{key}_checked_at", None)
            if key == "ffmpeg":
                self.state.pop("ffmpeg_stamp", None)
            cache = self.state.get("tool_version_cache")
            if isinstance(cache, dict):
                for member in members:
                    cache.pop(str((self.bin_dir / member).resolve()), None)
            self._version_cache.clear()
            self._state_dirty = True
            repaired.append(name)
        return repaired

    # ------------------------------------------------------------ HTTP/ETag
    def _get_json(self, url: str):
        """GET na API do GitHub com ``If-None-Match``.

        Respostas 304 não contam no limite anônimo de 60 requisições/hora, que
        esgota rápido em redes com NAT compartilhado.
        """
        cache = self._http_cache()
        entry = cache.get(url) if isinstance(cache.get(url), dict) else None
        headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
        if entry and entry.get("etag"):
            headers["If-None-Match"] = str(entry["etag"])
        request = urllib.request.Request(require_https(url), headers=headers)
        try:
            with urllib.request.urlopen(  # noqa: S310 - HTTPS garantido acima
                    request, timeout=30, context=_verified_ssl_context()) as resp:
                raw = resp.read()
                etag = resp.headers.get("ETag") or ""
        except urllib.error.HTTPError as exc:
            if exc.code == 304 and entry and "body" in entry:
                return json.loads(entry["body"])
            raise
        data = json.loads(raw.decode("utf-8"))
        if etag:
            cache[url] = {"etag": etag, "body": raw.decode("utf-8")}
            self._save_http_cache(cache)
        return data

    def _http_cache(self) -> dict:
        if self._http_cache_data is None:
            try:
                loaded = json.loads(HTTP_CACHE_PATH.read_text(encoding="utf-8"))
                self._http_cache_data = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                self._http_cache_data = {}
        return self._http_cache_data

    @staticmethod
    def _save_http_cache(cache: dict) -> None:
        try:
            HTTP_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary = HTTP_CACHE_PATH.with_suffix(".tmp")
            temporary.write_text(json.dumps(cache), encoding="utf-8")
            temporary.replace(HTTP_CACHE_PATH)
        except OSError:
            pass

    @staticmethod
    def _extract_zip_member(zf: zipfile.ZipFile, member: str, destination: Path) -> None:
        """Extrai sem manter um executável inteiro duplicado na memória."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(member) as src, open(destination, "wb") as dst:
            shutil.copyfileobj(src, dst, length=1 << 20)

    def _should_check(self, key: str, hours: int) -> bool:
        last = self.state.get(f"{key}_checked_at")
        if not last:
            return True
        return (time.time() - float(last)) > hours * 3600

    def _mark_checked(self, key: str) -> None:
        self.state[f"{key}_checked_at"] = time.time()

    # ----------------------------------------------------------------- yt-dlp
    def local_ytdlp_version(self, path: Optional[Path] = None) -> str:
        path = path or self._resolve(YTDLP_EXE)
        return self._cached_version(path, self._read_ytdlp_version)

    @staticmethod
    def _read_ytdlp_version(path: Path) -> str:
        try:
            return run_hidden([str(path), "--version"], timeout=25).stdout.strip()
        except Exception:
            return ""

    def _latest_ytdlp(self) -> tuple[str, str, dict[str, str]]:
        """Devolve (tag, url_do_exe, {arquivo: sha256})."""
        data = self._get_json(YTDLP_CHANNELS[self.ytdlp_channel])
        tag = data.get("tag_name", "")
        assets = {a["name"]: a["browser_download_url"] for a in data.get("assets", [])}
        sums: dict[str, str] = {}
        if "SHA2-256SUMS" in assets:
            try:
                with self._request(assets["SHA2-256SUMS"], accept="text/plain") as resp:
                    for line in resp.read().decode("utf-8", "replace").splitlines():
                        parts = line.split()
                        if len(parts) == 2:
                            sums[parts[1].lstrip("*")] = parts[0].lower()
            except Exception as exc:
                raise IntegrityError(
                    "yt-dlp: não foi possível obter o arquivo SHA2-256SUMS."
                ) from exc
        return tag, assets.get(YTDLP_ASSET, ""), sums

    def ensure_ytdlp(self, progress: ProgressCB, check_now: bool = False) -> None:
        target = self.bin_dir / YTDLP_EXE
        current = self.local_ytdlp_version(target)
        system_ytdlp = (shutil.which("yt-dlp")
                         if self.allow_system_tools and not target.exists() else None)

        if current and not check_now and not self._should_check("ytdlp", 12):
            progress(f"yt-dlp {current} (verificado recentemente)", 100)
            return

        progress("Consultando a versão mais recente do yt-dlp…", -1)
        try:
            tag, url, sums = self._latest_ytdlp()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando yt-dlp {current}", 100)
                return
            if system_ytdlp:
                progress("Sem rede — usando o yt-dlp disponível no sistema", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o yt-dlp: {exc}") from exc

        self._mark_checked("ytdlp")
        if current and tag and current == tag:
            progress(f"yt-dlp {current} já está atualizado", 100)
            self._save_state()
            return

        if not url:
            raise RuntimeError("O release do yt-dlp não trouxe o executável esperado.")

        progress(f"Baixando yt-dlp {tag}…", 0)
        staged = self.bin_dir / f"{YTDLP_EXE}.new"
        self._download(url, staged, progress, f"Baixando yt-dlp {tag}")

        progress("Conferindo a integridade do yt-dlp…", -1)
        self.require_sha256(staged, sums.get(YTDLP_ASSET, ""), "yt-dlp")

        self._replace(staged, target)
        self._record_integrity(YTDLP_EXE, target)
        self.state["ytdlp_version"] = tag
        self._save_state()
        progress(f"yt-dlp atualizado para {tag}", 100)

    # ----------------------------------------------------------------- FFmpeg
    def local_ffmpeg_version(self, path: Optional[Path] = None) -> str:
        path = path or self._resolve(FFMPEG_EXE)
        return self._cached_version(path, self._read_ffmpeg_version)

    @staticmethod
    def _read_ffmpeg_version(path: Path) -> str:
        try:
            out = run_hidden([str(path), "-hide_banner", "-version"], timeout=25).stdout
            match = re.search(r"ffmpeg version (\S+)", out)
            return match.group(1) if match else ""
        except Exception:
            return ""

    def _mac_ffmpeg_asset(self) -> tuple[str, dict]:
        """Obtém o pacote estático de FFmpeg/ffprobe para a arquitetura atual."""
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        data = self._get_json(MAC_FFMPEG_RELEASE_API)
        assets = {str(asset.get("name")): asset for asset in data.get("assets", [])}
        name = f"ffmpeg-osx-{arch}.zip"
        if name not in assets:
            raise RuntimeError(f"A release não trouxe FFmpeg/ffprobe para macOS {arch}.")
        return str(data.get("tag_name") or ""), assets[name]

    def _ensure_macos_ffmpeg(self, progress: ProgressCB, check_now: bool = False) -> None:
        target = self.bin_dir / FFMPEG_EXE
        current = self.local_ffmpeg_version(target)
        if current and not check_now and not self._should_check("ffmpeg", 168):
            progress(f"FFmpeg {current} (verificado recentemente)", 100)
            return

        progress("Consultando o FFmpeg para macOS…", -1)
        try:
            tag, asset = self._mac_ffmpeg_asset()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando FFmpeg {current}", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o FFmpeg para macOS: {exc}") from exc

        stamp = f"{tag}:{asset.get('id')}:{asset.get('updated_at', '')}"
        self._mark_checked("ffmpeg")
        if current and self.state.get("ffmpeg_stamp") == stamp:
            progress(f"FFmpeg {current} já está atualizado", 100)
            self._save_state()
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / str(asset["name"])
            self._download(
                str(asset["browser_download_url"]), archive_path, progress,
                "Baixando FFmpeg para macOS",
            )
            progress("Conferindo a integridade do FFmpeg…", -1)
            self.require_sha256(
                archive_path, self._asset_sha256(asset), "FFmpeg para macOS")
            progress("Extraindo FFmpeg…", -1)
            wanted = {FFMPEG_EXE, FFPROBE_EXE}
            with zipfile.ZipFile(archive_path) as archive:
                members = {
                    Path(member).name: member for member in archive.namelist()
                    if Path(member).name in wanted
                }
                missing = wanted - members.keys()
                if missing:
                    raise RuntimeError(
                        "O pacote FFmpeg não trouxe: " + ", ".join(sorted(missing)))
                for name, member in members.items():
                    staged = self.bin_dir / f"{name}.new"
                    self._extract_zip_member(archive, member, staged)
                    self._replace(staged, self.bin_dir / name)
                    self._record_integrity(name, self.bin_dir / name)

        self.state["ffmpeg_stamp"] = stamp
        self._save_state()
        progress("FFmpeg para macOS instalado", 100)

    def _ensure_linux_ffmpeg(self, progress: ProgressCB, check_now: bool = False) -> None:
        """Instala FFmpeg estático no perfil do usuário em Debian/Ubuntu.

        O pacote .deb não depende de uma versão do FFmpeg da distribuição. Isso
        evita que instalações recém-feitas recebam recursos muito antigos para
        mesclar streams, miniaturas ou legendas, e mantém o mesmo fluxo de
        atualização em runtime usado no Windows e no macOS.
        """
        target = self.bin_dir / FFMPEG_EXE
        current = self.local_ffmpeg_version(target)
        if current and not check_now and not self._should_check("ffmpeg", 168):
            progress(f"FFmpeg {current} (verificado recentemente)", 100)
            return

        machine = platform.machine().lower()
        if machine not in FFMPEG_BTBN_PLATFORMS or machine == "win64":
            system_ffmpeg = shutil.which("ffmpeg") if self.allow_system_tools else None
            if system_ffmpeg:
                progress("FFmpeg do sistema será usado nesta arquitetura", 100)
                return
            raise RuntimeError(
                f"Não há build FFmpeg em runtime para a arquitetura Linux {machine}. "
                "Instale o pacote ffmpeg da sua distribuição."
            )

        progress("Consultando a build mais recente do FFmpeg para Linux…", -1)
        try:
            data = self._get_json(FFMPEG_RELEASE_API)
            asset = pick_btbn_asset(data.get("assets", []), machine)
            asset_name = str(asset["name"])
        except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError, OSError, KeyError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando FFmpeg {current}", 100)
                return
            if self.allow_system_tools and shutil.which("ffmpeg"):
                progress("Sem rede — usando o FFmpeg disponível no sistema", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o FFmpeg para Linux: {exc}") from exc

        self._mark_checked("ffmpeg")
        stamp = f"{asset['id']}:{asset.get('updated_at', '')}"
        if current and self.state.get("ffmpeg_stamp") == stamp:
            progress(f"FFmpeg {current} já está atualizado", 100)
            self._save_state()
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / asset_name
            self._download(asset["browser_download_url"], archive_path, progress,
                           "Baixando FFmpeg para Linux")
            progress("Conferindo a integridade do FFmpeg…", -1)
            self.require_sha256(archive_path, self._asset_sha256(asset), "FFmpeg")
            progress("Extraindo FFmpeg…", -1)
            wanted = {FFMPEG_EXE, FFPROBE_EXE}
            with tarfile.open(archive_path, mode="r:xz") as archive:
                members = {
                    Path(member.name).name: member for member in archive.getmembers()
                    if member.isfile() and Path(member.name).name in wanted
                }
                missing = wanted - members.keys()
                if missing:
                    raise RuntimeError("O pacote FFmpeg não trouxe: " + ", ".join(sorted(missing)))
                for name, member in members.items():
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise RuntimeError(f"Não foi possível extrair {name} do pacote FFmpeg")
                    staged = self.bin_dir / f"{name}.new"
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    with stream, open(staged, "wb") as destination:
                        shutil.copyfileobj(stream, destination, length=1 << 20)
                    self._replace(staged, self.bin_dir / name)
                    self._record_integrity(name, self.bin_dir / name)

        # O id/timestamp complementa a conferência de hash e indica ao cache
        # local quando uma nova build foi publicada.
        self.state["ffmpeg_stamp"] = stamp
        self._save_state()
        progress("FFmpeg para Linux instalado", 100)

    def ensure_ffmpeg(self, progress: ProgressCB, check_now: bool = False) -> None:
        target = self.bin_dir / FFMPEG_EXE
        current = self.local_ffmpeg_version(target)

        if sys.platform == "darwin":
            self._ensure_macos_ffmpeg(progress, check_now)
            return

        if not IS_WINDOWS:
            self._ensure_linux_ffmpeg(progress, check_now)
            return

        if current and not check_now and not self._should_check("ffmpeg", 168):  # 7 dias
            progress(f"FFmpeg {current} (verificado recentemente)", 100)
            return

        progress("Consultando a build mais recente do FFmpeg…", -1)
        try:
            data = self._get_json(FFMPEG_RELEASE_API)
            asset = pick_btbn_asset(data.get("assets", []), "win64")
        except (RuntimeError, ValueError, urllib.error.URLError, TimeoutError, OSError, KeyError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando FFmpeg {current}", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o FFmpeg: {exc}") from exc

        self._mark_checked("ffmpeg")
        stamp = f"{asset['id']}:{asset.get('updated_at', '')}"
        if current and self.state.get("ffmpeg_stamp") == stamp:
            progress(f"FFmpeg {current} já está atualizado", 100)
            self._save_state()
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / str(asset["name"])
            self._download(asset["browser_download_url"], zip_path, progress, "Baixando FFmpeg")
            progress("Conferindo a integridade do FFmpeg…", -1)
            self.require_sha256(zip_path, self._asset_sha256(asset), "FFmpeg")
            progress("Extraindo FFmpeg…", -1)
            wanted = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    name = Path(member).name
                    if name.lower() in wanted:
                        staged = self.bin_dir / f"{name}.new"
                        self._extract_zip_member(zf, member, staged)
                        self._replace(staged, self.bin_dir / name)
                        self._record_integrity(name, self.bin_dir / name)

        self.state["ffmpeg_stamp"] = stamp
        self._save_state()
        progress("FFmpeg atualizado", 100)

    # ------------------------------------------------------------------- Deno
    def local_deno_version(self, path: Optional[Path] = None) -> str:
        path = path or self._resolve(DENO_EXE)
        return self._cached_version(path, self._read_deno_version)

    @staticmethod
    def _read_deno_version(path: Path) -> str:
        try:
            out = run_hidden([str(path), "--version"], timeout=25).stdout
            match = re.search(r"deno (\d+\.\d+\.\d+)", out)
            return match.group(1) if match else ""
        except Exception:
            return ""

    @staticmethod
    def _deno_asset_name() -> str:
        """Nome do artefato do Deno para a arquitetura desta máquina."""
        machine = platform.machine().lower()
        arch = "aarch64" if machine in ("arm64", "aarch64") else "x86_64"
        if IS_WINDOWS:
            return f"deno-{arch}-pc-windows-msvc.zip"
        if sys.platform == "darwin":
            return f"deno-{arch}-apple-darwin.zip"
        return f"deno-{arch}-unknown-linux-gnu.zip"

    @staticmethod
    def _version_ok(version: str, minimum: tuple[int, ...]) -> bool:
        try:
            return tuple(int(p) for p in version.split(".")[:3]) >= minimum
        except ValueError:
            return False

    def ensure_deno(self, progress: ProgressCB, check_now: bool = False) -> None:
        """Instala o runtime JavaScript exigido pelo yt-dlp para o YouTube.

        Falhar aqui não impede o aplicativo de abrir: sites que não exigem
        desafio JS continuam funcionando. Por isso os erros viram aviso, e não
        exceção.
        """
        target = self.bin_dir / DENO_EXE
        current = self.local_deno_version(target)

        if current and self._version_ok(current, DENO_MIN_VERSION) and not check_now \
                and not self._should_check("deno", 168):  # 7 dias
            progress(f"Runtime JavaScript: Deno {current}", 100)
            return

        progress("Consultando o runtime JavaScript (Deno)…", -1)
        asset_name = self._deno_asset_name()
        try:
            releases = self._get_json(DENO_RELEASES_API)
            data = pick_deno_release(releases if isinstance(releases, list) else [])
            assets = {a["name"]: a for a in data.get("assets", [])}
            asset = assets[asset_name]
        except (RuntimeError, KeyError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
            # Isto falhava em silêncio: sem rede, com a API do GitHub limitando
            # requisições ou sem o pacote da plataforma, o Deno simplesmente não
            # era instalado e o YouTube quebrava sem deixar rastro no log.
            get_logger().warning("Deno: não deu para consultar %s (%s: %s); pacote %s",
                                 DENO_RELEASES_API, type(exc).__name__, exc, asset_name)
            if current:
                progress(f"Sem rede para checar o Deno — usando {current}", 100)
                return
            progress(f"Runtime JavaScript indisponível ({exc}). O YouTube pode falhar.", 100)
            return

        self._mark_checked("deno")
        tag = (data.get("tag_name") or "").lstrip("v")
        if current and tag and current == tag:
            progress(f"Deno {current} já está atualizado", 100)
            self._save_state()
            return

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                zip_path = Path(tmpdir) / asset_name
                self._download(asset["browser_download_url"], zip_path, progress,
                               f"Baixando o runtime JavaScript (Deno {tag})")

                # Releases atuais expõem o digest do próprio ZIP na API. O
                # .sha256sum do Deno no Windows é um relatório PowerShell
                # ("Hash : ..."), não o formato tradicional "hash arquivo".
                expected = (self._asset_sha256(asset)
                            or self._remote_sha256(assets.get(asset_name + ".sha256sum")))
                progress("Conferindo a integridade do Deno…", -1)
                self.require_sha256(zip_path, expected, "Deno")

                progress("Extraindo o Deno…", -1)
                with zipfile.ZipFile(zip_path) as zf:
                    member = next((m for m in zf.namelist()
                                   if Path(m).name.lower() == DENO_EXE), None)
                    if not member:
                        raise RuntimeError(f"{DENO_EXE} não veio no pacote")
                    staged = self.bin_dir / f"{DENO_EXE}.new"
                    self._extract_zip_member(zf, member, staged)
                self._replace(staged, target)
                self._record_integrity(DENO_EXE, target)
        except Exception as exc:  # noqa: BLE001 - runtime JS é opcional
            get_logger().warning("Deno: falha ao instalar %s (%s: %s)",
                                 asset_name, type(exc).__name__, exc, exc_info=True)
            progress(f"Não deu para instalar o Deno ({exc}). O YouTube pode falhar.", 100)
            return

        self.state["deno_version"] = tag
        self._save_state()
        get_logger().info("Deno %s instalado em %s", tag, target)
        progress(f"Runtime JavaScript instalado: Deno {tag}", 100)

    def _remote_sha256(self, asset: Optional[dict]) -> str:
        """Lê o .sha256sum publicado ao lado do artefato."""
        if not asset:
            return ""
        try:
            with self._request(asset["browser_download_url"], accept="text/plain") as resp:
                content = resp.read().decode("utf-8", "replace")
                match = re.search(r"(?i)\b([0-9a-f]{64})\b", content)
                return match.group(1).lower() if match else ""
        except Exception:
            return ""

    # ------------------------------------------------------------------ misc
    @staticmethod
    def _replace(staged: Path, target: Path) -> None:
        """Troca o binário mesmo se o antigo estiver em uso (renomeia e apaga depois)."""
        old = target.with_suffix(target.suffix + ".old")
        _quiet_unlink(old)
        if target.exists():
            try:
                target.rename(old)
            except OSError:
                _quiet_unlink(target)
        staged.replace(target)
        if not IS_WINDOWS:
            target.chmod(0o755)
        # O .old pode estar travado por um processo ainda vivo; o cleanup da
        # próxima abertura remove. Falhar aqui perderia a atualização já aplicada.
        _quiet_unlink(old)

    def cleanup(self) -> None:
        for pattern in ("*.old", "*.part", "*.new"):
            for leftover in self.bin_dir.glob(pattern):
                _quiet_unlink(leftover)

    def ensure_all(self, progress: ProgressCB, check_now: bool = False) -> Toolchain:
        """Confere as dependências e baixa somente uma versão nova ou ausente.

        ``check_now`` ignora apenas o intervalo de consulta local. Ele nunca
        transforma uma checagem manual em reinstalação dos binários atuais.
        """
        ensure_dirs()
        self.cleanup()
        progress("Preparando o ambiente…", -1)
        if self.repair_tampered_tools(progress):
            check_now = True
        self.ensure_ytdlp(progress, check_now)
        self.ensure_ffmpeg(progress, check_now)
        self.ensure_deno(progress, check_now)
        # O motor do legendador vem no instalador. A checagem confirma sua
        # disponibilidade e preserva o fallback seguro para desenvolvimento.
        self.runtime_info = self.runtime.ensure(progress, check_now)
        tc = self.toolchain()
        if not tc.ok:
            raise RuntimeError("As dependências não ficaram disponíveis após a instalação.")
        if self._state_dirty:
            self._save_state()
            self._state_dirty = False
        progress("Tudo pronto", 100)
        return tc
