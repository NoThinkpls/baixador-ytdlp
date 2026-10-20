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


def execucao_empacotada() -> bool:
    """Indica se o app está dentro de uma distribuição PyInstaller ou Nuitka.

    PyInstaller expõe ``sys.frozen``. Nuitka usa o global ``__compiled__`` em
    cada módulo compilado. Concentrar essa diferença aqui evita que detalhes do
    empacotador vazem para caminhos, recursos e ferramentas embarcadas.
    """
    return bool(getattr(sys, "frozen", False) or globals().get("__compiled__"))


def pasta_do_executavel() -> Path:
    """Retorna a raiz da distribuição ou a raiz do projeto em desenvolvimento."""
    if execucao_empacotada():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


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


def ytdlp_em_pasta(
    platform_name: str | None = None,
    machine: str | None = None,
) -> tuple[str, str] | None:
    """(ZIP oficial, executável dentro dele) da distribuição do yt-dlp em pasta.

    O executável de arquivo único se descompacta numa pasta temporária a cada
    chamada (o dobro do tempo para abrir) e o ``yt-dlp`` do Linux é o zipimport,
    que depende do Python do sistema e vem sem curl_cffi, mutagen e
    secretstorage. A versão em pasta abre direto e traz essas dependências.
    ``None`` quando o projeto não publica a pasta para esta arquitetura.
    """
    if is_windows(platform_name):
        return "yt-dlp_win.zip", "yt-dlp.exe"
    if is_macos(platform_name):
        return "yt-dlp_macos.zip", "yt-dlp_macos"
    arch = arquitetura(machine)
    if arch in {"x86_64", "amd64"}:
        return "yt-dlp_linux.zip", "yt-dlp_linux"
    if arch in {"aarch64", "arm64"}:
        return "yt-dlp_linux_aarch64.zip", "yt-dlp_linux_aarch64"
    return None


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


# Variáveis que o PyInstaller aponta para dentro do pacote no Linux. Herdadas por
# xdg-open, gerenciador de arquivos e navegador, faziam esses programas carregarem
# as bibliotecas e os plugins Qt do app em vez dos do sistema (e fechar ao abrir).
_VARIAVEIS_QT_DO_PACOTE = ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH")


def restaurar_bibliotecas_do_sistema(
    environ: dict[str, str] | None = None,
    *,
    frozen: bool | None = None,
    platform_name: str | None = None,
) -> None:
    """Devolve o ``LD_LIBRARY_PATH`` original aos processos filhos no Linux.

    O carregador do glibc só lê a variável quando o processo começa, então o próprio
    app continua achando as bibliotecas do pacote; só os programas abertos depois
    deixam de herdar a pasta ``_internal``.
    """
    variables = os.environ if environ is None else environ
    frozen = execucao_empacotada() if frozen is None else frozen
    if not frozen or not is_linux(platform_name):
        return
    original = variables.pop("LD_LIBRARY_PATH_ORIG", None)
    if original:
        variables["LD_LIBRARY_PATH"] = original
    else:
        variables.pop("LD_LIBRARY_PATH", None)


def liberar_caminhos_qt_do_pacote(
    library_paths: list[str],
    environ: dict[str, str] | None = None,
    *,
    frozen: bool | None = None,
    platform_name: str | None = None,
) -> None:
    """Remove do ambiente os caminhos de plugins Qt do pacote (Linux empacotado).

    Chame com ``QCoreApplication.libraryPaths()`` já calculado: o Qt guarda a lista
    na primeira consulta, então o app segue achando os próprios plugins.
    """
    variables = os.environ if environ is None else environ
    frozen = execucao_empacotada() if frozen is None else frozen
    if not frozen or not is_linux(platform_name) or not library_paths:
        return
    for name in _VARIAVEIS_QT_DO_PACOTE:
        variables.pop(name, None)
