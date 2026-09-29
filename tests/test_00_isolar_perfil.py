"""Os testes nunca podem gravar no perfil real do usuário.

Este arquivo tem o prefixo ``test_00`` para ser importado primeiro: a variável abaixo
precisa existir antes de qualquer módulo do app ler ``baixador_ytdlp.config``. Em 29/09/2026
a suíte rodada numa máquina de desenvolvimento gravou ``history_enabled=false`` e uma pasta
temporária como pasta de downloads no ``settings.json`` real.
"""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile
import unittest
from pathlib import Path

if not os.environ.get("BAIXADOR_YTDLP_DATA_DIR"):
    _SANDBOX = tempfile.mkdtemp(prefix="baixador-testes-")
    os.environ["BAIXADOR_YTDLP_DATA_DIR"] = _SANDBOX
    atexit.register(shutil.rmtree, _SANDBOX, ignore_errors=True)


class ProfileIsolationTests(unittest.TestCase):
    def test_data_dir_is_the_sandbox_not_the_real_profile(self) -> None:
        from baixador_ytdlp import config

        expected = Path(os.environ["BAIXADOR_YTDLP_DATA_DIR"])
        self.assertEqual(config.DATA_DIR, expected)
        for path in (config.SETTINGS_PATH, config.HISTORY_PATH, config.QUEUE_STATE_PATH):
            self.assertEqual(path.parent, expected)


if __name__ == "__main__":
    unittest.main()
