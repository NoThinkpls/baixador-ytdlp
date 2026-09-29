"""Gera as capturas de tela do README em docs/images.

Usa uma pasta temporária e não grava configurações, então não toca no perfil real.
Uso: python scripts/capture_screenshots.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WANTED = {("dark", "baixar"), ("light", "ferramentas"), ("dark", "legendar"),
          ("dark", "configuracoes")}


def main() -> int:
    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.ui import main_window as mw
    from baixador_ytdlp.ui import theme

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
                       window_rect=[100, 60, 1180, 760], tray_notifications=False)
        cfg.save = lambda *args, **kwargs: None
        with tempfile.TemporaryDirectory() as tmp:
            window = mw.MainWindow(cfg, ToolManager(bin_dir=Path(tmp)))
            window.resize(1180, 760)
            window.show()
            wait(1500)
            pages = (("baixar", window.home), ("ferramentas", window.media_tools),
                     ("legendar", window.transcription), ("configuracoes", window.settings))
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
