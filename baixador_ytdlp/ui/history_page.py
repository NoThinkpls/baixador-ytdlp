"""Página 'Histórico': downloads e transcrições, cada tipo com as suas ações."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from ..config import Settings
from ..history import History, HistoryEntry
from .components import (Button, EmptyState, Headline, IconButton, ListRow, Muted,
                         PageHeader, ScrollColumn)
from .queue_page import reveal, state_badge

MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv",
                  ".mp3", ".m4a", ".opus", ".flac", ".wav", ".aac", ".ogg", ".m4b"}


class HistoryCard(ListRow):
    """Uma linha do histórico. As ações são ligadas ou desligadas conforme o que
    existe no disco AGORA — não conforme o que existia quando o item foi criado."""

    reopen = Signal(str)          # url, para baixar de novo
    transcribe = Signal(str)      # caminho da mídia, para legendar
    forget = Signal(object)       # HistoryEntry

    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent, padding=(14, 11, 12, 11), spacing=12)
        self.entry = entry

        transcription = entry.is_transcription
        self.body.addWidget(
            state_badge(self, "captions" if transcription else "download",
                        "accent" if transcription else "success"),
            0, Qt.AlignmentFlag.AlignVCenter)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(Headline(entry.title, self, wrap=True))
        texts.addWidget(Muted(self._meta_text(entry), self))
        self.body.addLayout(texts, 1)

        for button in self._actions(entry):
            self.body.addWidget(button, 0, Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------ texto
    @staticmethod
    def _meta_text(entry: HistoryEntry) -> str:
        arquivo = entry.existing_file()
        if entry.is_transcription:
            tipo = f"legenda {Path(entry.path).suffix.lstrip('.').upper() or '—'}"
        else:
            tipo = "áudio" if entry.audio_only else (entry.container or "vídeo")
        partes = [entry.date_label, tipo, str(entry.folder)]
        if entry.path and arquivo is None:
            partes.append("arquivo não está mais lá")
        return " · ".join(partes)

    # ------------------------------------------------------------------ ações
    def _actions(self, entry: HistoryEntry) -> list[IconButton]:
        arquivo = entry.existing_file()
        pasta = entry.existing_folder()

        # "Mostrar na pasta" vale mesmo sem o arquivo: a pasta continua útil.
        abrir = IconButton("folder", "Mostrar na pasta" if arquivo else "Abrir a pasta", self)
        abrir.setEnabled(bool(arquivo or pasta))
        abrir.clicked.connect(lambda: self._reveal(arquivo, pasta))
        botoes = [abrir]

        if entry.is_transcription:
            ver = IconButton("document", "Abrir a legenda", self)
            ver.setEnabled(bool(arquivo))
            ver.clicked.connect(lambda: self._open_file(arquivo))
            botoes.append(ver)

            origem = entry.existing_source()
            refazer = IconButton("refresh", "Transcrever de novo" if origem
                                 else "A mídia de origem não está mais no lugar", self)
            refazer.setEnabled(bool(origem))
            refazer.clicked.connect(lambda: self.transcribe.emit(str(origem)))
            botoes.append(refazer)
        else:
            pode = bool(arquivo) and arquivo.suffix.lower() in MEDIA_SUFFIXES
            legendar = IconButton("captions", "Gerar legenda deste arquivo" if pode
                                  else "O arquivo não está mais no lugar", self)
            legendar.setEnabled(pode)
            legendar.clicked.connect(lambda: self.transcribe.emit(str(arquivo)))
            botoes.append(legendar)

            de_novo = IconButton("refresh", "Baixar de novo" if entry.url
                                 else "Sem link guardado", self)
            de_novo.setEnabled(bool(entry.url))
            de_novo.clicked.connect(lambda: self.reopen.emit(entry.url))
            botoes.append(de_novo)

        remover = IconButton("trash", "Remover do histórico", self)
        remover.clicked.connect(lambda: self.forget.emit(entry))
        botoes.append(remover)
        return botoes

    def _reveal(self, arquivo: Path | None, pasta: Path | None) -> None:
        if arquivo:
            reveal(arquivo)
        elif pasta:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

    def _open_file(self, arquivo: Path | None) -> None:
        if arquivo:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(arquivo)))


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
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(16)

        header = PageHeader("Histórico", "Tudo o que você baixou e legendou nesta máquina.", self)
        self.summary = Muted("", header)
        self.summary.setWordWrap(False)
        header.add_action(self.summary)
        clear = Button("Limpar tudo", "sweep", "secondary", header)
        clear.clicked.connect(self._clear)
        header.add_action(clear)
        root.addWidget(header)

        self.empty = EmptyState(
            "history", "Nada guardado ainda",
            "O que você baixar ou transcrever aparece nesta lista, só na sua máquina.", self)
        root.addWidget(self.empty, 1)

        self.scroll = ScrollColumn(self, spacing=8)
        self.cards = self.scroll.column
        self.cards.addStretch(1)
        self.container = self.scroll.body
        self.scroll.hide()
        root.addWidget(self.scroll, 4)

    # ------------------------------------------------------------- dados
    def invalidate(self) -> None:
        """Marca a lista como desatualizada; a reconstrução só ocorre ao abrir a aba."""
        self._dirty = True

    def showEvent(self, event):  # noqa: N802 - assinatura do Qt
        # Sempre reconstrói ao abrir: arquivos podem ter sido movidos ou apagados
        # fora do aplicativo, e os botões precisam refletir o disco de agora.
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

        downloads = sum(1 for e in entries if not e.is_transcription)
        legendas = len(entries) - downloads
        partes = []
        if downloads:
            partes.append(f"{downloads} download{'s' if downloads > 1 else ''}")
        if legendas:
            partes.append(f"{legendas} transcriç{'ões' if legendas > 1 else 'ão'}")
        self.summary.setText(" · ".join(partes))

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
