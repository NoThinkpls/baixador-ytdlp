"""FFmpeg fornece apenas os executáveis usados pelo app."""
from __future__ import annotations

import hashlib
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock

from baixador_ytdlp.tools import ToolManager


@unittest.skipUnless(sys.platform.startswith("win"), "Artefato FFmpeg é específico do Windows")
class FfplayRemovalTests(unittest.TestCase):
    def test_ffmpeg_archive_does_not_install_ffplay(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "source.zip"
            with zipfile.ZipFile(archive, "w") as output:
                for name in ("ffmpeg.exe", "ffprobe.exe", "ffplay.exe"):
                    output.writestr(f"ffmpeg/bin/{name}", name.encode())
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            manager = ToolManager(bin_dir=root / "bin")
            manager.local_ffmpeg_version = Mock(return_value="")
            manager._get_json = Mock(return_value={"assets": [{
                "name": "ffmpeg-n9.0-latest-win64-gpl-9.0.zip", "id": 1,
                "browser_download_url": "https://example.invalid/ffmpeg.zip",
                "digest": f"sha256:{digest}"}]})
            manager._download = Mock(side_effect=lambda _url, path, *_: shutil.copyfile(archive, path))
            manager._save_state = Mock()
            manager.bin_dir.mkdir()
            (manager.bin_dir / "ffplay.exe").write_bytes(b"legacy")

            manager.ensure_ffmpeg(Mock())

            self.assertTrue((manager.bin_dir / "ffmpeg.exe").is_file())
            self.assertTrue((manager.bin_dir / "ffprobe.exe").is_file())
            self.assertFalse((manager.bin_dir / "ffplay.exe").exists())
