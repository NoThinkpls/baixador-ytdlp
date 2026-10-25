"""Página 'Histórico': downloads, transcrições, cortes e ferramentas, cada tipo com as suas ações."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QVBoxLayout, QWidget

from ..config import Settings
from ..history import History, HistoryEntry
from .components import (Button, EmptyState, Headline, IconButton, ListRow, Muted,
                         PageHeader, ScrollColumn)
from .queue_page import reveal, state_badge

# Ícone e cor do disco de cada tipo de item.
BADGES = {"download": ("download", "success"), "transcription": ("captions", "accent"),
          "clip": ("cut", "warning"), "tool": ("tools", "neutral")}
MEDIA_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v", ".flv", ".wmv",
                  ".mp3", ".m4a", ".opus", ".flac", ".wav", ".aac", ".ogg", ".m4b"}


def summary_text(entries: list[HistoryEntry]) -> str:
    """Contagem por tipo, só dos tipos que aparecem: "3 downloads · 1 corte"."""
    nomes = (("download", "download", "downloads"), ("transcription", "transcrição", "transcrições"),
             ("clip", "corte", "cortes"), ("tool", "ferramenta", "ferramentas"))
    partes = []
    for kind, singular, plural in nomes:
        total = sum(1 for entry in entries if (entry.kind if entry.kind in BADGES
                                                  else "download") == kind)
        if total:
            partes.append(f"{total} {singular if total == 1 else plural}")
    return " · ".join(partes)


class HistoryCard(ListRow):
    """Uma linha do histórico. As ações são ligadas ou desligadas conforme o que
    existe no disco AGORA — não conforme o que existia quando o item foi criado."""

    reopen = Signal(str)          # url, para baixar de novo
    transcribe = Signal(str)      # caminho da mídia, para legendar
    new_clips = Signal(str)       # arquivo ou link de origem, para fazer outros cortes
    forget = Signal(object)       # HistoryEntry

    def __init__(self, entry: HistoryEntry, parent=None):
        super().__init__(parent, padding=(14, 11, 12, 11), spacing=12)
        self.entry = entry

        icon, tone = BADGES.get(entry.kind, BADGES["download"])
        self.body.addWidget(state_badge(self, icon, tone), 0, Qt.AlignmentFlag.AlignVCenter)

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
        elif entry.is_clip:
            tipo = " ".join(filter(None, ["corte vertical", entry.operation]))
        elif entry.is_tool:
            tipo = entry.operation or "ferramenta"
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
        elif entry.is_clip or entry.is_tool:
            ver = IconButton("play", "Abrir o arquivo", self)
            ver.setEnabled(bool(arquivo))
            ver.clicked.connect(lambda: self._open_file(arquivo))
            botoes.append(ver)

            pode = bool(arquivo) and arquivo.suffix.lower() in MEDIA_SUFFIXES
            legendar = IconButton("captions", "Gerar legenda deste arquivo" if pode
                                  else "O arquivo não está mais no lugar", self)
            legendar.setEnabled(pode)
            legendar.clicked.connect(lambda: self.transcribe.emit(str(arquivo)))
            botoes.append(legendar)

            if entry.is_clip:
                # Link continua valendo; arquivo, só se ainda estiver no lugar.
                origem = entry.source if "://" in entry.source else entry.existing_source()
                outro = IconButton("cut", "Fazer outros cortes deste vídeo" if origem
                                   else "O vídeo de origem não está mais no lugar", self)
                outro.setEnabled(bool(origem))
                outro.clicked.connect(lambda: self.new_clips.emit(str(origem)))
                botoes.append(outro)
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
    clips_requested = Signal(str)

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

        header = PageHeader("Histórico", "Tudo o que você baixou, legendou, cortou e converteu nesta máquina.", self)
        self.summary = Muted("", header)
        self.summary.setWordWrap(False)
        header.add_action(self.summary)
        clear = Button("Limpar tudo", "sweep", "secondary", header)
        clear.clicked.connect(self._clear)
        header.add_action(clear)
        root.addWidget(header)

        self.empty = EmptyState(
            "history", "Nada guardado ainda",
            "O que você baixar, transcrever, cortar ou converter aparece nesta lista, só na sua máquina.", self)
        root.addWidget(self.empty, 1)

        self.scroll_area = ScrollColumn(self, spacing=8)
        self.cards = self.scroll_area.column
        self.cards.addStretch(1)
        self.container = self.scroll_area.body
        self.scroll_area.hide()
        root.addWidget(self.scroll_area, 4)

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
            if item is not None and (widget := item.widget()):
                widget.deleteLater()

        entries = self.history.entries[:self.cfg.history_limit]
        for entry in entries:
            card = HistoryCard(entry, self.container)
            card.reopen.connect(self.reopen_requested)
            card.transcribe.connect(self.transcribe_requested)
            card.new_clips.connect(self.clips_requested)
            card.forget.connect(self._forget)
            self.cards.insertWidget(self.cards.count() - 1, card)

        self.summary.setText(summary_text(entries))

        self.scroll_area.setVisible(bool(entries))
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
