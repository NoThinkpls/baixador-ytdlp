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
import sys
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import APP_NAME, APP_VERSION, BIN_DIR, IS_WINDOWS, STATE_PATH, ensure_dirs
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
DENO_RELEASE_API = "https://api.github.com/repos/denoland/deno/releases/latest"

YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
FFMPEG_ASSET = "ffmpeg-master-latest-win64-gpl.zip"
LINUX_FFMPEG_ASSETS = {
    "x86_64": "ffmpeg-master-latest-linux64-gpl.tar.xz",
    "amd64": "ffmpeg-master-latest-linux64-gpl.tar.xz",
    # BtbN publica esta variante quando há build Linux ARM64 disponível.
    "aarch64": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
    "arm64": "ffmpeg-master-latest-linuxarm64-gpl.tar.xz",
}
# Builds estáticas para macOS; os IDs dos assets são gravados como no fluxo Windows
# quando o fornecedor não publica um arquivo de checksums separado.
MAC_FFMPEG_RELEASE_API = "https://api.github.com/repos/descriptinc/ffmpeg-ffprobe-static/releases/latest"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://github.com/yt-dlp/yt-dlp)"

# Esconde a janela preta do console em cada subprocesso no Windows.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

ProgressCB = Callable[[str, int], None]  # (mensagem, percentual 0-100 ou -1 = indeterminado)


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

    def __init__(self, bin_dir: Path = BIN_DIR, runtime_check_hours: int = 24):
        self.bin_dir = bin_dir
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

    # ---------------------------------------------------------------- estado
    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(self.state, indent=2), encoding="utf-8")
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
            return local
        # Um binário que já vem na aplicação congelada tem precedência sobre o
        # PATH do sistema, mas nunca é alterado em lugar: atualizações vão para
        # a pasta de dados do usuário.
        frozen_root = getattr(sys, "_MEIPASS", None)
        if frozen_root:
            bundled = Path(frozen_root) / "bin" / name
            if bundled.is_file():
                return bundled
        found = shutil.which(name)
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
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
        return urllib.request.urlopen(req, timeout=30)

    def _download(self, url: str, dest: Path, progress: ProgressCB, label: str) -> Path:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with self._request(url, accept="application/octet-stream") as resp, open(tmp, "wb") as fh:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while chunk := resp.read(256 * 1024):
                fh.write(chunk)
                done += len(chunk)
                pct = int(done * 100 / total) if total else -1
                mb = done / 1_048_576
                suffix = f"{mb:.1f} MB" if not total else f"{mb:.1f} / {total / 1_048_576:.1f} MB"
                progress(f"{label} — {suffix}", pct)
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
        with self._request(YTDLP_RELEASE_API) as resp:
            data = json.load(resp)
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
            except Exception:
                pass
        return tag, assets.get(YTDLP_ASSET, ""), sums

    def ensure_ytdlp(self, progress: ProgressCB, check_now: bool = False) -> None:
        target = self.bin_dir / YTDLP_EXE
        current = self.local_ytdlp_version(target)
        system_ytdlp = shutil.which("yt-dlp") if not target.exists() else None

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

        expected = sums.get(YTDLP_ASSET)
        if expected:
            progress("Conferindo a integridade do yt-dlp…", -1)
            got = self._sha256(staged)
            if got != expected:
                staged.unlink(missing_ok=True)
                raise RuntimeError("Hash SHA-256 do yt-dlp não confere. Download descartado.")

        self._replace(staged, target)
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

    def _mac_ffmpeg_assets(self) -> tuple[str, dict[str, dict]]:
        """Obtém os binários estáticos de FFmpeg/ffprobe para a arquitetura atual."""
        machine = platform.machine().lower()
        arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
        with self._request(MAC_FFMPEG_RELEASE_API) as resp:
            data = json.load(resp)
        assets = {str(asset.get("name")): asset for asset in data.get("assets", [])}
        names = (f"ffmpeg-darwin-{arch}", f"ffprobe-darwin-{arch}")
        if not all(name in assets for name in names):
            raise RuntimeError(f"A release não trouxe FFmpeg/ffprobe para macOS {arch}.")
        return str(data.get("tag_name") or ""), {name: assets[name] for name in names}

    def _ensure_macos_ffmpeg(self, progress: ProgressCB, check_now: bool = False) -> None:
        target = self.bin_dir / FFMPEG_EXE
        current = self.local_ffmpeg_version(target)
        if current and not check_now and not self._should_check("ffmpeg", 168):
            progress(f"FFmpeg {current} (verificado recentemente)", 100)
            return

        progress("Consultando o FFmpeg para macOS…", -1)
        try:
            tag, assets = self._mac_ffmpeg_assets()
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando FFmpeg {current}", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o FFmpeg para macOS: {exc}") from exc

        stamp = ":".join(
            [tag, *(f"{asset.get('id')}:{asset.get('updated_at', '')}" for asset in assets.values())]
        )
        self._mark_checked("ffmpeg")
        if current and self.state.get("ffmpeg_stamp") == stamp:
            progress(f"FFmpeg {current} já está atualizado", 100)
            self._save_state()
            return

        arch = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
        targets = {
            f"ffmpeg-darwin-{arch}": FFMPEG_EXE,
            f"ffprobe-darwin-{arch}": FFPROBE_EXE,
        }
        for asset_name, target_name in targets.items():
            staged = self.bin_dir / f"{target_name}.new"
            self._download(
                str(assets[asset_name]["browser_download_url"]),
                staged,
                progress,
                f"Baixando {target_name} para macOS",
            )
            self._replace(staged, self.bin_dir / target_name)

        # O fornecedor publica artefatos estáticos no GitHub, mas não um
        # SHA-256 separado. Preservamos o id/versionamento do asset para detectar
        # qualquer troca posterior antes da próxima atualização.
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
        asset_name = LINUX_FFMPEG_ASSETS.get(machine)
        if not asset_name:
            system_ffmpeg = shutil.which("ffmpeg")
            if system_ffmpeg:
                progress("FFmpeg do sistema será usado nesta arquitetura", 100)
                return
            raise RuntimeError(
                f"Não há build FFmpeg em runtime para a arquitetura Linux {machine}. "
                "Instale o pacote ffmpeg da sua distribuição."
            )

        progress("Consultando a build mais recente do FFmpeg para Linux…", -1)
        try:
            with self._request(FFMPEG_RELEASE_API) as resp:
                data = json.load(resp)
            asset = next(a for a in data["assets"] if a["name"] == asset_name)
        except (StopIteration, urllib.error.URLError, TimeoutError, OSError, KeyError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando FFmpeg {current}", 100)
                return
            if shutil.which("ffmpeg"):
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
            expected = self._asset_sha256(asset)
            if expected:
                progress("Conferindo a integridade do FFmpeg…", -1)
                if self._sha256(archive_path) != expected:
                    raise RuntimeError("Hash SHA-256 do FFmpeg não confere. Download descartado.")
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
            with self._request(FFMPEG_RELEASE_API) as resp:
                data = json.load(resp)
            asset = next(a for a in data["assets"] if a["name"] == FFMPEG_ASSET)
        except (StopIteration, urllib.error.URLError, TimeoutError, OSError, KeyError) as exc:
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
            zip_path = Path(tmpdir) / FFMPEG_ASSET
            self._download(asset["browser_download_url"], zip_path, progress, "Baixando FFmpeg")
            expected = self._asset_sha256(asset)
            if expected:
                progress("Conferindo a integridade do FFmpeg…", -1)
                if self._sha256(zip_path) != expected:
                    raise RuntimeError("Hash SHA-256 do FFmpeg não confere. Download descartado.")
            progress("Extraindo FFmpeg…", -1)
            wanted = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    name = Path(member).name
                    if name.lower() in wanted:
                        staged = self.bin_dir / f"{name}.new"
                        self._extract_zip_member(zf, member, staged)
                        self._replace(staged, self.bin_dir / name)

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
            with self._request(DENO_RELEASE_API) as resp:
                data = json.load(resp)
            assets = {a["name"]: a for a in data.get("assets", [])}
            asset = assets[asset_name]
        except (KeyError, ValueError, urllib.error.URLError, TimeoutError, OSError) as exc:
            # Isto falhava em silêncio: sem rede, com a API do GitHub limitando
            # requisições ou sem o pacote da plataforma, o Deno simplesmente não
            # era instalado e o YouTube quebrava sem deixar rastro no log.
            get_logger().warning("Deno: não deu para consultar %s (%s: %s); pacote %s",
                                 DENO_RELEASE_API, type(exc).__name__, exc, asset_name)
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

                expected = self._remote_sha256(assets.get(asset_name + ".sha256sum"))
                if expected:
                    progress("Conferindo a integridade do Deno…", -1)
                    if self._sha256(zip_path) != expected:
                        raise RuntimeError("hash SHA-256 do Deno não confere")

                progress("Extraindo o Deno…", -1)
                with zipfile.ZipFile(zip_path) as zf:
                    member = next((m for m in zf.namelist()
                                   if Path(m).name.lower() == DENO_EXE), None)
                    if not member:
                        raise RuntimeError(f"{DENO_EXE} não veio no pacote")
                    staged = self.bin_dir / f"{DENO_EXE}.new"
                    self._extract_zip_member(zf, member, staged)
                self._replace(staged, target)
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
                return resp.read().decode("utf-8", "replace").split()[0].strip().lower()
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
