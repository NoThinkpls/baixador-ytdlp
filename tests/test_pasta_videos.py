"""Pasta padrão de downloads no macOS e no Linux.

Até a 1.13.8 era sempre ``~/Videos``: no Mac a pasta certa é ``~/Movies`` e no Linux em
português o sistema usa ``~/Vídeos``, então o app criava uma pasta paralela.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from baixador_ytdlp.config import _videos_dir


class PastaVideosTests(unittest.TestCase):
    def test_macos_usa_movies(self) -> None:
        self.assertEqual(_videos_dir(Path("/Users/ana"), {}, "darwin"), Path("/Users/ana/Movies"))

    def test_linux_le_o_nome_traduzido_do_user_dirs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            (home / ".config").mkdir()
            (home / ".config" / "user-dirs.dirs").write_text(
                '# comentário\nXDG_DOWNLOAD_DIR="$HOME/Downloads"\nXDG_VIDEOS_DIR="$HOME/Vídeos"\n',
                encoding="utf-8")
            self.assertEqual(_videos_dir(home, {}, "linux"), home / "Vídeos")

    def test_linux_sem_user_dirs_ou_desativado_usa_videos(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(_videos_dir(home, {}, "linux"), home / "Videos")
            config = home / "cfg"
            config.mkdir()
            (config / "user-dirs.dirs").write_text('XDG_VIDEOS_DIR="$HOME/"\n', encoding="utf-8")
            self.assertEqual(_videos_dir(home, {"XDG_CONFIG_HOME": str(config)}, "linux"),
                             home / "Videos")


if __name__ == "__main__":
    unittest.main()
