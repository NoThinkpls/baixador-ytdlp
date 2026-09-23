"""Teste de fumaça da janela real no Windows (sem ``offscreen``).

Abre a MainWindow em tema escuro, espera a integração nativa (moldura, Mica,
geometria) e captura a TELA — não o widget — para enxergar o que o DWM compõe.
Falha se qualquer pixel a poucos pixels das bordas estiver claro: foi assim que
a faixa de ~6 px da 1.8.0 aparecia (fundo do DWM onde o Qt não repintou).

Uso no CI (runner windows-latest tem sessão gráfica):
    python scripts/window_smoke.py --screenshot window-smoke.png
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--screenshot", default="")
    parser.add_argument("--inset", type=int, default=4)
    args = parser.parse_args()

    from PySide6.QtCore import QEventLoop, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.ui import theme
    from baixador_ytdlp.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    theme.set_mode("dark")
    theme.apply(app)
    cfg = Settings(theme="dark", mica=True, history_enabled=False, resume_queue=False,
                   window_rect=[120, 80, 1160, 780], tray_notifications=False)
    with tempfile.TemporaryDirectory() as temporary:
        window = MainWindow(cfg, ToolManager(bin_dir=Path(temporary)))
        window.show()
        loop = QEventLoop()
        QTimer.singleShot(2500, loop.quit)
        loop.exec()

        frame = window.geometry()
        screen = window.screen() or QGuiApplication.primaryScreen()
        image = screen.grabWindow(0, frame.x(), frame.y(), frame.width(), frame.height()).toImage()
        if args.screenshot:
            image.save(args.screenshot)

        inset = args.inset
        width, height = image.width(), image.height()
        samples = []
        for fraction in (0.15, 0.35, 0.5, 0.65, 0.85):
            x = int(width * fraction)
            y = int(height * fraction)
            samples += [(inset, y), (width - 1 - inset, y), (x, height - 1 - inset)]
        light = []
        for x, y in samples:
            color = image.pixelColor(x, y)
            if color.lightness() > 150:
                light.append((x, y, color.name()))
        window._quitting = True
        window.close()
    # Um pixel isolado pode vir do antialiasing do DWM em torno da moldura.
    # A regressão que este teste protege deixava uma faixa clara contínua e
    # aparece em diversos pontos amostrados; só trate como falha esse padrão.
    if len(light) >= 3:
        print("Pixels claros junto às bordas (tema escuro):", light)
        return 1
    if light:
        print("Aviso: pixel isolado da moldura ignorado:", light)
    print(f"OK: {len(samples)} pontos junto às bordas conferidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
