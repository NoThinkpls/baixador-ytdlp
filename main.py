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


_MUTEX = None


def single_instance() -> bool:
    """Impede duas cópias do app. Devolve False se já existe uma rodando."""
    if not IS_WINDOWS:
        return True
    global _MUTEX  # o handle precisa sobreviver a esta função, senão o mutex some
    _MUTEX = ctypes.windll.kernel32.CreateMutexW(None, False, f"Global\\{APP_ID}")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main() -> int:
    # Os imports Qt ficam aqui: o processo auxiliar do multiprocessing entra
    # por freeze_support antes de carregar qualquer componente de interface.
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.ui.main_window import MainWindow

    ensure_dirs()
    install_diagnostics()

    if IS_WINDOWS:
        # Agrupa a janela sob o ícone certo na barra de tarefas.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
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

    if not single_instance():
        log_event("Encerrando: outra instância já está aberta")
        return 0

    cfg = Settings.load()
    window = MainWindow(cfg, ToolManager(runtime_check_hours=cfg.runtime_check_hours), icon)
    window.show()

    if not window.run_setup(force=False) and window.toolchain is None:
        log_event("Encerrando: preparação inicial não foi concluída")
        return 1

    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        window.home.set_url(sys.argv[1])
        window.home.analyze()

    result = app.exec()
    log_event("Sessão encerrada normalmente: código=%s", result)
    return result


if __name__ == "__main__":
    # Obrigatório para que o modo spawn no Windows execute somente o alvo do
    # processo auxiliar, sem abrir uma segunda janela Qt.
    multiprocessing.freeze_support()
    raise SystemExit(main())
