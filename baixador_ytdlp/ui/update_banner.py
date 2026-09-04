"""Faixa inferior não intrusiva para uma atualização disponível."""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout

from qfluentwidgets import (BodyLabel, CaptionLabel, CardWidget, FluentIcon as FIF,
                            PrimaryPushButton, PushButton)

from ..updater import ReleaseInfo


class UpdateBanner(CardWidget):
    """Mostra estado da atualização sem bloquear a página que a pessoa está usando."""

    update_requested = Signal()
    dismissed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._release: ReleaseInfo | None = None
        self.setObjectName("appUpdateBanner")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 12, 16, 12)
        layout.setSpacing(12)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = BodyLabel("Atualização disponível", self)
        self.details = CaptionLabel("", self)
        self.details.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.details)
        layout.addLayout(texts, 1)

        self.update_button = PrimaryPushButton(FIF.UPDATE, "Atualizar", self)
        self.update_button.clicked.connect(self.update_requested)
        self.dismiss_button = PushButton(FIF.CLOSE, "Agora não", self)
        self.dismiss_button.clicked.connect(self.dismissed)
        layout.addWidget(self.update_button)
        layout.addWidget(self.dismiss_button)

        self.hide()

    @property
    def release(self) -> ReleaseInfo | None:
        return self._release

    def show_release(self, release: ReleaseInfo) -> None:
        self._release = release
        self.title.setText(f"Nova versão {release.tag} disponível")
        self.details.setText(
            "A atualização será baixada e conferida antes de abrir o instalador."
        )
        self.update_button.setEnabled(True)
        self.dismiss_button.setEnabled(True)
        self.update_button.setText("Atualizar")
        self.show()

    def show_download_progress(self, received: int, total: int) -> None:
        self.update_button.setEnabled(False)
        self.dismiss_button.setEnabled(False)
        if total > 0:
            percent = min(100, round(received * 100 / total))
            self.details.setText(f"Baixando e verificando a atualização… {percent}%")
        else:
            self.details.setText("Baixando e verificando a atualização…")
        self.update_button.setText("Baixando…")

    def show_error(self, message: str) -> None:
        self.details.setText(message)
        self.update_button.setEnabled(True)
        self.dismiss_button.setEnabled(True)
        self.update_button.setText("Tentar de novo")
