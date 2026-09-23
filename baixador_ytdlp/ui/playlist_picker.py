"""Diálogo para escolher quais itens de uma playlist baixar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QListWidget, QListWidgetItem,
                               QVBoxLayout)

from ..probe import PlaylistEntry, compress_indices
from .components import Button, Headline, Muted, PrimaryButton, TextField


class PlaylistPickerDialog(QDialog):
    """Lista com caixas de seleção, busca e seleção em massa.

    Devolve em :meth:`selection` o texto no formato do ``--playlist-items``
    (``1-3,7``); vazio quando todos os itens estão marcados.
    """

    def __init__(self, entries: list[PlaylistEntry], current: str = "", parent=None):
        super().__init__(parent)
        self.entries = entries
        self.setWindowTitle("Escolher itens da playlist")
        self.resize(640, 560)
        self.setMinimumSize(520, 420)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(10)
        root.addWidget(Headline(f"{len(entries)} itens na playlist", self))
        root.addWidget(Muted("Desmarque o que não quer baixar. A numeração segue a "
                             "ordem da playlist.", self))

        self.search = TextField("Filtrar por título", self)
        self.search.textChanged.connect(self._filter)
        root.addWidget(self.search)

        self.list = QListWidget(self)
        self.list.setAccessibleName("Itens da playlist")
        chosen = self._parse(current) if current else None
        for entry in entries:
            label = f"{entry.index:>3}. {entry.title}"
            if entry.duration and entry.duration != "—":
                label += f"  ·  {entry.duration}"
            item = QListWidgetItem(label, self.list)
            item.setData(Qt.ItemDataRole.UserRole, entry.index)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            checked = chosen is None or entry.index in chosen
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.list.itemChanged.connect(self._update_count)
        root.addWidget(self.list, 1)

        tools = QHBoxLayout()
        all_button = Button("Marcar visíveis", "success", "ghost", self)
        none_button = Button("Desmarcar visíveis", "close", "ghost", self)
        all_button.clicked.connect(lambda: self._set_visible(True))
        none_button.clicked.connect(lambda: self._set_visible(False))
        tools.addWidget(all_button)
        tools.addWidget(none_button)
        tools.addStretch(1)
        self.count = Muted("", self)
        tools.addWidget(self.count)
        root.addLayout(tools)

        actions = QHBoxLayout()
        actions.addStretch(1)
        cancel = Button("Cancelar", "close", "secondary", self)
        cancel.clicked.connect(self.reject)
        self.ok = PrimaryButton("Usar seleção", "download", self)
        self.ok.clicked.connect(self.accept)
        actions.addWidget(cancel)
        actions.addWidget(self.ok)
        root.addLayout(actions)
        self._update_count()

    @staticmethod
    def _parse(text: str) -> set[int]:
        result: set[int] = set()
        for part in text.split(","):
            if "-" in part:
                start, _, end = part.partition("-")
                if start.isdigit() and end.isdigit():
                    result.update(range(int(start), int(end) + 1))
            elif part.strip().isdigit():
                result.add(int(part))
        return result

    def _filter(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().casefold())

    def _set_visible(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        self.list.blockSignals(True)
        for row in range(self.list.count()):
            item = self.list.item(row)
            if not item.isHidden():
                item.setCheckState(state)
        self.list.blockSignals(False)
        self._update_count()

    def checked_indices(self) -> list[int]:
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole)
                for row in range(self.list.count())
                if self.list.item(row).checkState() == Qt.CheckState.Checked]

    def _update_count(self, *_args) -> None:
        chosen = len(self.checked_indices())
        self.count.setText(f"{chosen} de {len(self.entries)} selecionados")
        self.ok.setEnabled(chosen > 0)

    def selection(self) -> str:
        indices = self.checked_indices()
        return "" if len(indices) == len(self.entries) else compress_indices(indices)
