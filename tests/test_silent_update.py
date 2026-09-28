"""A atualização disparada pelo app pula o assistente e reabre o aplicativo."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.updater import AppUpdater

ROOT = Path(__file__).resolve().parents[1]


class SilentUpdateTests(unittest.TestCase):
    def test_instalador_roda_sem_assistente_mas_visivel(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            installer = Path(folder) / "setup.exe"
            installer.write_bytes(b"MZ")
            with patch("baixador_ytdlp.updater.IS_WINDOWS", True), \
                    patch("baixador_ytdlp.updater.subprocess.Popen") as popen:
                AppUpdater.launch_installer(installer)
        args = popen.call_args.args[0]
        self.assertIn("/SILENT", args)
        self.assertIn("/CLOSEAPPLICATIONS", args)
        self.assertNotIn("/VERYSILENT", args)

    def test_instalador_reabre_o_app_no_modo_silencioso(self) -> None:
        script = (ROOT / "installer.iss").read_text(encoding="utf-8")
        run = script[script.index("[Run]"):]
        self.assertIn("Check: WizardSilent", run)
        self.assertIn("skipifsilent", run)  # o modo interativo continua perguntando


if __name__ == "__main__":
    unittest.main()
