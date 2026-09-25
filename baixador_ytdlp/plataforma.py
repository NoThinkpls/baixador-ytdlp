"""Pontos de diferença entre Windows, macOS e Linux.

O restante do aplicativo deve pedir nomes de executáveis, diretórios de dados e
capacidades da máquina aqui, em vez de espalhar comparações com ``sys.platform``.
As funções recebem os valores como argumentos opcionais para que os testes possam
exercitar as três plataformas sem alterar o computador que está executando-os.
"""
from __future__ import annotations

import os
import platform as _platform
import sys
from collections.abc import Mapping
from pathlib import Path


WINDOWS = "windows"
MACOS = "macos"
LINUX = "linux"


def sistema(platform_name: str | None = None) -> str:
    """Normaliza o identificador do Python para uma das plataformas suportadas."""
    name = platform_name if platform_name is not None else sys.platform
    if name.startswith("win"):
        return WINDOWS
    if name == "darwin":
        return MACOS
    return LINUX


def is_windows(platform_name: str | None = None) -> bool:
    return sistema(platform_name) == WINDOWS


def is_macos(platform_name: str | None = None) -> bool:
    return sistema(platform_name) == MACOS


def is_linux(platform_name: str | None = None) -> bool:
    return sistema(platform_name) == LINUX


def arquitetura(machine: str | None = None) -> str:
    """Arquitetura normalizada, sem presumir como o sistema a escreve."""
    return (machine if machine is not None else _platform.machine()).casefold()


def is_apple_silicon(
    platform_name: str | None = None,
    machine: str | None = None,
) -> bool:
    return is_macos(platform_name) and arquitetura(machine) in {"arm64", "aarch64"}


def nome_binario(nome: str, platform_name: str | None = None) -> str:
    """Acrescenta a extensão de executável somente onde ela é necessária."""
    return f"{nome}.exe" if is_windows(platform_name) else nome


def asset_ytdlp(platform_name: str | None = None) -> str:
    """Nome do artefato standalone publicado pelo projeto yt-dlp."""
    if is_windows(platform_name):
        return "yt-dlp.exe"
    return "yt-dlp_macos" if is_macos(platform_name) else "yt-dlp"


def asset_deno(
    platform_name: str | None = None,
    machine: str | None = None,
) -> str:
    """Nome do ZIP oficial do Deno para a plataforma e arquitetura atuais."""
    arch = "aarch64" if arquitetura(machine) in {"arm64", "aarch64"} else "x86_64"
    if is_windows(platform_name):
        triple = "pc-windows-msvc"
    elif is_macos(platform_name):
        triple = "apple-darwin"
    else:
        triple = "unknown-linux-gnu"
    return f"deno-{arch}-{triple}.zip"


def pasta_dados_usuario(
    app_id: str,
    *,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Diretório de dados gravável do usuário, conforme a convenção do sistema."""
    variables = os.environ if environ is None else environ
    user_home = Path.home() if home is None else Path(home)
    if is_windows(platform_name):
        base = Path(variables.get("LOCALAPPDATA") or user_home / "AppData" / "Local")
    elif is_macos(platform_name):
        base = user_home / "Library" / "Application Support"
    else:
        base = Path(variables.get("XDG_DATA_HOME") or user_home / ".local" / "share")
    return base / app_id
