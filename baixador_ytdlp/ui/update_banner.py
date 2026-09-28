"""Faixa inferior não intrusiva para uma atualização disponível."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..updater import ReleaseInfo
from . import icons, theme
from .components import Button, Headline, Muted, PrimaryButton


class UpdateBanner(QFrame):
    """Mostra o estado da atualização sem bloquear a página que a pessoa está usando."""

    update_requested = Signal()
    dismissed = Signal()      # lembrar depois: some só nesta sessão
    skipped = Signal()        # pular esta versão de vez
    notes_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._release: ReleaseInfo | None = None
        self.setObjectName("appUpdateBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # Em janelas estreitas os botões descem para uma segunda linha; lado a
        # lado eles espremiam o texto até ficar ilegível.
        self._layout = QBoxLayout(QBoxLayout.Direction.LeftToRight, self)
        self._layout.setContentsMargins(18, 12, 14, 12)
        self._layout.setSpacing(10)

        info = QWidget(self)
        info_row = QHBoxLayout(info)
        info_row.setContentsMargins(0, 0, 0, 0)
        info_row.setSpacing(14)
        badge = QLabel(info)
        badge.setFixedSize(22, 22)
        badge.setPixmap(icons.pixmap("update", theme.color("accent"), 20))
        info_row.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        texts = QVBoxLayout()
        texts.setSpacing(2)
        self.title = Headline("Atualização disponível", info)
        self.details = Muted("", info)
        self.details.setWordWrap(True)
        texts.addWidget(self.title)
        texts.addWidget(self.details)
        info_row.addLayout(texts, 1)
        self._layout.addWidget(info, 1)

        actions = QWidget(self)
        layout = QHBoxLayout(actions)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self._actions = actions

        self.update_button = PrimaryButton("Atualizar", "update", self)
        self.update_button.clicked.connect(self.update_requested)
        self.notes_button = Button("Novidades", "", "ghost", self)
        self.notes_button.setToolTip("Ver o que mudou nesta versão")
        self.notes_button.clicked.connect(self.notes_requested)
        self.dismiss_button = Button("Lembrar depois", "", "ghost", self)
        self.dismiss_button.setToolTip("Esconder até a próxima abertura do aplicativo")
        self.dismiss_button.clicked.connect(self.dismissed)
        self.skip_button = Button("Pular versão", "", "ghost", self)
        self.skip_button.setToolTip("Não avisar mais sobre esta versão")
        self.skip_button.clicked.connect(self.skipped)
        for button in (self.update_button, self.notes_button, self.dismiss_button,
                       self.skip_button):
            button.setParent(actions)
            layout.addWidget(button)
        self._layout.addWidget(actions, 0)

        self.hide()

    def resizeEvent(self, event):  # noqa: N802 - assinatura do Qt
        narrow = self.width() < 980
        direction = (QBoxLayout.Direction.TopToBottom if narrow
                     else QBoxLayout.Direction.LeftToRight)
        if self._layout.direction() != direction:
            self._layout.setDirection(direction)
            self._layout.setAlignment(self._actions, Qt.AlignmentFlag.AlignRight if narrow
                                      else Qt.AlignmentFlag.AlignVCenter)
        super().resizeEvent(event)

    @property
    def release(self) -> ReleaseInfo | None:
        return self._release

    def show_release(self, release: ReleaseInfo) -> None:
        self._release = release
        self.title.setText(f"Nova versão {release.tag} disponível")
        size = f"{release.size / 1_000_000:.0f} MB · " if release.size else ""
        self.details.setText(
            f"{size}Conferida antes de instalar; o aplicativo fecha para concluir."
        )
        self.update_button.setEnabled(True)
        self.dismiss_button.setEnabled(True)
        self.dismiss_button.setText("Lembrar depois")
        self.update_button.setText("Atualizar")
        self.notes_button.setVisible(bool(release.notes))
        self.skip_button.show()
        self.show()

    def show_download_progress(self, received: int, total: int) -> None:
        self.update_button.setEnabled(False)
        self.dismiss_button.setEnabled(False)
        self.skip_button.setEnabled(False)
        if total > 0:
            percent = min(100, round(received * 100 / total))
            self.details.setText(f"Baixando e verificando a atualização… {percent}%")
        else:
            self.details.setText("Baixando e verificando a atualização…")
        self.update_button.setText("Baixando…")

    def show_ready_on_exit(self) -> None:
        self.details.setText(
            "Baixada e verificada. Será instalada quando você fechar o aplicativo."
        )
        self.update_button.setText("Instalar agora")
        self.update_button.setEnabled(True)
        self.dismiss_button.setText("Ocultar")
        self.dismiss_button.setEnabled(True)
        self.skip_button.hide()
        self.show()

    def show_error(self, message: str) -> None:
        self.details.setText(message)
        self.update_button.setEnabled(True)
        self.dismiss_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        self.update_button.setText("Tentar de novo")
