"""Estratégia de cookies para o yt-dlp.

Existe um motivo técnico para este módulo existir separado. Desde o Chrome 127,
os navegadores baseados em Chromium no Windows guardam a chave dos cookies sob
*App-Bound Encryption*: a DPAPI só devolve a chave para o próprio processo do
navegador. Nenhum programa externo — yt-dlp incluído — consegue mais descriptografar
esses cookies, e a falha aparece como ``Failed to decrypt with DPAPI``.

Isso não é um defeito do yt-dlp nem deste programa: é uma decisão de projeto do
Chromium. Na prática sobram dois caminhos que funcionam no Windows:

1. Firefox (e derivados), que não usa App-Bound Encryption.
2. Um arquivo ``cookies.txt`` exportado do navegador — o caminho recomendado pelo
   próprio yt-dlp para o YouTube, porque cookies lidos de uma sessão aberta são
   rotacionados pelo YouTube e costumam chegar já inválidos.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

from .config import COOKIES_DIR, IS_WINDOWS, Settings

# Navegadores Chromium: no Windows, o App-Bound Encryption impede a leitura.
CHROMIUM_BROWSERS = frozenset({"chrome", "chromium", "edge", "brave", "opera", "vivaldi"})

# Trechos que identificam falha em LER o cookie — não falha do site.
_COOKIE_SOURCE_ERRORS = (
    "failed to decrypt with dpapi",
    "could not copy",
    "unable to read",
    "permission denied",
    "failed to decrypt",
    "could not find",
    "no such file or directory",
)


def is_cookie_source_failure(message: str) -> bool:
    """A falha foi ao obter o cookie, e não uma recusa do site?"""
    low = (message or "").lower()
    return any(needle in low for needle in _COOKIE_SOURCE_ERRORS) and (
        "cookie" in low or "dpapi" in low or "keyring" in low
    )


def browser_is_blocked(browser: str) -> bool:
    """Navegador cuja leitura de cookies não funciona nesta plataforma."""
    return IS_WINDOWS and browser.lower() in CHROMIUM_BROWSERS


def cookie_args(cfg: Settings) -> list[str]:
    """Argumentos de cookie na ordem de preferência: arquivo antes de navegador."""
    if cfg.cookies_file and Path(cfg.cookies_file).is_file():
        return ["--cookies", cfg.cookies_file]
    if cfg.cookies_browser:
        return ["--cookies-from-browser", cfg.cookies_browser]
    return []


def describe_source(cfg: Settings) -> str:
    """Texto curto sobre de onde os cookies estão vindo, para mensagens de erro."""
    if cfg.cookies_file and Path(cfg.cookies_file).is_file():
        return f"arquivo {Path(cfg.cookies_file).name}"
    if cfg.cookies_browser:
        return f"navegador {cfg.cookies_browser}"
    return "nenhuma fonte de cookies"


def _system32(executable: str) -> str:
    """Caminho absoluto de uma ferramenta do Windows — nunca pelo PATH."""
    root = os.environ.get("SystemRoot") or r"C:\Windows"
    return str(Path(root) / "System32" / executable)


def current_user_sid() -> str:
    """SID do usuário atual (ASCII, independe de idioma e de acentos no nome).

    Usar o nome devolvido por ``whoami`` falhava para ``DESKTOP\\joão``: o
    console escreve em CP850 e o Python decodificava em CP1252, então o
    ``icacls`` recebia um nome inexistente e a importação era desfeita.
    """
    from .processes import CREATE_NO_WINDOW

    output = subprocess.run(
        [_system32("whoami.exe"), "/user", "/fo", "csv", "/nh"],
        capture_output=True, text=True, timeout=5, check=True,
        creationflags=CREATE_NO_WINDOW,
    ).stdout.strip()
    sid = output.rsplit(",", 1)[-1].strip().strip('"') if output else ""
    if not sid.startswith("S-1-"):
        raise RuntimeError("Não foi possível identificar o usuário atual.")
    return sid


def import_cookie_file(source: Path) -> tuple[Path, str]:
    """Copia cookies para a área privada do app e restringe o acesso ao usuário.

    Devolve ``(destino, aviso)``. O aviso é preenchido quando o volume não
    suporta ACL (FAT32/exFAT de pendrive): a cópia é mantida mesmo assim.
    """
    from .processes import CREATE_NO_WINDOW

    if not source.is_file():
        raise FileNotFoundError("Arquivo cookies.txt não encontrado.")
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
    destination = COOKIES_DIR / "cookies.txt"
    staged = COOKIES_DIR / "cookies.txt.new"
    warning = ""
    try:
        shutil.copyfile(source, staged)
        os.chmod(staged, stat.S_IRUSR | stat.S_IWUSR)
        if IS_WINDOWS:
            sid = current_user_sid()
            result = subprocess.run(
                [_system32("icacls.exe"), str(staged), "/inheritance:r",
                 "/grant:r", f"*{sid}:(R,W)"],
                capture_output=True, text=True, timeout=10, check=False,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode != 0:
                warning = ("A cópia foi criada, mas este disco não aceita permissões "
                           "por usuário (comum em pendrives FAT32/exFAT).")
        staged.replace(destination)
        return destination, warning
    except Exception:
        staged.unlink(missing_ok=True)
        raise


def cookie_age_days(path: Path) -> int:
    """Idade aproximada do arquivo; zero também cobre relógios desalinhados."""
    return max(0, int((time.time() - path.stat().st_mtime) // 86_400))


EXPORT_INSTRUCTIONS = (
    "Passo a passo simples para salvar um cookies.txt:\n\n"
    "1. No Chrome, Edge ou Firefox, instale a extensão gratuita “Get cookies.txt LOCALLY”.\n"
    "2. Abra uma janela anônima/privativa e entre na sua conta do YouTube.\n"
    "3. Ainda nessa janela, abra youtube.com/robots.txt.\n"
    "4. Clique na extensão e escolha o formato “Netscape cookies.txt”; salve o arquivo.\n"
    "5. Feche a janela anônima e use “Escolher arquivo” aqui para selecionar o .txt.\n\n"
    "Segurança: cookies dão acesso à sua conta. Nunca envie esse arquivo a ninguém; "
    "o aplicativo só o lê no seu computador. Evite a extensão antiga “Get cookies.txt” "
    "sem o sufixo LOCALLY."
)
