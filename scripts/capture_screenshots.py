"""Gera as capturas de tela do README em docs/images (usa uma pasta temporária, sem tocar no perfil real)."""
import sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(ROOT))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication
from baixador_ytdlp.config import Settings
from baixador_ytdlp.tools import ToolManager
from baixador_ytdlp.ui import theme
from baixador_ytdlp.ui import main_window as mw

def wait(ms):
    l = QEventLoop(); QTimer.singleShot(ms, l.quit); l.exec()

app = QApplication(sys.argv)
mw.MainWindow.run_setup = lambda self, *a, **k: None
out = ROOT / "docs" / "images"
WANTED = {("dark", "baixar"), ("light", "ferramentas"), ("dark", "legendar"), ("dark", "configuracoes")}
for mode in ("dark", "light"):
    theme.set_mode(mode); theme.apply(app)
    cfg = Settings(theme=mode, mica=False, history_enabled=False, resume_queue=False,
                   window_rect=[100, 60, 1180, 760], tray_notifications=False)
    cfg.save = lambda *a, **k: None
    with tempfile.TemporaryDirectory() as tmp:
        w = mw.MainWindow(cfg, ToolManager(bin_dir=Path(tmp)))
        w.resize(1180, 760); w.show(); wait(1500)
        for name, page in (("baixar", w.home), ("ferramentas", w.media_tools), ("legendar", w.transcription), ("configuracoes", w.settings)):
            if (mode, name) not in WANTED:
                continue
            w.switchTo(page); wait(700)
            w.grab().save(str(out / f"{name}-{mode}.png"))
        w._quitting = True
        w.close()
print("ok")
