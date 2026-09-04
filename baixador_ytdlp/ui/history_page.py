"""Página 'Histórico': downloads e transcrições, cada tipo com as suas ações."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF, PushButton,
                            SmoothScrollArea, StrongBodyLabel, TitleLabel, TransparentToolButton)

from ..config import Settings
from ..history import History, HistoryEntry
from .queue_page import reveal

MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv",
                  ".mp3", ".m4a", ".opus", ".flac", ".wav", ".aac", ".ogg", ".m4b"}


class HistoryCard(CardWidget):
    """Uma linha do histórico. As ações são ligadas ou desligadas conforme o que
    existe no disco AGORA — não conforme o que existia quando o item foi criado."""

    reopen = Signal(str)          # url, para baixar de novo
    transcribe = Signal(str)      # caminho da mídia, para legendar
    forget = Signal(object)       # HistoryEntry

    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent)
        self.entry = entry

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(10)

        badge = TransparentToolButton(
            FIF.MESSAGE if entry.is_transcription else FIF.CLOUD_DOWNLOAD, self)
        badge.setEnabled(False)
        badge.setToolTip("Transcrição" if entry.is_transcription else "Download")
        layout.addWidget(badge)

        texts = QVBoxLayout()
        texts.setSpacing(1)
        title = StrongBodyLabel(entry.title, self)
        title.setWordWrap(True)
        meta = CaptionLabel(self._meta_text(entry), self)
        meta.setWordWrap(True)
        texts.addWidget(title)
        texts.addWidget(meta)
        layout.addLayout(texts, 1)

        for button in self._actions(entry):
            layout.addWidget(button)

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
    def _actions(self, entry: HistoryEntry) -> list[TransparentToolButton]:
        arquivo = entry.existing_file()
        pasta = entry.existing_folder()

        # "Mostrar na pasta" vale mesmo sem o arquivo: a pasta continua útil.
        # Era isto que travava os botões — a checagem antiga exigia o arquivo,
        # e o caminho gravado podia apontar para um temporário já removido.
        abrir = TransparentToolButton(FIF.FOLDER, self)
        abrir.setToolTip("Mostrar na pasta" if arquivo else "Abrir a pasta")
        abrir.setEnabled(bool(arquivo or pasta))
        abrir.clicked.connect(lambda: self._reveal(arquivo, pasta))
        botoes = [abrir]

        if entry.is_transcription:
            ver = TransparentToolButton(FIF.DOCUMENT, self)
            ver.setToolTip("Abrir a legenda")
            ver.setEnabled(bool(arquivo))
            ver.clicked.connect(lambda: self._open_file(arquivo))
            botoes.append(ver)

            origem = entry.existing_source()
            refazer = TransparentToolButton(FIF.SYNC, self)
            refazer.setToolTip("Transcrever de novo" if origem
                               else "A mídia de origem não está mais no lugar")
            refazer.setEnabled(bool(origem))
            refazer.clicked.connect(lambda: self.transcribe.emit(str(origem)))
            botoes.append(refazer)
        else:
            legendar = TransparentToolButton(FIF.MESSAGE, self)
            pode = bool(arquivo) and arquivo.suffix.lower() in MEDIA_SUFFIXES
            legendar.setToolTip("Gerar legenda deste arquivo" if pode
                                else "O arquivo não está mais no lugar")
            legendar.setEnabled(pode)
            legendar.clicked.connect(lambda: self.transcribe.emit(str(arquivo)))
            botoes.append(legendar)

            de_novo = TransparentToolButton(FIF.SYNC, self)
            de_novo.setToolTip("Baixar de novo" if entry.url else "Sem link guardado")
            de_novo.setEnabled(bool(entry.url))
            de_novo.clicked.connect(lambda: self.reopen.emit(entry.url))
            botoes.append(de_novo)

        remover = TransparentToolButton(FIF.DELETE, self)
        remover.setToolTip("Remover do histórico")
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
        root.setContentsMargins(28, 16, 28, 20)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.addWidget(TitleLabel("Histórico", self), 1)
        self.summary = CaptionLabel("", self)
        header.addWidget(self.summary)
        clear = PushButton(FIF.BROOM, "Limpar tudo", self)
        clear.clicked.connect(self._clear)
        header.addWidget(clear)
        root.addLayout(header)

        self.empty = BodyLabel(
            "Nada aqui ainda. O que você baixar ou transcrever aparece nesta lista.", self)
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
