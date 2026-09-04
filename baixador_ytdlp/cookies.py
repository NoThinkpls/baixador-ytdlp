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

from pathlib import Path

from .config import IS_WINDOWS, Settings

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


EXPORT_INSTRUCTIONS = (
    "Como exportar o cookies.txt do jeito que o YouTube aceita:\n\n"
    "1. Instale uma extensão de exportação de cookies no formato Netscape.\n"
    "2. Abra uma janela ANÔNIMA e faça login no YouTube.\n"
    "3. Na mesma aba, vá para youtube.com/robots.txt.\n"
    "4. Exporte os cookies de youtube.com e feche a janela anônima em seguida.\n"
    "5. Aponte o arquivo salvo no campo 'Arquivo cookies.txt'.\n\n"
    "A janela anônima importa: o YouTube rotaciona os cookies de abas abertas por "
    "segurança, então cookies tirados da sua sessão normal costumam já chegar "
    "inválidos. Fechar a janela sem reabrir o YouTube congela a sessão exportada."
)
