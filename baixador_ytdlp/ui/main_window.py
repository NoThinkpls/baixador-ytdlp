"""Janela principal: barra unificada, navegação lateral e as páginas do app."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QSizePolicy

from ..config import APP_NAME, APP_VERSION, Settings
from ..history import DOWNLOAD, TRANSCRIPTION, History, HistoryEntry
from ..taskbar import TaskbarProgress
from ..tools import ToolManager
from ..updater import AppUpdater, ReleaseInfo
from ..workers import AppUpdateCheckWorker, AppUpdateDownloadWorker, GpuWorker
from . import theme
from .components import Toast
from .history_page import HistoryPage
from .home_page import HomePage
from .media_tools_page import MediaToolsPage
from .queue_page import QueuePage
from .settings_page import SettingsPage
from .setup_dialog import SetupDialog
from .shell import AppShell
from .transcription_page import TranscriptionPage
from .update_banner import UpdateBanner

URL_RE = re.compile(r"https?://\S+")
WM_NCHITTEST = 0x0084
HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT = 10, 11, 12, 13, 14
HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 15, 16, 17


class MainWindow(AppShell):
    def __init__(self, cfg: Settings, manager: ToolManager, icon: QIcon | None = None):
        super().__init__()
        self.cfg = cfg
        self.manager = manager
        self.toolchain = None
        self._last_clipboard = ""
        self._gpu_worker: GpuWorker | None = None
        self._app_update_check: AppUpdateCheckWorker | None = None
        self._app_update_download: AppUpdateDownloadWorker | None = None
        self._available_update: ReleaseInfo | None = None
        self.taskbar = TaskbarProgress()

        self.history = History(limit=max(20, cfg.history_limit)).load()

        self.home = HomePage(cfg, self)
        self.queue = QueuePage(cfg, self)
        self.transcription = TranscriptionPage(cfg, self)
        self.media_tools = MediaToolsPage(cfg, self)
        self.history_page = HistoryPage(cfg, self.history, self)
        self.settings = SettingsPage(cfg, self)
        self.update_banner = UpdateBanner(self)

        self._init_window(icon)
        self._init_navigation()
        self._init_update_banner()
        self._init_shortcuts()
        self._wire()

    # ------------------------------------------------------------------ UI
    def _init_window(self, icon: QIcon | None) -> None:
        # Janela deliberadamente redimensionável: mantém área útil em notebooks
        # menores, mas aproveita telas grandes sem conteúdo fixo.
        # A borda de arrasto padrão do qframelesswindow é de 5 px, o que torna os
        # cantos quase impossíveis de pegar com o mouse, ainda mais com escala de
        # tela alta. 12 px dá margem confortável nos quatro cantos e nas laterais.
        self.BORDER_WIDTH = 12
        self.setResizeEnabled(True)
        self.resize(1160, 780)
        self.setMinimumSize(880, 560)
        self.setMaximumSize(16_777_215, 16_777_215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMinMaxButtonsHint)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        if icon:
            self.setWindowIcon(icon)
        theme.set_mode(self.cfg.theme)
        self._refresh_appearance()
        self.set_sidebar_collapsed(self.cfg.sidebar_collapsed)
        self.set_brand(APP_NAME, APP_VERSION, icon)
        if self.cfg.mica and sys.platform.startswith("win"):
            self.setMicaEffectEnabled(True)

        # No modo automático, seguir a troca de tema do sistema sem reabrir o app.
        hints = QGuiApplication.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            try:
                signal.connect(lambda *_: self._refresh_appearance())
            except Exception:  # noqa: BLE001 - Qt sem o sinal
                pass

    def _init_navigation(self) -> None:
        # Ícones escolhidos pelo que cada página faz: seta para baixo = trazer da
        # internet; camadas empilhadas = a fila de itens; balões = legenda;
        # controles deslizantes = ferramentas; relógio com seta = histórico.
        self.add_nav_section("Navegação")
        self.addSubInterface(self.home, "download", "Baixar")
        self.addSubInterface(self.queue, "queue", "Fila")
        self.addSubInterface(self.transcription, "captions", "Legendar")
        self.addSubInterface(self.media_tools, "tools", "Ferramentas")
        self.addSubInterface(self.history_page, "history", "Histórico")
        self.addSubInterface(self.settings, "settings", "Configurações", bottom=True)

    def _init_update_banner(self) -> None:
        """Reserva uma faixa inferior sem sobrepor o conteúdo das páginas."""
        self.add_footer_widget(self.update_banner)

    def _init_shortcuts(self) -> None:
        pages = (self.home, self.queue, self.transcription, self.media_tools, self.history_page)
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
        self.home.enqueue_many.connect(self._on_enqueue_many)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.transcribe_requested.connect(self._on_transcribe)
        self.queue.overall_progress.connect(self._on_overall_progress)
        self.history_page.reopen_requested.connect(self._on_reopen)
        self.history_page.transcribe_requested.connect(self._on_transcribe)
        self.transcription.transcription_finished.connect(self._on_transcribed)
        self.settings.update_requested.connect(lambda: self.run_setup(check_now=True))
        self.settings.app_update_requested.connect(lambda: self._check_app_update(force=True))
        self.settings.download_dir_changed.connect(self.home.refresh_default_folder)
        self.settings.theme_changed.connect(self._refresh_appearance)
        self.sidebar_collapsed_changed.connect(self._save_sidebar_state)
        self.update_banner.update_requested.connect(self._download_app_update)
        self.update_banner.dismissed.connect(self._dismiss_app_update)
        # A tela aparece imediatamente; a consulta de rede começa depois, em thread própria.
        QTimer.singleShot(700, self._check_app_update)

    def _save_sidebar_state(self, collapsed: bool) -> None:
        self.cfg.sidebar_collapsed = bool(collapsed)
        self.cfg.save()

    def _refresh_appearance(self, _theme: str = "") -> None:
        """Reaplica tokens, folha de estilo e as cores dos botões da janela."""
        app = QApplication.instance()
        if app is not None:
            theme.apply(app)
        self.refresh_title_bar_colors()
        self.update()

    # ------------------------------------------------------- atualização app
    def _check_app_update(self, force: bool = False) -> None:
        if self._app_update_check and self._app_update_check.isRunning():
            return
        worker = AppUpdateCheckWorker(
            enabled=self.cfg.auto_update,
            last_checked_at=self.cfg.app_update_checked_at,
            interval_hours=self.cfg.update_check_hours,
            dismissed_version=self.cfg.update_dismissed_version,
            force=force,
            parent=self,
        )
        self._app_update_check = worker
        worker.finished_ok.connect(
            lambda release, checked_at, manual=force:
            self._on_app_update_checked(release, checked_at, manual)
        )
        worker.failed.connect(
            lambda message, manual=force: self._on_app_update_check_failed(message, manual)
        )
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_update_check_worker(w))
        worker.start()

    def _clear_update_check_worker(self, worker: AppUpdateCheckWorker) -> None:
        if self._app_update_check is worker:
            self._app_update_check = None

    def _on_app_update_checked(
        self,
        release: ReleaseInfo | None,
        checked_at: float,
        manual: bool,
    ) -> None:
        if checked_at:
            self.cfg.app_update_checked_at = checked_at
            self.cfg.save()
        if release:
            self._available_update = release
            self.update_banner.show_release(release)
            return
        if manual:
            Toast.info("Atualização", "Você já está usando a versão mais recente.",
                       parent=self, duration=5000)

    def _on_app_update_check_failed(self, message: str, manual: bool) -> None:
        # Na abertura, uma indisponibilidade temporária de rede não interrompe o trabalho.
        if manual:
            Toast.error("Não foi possível verificar atualizações", message,
                        parent=self, duration=7000)

    def _dismiss_app_update(self) -> None:
        if self._available_update:
            self.cfg.update_dismissed_version = self._available_update.version
            self.cfg.save()
        self.update_banner.hide()

    def _download_app_update(self) -> None:
        release = self._available_update or self.update_banner.release
        if not release or (self._app_update_download and self._app_update_download.isRunning()):
            return
        worker = AppUpdateDownloadWorker(release, self)
        self._app_update_download = worker
        worker.progress.connect(self.update_banner.show_download_progress)
        worker.finished_ok.connect(self._on_app_update_ready)
        worker.failed.connect(self._on_app_update_download_failed)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_update_download_worker(w))
        worker.start()

    def _clear_update_download_worker(self, worker: AppUpdateDownloadWorker) -> None:
        if self._app_update_download is worker:
            self._app_update_download = None

    def _on_app_update_ready(self, installer: str) -> None:
        try:
            AppUpdater.launch_installer(Path(installer))
        except Exception as exc:  # noqa: BLE001
            self._on_app_update_download_failed(str(exc))
            return
        self.update_banner.details.setText(
            "Atualização validada. O instalador foi aberto; fechando o aplicativo…"
        )
        Toast.success("Atualização pronta", "O instalador validado foi aberto.",
                      parent=self, duration=4000)
        QTimer.singleShot(900, QApplication.quit)

    def _on_app_update_download_failed(self, message: str) -> None:
        self.update_banner.show_error(message)
        Toast.error("Atualização não concluída", message, parent=self, duration=7000)

    # --------------------------------------------------------------- fluxo
    def run_setup(self, check_now: bool = False) -> bool:
        """Roda a checagem de dependências sem reinstalar versões atuais."""
        dialog = SetupDialog(self.manager, check_now=check_now, parent=self)
        dialog.ready.connect(self._on_toolchain)
        dialog.start()
        return dialog.exec() == dialog.DialogCode.Accepted or self.toolchain is not None

    def _on_toolchain(self, toolchain) -> None:
        self.toolchain = toolchain
        self.home.set_toolchain(toolchain)
        self.queue.set_toolchain(toolchain)
        self.transcription.set_toolchain(toolchain)
        self.media_tools.set_toolchain(toolchain)
        runtime = self.manager.runtime_info.summary
        js = (f"Deno {toolchain.deno_version}" if toolchain.has_js_runtime
              else "sem runtime JavaScript — o YouTube vai falhar")
        self.settings.set_versions(toolchain.ytdlp_version, toolchain.ffmpeg_version,
                                   f"{runtime}\nRuntime JS: {js}")
        # A detecção da GPU chama nvidia-smi e o FFmpeg duas vezes: fora da thread da UI.
        self._gpu_worker = GpuWorker(toolchain.ffmpeg, self)
        self._gpu_worker.finished_ok.connect(self.settings.set_gpu)
        self._gpu_worker.finished.connect(self._gpu_worker.deleteLater)
        self._gpu_worker.start()

    def _on_enqueue(self, opts) -> None:
        if self.queue.add(opts):
            self.switchTo(self.queue)
            return
        Toast.warning("Já está na fila",
                      "Este download já está aguardando ou em andamento.",
                      parent=self, duration=4500)

    def _on_enqueue_many(self, options) -> None:
        added, skipped = self.queue.add_many(options)
        if added:
            self.switchTo(self.queue)
        if skipped:
            Toast.info("Itens repetidos ignorados",
                       f"{skipped} link(s) já estavam aguardando ou baixando.",
                       parent=self, duration=5000)

    def _on_finished(self, opts, files) -> None:
        title = opts.title or opts.url
        Toast.success("Download concluído", title, parent=self, duration=6000)
        if not self.cfg.history_enabled:
            return
        # A URL vem do próprio job, não do campo da tela: entre o início e o fim
        # do download o usuário pode ter colado outro link ali.
        # Guarda o primeiro arquivo que de fato existe. O yt-dlp também imprime
        # caminhos de arquivos intermediários, que somem depois da junção — era
        # por isso que "Mostrar na pasta" e "Legendar" apareciam desabilitados.
        paths = [Path(f) for f in files]
        final = next((p for p in paths if p.is_file()), paths[0] if paths else None)
        self.history.add(HistoryEntry(
            title=title,
            url=opts.url,
            path=str(final) if final else "",
            folder_path=opts.output_dir,
            files=len(paths),
            audio_only=opts.audio_only,
            container=final.suffix.lstrip(".") if final else "",
            kind=DOWNLOAD,
        ))
        self.history_page.invalidate()

    def _on_transcribed(self, output: str, source: str) -> None:
        """Registra a legenda no histórico, ao lado dos downloads."""
        if not self.cfg.history_enabled or not output:
            return
        legenda = Path(output)
        self.history.add(HistoryEntry(
            title=Path(source).stem or legenda.stem,
            path=str(legenda),
            folder_path=str(legenda.parent),
            source=source,
            container=legenda.suffix.lstrip("."),
            kind=TRANSCRIPTION,
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
    def nativeEvent(self, event_type, message):  # noqa: N802 - assinatura do Qt
        """Prioriza a borda física da janela no Windows antes dos widgets filhos.

        A barra de título personalizada pode consumir o hit-test dos cantos
        direitos. Ao responder a WM_NCHITTEST no topo, o Windows recebe sempre o
        cursor de redimensionamento correto em todas as bordas e cantos.
        """
        if sys.platform.startswith("win") and not self.isMaximized() and not self.isFullScreen():
            try:
                import ctypes
                from ctypes import wintypes

                # Algumas versões de PySide6 não expõem wintypes.MSG e outras
                # entregam um VoidPtr. Declarar a estrutura aqui evita que a
                # exceção silenciosa faça o qframelesswindow perder *todas* as
                # bordas de redimensionamento.
                class WinMessage(ctypes.Structure):
                    _fields_ = [
                        ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                        ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                        ("time", wintypes.DWORD), ("pt", wintypes.POINT),
                    ]

                pointer = int(message)
                msg = WinMessage.from_address(pointer)
                if msg.message == WM_NCHITTEST:
                    hwnd = int(self.winId())
                    rect = wintypes.RECT()
                    if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                        # WM_NCHITTEST usa pixels físicos e o retângulo externo
                        # inclui a moldura invisível do Windows. Isso evita que a
                        # barra de título personalizada engula os cantos direitos.
                        dpi = getattr(ctypes.windll.user32, "GetDpiForWindow", lambda _hwnd: 96)(hwnd)
                        border = max(12, round(self.BORDER_WIDTH * int(dpi) / 96))
                        # GetCursorPos evita truncamento de coordenadas em telas
                        # posicionadas à esquerda/acima do monitor principal.
                        cursor = wintypes.POINT()
                        ctypes.windll.user32.GetCursorPos(ctypes.byref(cursor))
                        point_x, point_y = cursor.x, cursor.y
                        left = point_x <= rect.left + border
                        right = point_x >= rect.right - border - 1
                        top = point_y <= rect.top + border
                        bottom = point_y >= rect.bottom - border - 1
                        if left or right or top or bottom:
                            if left and top:
                                return True, HTTOPLEFT
                            if right and top:
                                return True, HTTOPRIGHT
                            if left and bottom:
                                return True, HTBOTTOMLEFT
                            if right and bottom:
                                return True, HTBOTTOMRIGHT
                            if top:
                                return True, HTTOP
                            if bottom:
                                return True, HTBOTTOM
                            if left:
                                return True, HTLEFT
                            if right:
                                return True, HTRIGHT
            except Exception:
                # O backend do qframelesswindow continua como fallback.
                pass
        return super().nativeEvent(event_type, message)

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
        self.home.shutdown()
        self.transcription.shutdown()
        self.media_tools.shutdown()
        self.queue.stop_all()
        self.history.flush()
        self.cfg.save()
        super().closeEvent(event)
