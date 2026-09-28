"""Instalar uma atualização fecha o app pelo caminho normal e respeita tarefas ativas."""
from __future__ import annotations

import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HAS_QT = all(importlib.util.find_spec(module) is not None
             for module in ("PySide6", "qframelesswindow"))

if HAS_QT:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtWidgets import QApplication

    from baixador_ytdlp.config import Settings
    from baixador_ytdlp.tools import ToolManager
    from baixador_ytdlp.ui.main_window import MainWindow


@unittest.skipUnless(HAS_QT, "requer PySide6 e PySideSix-Frameless-Window")
class UpdateFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        cfg = Settings(history_enabled=False, resume_queue=False, tray_notifications=False,
                       auto_update=False)
        cfg.save = MagicMock()  # nunca grava no perfil real de quem roda os testes
        self.window = MainWindow(cfg, ToolManager(bin_dir=Path(self.temp.name)))
        # Nada disto pode tocar nos arquivos reais de fila/histórico.
        self.window.queue.stop_all = MagicMock()
        self.window.history.flush = MagicMock()
        self.installer = Path(self.temp.name) / "BaixadorYtdlp-9.9.9-setup.exe"
        self.installer.write_bytes(b"MZ")
        self.launch = patch("baixador_ytdlp.ui.main_window.AppUpdater.launch_installer").start()
        patch.object(QApplication, "quit").start()
        self.window.show()

    def tearDown(self) -> None:
        patch.stopall()
        self.window._quitting = True
        self.window._skip_close_prompt = True
        self.window._launch_installer_on_close = False
        self.window.close()
        self.window.deleteLater()
        self.temp.cleanup()

    def _pump(self) -> None:
        for _ in range(3):
            QCoreApplication.processEvents()

    def test_instalar_agora_fecha_mesmo_com_fechar_para_bandeja(self) -> None:
        self.window.cfg.close_to_tray = True
        self.window.tray = MagicMock()
        self.window._on_app_update_ready(str(self.installer))
        self._pump()
        self.launch.assert_called_once_with(self.installer)
        self.assertFalse(self.window.isVisible())
        self.window.queue.stop_all.assert_called_once()
        self.window.tray = None

    def test_instalar_ao_fechar_espera_o_fechamento(self) -> None:
        self.window._install_mode = "on_exit"
        self.window._on_app_update_ready(str(self.installer))
        self._pump()
        self.launch.assert_not_called()
        self.assertTrue(self.window.isVisible())
        self.assertIn("fechar", self.window.update_banner.details.text())
        with patch.object(self.window, "_active_work", return_value=[]):
            self.window.close()
        self.launch.assert_called_once_with(self.installer)

    def test_tarefas_ativas_perguntam_antes_de_baixar(self) -> None:
        self.window._available_update = MagicMock()
        with patch.object(self.window, "_active_work", return_value=["downloads"]), \
                patch.object(self.window, "_ask_update_timing", return_value=None) as ask, \
                patch("baixador_ytdlp.ui.main_window.AppUpdateDownloadWorker") as worker:
            self.window._download_app_update()
        ask.assert_called_once_with(["downloads"])
        worker.assert_not_called()

    def test_trabalho_que_comecou_durante_o_download_e_confirmado(self) -> None:
        with patch.object(self.window, "_active_work", return_value=["legendas"]), \
                patch.object(self.window, "_confirm_install_now", return_value=False):
            self.window._on_app_update_ready(str(self.installer))
            self._pump()
        self.launch.assert_not_called()
        self.assertTrue(self.window.isVisible())
        self.assertEqual(self.window._install_mode, "on_exit")

    def test_esc_so_cancela_transcricao_com_confirmacao(self) -> None:
        page = self.window.transcription
        self.window.switchTo(page)
        with patch.object(page.cancel_btn, "isEnabled", return_value=True), \
                patch.object(page, "cancel") as cancel:
            with patch.object(self.window, "_confirm_cancel", return_value=False):
                self.window._shortcut_cancel()
            cancel.assert_not_called()
            with patch.object(self.window, "_confirm_cancel", return_value=True):
                self.window._shortcut_cancel()
            cancel.assert_called_once()

    def test_lembrar_depois_nao_pula_a_versao(self) -> None:
        release = MagicMock(version="9.9.9", tag="v9.9.9", size=0, notes="")
        self.window._available_update = release
        self.window.update_banner.show_release(release)
        self.window._dismiss_app_update()
        self.assertEqual(self.window.cfg.update_dismissed_version, "")
        self.assertFalse(self.window.update_banner.isVisible())
        self.window.update_banner.show_release(release)
        self.window._skip_app_update()
        self.assertEqual(self.window.cfg.update_dismissed_version, "9.9.9")


if __name__ == "__main__":
    unittest.main()
