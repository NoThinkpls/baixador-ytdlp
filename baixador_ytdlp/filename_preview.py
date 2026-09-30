"""Pré-visualização local dos campos mais comuns do template do yt-dlp."""
from __future__ import annotations

import re
from datetime import datetime

# Modelos prontos para o campo "Nome do arquivo" (o primeiro é o padrão do app).
FILENAME_PRESETS = (
    ("Título [id] (padrão)", "%(title).180B [%(id)s].%(ext)s"),
    ("Plataforma - data - título [id]",
     "%(extractor_key)s - %(upload_date>%Y-%m-%d|sem data)s - %(title).100B [%(id).40B].%(ext)s"),
    ("Só o título", "%(title).180B.%(ext)s"),
)

_FIELD_RE = re.compile(
    r"%\((?P<field>[A-Za-z0-9_]+)(?:>(?P<fmt>[^|)]+))?(?:\|(?P<default>[^)]+))?\)"
    r"(?:(?:\.(?P<limit>\d+)B)|(?P<kind>[sd]))"
)


def render_filename_preview(template: str, metadata: dict | None, extension: str) -> str:
    """Renderiza uma amostra sem executar yt-dlp nem acessar a rede."""
    data = dict(metadata or {})
    data.setdefault("title", "Título do vídeo")
    data.setdefault("uploader", data.get("channel") or "Canal")
    data.setdefault("channel", data.get("uploader") or "Canal")
    data.setdefault("id", "abc123")
    data.setdefault("extractor_key", "YouTube")
    data.setdefault("upload_date", "20260923")
    data.setdefault("height", 1080)
    data.setdefault("resolution", "1920x1080")
    data["ext"] = extension.lstrip(".") or "mp4"

    def replace(match: re.Match[str]) -> str:
        field = match.group("field")
        value = data.get(field)
        if value in (None, ""):
            value = match.group("default") or f"{{{field}}}"
        if value != match.group("default") and match.group("fmt"):
            try:
                value = datetime.strptime(str(value), "%Y%m%d").strftime(match.group("fmt"))
            except ValueError:
                value = match.group("default") or str(value)
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
