"""Janela principal: navegação lateral no padrão Fluent do Windows 11."""
from __future__ import annotations

import re

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (FluentIcon as FIF, FluentWindow, InfoBar, InfoBarPosition,
                            NavigationItemPosition, Theme, setTheme, setThemeColor)

from ..config import APP_NAME, APP_VERSION, Settings
from ..gpu import detect
from ..tools import ToolManager
from .home_page import HomePage
from .queue_page import QueuePage
from .settings_page import SettingsPage
from .setup_dialog import SetupDialog
from .transcription_page import TranscriptionPage

URL_RE = re.compile(r"https?://\S+")


class MainWindow(FluentWindow):
    def __init__(self, cfg: Settings, manager: ToolManager, icon: QIcon | None = None):
        super().__init__()
        self.cfg = cfg
        self.manager = manager
        self.toolchain = None
        self._last_clipboard = ""

        self.home = HomePage(cfg, self)
        self.queue = QueuePage(cfg, self)
        self.transcription = TranscriptionPage(cfg, self)
        self.settings = SettingsPage(cfg, self)

        self._init_window(icon)
        self._init_navigation()
        self._wire()

    # ------------------------------------------------------------------ UI
    def _init_window(self, icon: QIcon | None) -> None:
        self.resize(1040, 720)
        self.setMinimumSize(900, 600)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        if icon:
            self.setWindowIcon(icon)
        setTheme({"light": Theme.LIGHT, "dark": Theme.DARK}.get(self.cfg.theme, Theme.AUTO))
        if self.cfg.mica:
            try:
                self.setMicaEffectEnabled(True)
            except Exception:
                pass
        self.navigationInterface.setExpandWidth(200)

    def _init_navigation(self) -> None:
        self.addSubInterface(self.home, FIF.DOWNLOAD, "Baixar")
        self.addSubInterface(self.queue, FIF.MENU, "Fila")
        self.addSubInterface(self.transcription, FIF.DOWNLOAD, "Legendar")
        self.addSubInterface(self.settings, FIF.SETTING, "Configurações",
                             position=NavigationItemPosition.BOTTOM)

    def _wire(self) -> None:
        self.home.enqueue.connect(self._on_enqueue)
        self.queue.job_finished.connect(self._on_finished)
        self.settings.update_requested.connect(lambda: self.run_setup(force=True))

    # --------------------------------------------------------------- fluxo
    def run_setup(self, force: bool = False) -> bool:
        """Roda a checagem de dependências. Devolve False se o usuário fechou sem sucesso."""
        dialog = SetupDialog(self.manager, force=force, parent=self)
        dialog.ready.connect(self._on_toolchain)
        dialog.start()
        return dialog.exec() == dialog.DialogCode.Accepted or self.toolchain is not None

    def _on_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain
        self.home.set_toolchain(toolchain)
        self.queue.set_toolchain(toolchain)
        self.transcription.set_toolchain(toolchain)
        self.settings.set_versions(toolchain.ytdlp_version, toolchain.ffmpeg_version,
                                   self.manager.runtime_info.summary)
        self.settings.set_gpu(detect(toolchain.ffmpeg))

    def _on_enqueue(self, opts) -> None:
        self.queue.add(opts)
        self.switchTo(self.queue)

    def _on_finished(self, title: str) -> None:
        InfoBar.success("Download concluído", title, duration=6000,
                        position=InfoBarPosition.TOP_RIGHT, parent=self)

    # ------------------------------------------------------- área de transf.
    def event(self, event: QEvent):  # noqa: N802 - assinatura do Qt
        if event.type() == QEvent.Type.WindowActivate and self.cfg.clipboard_watch:
            self._check_clipboard()
        return super().event(event)

    def _check_clipboard(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if not text or text == self._last_clipboard:
            return
        if URL_RE.fullmatch(text) and not self.home.url_edit.text().strip():
            self._last_clipboard = text
            self.home.set_url(text)

    def closeEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.queue.stop_all()
        self.cfg.save()
        super().closeEvent(event)
