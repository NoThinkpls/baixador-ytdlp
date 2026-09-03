"""Tela de inicialização: verifica e atualiza as dependências antes de abrir o app."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QDialog, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import (BodyLabel, CaptionLabel, IndeterminateProgressBar, ProgressBar,
                            PushButton, SubtitleLabel, isDarkTheme)

from ..config import APP_NAME, APP_VERSION
from ..tools import ToolManager
from ..workers import SetupWorker

try:  # o qfluentwidgets já traz o qframelesswindow
    from qframelesswindow import FramelessDialog as _Base
except Exception:  # pragma: no cover - fallback defensivo
    _Base = QDialog


class SetupDialog(_Base):
    """Mostra o progresso da checagem de dependências. Fecha sozinho quando termina."""

    ready = Signal(object)  # Toolchain

    def __init__(self, manager: ToolManager, force: bool = False, parent=None):
        super().__init__(parent)
        self.manager = manager
        self.toolchain = None
        self._build_ui()
        self.worker = SetupWorker(manager, force, self)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.failed.connect(self._on_fail)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.setWindowTitle(APP_NAME)
        self.resize(560, 290)
        self.setMinimumSize(460, 250)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)

        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(32, 40, 32, 28)
        layout.setSpacing(10)

        self.title = SubtitleLabel(APP_NAME, container)
        self.subtitle = CaptionLabel(
            f"versão {APP_VERSION} · o programa será liberado após atualizar todas as dependências",
            container)
        self.status = BodyLabel("Iniciando…", container)
        self.status.setWordWrap(True)

        self.spinner = IndeterminateProgressBar(container)
        self.bar = ProgressBar(container)
        self.bar.setRange(0, 100)
        self.bar.hide()

        self.retry = PushButton("Tentar de novo", container)
        self.retry.clicked.connect(self.start)
        self.retry.hide()

        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)
        layout.addSpacing(18)
        layout.addWidget(self.status)
        layout.addWidget(self.spinner)
        layout.addWidget(self.bar)
        layout.addStretch(1)
        layout.addWidget(self.retry, 0, Qt.AlignmentFlag.AlignRight)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(container)

        if hasattr(self, "titleBar"):
            self.titleBar.raise_()
            for name in ("minBtn", "maxBtn"):
                button = getattr(self.titleBar, name, None)
                if button:
                    button.show()
        self._apply_background()

    def _apply_background(self) -> None:
        color = "#202020" if isDarkTheme() else "#f3f3f3"
        self.setStyleSheet(f"SetupDialog {{ background-color: {color}; }}")

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
