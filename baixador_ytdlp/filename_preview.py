"""Pré-visualização local dos campos mais comuns do template do yt-dlp."""
from __future__ import annotations

import re

_FIELD_RE = re.compile(
    r"%\((?P<field>[A-Za-z0-9_]+)(?:\|(?P<default>[^)]+))?\)"
    r"(?:(?:\.(?P<limit>\d+)B)|(?P<kind>[sd]))"
)


def render_filename_preview(template: str, metadata: dict | None, extension: str) -> str:
    """Renderiza uma amostra sem executar yt-dlp nem acessar a rede."""
    data = dict(metadata or {})
    data.setdefault("title", "Título do vídeo")
    data.setdefault("uploader", data.get("channel") or "Canal")
    data.setdefault("channel", data.get("uploader") or "Canal")
    data.setdefault("id", "abc123")
    data.setdefault("upload_date", "20260923")
    data.setdefault("height", 1080)
    data.setdefault("resolution", "1920x1080")
    data["ext"] = extension.lstrip(".") or "mp4"

    def replace(match: re.Match[str]) -> str:
        field = match.group("field")
        value = data.get(field)
        if value in (None, ""):
            value = match.group("default") or f"{{{field}}}"
        if match.group("kind") == "d":
            try:
                return str(int(value))
            except (TypeError, ValueError):
                return "0"
        text = str(value)
        limit = match.group("limit")
        if limit:
            text = text.encode("utf-8")[:int(limit)].decode("utf-8", errors="ignore")
        return text

    rendered = _FIELD_RE.sub(replace, (template or "%(title)s.%(ext)s").strip())
    rendered = rendered.replace("%%", "%")
    return rendered[:260]
