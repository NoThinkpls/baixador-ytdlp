"""Instala o yt-dlp como o app faz e confere que ele abre com as dependências opcionais.

Roda no CI das três plataformas, num perfil descartável. Usa os links diretos
``releases/latest/download`` em vez da API do GitHub (limite de 60 consultas por hora
por IP, compartilhado entre os runners), mas passa pelo mesmo download, conferência
de SHA-256, extração e cache de integridade de ``ToolManager.ensure_ytdlp``.

    python scripts/check_runtime_tools.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Antes de qualquer import do app: nunca gravar no perfil real.
os.environ["BAIXADOR_YTDLP_DATA_DIR"] = tempfile.mkdtemp(prefix="baixador-ferramentas-")

from baixador_ytdlp.tools import (  # noqa: E402
    YTDLP_ASSET, YTDLP_ONEDIR, ToolManager, run_hidden,
)

BASE = "https://github.com/yt-dlp/yt-dlp/releases/latest"
# O executável único do Linux (zipimport) não traz estas; a pasta oficial traz.
REQUIRED = ("curl_cffi", "mutagen", "certifi")


def main() -> int:
    manager = ToolManager()

    def latest() -> tuple[str, str, dict[str, str]]:
        # A tag só aparece nas mensagens; a versão real é lida do executável depois.
        with manager._request(f"{BASE}/download/SHA2-256SUMS", accept="text/plain") as response:
            sums = {}
            for line in response.read().decode("utf-8").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    sums[parts[1].lstrip("*")] = parts[0].lower()
        return "latest", f"{BASE}/download/{YTDLP_ASSET}", sums

    manager._latest_ytdlp = latest  # type: ignore[method-assign]
    manager.ensure_ytdlp(lambda message, percent: print(message) if percent in (0, 100) else None,
                         check_now=True)
    manager._save_state()

    started = time.perf_counter()
    toolchain = ToolManager().toolchain()
    elapsed = time.perf_counter() - started
    print(f"yt-dlp {toolchain.ytdlp_version} em {toolchain.ytdlp} "
          f"(pasta: {bool(YTDLP_ONEDIR)}; toolchain em {elapsed:.2f} s)")
    if not toolchain.ytdlp.is_file() or not toolchain.ytdlp_version:
        print("ERRO: o yt-dlp instalado não abriu.")
        return 1

    verbose = run_hidden([str(toolchain.ytdlp), "-v", "--ignore-config", "--simulate", "x"],
                         timeout=120)
    optional = next((line for line in verbose.stderr.splitlines()
                     if "Optional libraries" in line), "")
    print(optional or verbose.stderr[-2000:])
    missing = [name for name in REQUIRED if name not in optional]
    if YTDLP_ONEDIR and missing:
        print("ERRO: faltam no yt-dlp instalado: " + ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
