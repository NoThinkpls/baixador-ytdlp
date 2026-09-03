"""Janela principal: navegação lateral no padrão Fluent do Windows 11."""
from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QSizePolicy
from qfluentwidgets import (FluentIcon as FIF, FluentWindow, InfoBar, InfoBarPosition,
                            NavigationItemPosition, Theme, setTheme)

from ..config import APP_NAME, APP_VERSION, Settings
from ..history import History, HistoryEntry
from ..taskbar import TaskbarProgress
from ..tools import ToolManager
from ..workers import GpuWorker
from .history_page import HistoryPage
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
        self._gpu_worker: GpuWorker | None = None
        self.taskbar = TaskbarProgress()

        self.history = History(limit=max(20, cfg.history_limit)).load()

        self.home = HomePage(cfg, self)
        self.queue = QueuePage(cfg, self)
        self.transcription = TranscriptionPage(cfg, self)
        self.history_page = HistoryPage(cfg, self.history, self)
        self.settings = SettingsPage(cfg, self)

        self._init_window(icon)
        self._init_navigation()
        self._init_shortcuts()
        self._wire()

    # ------------------------------------------------------------------ UI
    def _init_window(self, icon: QIcon | None) -> None:
        # Janela deliberadamente redimensionável: mantém área útil em notebooks
        # menores, mas aproveita telas grandes sem conteúdo fixo.
        self.resize(1120, 760)
        self.setMinimumSize(820, 540)
        self.setMaximumSize(16_777_215, 16_777_215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
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
        # qframelesswindow expõe estes controles no Windows; os guards preservam
        # compatibilidade com versões que adotem uma title bar diferente.
        title_bar = getattr(self, "titleBar", None)
        for name in ("minBtn", "maxBtn"):
            button = getattr(title_bar, name, None)
            if button:
                button.show()

    def _init_navigation(self) -> None:
        # Ícones escolhidos pelo que cada página faz, não por serem genéricos:
        # nuvem-com-seta = trazer da internet; lista escalonada = fila de espera;
        # balão de fala = legenda; relógio-com-seta = histórico.
        self.addSubInterface(self.home, FIF.CLOUD_DOWNLOAD, "Baixar")
        self.addSubInterface(self.queue, FIF.ALIGNMENT, "Fila")
        self.addSubInterface(self.transcription, FIF.MESSAGE, "Legendar")
        self.addSubInterface(self.history_page, FIF.HISTORY, "Histórico")
        self.addSubInterface(self.settings, FIF.SETTING, "Configurações",
                             position=NavigationItemPosition.BOTTOM)

    def _init_shortcuts(self) -> None:
        pages = (self.home, self.queue, self.transcription, self.history_page)
        for index, page in enumerate(pages, start=1):
            QShortcut(QKeySequence(f"Ctrl+{index}"), self,
                      activated=lambda p=page: self.switchTo(p))
        QShortcut(QKeySequence("Ctrl+,"), self, activated=lambda: self.switchTo(self.settings))
        QShortcut(QKeySequence.StandardKey.Paste, self, activated=self._shortcut_paste)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._shortcut_download)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._shortcut_download)
        QShortcut(QKeySequence("Esc"), self, activated=self._shortcut_cancel)

    def _shortcut_paste(self) -> None:
        if self.stackedWidget.currentWidget() is self.home:
            self.home.paste_and_analyze()

    def _shortcut_download(self) -> None:
        if self.stackedWidget.currentWidget() is self.home and self.home.download_btn.isEnabled():
            self.home.download_btn.click()

    def _shortcut_cancel(self) -> None:
        current = self.stackedWidget.currentWidget()
        if current is self.transcription and self.transcription.cancel_btn.isEnabled():
            self.transcription.cancel()

    def _wire(self) -> None:
        self.home.enqueue.connect(self._on_enqueue)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.transcribe_requested.connect(self._on_transcribe)
        self.queue.overall_progress.connect(self._on_overall_progress)
        self.history_page.reopen_requested.connect(self._on_reopen)
        self.history_page.transcribe_requested.connect(self._on_transcribe)
        self.settings.update_requested.connect(lambda: self.run_setup(force=True))
        self.settings.download_dir_changed.connect(self.home.refresh_default_folder)

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
        # A detecção da GPU chama nvidia-smi e o FFmpeg duas vezes: fora da thread da UI.
        self._gpu_worker = GpuWorker(toolchain.ffmpeg, self)
        self._gpu_worker.finished_ok.connect(self.settings.set_gpu)
        self._gpu_worker.finished.connect(self._gpu_worker.deleteLater)
        self._gpu_worker.start()

    def _on_enqueue(self, opts) -> None:
        self.queue.add(opts)
        self.switchTo(self.queue)

    def _on_finished(self, opts, files) -> None:
        title = opts.title or opts.url
        InfoBar.success("Download concluído", title, duration=6000,
                        position=InfoBarPosition.TOP_RIGHT, parent=self)
        if not self.cfg.history_enabled:
            return
        # A URL vem do próprio job, não do campo da tela: entre o início e o fim
        # do download o usuário pode ter colado outro link ali.
        paths = [Path(f) for f in files]
        self.history.add(HistoryEntry(
            title=title,
            url=opts.url,
            path=str(paths[0]) if paths else "",
            files=len(paths),
            audio_only=opts.audio_only,
            container=paths[0].suffix.lstrip(".") if paths else "",
        ))
        self.history_page.invalidate()

    def _on_transcribe(self, path: str) -> None:
        self.transcription.set_media(path)
        self.switchTo(self.transcription)

    def _on_reopen(self, url: str) -> None:
        self.home.set_url(url)
        self.switchTo(self.home)
        self.home.analyze()

    def _on_overall_progress(self, percent: float) -> None:
        if not self.cfg.taskbar_progress:
            return
        handle = int(self.winId())
        if percent < 0:
            self.taskbar.clear(handle)
        else:
            self.taskbar.set_value(handle, percent)

    # ------------------------------------------------------- área de transf.
    def event(self, event: QEvent):  # noqa: N802 - assinatura do Qt
        if event.type() == QEvent.Type.WindowActivate and self.cfg.clipboard_watch:
            self._check_clipboard()
        return super().event(event)

    def _check_clipboard(self) -> None:
        text = (QApplication.clipboard().text() or "").strip()
        if not text or text == self._last_clipboard or len(text) > 2048:
            return
        # Marca como visto mesmo quando não usa: evita reavaliar a mesma string
        # a cada troca de janela.
        self._last_clipboard = text
        if URL_RE.fullmatch(text) and not self.home.url_edit.text().strip():
            self.home.set_url(text)

    def closeEvent(self, event):  # noqa: N802 - assinatura do Qt
        self.taskbar.clear(int(self.winId()))
        self.transcription.shutdown()
        self.queue.stop_all()
        self.history.flush()
        self.cfg.save()
        super().closeEvent(event)
