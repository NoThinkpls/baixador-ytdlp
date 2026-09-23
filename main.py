"""Ponto de entrada do baixador-ytdlp."""
from __future__ import annotations

import ctypes
import multiprocessing
import os
import sys
from pathlib import Path

# O huggingface_hub envia telemetria de uso por padrão; nada além dos pesos
# fixados precisa sair desta máquina. Vale também para o processo do Whisper,
# que herda o ambiente.
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from baixador_ytdlp.config import APP_ID, APP_NAME, IS_WINDOWS, Settings, ensure_dirs  # noqa: E402
from baixador_ytdlp.diagnostics import install_diagnostics, install_qt_logging, log_event  # noqa: E402


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
    from baixador_ytdlp.instance import InstanceLock, InstanceServer, forward_to_running
    from baixador_ytdlp.ui.main_window import MainWindow

    ensure_dirs()
    install_diagnostics()

    if IS_WINDOWS:
        # Agrupa a janela sob o ícone certo na barra de tarefas.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    instance_lock = InstanceLock()
    if not instance_lock.acquire():
        if forward_to_running(sys.argv[1:]):
            log_event("Argumentos encaminhados para a instância já aberta")
        else:
            log_event("Outra instância detém a trava, mas não respondeu ao encaminhamento")
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

    try:  # pesos de versões ≤ 1.7: só renomeia pastas no mesmo volume
        from baixador_ytdlp.transcription import migrate_legacy_model_cache
        moved = migrate_legacy_model_cache()
        if moved:
            log_event("Modelos Whisper migrados para o cache novo: %s", ", ".join(moved))
    except Exception as exc:  # noqa: BLE001 - migração é conveniência
        log_event("Migração de modelos ignorada: %s", exc)

    cfg = Settings.load()
    window = MainWindow(
        cfg,
        ToolManager(runtime_check_hours=cfg.runtime_check_hours,
                    allow_system_tools=cfg.allow_system_tools,
                    ytdlp_channel=cfg.ytdlp_channel),
        icon,
        icon_path,
    )
    window.show()
    instance_server.arguments_received.connect(window.handle_external_arguments)
    # macOS entrega baixador://… como QFileOpenEvent, não em sys.argv.
    from PySide6.QtCore import QEvent, QObject

    class _UrlOpenFilter(QObject):
        def eventFilter(self, _watched, event):  # noqa: N802 - assinatura do Qt
            if event.type() == QEvent.Type.FileOpen and event.url().isValid():
                window.handle_external_arguments([event.url().toString()])
                return True
            return False

    url_filter = _UrlOpenFilter(app)
    app.installEventFilter(url_filter)

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
