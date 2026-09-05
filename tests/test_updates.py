"""Regressões para as checagens manuais de componentes e do aplicativo."""
from __future__ import annotations

import tempfile
import unittest
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import Mock, patch

from baixador_ytdlp.tools import DENO_EXE, FFMPEG_ASSET, FFMPEG_EXE, ToolManager
from baixador_ytdlp.updater import AppUpdater


class ToolCheckTests(unittest.TestCase):
    def test_manual_ytdlp_check_does_not_redownload_current_version(self) -> None:
        """"Verificar agora" consulta a origem, mas preserva o binário atual."""
        with tempfile.TemporaryDirectory() as tmp:
            manager = ToolManager(bin_dir=Path(tmp))
            (Path(tmp) / "yt-dlp").touch()
            manager.local_ytdlp_version = Mock(return_value="2026.09.01")
            manager._latest_ytdlp = Mock(return_value=("2026.09.01", "https://example.invalid/yt-dlp", {}))
            manager._download = Mock(side_effect=AssertionError("não deveria baixar"))
            manager._save_state = Mock()
            progress = Mock()

            manager.ensure_ytdlp(progress, check_now=True)

            manager._latest_ytdlp.assert_called_once()
            manager._download.assert_not_called()
            self.assertIn("já está atualizado", progress.call_args.args[0])

    def test_manual_ffmpeg_check_does_not_redownload_current_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ToolManager(bin_dir=Path(tmp))
            (Path(tmp) / FFMPEG_EXE).touch()
            asset = {
                "name": FFMPEG_ASSET,
                "id": 99,
                "updated_at": "2026-09-05T00:00:00Z",
                "browser_download_url": "https://example.invalid/ffmpeg.zip",
            }
            manager.local_ffmpeg_version = Mock(return_value="git-current")
            manager._request = Mock(return_value=nullcontext(None))
            manager._download = Mock(side_effect=AssertionError("não deveria baixar"))
            manager._save_state = Mock()
            manager.state["ffmpeg_stamp"] = "99:2026-09-05T00:00:00Z"

            with patch("baixador_ytdlp.tools.json.load", return_value={"assets": [asset]}):
                manager.ensure_ffmpeg(Mock(), check_now=True)

            manager._download.assert_not_called()

    def test_manual_deno_check_does_not_redownload_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ToolManager(bin_dir=Path(tmp))
            (Path(tmp) / DENO_EXE).touch()
            asset_name = manager._deno_asset_name()
            manager.local_deno_version = Mock(return_value="2.3.0")
            manager._request = Mock(return_value=nullcontext(None))
            manager._download = Mock(side_effect=AssertionError("não deveria baixar"))
            manager._save_state = Mock()
            payload = {
                "tag_name": "v2.3.0",
                "assets": [{"name": asset_name,
                            "browser_download_url": "https://example.invalid/deno.zip"}],
            }

            with patch("baixador_ytdlp.tools.json.load", return_value=payload):
                manager.ensure_deno(Mock(), check_now=True)

            manager._download.assert_not_called()


class AppUpdateTests(unittest.TestCase):
    def test_finds_versioned_installer_and_checksum(self) -> None:
        payload = {
            "tag_name": "v1.4.4",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": "BaixadorYtdlp-1.4.4-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
                },
            ],
        }
        checksum = "a" * 64 + "  dist/installer/BaixadorYtdlp-1.4.4-setup.exe\n"
        with patch("baixador_ytdlp.updater.IS_WINDOWS", True), \
                patch.object(AppUpdater, "_request_json", return_value=payload), \
                patch.object(AppUpdater, "_request_text", return_value=checksum):
            release = AppUpdater().find_update("1.4.3")

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.version, "1.4.4")
        self.assertEqual(release.installer_name, "BaixadorYtdlp-1.4.4-setup.exe")
        self.assertEqual(release.sha256, "a" * 64)

    def test_accepts_stable_installer_alias_for_older_release(self) -> None:
        payload = {
            "tag_name": "v1.4.4",
            "html_url": "https://example.invalid/release",
            "assets": [
                {
                    "name": "baixador-ytdlp-setup.exe",
                    "browser_download_url": "https://example.invalid/setup.exe",
                },
                {
                    "name": "SHA256SUMS.txt",
                    "browser_download_url": "https://example.invalid/SHA256SUMS.txt",
                },
            ],
        }
        checksum = "b" * 64 + "  baixador-ytdlp-setup.exe\n"
        with patch("baixador_ytdlp.updater.IS_WINDOWS", True), \
                patch.object(AppUpdater, "_request_json", return_value=payload), \
                patch.object(AppUpdater, "_request_text", return_value=checksum):
            release = AppUpdater().find_update("1.4.3")

        self.assertIsNotNone(release)
        assert release is not None
        self.assertEqual(release.installer_name, "baixador-ytdlp-setup.exe")


if __name__ == "__main__":
    unittest.main()
