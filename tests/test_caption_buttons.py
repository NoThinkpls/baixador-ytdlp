"""Botões da moldura: semáforo nativo no Mac e glifos iguais em todas as janelas do Windows."""
from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

try:
    from PySide6.QtWidgets import QApplication, QHBoxLayout, QWidget  # noqa: E402

    from baixador_ytdlp.ui import shell
    from baixador_ytdlp.ui.shell import CaptionControls, install_caption_buttons
except ImportError:  # pragma: no cover - ambiente sem Qt
    QApplication = None


def _window(height: int, mac: bool = False):
    title_bar = QWidget()
    title_bar.setFixedHeight(height)
    title_bar.hBoxLayout = QHBoxLayout(title_bar)
    for name in ("minBtn", "maxBtn", "closeBtn"):
        button = QWidget(title_bar)
        button.show()
        setattr(title_bar, name, button)
    window = SimpleNamespace(titleBar=title_bar)
    if mac:
        window.setSystemTitleBarButtonVisible = Mock()
    return window


@unittest.skipUnless(QApplication is not None, "PySide6 não está instalado neste ambiente")
class CaptionButtonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_windows_draws_the_three_glyphs_in_the_bar_height(self) -> None:
        window = _window(32)
        with patch.object(shell, "sys", SimpleNamespace(platform="win32")):
            controls = install_caption_buttons(window, 32)
        self.assertIsInstance(controls, CaptionControls)
        assert controls is not None
        self.assertEqual([button.action for button in controls.buttons],
                         ["minimize", "maximize", "close"])
        self.assertEqual({button.height() for button in controls.buttons}, {32})
        for name in ("minBtn", "maxBtn", "closeBtn"):
            self.assertTrue(getattr(window.titleBar, name).isHidden(), name)

    def test_mac_uses_the_native_traffic_lights(self) -> None:
        window = _window(44, mac=True)
        with patch.object(shell, "sys", SimpleNamespace(platform="darwin")):
            controls = install_caption_buttons(window, 44)
        self.assertIsNone(controls)
        window.setSystemTitleBarButtonVisible.assert_called_once_with(True)
        for name in ("minBtn", "maxBtn", "closeBtn"):
            self.assertTrue(getattr(window.titleBar, name).isHidden(), name)

    def test_linux_keeps_the_library_buttons(self) -> None:
        window = _window(44)
        with patch.object(shell, "sys", SimpleNamespace(platform="linux")):
            self.assertIsNone(install_caption_buttons(window, 44))
        self.assertFalse(window.titleBar.closeBtn.isHidden())

    # No macOS o SetupDialog é o diálogo Cocoa do qframelesswindow, que chama o Objective-C
    # sobre a janela e derruba o processo no Qt offscreen (por isso test_update_flow também
    # só roda no Windows). O comportamento verificado aqui é o do Windows.
    @unittest.skipIf(sys.platform == "darwin", "diálogo Cocoa não abre no Qt offscreen")
    def test_setup_dialog_uses_the_same_buttons_as_the_main_window_on_windows(self) -> None:
        # A tela de preparação abre antes do app e mostrava o X em SVG, maior que os outros.
        from baixador_ytdlp.ui.setup_dialog import SetupDialog

        with patch.object(shell, "sys", SimpleNamespace(platform="win32")):
            dialog = SetupDialog(Mock())
        self.addCleanup(dialog.deleteLater)
        self.assertIsInstance(dialog.caption_controls, CaptionControls)
        self.assertTrue(dialog.titleBar.closeBtn.isHidden())
        self.assertEqual({button.height() for button in dialog.caption_controls.buttons},
                         {dialog.titleBar.height()})

    def test_traffic_light_placement_never_breaks_painting(self) -> None:
        # Sem o pyobjc (ou fora do Mac) a função precisa sair calada: roda no paintEvent.
        shell.place_mac_traffic_lights(SimpleNamespace(winId=lambda: 0), 44)


if __name__ == "__main__":
    unittest.main()
