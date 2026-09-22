"""Ponto de entrada do baixador-ytdlp."""
from __future__ import annotations

import ctypes
import multiprocessing
import sys
from pathlib import Path

from baixador_ytdlp.config import APP_ID, APP_NAME, IS_WINDOWS, Settings, ensure_dirs
from baixador_ytdlp.diagnostics import install_diagnostics, install_qt_logging, log_event


def asset(name: str) -> Path:
    """Resolve arquivos empacotados tanto no modo script quanto congelado."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "assets" / name


def main() -> int:
    # Os imports Qt ficam aqui: o processo auxiliar do multiprocessing entra
    # por freeze_support antes de carregar qualquer componente de interface.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.instance import InstanceServer, forward_to_running
    from baixador_ytdlp.ui.main_window import MainWindow

    ensure_dirs()
    install_diagnostics()

    if IS_WINDOWS:
        # Agrupa a janela sob o ícone certo na barra de tarefas.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    if forward_to_running(sys.argv[1:]):
        log_event("Argumentos encaminhados para a instância já aberta")
        return 0
    instance_server = InstanceServer(app)
    if not instance_server.listen():
        log_event("Encerrando: não foi possível reservar o canal da instância única")
        return 1
    # A folha de estilo entra antes de qualquer janela: assim a tela de
    # preparação já abre com a identidade visual do aplicativo.
    from baixador_ytdlp.ui import theme
    theme.apply(app)
    install_qt_logging()
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    icon_path = asset("icon.ico" if IS_WINDOWS else "icon.png")
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    app.setWindowIcon(icon)

    cfg = Settings.load()
    window = MainWindow(
        cfg,
        ToolManager(runtime_check_hours=cfg.runtime_check_hours,
                    allow_system_tools=cfg.allow_system_tools),
        icon,
        icon_path,
    )
    window.show()
    instance_server.arguments_received.connect(window.handle_external_arguments)

    if not window.run_setup() and window.toolchain is None:
        log_event("Encerrando: preparação inicial não foi concluída")
        return 1

    window.handle_external_arguments(sys.argv[1:])

    result = app.exec()
    log_event("Sessão encerrada normalmente: código=%s", result)
    return result


if __name__ == "__main__":
    # Obrigatório para que o modo spawn no Windows execute somente o alvo do
    # processo auxiliar, sem abrir uma segunda janela Qt.
    multiprocessing.freeze_support()
    raise SystemExit(main())
