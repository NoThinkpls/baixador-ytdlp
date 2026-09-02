"""Gerenciamento das dependências externas (yt-dlp e FFmpeg).

Os binários ficam em %LOCALAPPDATA%\\BaixadorYtdlp\\bin, fora de Program Files,
para que a atualização automática não precise de elevação.

Integridade: o yt-dlp.exe é conferido contra o arquivo SHA2-256SUMS assinado
publicado no próprio release. O FFmpeg (BtbN) não publica checksums, então
comparamos o id do asset retornado pela API do GitHub e gravamos no estado
local — qualquer troca do binário exige um novo id vindo do GitHub por HTTPS.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from .config import APP_NAME, APP_VERSION, BIN_DIR, IS_WINDOWS, STATE_PATH, ensure_dirs

YTDLP_EXE = "yt-dlp.exe" if IS_WINDOWS else "yt-dlp"
FFMPEG_EXE = "ffmpeg.exe" if IS_WINDOWS else "ffmpeg"
FFPROBE_EXE = "ffprobe.exe" if IS_WINDOWS else "ffprobe"

YTDLP_RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
FFMPEG_RELEASE_API = "https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/latest"
FFMPEG_ASSET = "ffmpeg-master-latest-win64-gpl.zip"
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://github.com/yt-dlp/yt-dlp)"

# Esconde a janela preta do console em cada subprocesso no Windows.
CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0

ProgressCB = Callable[[str, int], None]  # (mensagem, percentual 0-100 ou -1 = indeterminado)


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


@dataclass
class Toolchain:
    ytdlp: Path
    ffmpeg: Path
    ffprobe: Path
    bin_dir: Path
    ytdlp_version: str = ""
    ffmpeg_version: str = ""

    @property
    def ok(self) -> bool:
        return self.ytdlp.exists() and self.ffmpeg.exists()


class ToolManager:
    """Verifica, instala e atualiza yt-dlp e FFmpeg."""

    def __init__(self, bin_dir: Path = BIN_DIR):
        self.bin_dir = bin_dir
        self.state = self._load_state()

    # ---------------------------------------------------------------- estado
    def _load_state(self) -> dict:
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    # --------------------------------------------------------------- caminhos
    def _resolve(self, name: str) -> Path:
        local = self.bin_dir / name
        if local.exists():
            return local
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
        if not path.exists():
            return ""
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
        return tag, assets.get(YTDLP_EXE, ""), sums

    def ensure_ytdlp(self, progress: ProgressCB, force: bool = False) -> None:
        target = self.bin_dir / YTDLP_EXE
        current = self.local_ytdlp_version(target)

        if not IS_WINDOWS and not target.exists():
            if shutil.which("yt-dlp"):
                progress("yt-dlp encontrado no sistema", 100)
                return
            raise RuntimeError("Instale o yt-dlp (pip install yt-dlp) neste sistema.")

        if current and not force and not self._should_check("ytdlp", 12):
            progress(f"yt-dlp {current} (verificado recentemente)", 100)
            return

        progress("Consultando a versão mais recente do yt-dlp…", -1)
        try:
            tag, url, sums = self._latest_ytdlp()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if current:
                progress(f"Sem rede para checar atualização — usando yt-dlp {current}", 100)
                return
            raise RuntimeError(f"Não foi possível baixar o yt-dlp: {exc}") from exc

        self._mark_checked("ytdlp")
        if current and tag and current == tag and not force:
            progress(f"yt-dlp {current} já está atualizado", 100)
            self._save_state()
            return

        if not url:
            raise RuntimeError("O release do yt-dlp não trouxe o executável esperado.")

        progress(f"Baixando yt-dlp {tag}…", 0)
        staged = self.bin_dir / f"{YTDLP_EXE}.new"
        self._download(url, staged, progress, f"Baixando yt-dlp {tag}")

        expected = sums.get(YTDLP_EXE)
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
        if not path.exists():
            return ""
        try:
            out = run_hidden([str(path), "-hide_banner", "-version"], timeout=25).stdout
            match = re.search(r"ffmpeg version (\S+)", out)
            return match.group(1) if match else ""
        except Exception:
            return ""

    def ensure_ffmpeg(self, progress: ProgressCB, force: bool = False) -> None:
        target = self.bin_dir / FFMPEG_EXE
        current = self.local_ffmpeg_version(target)

        if not IS_WINDOWS and not target.exists():
            if shutil.which("ffmpeg"):
                progress("FFmpeg encontrado no sistema", 100)
                return
            raise RuntimeError("Instale o FFmpeg neste sistema.")

        if current and not force and not self._should_check("ffmpeg", 168):  # 7 dias
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
        if current and self.state.get("ffmpeg_stamp") == stamp and not force:
            progress(f"FFmpeg {current} já está atualizado", 100)
            self._save_state()
            return

        with tempfile.TemporaryDirectory() as tmpdir:
            zip_path = Path(tmpdir) / FFMPEG_ASSET
            self._download(asset["browser_download_url"], zip_path, progress, "Baixando FFmpeg")
            progress("Extraindo FFmpeg…", -1)
            wanted = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
            with zipfile.ZipFile(zip_path) as zf:
                for member in zf.namelist():
                    name = Path(member).name
                    if name.lower() in wanted:
                        with zf.open(member) as src:
                            staged = self.bin_dir / f"{name}.new"
                            staged.parent.mkdir(parents=True, exist_ok=True)
                            staged.write_bytes(src.read())
                        self._replace(staged, self.bin_dir / name)

        self.state["ffmpeg_stamp"] = stamp
        self._save_state()
        progress("FFmpeg atualizado", 100)

    # ------------------------------------------------------------------ misc
    @staticmethod
    def _replace(staged: Path, target: Path) -> None:
        """Troca o binário mesmo se o antigo estiver em uso (renomeia e apaga depois)."""
        old = target.with_suffix(target.suffix + ".old")
        old.unlink(missing_ok=True)
        if target.exists():
            try:
                target.rename(old)
            except OSError:
                target.unlink(missing_ok=True)
        staged.replace(target)
        if not IS_WINDOWS:
            target.chmod(0o755)
        old.unlink(missing_ok=True)

    def cleanup(self) -> None:
        for leftover in self.bin_dir.glob("*.old"):
            leftover.unlink(missing_ok=True)
        for leftover in self.bin_dir.glob("*.part"):
            leftover.unlink(missing_ok=True)

    def ensure_all(self, progress: ProgressCB, force: bool = False) -> Toolchain:
        ensure_dirs()
        self.cleanup()
        progress("Preparando o ambiente…", -1)
        self.ensure_ytdlp(progress, force)
        self.ensure_ffmpeg(progress, force)
        tc = self.toolchain()
        if not tc.ok:
            raise RuntimeError("As dependências não ficaram disponíveis após a instalação.")
        progress("Tudo pronto", 100)
        return tc
