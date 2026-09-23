"""Validações e redação de dados sensíveis compartilhadas pelo aplicativo."""
from __future__ import annotations

import re
import urllib.parse


_SENSITIVE_QUERY_KEYS = (
    "token", "sig", "signature", "key", "api_key", "apikey", "auth",
    "authorization", "expire", "expires", "policy", "credential", "lsig",
    "spc", "sparams", "xpc",
)
_QUERY_RE = re.compile(
    rf"(?i)([?&](?:{'|'.join(map(re.escape, _SENSITIVE_QUERY_KEYS))})=)[^&#\s]+"
)
# A senha pode conter "/" ou "@": o usuário/senha vai até o ÚLTIMO "@" antes
# do host (``[^\s'"]*@`` é guloso até ele).
_PROXY_RE = re.compile(r"(?i)(--proxy\s+['\"]?[a-z0-9+.-]+://)[^\s'\"]*@")
_URL_CREDENTIAL_RE = re.compile(r"(?i)((?:https?|socks[45]h?)://)[^\s/'\"@]+(?::[^\s'\"]*)?@")
_COOKIE_RE = re.compile(r"(?i)(--cookies(?:-from-browser)?\s+)\S+")
_HEADER_RE = re.compile(r"(?i)(--(?:add-)?headers?\s+)\S+")
_INLINE_SECRET_RE = re.compile(
    r"(?i)\b(authorization|cookie|x-api-key)(\s*[:=]\s*)[^\s,;]+"
)


def validate_media_url(value: str) -> str:
    """Aceita somente URLs HTTP(S) absolutas destinadas ao yt-dlp."""
    url = (value or "").strip()
    parts = urllib.parse.urlsplit(url)
    if parts.scheme.lower() not in {"http", "https"} or not parts.netloc:
        raise ValueError("Use um link que comece com http:// ou https://.")
    if parts.username or parts.password:
        raise ValueError("Links com usuário ou senha embutidos não são aceitos.")
    return url


def redact_sensitive(value: str) -> str:
    """Remove segredos comuns antes que mensagens sejam persistidas em logs."""
    text = str(value)
    text = _PROXY_RE.sub(r"\1***:***@", text)
    text = _URL_CREDENTIAL_RE.sub(r"\1***:***@", text)
    text = _QUERY_RE.sub(r"\1***", text)
    text = _COOKIE_RE.sub(r"\1<cookies>", text)
    text = _HEADER_RE.sub(r"\1***", text)
    return _INLINE_SECRET_RE.sub(r"\1\2***", text)


PROTOCOL_SCHEME = "baixador"


def media_url_from_argument(value: str) -> str:
    """Extrai a URL de mídia de um argumento de linha de comando ou do protocolo.

    Aceita ``https://…`` direto e ``baixador://baixar?url=<URL codificada>``
    (usado pelo bookmarklet/extensão). Devolve ``""`` para qualquer outra coisa.
    O protocolo pode ser acionado por qualquer página web, então o app apenas
    ANALISA o link recebido — nunca inicia um download sozinho.
    """
    text = (value or "").strip()
    if text.lower().startswith(f"{PROTOCOL_SCHEME}:"):
        parts = urllib.parse.urlsplit(text)
        query = urllib.parse.parse_qs(parts.query)
        candidate = (query.get("url") or [""])[0]
        if not candidate:
            # Forma curta: baixador://https://exemplo… (alguns navegadores
            # normalizam para baixador:https://…)
            candidate = text.split(":", 1)[1].lstrip("/")
            if candidate.lower().startswith(("https//", "http//")):
                candidate = candidate.replace("//", "://", 1)
        text = candidate
    try:
        return validate_media_url(text)
    except ValueError:
        return ""
