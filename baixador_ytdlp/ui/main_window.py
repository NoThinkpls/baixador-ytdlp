"""Janela principal: barra unificada, navegação lateral e as páginas do app."""
from __future__ import annotations

import re
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, QRect, Qt, QTimer, QUrl
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSizePolicy, QSystemTrayIcon

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
from .windowing import _resize_hit_test

URL_RE = re.compile(r"https?://\S+")
WM_NCHITTEST = 0x0084


class MainWindow(AppShell):
    def __init__(
        self,
        cfg: Settings,
        manager: ToolManager,
        icon: QIcon | None = None,
        icon_path: Path | None = None,
    ):
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
        self._icon_path = icon_path
        self._download_taskbar_progress: float | None = None
        self._transcription_taskbar_progress: float | None = None
        self._media_taskbar_progress: float | None = None
        self._quitting = False
        self.tray: QSystemTrayIcon | None = None
        self._taskbar_completion_timer = QTimer(self)
        self._taskbar_completion_timer.setSingleShot(True)
        self._taskbar_completion_timer.timeout.connect(self._clear_taskbar_completion)

        self.history = History(limit=max(20, cfg.history_limit)).load()

        self.home = HomePage(cfg, self)
        self.queue = QueuePage(cfg, self)
        self.transcription = TranscriptionPage(cfg, self)
        self.media_tools = MediaToolsPage(cfg, self)
        self.history_page = HistoryPage(cfg, self.history, self)
        self.settings = SettingsPage(cfg, self)
        self.update_banner = UpdateBanner(self)

        self._init_window(icon)
        self._init_tray(icon)
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
        self.resize(1160, 780)
        # As páginas já rolam verticalmente; permitir 760 px dá espaço para
        # notebooks menores sem cortar controles. A barra lateral recolhe para
        # ícones abaixo de 920 px (ver AppShell.resizeEvent).
        self.setMinimumSize(760, 520)
        self.setMaximumSize(16_777_215, 16_777_215)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        flags = self.windowFlags() | Qt.WindowType.Window | Qt.WindowType.WindowMinMaxButtonsHint
        flags &= ~Qt.WindowType.MSWindowsFixedSizeDialogHint
        self.setWindowFlags(flags)
        # setWindowFlags pode recriar a janela nativa e descartar a preferência
        # do qframelesswindow. Reaplicamos depois dos flags e também no primeiro
        # showEvent para não depender da ordem interna da biblioteca.
        self.setResizeEnabled(True)
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        if icon:
            self.setWindowIcon(icon)
        theme.set_mode(self.cfg.theme)
        self._refresh_appearance()
        self.set_sidebar_collapsed(self.cfg.sidebar_collapsed)
        self.set_brand(APP_NAME, APP_VERSION, icon)
        if self.cfg.mica and sys.platform.startswith("win"):
            self.setMicaEffectEnabled(True)
        # A borda redimensionável e a geometria salva só são aplicadas depois
        # que o qframelesswindow termina o HWND (ver _apply_native_window_integration).
        # Mexer na janela nativa antes do show() mudava a área cliente depois da
        # primeira pintura e deixava faixas claras nas bordas até algo repintar.
        self._geometry_restored = False

        # No modo automático, seguir a troca de tema do sistema sem reabrir o app.
        hints = QGuiApplication.styleHints()
        signal = getattr(hints, "colorSchemeChanged", None)
        if signal is not None:
            try:
                signal.connect(lambda *_: self._refresh_appearance())
            except Exception:  # noqa: BLE001 - Qt sem o sinal
                pass

    def showEvent(self, event):  # noqa: N802 - assinatura do Qt
        super().showEvent(event)
        if sys.platform.startswith("win"):
            # O qframelesswindow termina a criação do HWND durante o showEvent.
            # Rodar no próximo ciclo garante que a moldura redimensionável não
            # seja removida depois da nossa configuração inicial.
            QTimer.singleShot(0, self._apply_native_window_integration)

    def _apply_native_window_integration(self) -> None:
        """Restaura borda, ícone e geometria depois que o qframelesswindow cria o HWND."""
        self._enable_windows_resize_style()
        self.taskbar.apply_window_icon(int(self.winId()), self._icon_path)
        if not self._geometry_restored:
            self._geometry_restored = True
            self._restore_saved_geometry()
            from .. import config as app_config
            if app_config.PORTABLE_FALLBACK_REASON:
                QTimer.singleShot(900, lambda: Toast.warning(
                    "Modo portable indisponível", app_config.PORTABLE_FALLBACK_REASON,
                    parent=self, duration=9000))
            handle = self.windowHandle()
            if handle is not None:
                handle.screenChanged.connect(
                    lambda _screen: QTimer.singleShot(0, self._force_full_redraw))
        QTimer.singleShot(0, self._force_full_redraw)

    def _restore_saved_geometry(self) -> None:
        """Restaura posição/tamanho próprios, validados contra os monitores atuais."""
        rect = list(self.cfg.window_rect or [])
        if len(rect) == 4:
            try:
                x, y, width, height = (int(value) for value in rect)
            except (TypeError, ValueError):
                x = y = width = height = 0
            target = QRect(x, y, max(width, self.minimumWidth()),
                           max(height, self.minimumHeight()))
            # O monitor onde a janela estava pode não existir mais.
            visible = any(
                screen.availableGeometry().intersects(target.adjusted(40, 40, -40, -40))
                for screen in QGuiApplication.screens()
            )
            if width > 0 and height > 0 and visible:
                self.setGeometry(target)
        if self.cfg.window_maximized:
            self.showMaximized()

    def _force_full_redraw(self) -> None:
        """Reenvia a janela inteira ao compositor após mudança de moldura/estado.

        Sem isto, a faixa exposta quando o WM_NCCALCSIZE muda a área cliente
        continuava mostrando o fundo do DWM até o mouse passar por cima.
        """
        if sys.platform.startswith("win"):
            try:
                import ctypes

                rdw_invalidate, rdw_erase, rdw_allchildren = 0x0001, 0x0004, 0x0080
                rdw_updatenow, rdw_frame = 0x0100, 0x0400
                ctypes.windll.user32.RedrawWindow(
                    int(self.winId()), None, None,
                    rdw_invalidate | rdw_erase | rdw_frame | rdw_allchildren | rdw_updatenow,
                )
            except Exception:  # noqa: BLE001 - a repintura do Qt abaixo ainda ocorre
                pass
        self.update()

    def _enable_windows_resize_style(self) -> None:
        """Mantém os botões nativos sem reintroduzir uma moldura não pintada.

        O redimensionamento é atendido por ``nativeEvent``/WM_NCHITTEST. Somar
        ``WS_THICKFRAME`` fazia o DWM reservar uma borda física por fora da
        área Qt; como a janela é frameless, ela ficava branca até um hover
        acionar uma repintura. Removemos explicitamente esse estilo para também
        corrigir instalações que já o receberam numa abertura anterior.
        """
        if not sys.platform.startswith("win"):
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = int(self.winId())
            if not hwnd:
                return
            user32 = ctypes.windll.user32
            get_style = user32.GetWindowLongW
            get_style.argtypes = (wintypes.HWND, ctypes.c_int)
            get_style.restype = ctypes.c_long
            set_style = user32.SetWindowLongW
            set_style.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_long)
            set_style.restype = ctypes.c_long
            set_window_pos = user32.SetWindowPos
            set_window_pos.argtypes = (
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            )
            set_window_pos.restype = wintypes.BOOL

            GWL_STYLE = -16
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_NOACTIVATE = 0x0010
            SWP_FRAMECHANGED = 0x0020

            style = get_style(hwnd, GWL_STYLE)
            wanted = (style & ~WS_THICKFRAME) | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
            if wanted != style:
                set_style(hwnd, GWL_STYLE, wanted)
                set_window_pos(
                    hwnd, None, 0, 0, 0, 0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
                )
            self.setResizeEnabled(True)
        except Exception:
            # A rotina só é complementar; o WM_NCHITTEST abaixo continua como
            # o caminho principal para as bordas e os cantos.
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
        from .components import PageHeader, ScrollColumn

        for page in (self.home, self.queue, self.transcription, self.media_tools,
                     self.history_page, self.settings):
            headers = page.findChildren(PageHeader)
            scrolls = page.findChildren(ScrollColumn)
            if headers and scrolls:
                headers[0].follow(scrolls[0])

    def _init_tray(self, icon: QIcon | None) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable() or icon is None or icon.isNull():
            return
        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip(f"{APP_NAME} {APP_VERSION}")
        menu = QMenu(self)
        open_action = QAction("Abrir baixador-ytdlp", menu)
        queue_action = QAction("Mostrar fila", menu)
        quit_action = QAction("Sair", menu)
        open_action.triggered.connect(lambda _checked=False: self._restore_from_tray())
        queue_action.triggered.connect(
            lambda _checked=False: self._restore_from_tray(self.queue)
        )
        quit_action.triggered.connect(self._quit_from_tray)
        menu.addAction(open_action)
        menu.addAction(queue_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        tray.setContextMenu(menu)
        tray.activated.connect(self._tray_activated)
        tray.show()
        self.tray = tray

    def _tray_activated(self, reason) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self._restore_from_tray()

    def _restore_from_tray(self, page=None) -> None:
        if self.isMinimized():
            self.showNormal()
        self.show()
        if page is not None:
            self.switchTo(page)
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._quitting = True
        self.close()

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
        QShortcut(QKeySequence("Ctrl+L"), self, activated=self._shortcut_focus_link)
        QShortcut(QKeySequence.StandardKey.Open, self, activated=self._shortcut_import)
        QShortcut(QKeySequence.StandardKey.HelpContents, self, activated=self._shortcut_help)
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=self._shortcut_download)
        QShortcut(QKeySequence("Ctrl+Enter"), self, activated=self._shortcut_download)
        QShortcut(QKeySequence("Esc"), self, activated=self._shortcut_cancel)

    def _shortcut_paste(self) -> None:
        if self.stackedWidget.currentWidget() is self.home:
            self.home.paste_and_analyze()

    def _shortcut_download(self) -> None:
        if self.stackedWidget.currentWidget() is self.home and self.home.download_btn.isEnabled():
            self.home.download_btn.click()

    def _shortcut_focus_link(self) -> None:
        self.switchTo(self.home)
        self.home.url_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.home.url_edit.selectAll()

    def _shortcut_import(self) -> None:
        self.switchTo(self.home)
        self.home._import_url_list()

    @staticmethod
    def _shortcut_help() -> None:
        QDesktopServices.openUrl(QUrl(
            "https://github.com/NoThinkpls/baixador-ytdlp/blob/main/docs/GUIA-DE-USO.md"))

    def _shortcut_cancel(self) -> None:
        current = self.stackedWidget.currentWidget()
        if current is self.transcription and self.transcription.cancel_btn.isEnabled():
            self.transcription.cancel()
        elif current is self.media_tools and self.media_tools.cancel_button.isVisible():
            self.media_tools.cancel_current()
        elif current is self.queue and self.queue.has_pending_work():
            answer = QMessageBox.question(
                self,
                "Cancelar a fila?",
                "Deseja cancelar e remover todos os downloads pendentes ou em andamento?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer == QMessageBox.StandardButton.Yes:
                self.queue.cancel_all()

    def _wire(self) -> None:
        self.home.enqueue.connect(self._on_enqueue)
        self.home.enqueue_many.connect(self._on_enqueue_many)
        self.queue.job_finished.connect(self._on_finished)
        self.queue.transcribe_requested.connect(self._on_transcribe)
        self.queue.overall_progress.connect(self._on_overall_progress)
        self.history_page.reopen_requested.connect(self._on_reopen)
        self.history_page.transcribe_requested.connect(self._on_transcribe)
        self.transcription.transcription_finished.connect(self._on_transcribed)
        self.transcription.embedded_finished.connect(
            lambda path: self._tray_message("Vídeo legendado concluído", Path(path).name)
        )
        self.transcription.taskbar_progress.connect(self._on_transcription_progress)
        self.media_tools.taskbar_progress.connect(self._on_media_progress)
        self.media_tools.operation_finished.connect(
            lambda path: self._tray_message("Processamento concluído", Path(path).name)
        )
        self.settings.update_requested.connect(lambda: self.run_setup(check_now=True))
        self.settings.ytdlp_channel_changed.connect(self._switch_ytdlp_channel)
        self.settings.diagnostics_export_requested.connect(self._export_diagnostics)
        self.settings.app_update_requested.connect(lambda: self._check_app_update(force=True))
        self.settings.gpu_detection_requested.connect(self._detect_gpu)
        self.settings.download_dir_changed.connect(self.home.refresh_default_folder)
        self.settings.theme_changed.connect(self._refresh_appearance)
        self.settings.language_changed.connect(self._language_changed)
        self.sidebar_collapsed_changed.connect(self._save_sidebar_state)
        self.update_banner.update_requested.connect(self._download_app_update)
        self.update_banner.dismissed.connect(self._dismiss_app_update)
        # A tela aparece imediatamente; a consulta de rede começa depois, em thread própria.
        QTimer.singleShot(700, self._check_app_update)

    def _save_sidebar_state(self, collapsed: bool) -> None:
        self.cfg.sidebar_collapsed = bool(collapsed)
        self.cfg.save()

    def _language_changed(self, value: str) -> None:
        from .i18n import set_language

        set_language(value)
        Toast.info(
            "Idioma da interface",
            "Reinicie o aplicativo para aplicar o novo idioma.",
            parent=self,
            duration=6500,
        )

    def _refresh_appearance(self, _theme: str = "") -> None:
        """Reaplica tokens, folha de estilo e as cores dos botões da janela."""
        app = QApplication.instance()
        if app is not None:
            theme.apply(app)
        self.refresh_title_bar_colors()
        # O Mica tem variante clara/escura; sem reaplicar, trocar o tema com o
        # app aberto deixava o material antigo por trás da janela.
        if getattr(self, "cfg", None) is not None and self.cfg.mica \
                and sys.platform.startswith("win") and self.isVisible():
            self.setMicaEffectEnabled(True)
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
        # Se a página ficou visível durante a preparação, o seu showEvent já
        # pediu a detecção. Agora que há um FFmpeg disponível, ela pode rodar.
        if self.settings._gpu_requested:
            self._detect_gpu()

    def _detect_gpu(self) -> None:
        """Só consulta GPU quando a informação pode ser mostrada ao usuário."""
        if self.toolchain is None:
            return
        if self._gpu_worker is not None and self._gpu_worker.isRunning():
            return
        # A detecção roda nvidia-smi e o FFmpeg duas vezes. Adiá-la evita esses
        # processos na abertura, sem mudar os encoders apresentados na aba.
        worker = GpuWorker(self.toolchain.ffmpeg, self)
        self._gpu_worker = worker
        worker.finished_ok.connect(self.settings.set_gpu)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda w=worker: self._clear_gpu_worker(w))
        worker.start()

    def _clear_gpu_worker(self, worker: GpuWorker) -> None:
        if self._gpu_worker is worker:
            self._gpu_worker = None

    def _on_enqueue(self, opts) -> None:
        if self.queue.add(opts):
            self.switchTo(self.queue)
            return
        if self._confirm_duplicate(1) and self.queue.add(opts, allow_duplicate=True):
            self.switchTo(self.queue)

    def _on_enqueue_many(self, options) -> None:
        added, duplicates = self.queue.add_many(options)
        if duplicates and self._confirm_duplicate(len(duplicates)):
            repeated, _ = self.queue.add_many(duplicates, allow_duplicates=True)
            added += repeated
        if added:
            self.switchTo(self.queue)

    def _confirm_duplicate(self, count: int) -> bool:
        plural = count != 1
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Download repetido")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            f"{'Estes itens já existem' if plural else 'Este item já existe'} na fila."
        )
        dialog.setInformativeText(
            f"Deseja adicionar {'as solicitações repetidas' if plural else 'outra solicitação'} "
            "mesmo assim?"
        )
        confirm = dialog.addButton(
            "Adicionar mesmo assim", QMessageBox.ButtonRole.AcceptRole
        )
        dialog.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is confirm

    def _on_finished(self, opts, files) -> None:
        title = opts.title or opts.url
        Toast.success("Download concluído", title, parent=self, duration=6000)
        self._tray_message("Download concluído", title)
        self._notify_taskbar_completion()
        paths = [Path(f) for f in files]
        final_paths = []
        seen: set[Path] = set()
        media_extensions = {
            ".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v", ".flv", ".wmv",
            ".mpeg", ".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a", ".opus", ".m4b",
        }
        for path in paths:
            resolved = path.resolve() if path.exists() else path
            if path.is_file() and path.suffix.casefold() in media_extensions and resolved not in seen:
                seen.add(resolved)
                final_paths.append(path)
        if opts.transcribe_after and final_paths:
            for path in final_paths:
                self.transcription.enqueue_media(
                    str(path),
                    embed=bool(opts.embed_transcription and not opts.audio_only),
                )
            Toast.info(
                "Fila de transcrição",
                f"{len(final_paths)} arquivo(s) enviado(s) ao Whisper.",
                parent=self,
                duration=5000,
            )
        if not self.cfg.history_enabled:
            return
        # A URL vem do próprio job, não do campo da tela: entre o início e o fim
        # do download o usuário pode ter colado outro link ali.
        # Guarda o primeiro arquivo que de fato existe. O yt-dlp também imprime
        # caminhos de arquivos intermediários, que somem depois da junção — era
        # por isso que "Mostrar na pasta" e "Legendar" apareciam desabilitados.
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
        self._notify_taskbar_completion()
        self._tray_message("Legenda concluída", Path(output).name if output else Path(source).name)
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

    def _switch_ytdlp_channel(self, channel: str) -> None:
        self.manager.ytdlp_channel = channel
        Toast.info("Canal do yt-dlp", "Baixando a versão do canal escolhido…",
                   parent=self, duration=4000)
        self.run_setup(check_now=True)

    def _export_diagnostics(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        from ..diagnostics import export_diagnostics

        default = str(Path.home() / f"diagnostico-{APP_NAME}-{APP_VERSION}.zip")
        path, _ = QFileDialog.getSaveFileName(self, "Exportar diagnóstico", default,
                                              "Arquivo ZIP (*.zip)")
        if not path:
            return
        try:
            target = export_diagnostics(Path(path), self.cfg)
        except OSError as exc:
            Toast.error("Não foi possível exportar", str(exc), parent=self, duration=7000)
            return
        Toast.success("Diagnóstico exportado",
                      f"{target.name} — revisado sem cookies, senhas nem tokens.",
                      parent=self, duration=7000)

    def handle_external_arguments(self, arguments: list[str]) -> None:
        """Traz a janela à frente e recebe links enviados por uma segunda abertura."""
        if self.isMinimized():
            self.showNormal()
        self.show()
        self.raise_()
        self.activateWindow()
        from ..security import media_url_from_argument

        url = next((found for value in arguments
                    if (found := media_url_from_argument(value))), "")
        if url:
            self.home.set_url(url)
            self.switchTo(self.home)
            self.home.analyze()

    def _on_overall_progress(self, percent: float) -> None:
        self._download_taskbar_progress = None if percent < 0 else max(0.0, min(100.0, percent))
        self._sync_taskbar_progress()

    def _on_transcription_progress(self, percent: float) -> None:
        """Combina o andamento do legendador ao mesmo botão da barra de tarefas."""
        self._transcription_taskbar_progress = (
            None if percent < 0 else max(0.0, min(100.0, percent))
        )
        self._sync_taskbar_progress()

    def _on_media_progress(self, percent: float) -> None:
        self._media_taskbar_progress = None if percent < 0 else max(0.0, min(100.0, percent))
        self._sync_taskbar_progress()

    def _sync_taskbar_progress(self) -> None:
        if not self.cfg.taskbar_progress:
            return
        active = [
            value for value in (
                self._download_taskbar_progress,
                self._transcription_taskbar_progress,
                self._media_taskbar_progress,
            ) if value is not None
        ]
        handle = int(self.winId())
        if active:
            self._taskbar_completion_timer.stop()
            self.taskbar.set_value(handle, sum(active) / len(active))
        else:
            self.taskbar.clear(handle)

    def _notify_taskbar_completion(self) -> None:
        """Deixa a conclusão visível mesmo quando a janela está minimizada."""
        if not self.cfg.taskbar_progress:
            return
        self.taskbar.complete(int(self.winId()))
        self._taskbar_completion_timer.start(1500)

    def _clear_taskbar_completion(self) -> None:
        if (self._download_taskbar_progress is None
                and self._transcription_taskbar_progress is None
                and self._media_taskbar_progress is None):
            self.taskbar.clear(int(self.winId()))

    def _tray_message(self, title: str, message: str) -> None:
        if self.tray is not None and self.cfg.tray_notifications:
            self.tray.showMessage(title, message, QSystemTrayIcon.MessageIcon.Information, 6000)

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
                        hit = _resize_hit_test(
                            rect.left, rect.top, rect.right, rect.bottom,
                            point_x, point_y, border,
                        )
                        if hit is not None:
                            return True, hit
            except Exception:
                # O backend do qframelesswindow continua como fallback.
                pass
        return super().nativeEvent(event_type, message)

    def event(self, event: QEvent):  # noqa: N802 - assinatura do Qt
        if event.type() == QEvent.Type.WindowActivate and self.cfg.clipboard_watch:
            self._check_clipboard()
        result = super().event(event)
        if event.type() == QEvent.Type.WindowStateChange:
            QTimer.singleShot(0, self._force_full_redraw)
        return result

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
        if self.cfg.close_to_tray and self.tray is not None and not self._quitting:
            self.hide()
            event.ignore()
            if self.cfg.tray_notifications:
                self.tray.showMessage(
                    "Continuando em segundo plano",
                    "O baixador-ytdlp permanece na bandeja do sistema.",
                    QSystemTrayIcon.MessageIcon.Information,
                    4500,
                )
            return
        if self.queue.has_pending_work():
            dialog = QMessageBox(self)
            dialog.setWindowTitle("Downloads em andamento")
            dialog.setIcon(QMessageBox.Icon.Warning)
            dialog.setText("Há downloads ativos ou aguardando na fila.")
            dialog.setInformativeText(
                "Ao sair, os processos serão pausados e os arquivos .part poderão ser "
                "retomados na próxima abertura."
            )
            leave = dialog.addButton("Pausar e sair", QMessageBox.ButtonRole.DestructiveRole)
            dialog.addButton("Continuar no aplicativo", QMessageBox.ButtonRole.RejectRole)
            dialog.exec()
            if dialog.clickedButton() is not leave:
                event.ignore()
                return
        self._taskbar_completion_timer.stop()
        self.taskbar.shutdown(int(self.winId()))
        if self.tray is not None:
            self.tray.hide()
        self.home.shutdown()
        self.transcription.shutdown()
        self.media_tools.shutdown()
        self.queue.stop_all()
        self.history.flush()
        normal = self.normalGeometry() if self.isMaximized() else self.geometry()
        if normal.isValid():
            self.cfg.window_rect = [normal.x(), normal.y(), normal.width(), normal.height()]
        self.cfg.window_maximized = self.isMaximized()
        self.cfg.save()
        super().closeEvent(event)

