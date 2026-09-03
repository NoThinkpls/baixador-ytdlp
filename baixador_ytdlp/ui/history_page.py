"""Página 'Histórico': o que já foi baixado, com abrir, legendar e baixar de novo."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, PushButton,
                            SmoothScrollArea, StrongBodyLabel, TitleLabel, TransparentToolButton)

from ..config import Settings
from ..history import History, HistoryEntry
from .queue_page import reveal


class HistoryCard(CardWidget):
    reopen = Signal(str)        # url
    transcribe = Signal(str)    # caminho
    forget = Signal(object)     # HistoryEntry

    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent)
        self.entry = entry

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        title = StrongBodyLabel(entry.title, self)
        title.setWordWrap(True)
        kind = "áudio" if entry.audio_only else (entry.container or "vídeo")
        meta = CaptionLabel(f"{entry.date_label} · {kind} · {entry.folder}", self)
        meta.setWordWrap(True)
        texts.addWidget(title)
        texts.addWidget(meta)
        layout.addLayout(texts, 1)

        exists = bool(entry.path) and Path(entry.path).exists()

        open_btn = TransparentToolButton(FIF.FOLDER, self)
        open_btn.setToolTip("Mostrar na pasta")
        open_btn.setEnabled(exists)
        open_btn.clicked.connect(lambda: reveal(Path(entry.path)))

        sub_btn = TransparentToolButton(FIF.MESSAGE, self)
        sub_btn.setToolTip("Gerar legenda deste arquivo")
        sub_btn.setEnabled(exists and not entry.audio_only or exists)
        sub_btn.clicked.connect(lambda: self.transcribe.emit(entry.path))

        again_btn = TransparentToolButton(FIF.SYNC, self)
        again_btn.setToolTip("Baixar de novo")
        again_btn.clicked.connect(lambda: self.reopen.emit(entry.url))

        del_btn = TransparentToolButton(FIF.DELETE, self)
        del_btn.setToolTip("Remover do histórico")
        del_btn.clicked.connect(lambda: self.forget.emit(entry))

        for button in (open_btn, sub_btn, again_btn, del_btn):
            layout.addWidget(button)


class HistoryPage(QWidget):
    reopen_requested = Signal(str)
    transcribe_requested = Signal(str)

    def __init__(self, cfg: Settings, history: History, parent=None):
        super().__init__(parent)
        self.setObjectName("historyPage")
        self.cfg = cfg
        self.history = history
        self._dirty = True          # só reconstrói os cartões quando algo mudou
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(TitleLabel("Histórico", self), 1)
        clear = PushButton(FIF.BROOM, "Limpar tudo", self)
        clear.clicked.connect(self._clear)
        header.addWidget(clear)
        root.addLayout(header)

        self.empty = BodyLabel("Nada aqui ainda. O que você baixar aparece nesta lista.", self)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty, 1)

        self.scroll = SmoothScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.container = QWidget(self.scroll)
        self.container.setStyleSheet("background: transparent;")
        self.cards = QVBoxLayout(self.container)
        self.cards.setContentsMargins(0, 0, 8, 0)
        self.cards.setSpacing(8)
        self.cards.addStretch(1)
        self.scroll.setWidget(self.container)
        self.scroll.hide()
        root.addWidget(self.scroll, 4)

    # ------------------------------------------------------------- dados
    def invalidate(self) -> None:
        """Marca a lista como desatualizada; a reconstrução só ocorre ao abrir a aba."""
        self._dirty = True

    def showEvent(self, event):  # noqa: N802 - assinatura do Qt
        if self._dirty:
            self.rebuild()
        super().showEvent(event)

    def rebuild(self) -> None:
        self._dirty = False
        while self.cards.count() > 1:
            item = self.cards.takeAt(0)
            if widget := item.widget():
                widget.deleteLater()

        entries = self.history.entries[:self.cfg.history_limit]
        for entry in entries:
            card = HistoryCard(entry, self.container)
            card.reopen.connect(self.reopen_requested)
            card.transcribe.connect(self.transcribe_requested)
            card.forget.connect(self._forget)
            self.cards.insertWidget(self.cards.count() - 1, card)

        self.scroll.setVisible(bool(entries))
        self.empty.setVisible(not entries)

    def _forget(self, entry: HistoryEntry) -> None:
        try:
            index = self.history.entries.index(entry)
        except ValueError:
            return
        self.history.remove(index)
        self.history.flush()
        self.rebuild()

    def _clear(self) -> None:
        self.history.clear()
        self.history.flush()
        self.rebuild()
