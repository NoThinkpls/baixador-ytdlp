"""Gera as capturas de tela do README em docs/images.

Usa uma pasta temporária e não grava configurações, então não toca no perfil real.
Uso: python scripts/capture_screenshots.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
# Perfil descartável: nada aqui pode tocar nas configurações reais.
os.environ["BAIXADOR_YTDLP_DATA_DIR"] = tempfile.mkdtemp(prefix="baixador-capturas-")

WANTED = {("dark", "baixar"), ("light", "ferramentas"), ("dark", "legendar"),
          ("dark", "configuracoes"), ("dark", "cortes")}
# O README mostra o app no Windows: pasta de exemplo e botões da moldura do Windows mesmo
# quando a captura roda no Linux ou no Mac (sem isso aparecia /root/Videos e o "X" do Linux).
SAMPLE_DOWNLOAD_DIR = r"C:\Users\Voce\Videos\baixador-ytdlp"


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.tools import ToolManager
    from types import SimpleNamespace

    from baixador_ytdlp.ui import main_window as mw
    from baixador_ytdlp.ui import shell, theme

    shell.sys = SimpleNamespace(platform="win32")   # type: ignore[assignment]

    def wait(ms: int) -> None:
        loop = QEventLoop()
        QTimer.singleShot(ms, loop.quit)
        loop.exec()

    app = QApplication(sys.argv)
    mw.MainWindow.run_setup = lambda self, *args, **kwargs: None  # sem rede
    out = ROOT / "docs" / "images"
    out.mkdir(parents=True, exist_ok=True)
    for mode in ("dark", "light"):
        theme.set_mode(mode)
        theme.apply(app)
        cfg = Settings(theme=mode, mica=False, history_enabled=False, resume_queue=False,
                       window_rect=[100, 60, 1180, 760], tray_notifications=False,
                       download_dir=SAMPLE_DOWNLOAD_DIR)
        cfg.save = lambda *args, **kwargs: None
        with tempfile.TemporaryDirectory() as tmp:
            window = mw.MainWindow(cfg, ToolManager(bin_dir=Path(tmp)))
            window.resize(1180, 760)
            window.show()
            wait(1500)
            pages = (("baixar", window.home), ("ferramentas", window.media_tools),
                     ("legendar", window.transcription), ("configuracoes", window.settings),
                     ("cortes", window.clips))
            for name, page in pages:
                if (mode, name) not in WANTED:
                    continue
                window.switchTo(page)
                wait(700)
                window.grab().save(str(out / f"{name}-{mode}.png"))
            window._quitting = True
            window.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
