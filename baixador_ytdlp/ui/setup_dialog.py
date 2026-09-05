"""Tela de inicialização: verifica e atualiza as dependências antes de abrir o app."""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..config import APP_NAME, APP_VERSION
from ..tools import ToolManager
from ..workers import SetupWorker
from . import theme
from .components import Body, BusyBar, Button, Headline, Muted, ProgressBar, Title

try:  # o qfluentwidgets já traz o qframelesswindow
    from qframelesswindow import FramelessDialog as _Base
except Exception:  # pragma: no cover - fallback defensivo
    _Base = QDialog


class SetupDialog(_Base):
    """Mostra o progresso da checagem de dependências. Fecha sozinho quando termina."""

    ready = Signal(object)  # Toolchain

    def __init__(self, manager: ToolManager, check_now: bool = False, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.toolchain = None
        self._build_ui()
        self.worker = SetupWorker(manager, check_now, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(560, 286)
        self.setMinimumSize(480, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)

        container = QWidget(self)
        container.setObjectName("setupBody")
        container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(36, 44, 36, 30)
        layout.setSpacing(10)

        brand = QHBoxLayout()
        brand.setSpacing(12)
        self.icon = QLabel(container)
        self.icon.setFixedSize(38, 38)
        window_icon = self.windowIcon()
        if not window_icon.isNull():
            self.icon.setPixmap(window_icon.pixmap(QSize(38, 38)))
        else:
            self.icon.hide()
        brand.addWidget(self.icon)
        self.title = Title(APP_NAME, container)
        brand.addWidget(self.title)
        brand.addStretch(1)
        layout.addLayout(brand)

        self.subtitle = Muted(
            f"Versão {APP_VERSION}. O aplicativo abre assim que as dependências "
            "estiverem conferidas.", container)
        layout.addWidget(self.subtitle)
        layout.addSpacing(20)

        self.status = Body("Iniciando…", container, wrap=True)
        self.status.setFont(theme.headline())
        layout.addWidget(self.status)

        self.spinner = BusyBar(container)
        self.bar = ProgressBar(container)
        self.bar.hide()
        layout.addWidget(self.spinner)
        layout.addWidget(self.bar)

        layout.addStretch(1)

        self.retry = Button("Tentar de novo", "refresh", "secondary", container)
        self.retry.hide()
        layout.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignRight)
        self.retry.clicked.connect(self.start)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        title_bar = getattr(self, "titleBar", None)
        if title_bar is not None:
            title_bar.raise_()
            for name in ("minBtn", "maxBtn"):
                button = getattr(title_bar, name, None)
                if button:
                    button.show()
        self._apply_background()

    def _apply_background(self) -> None:
        self.setStyleSheet(
            f"SetupDialog, #setupBody {{ background-color: {theme.color('base')}; }}")

    # ------------------------------------------------------------- fluxo
    def start(self) -> None:
        self.retry.hide()
        self.status.setText("Verificando dependências…")
        self.spinner.show()
        self.bar.hide()
        self.worker.start()

    def _on_progress(self, message: str, percent: int) -> None:
        self.status.setText(message)
        if percent < 0:
            self.spinner.show()
            self.bar.hide()
        else:
            self.spinner.hide()
            self.bar.show()
            self.bar.setValue(percent)

    def _on_done(self, toolchain) -> None:
        self.toolchain = toolchain
        self.ready.emit(toolchain)
        self.accept()

    def _on_fail(self, message: str) -> None:
        self.spinner.hide()
        self.bar.hide()
        self.status.setText(f"Não deu para preparar o ambiente.\n{message}")
        self.retry.show()

    def closeEvent(self, event):  # noqa: N802 - assinatura do Qt
        if self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(2000)
        super().closeEvent(event)
