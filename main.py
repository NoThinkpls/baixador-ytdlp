"""Ponto de entrada do baixador-ytdlp."""
from __future__ import annotations

import ctypes
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from baixador_ytdlp.config import APP_ID, APP_NAME, IS_WINDOWS, LOG_DIR, Settings, ensure_dirs
from baixador_ytdlp.tools import ToolManager
from baixador_ytdlp.ui.main_window import MainWindow


def asset(name: str) -> Path:
    """Resolve arquivos empacotados tanto no modo script quanto congelado."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "assets" / name


def single_instance() -> bool:
    """Impede duas cópias do app. Devolve False se já existe uma rodando."""
    if not IS_WINDOWS:
        return True
    handle = ctypes.windll.kernel32.CreateMutexW(None, False, f"Global\\{APP_ID}")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def install_excepthook() -> None:
    log = LOG_DIR / "crash.log"

    def hook(exc_type, exc, tb):
        import traceback
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            traceback.print_exception(exc_type, exc, tb, file=fh)
        traceback.print_exception(exc_type, exc, tb)

    sys.excepthook = hook


def main() -> int:
    ensure_dirs()
    install_excepthook()

    if IS_WINDOWS:
        # Agrupa a janela sob o ícone certo na barra de tarefas.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(True)

    icon_path = asset("icon.ico")
    icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()
    app.setWindowIcon(icon)

    if not single_instance():
        return 0

    cfg = Settings.load()
    window = MainWindow(cfg, ToolManager(), icon)
    window.show()

    if not window.run_setup(force=False) and window.toolchain is None:
        return 1

    if len(sys.argv) > 1 and sys.argv[1].startswith("http"):
        window.home.set_url(sys.argv[1])
        window.home.analyze()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
