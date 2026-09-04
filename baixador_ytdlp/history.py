"""Histórico dos downloads concluídos.

Arquivo pequeno em JSON, gravado de forma atômica e com teto de itens. É lido uma
vez na abertura e mantido em memória — a página de histórico nunca toca no disco
durante a navegação.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .config import HISTORY_PATH


DOWNLOAD = "download"
TRANSCRIPTION = "transcription"


@dataclass
class HistoryEntry:
    title: str
    url: str = ""
    path: str = ""
    files: int = 1
    audio_only: bool = False
    container: str = ""
    when: float = field(default_factory=time.time)
    kind: str = DOWNLOAD          # download | transcription
    folder_path: str = ""         # pasta de saída, guardada à parte do arquivo
    source: str = ""              # transcrição: a mídia que a originou

    @property
    def date_label(self) -> str:
        return time.strftime("%d/%m/%Y %H:%M", time.localtime(self.when))

    @property
    def is_transcription(self) -> bool:
        return self.kind == TRANSCRIPTION

    @property
    def folder(self) -> Path:
        """Pasta do item. Guardada explicitamente porque o caminho do arquivo
        pode apontar para um temporário que o yt-dlp já apagou."""
        if self.folder_path:
            return Path(self.folder_path)
        target = Path(self.path)
        return target.parent if target.suffix else target

    def existing_file(self) -> Path | None:
        """O arquivo, se ele ainda estiver lá. Confere no disco, não na memória."""
        if not self.path:
            return None
        target = Path(self.path)
        try:
            return target if target.is_file() else None
        except OSError:
            return None

    def existing_source(self) -> Path | None:
        """A mídia de origem de uma transcrição, se ainda existir."""
        if not self.source:
            return None
        target = Path(self.source)
        try:
            return target if target.is_file() else None
        except OSError:
            return None

    def existing_folder(self) -> Path | None:
        folder = self.folder
        try:
            return folder if folder.is_dir() else None
        except OSError:
            return None


class History:
    """Lista dos downloads concluídos, do mais recente para o mais antigo."""

    def __init__(self, path: Path = HISTORY_PATH, limit: int = 200):
        self.path = path
        self.limit = limit
        self.entries: list[HistoryEntry] = []
        self._dirty = False

    # ------------------------------------------------------------------ disco
    def load(self) -> "History":
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return self
        known = set(HistoryEntry.__dataclass_fields__)
        self.entries = [
            HistoryEntry(**{k: v for k, v in item.items() if k in known})
            for item in raw if isinstance(item, dict) and item.get("title")
        ]
        return self

    def flush(self) -> None:
        """Só escreve quando algo mudou — evita I/O a cada fechamento de janela."""
        if not self._dirty:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps([asdict(e) for e in self.entries], ensure_ascii=False, indent=1),
                encoding="utf-8")
            tmp.replace(self.path)
            self._dirty = False
        except OSError:
            pass

    # ------------------------------------------------------------------ dados
    def add(self, entry: HistoryEntry) -> None:
        self.entries.insert(0, entry)
        del self.entries[self.limit:]
        self._dirty = True

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.entries):
            del self.entries[index]
            self._dirty = True

    def clear(self) -> None:
        if self.entries:
            self.entries.clear()
            self._dirty = True
