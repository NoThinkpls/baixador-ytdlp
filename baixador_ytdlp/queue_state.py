"""Persistência leve dos itens que ainda não terminaram na fila.

O yt-dlp já preserva os arquivos ``.part`` e continua deles com ``--continue``.
Este módulo preserva a outra metade da retomada: se o aplicativo, o Windows ou
o Linux forem fechados no meio de uma fila, os jobs voltam como pendentes na
próxima abertura. Não guarda cookies, cabeçalhos ou qualquer outro segredo.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Iterable

from .config import QUEUE_STATE_PATH
from .downloader import DownloadOptions


class QueueState:
    """Arquivo atômico com os jobs que podem ser retomados."""

    def __init__(self, path: Path = QUEUE_STATE_PATH):
        self.path = path

    def load(self) -> list[DownloadOptions]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        if not isinstance(raw, list):
            return []

        known = set(DownloadOptions.__dataclass_fields__)
        result: list[DownloadOptions] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            values = {key: value for key, value in item.items() if key in known}
            if not isinstance(values.get("url"), str) or not isinstance(values.get("output_dir"), str):
                continue
            try:
                result.append(DownloadOptions(**values))
            except (TypeError, ValueError):
                continue
        return result

    def save(self, options: Iterable[DownloadOptions]) -> None:
        """Substitui o estado só depois de o arquivo novo estar completo."""
        entries = [asdict(item) for item in options]
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.path)
        except OSError:
            # A retomada é uma conveniência; falha de disco não pode interromper
            # nem cancelar um download que já esteja válido.
            pass

