"""Regressões para as checagens manuais de componentes e do aplicativo."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from baixador_ytdlp.tools import (DENO_EXE, FFMPEG_EXE, ToolManager, pick_btbn_asset,
                                  pick_deno_release)
from baixador_ytdlp.updater import AppUpdater


class ToolCheckTests(unittest.TestCase):
    def test_accepts_sha256_digest_exposed_by_github_assets(self) -> None:
        digest = "a" * 64
        self.assertEqual(ToolManager._asset_sha256({"digest": f"sha256:{digest}"}), digest)
        self.assertEqual(ToolManager._asset_sha256({"digest": "sha512:bad"}), "")

    def test_reads_current_deno_powershell_checksum_format(self) -> None:
        digest = "a0c3101b4158d1dfb7d6a78a7bf0f3de80c96bb423c152beec8beb22786f2238"
        response = Mock()
        response.read.return_value = (
            f"\r\nAlgorithm : SHA256\r\nHash      : {digest.upper()}\r\n"
            "Path      : C:\\a\\deno.zip\r\n"
        ).encode()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        manager = ToolManager()
        manager._request = Mock(return_value=response)

        actual = manager._remote_sha256({
            "browser_download_url": "https://example.invalid/deno.sha256sum",
        })

        self.assertEqual(actual, digest)

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
                "name": "ffmpeg-n8.1-latest-win64-gpl-8.1.zip",
                "id": 99,
                "updated_at": "2026-09-05T00:00:00Z",
                "browser_download_url": "https://example.invalid/ffmpeg.zip",
            }
            manager.local_ffmpeg_version = Mock(return_value="git-current")
            manager._get_json = Mock(return_value={"assets": [asset]})
            manager._download = Mock(side_effect=AssertionError("não deveria baixar"))
            manager._save_state = Mock()
            manager.state["ffmpeg_stamp"] = "99:2026-09-05T00:00:00Z"

            with patch("baixador_ytdlp.tools.IS_WINDOWS", True), \
                    patch("baixador_ytdlp.tools.sys.platform", "win32"):
                manager.ensure_ffmpeg(Mock(), check_now=True)

            manager._download.assert_not_called()

    def test_manual_deno_check_does_not_redownload_current_version(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ToolManager(bin_dir=Path(tmp))
            (Path(tmp) / DENO_EXE).touch()
            asset_name = manager._deno_asset_name()
            manager.local_deno_version = Mock(return_value="2.3.0")
            manager._download = Mock(side_effect=AssertionError("não deveria baixar"))
            manager._save_state = Mock()
            payload = {
                "tag_name": "v2.3.0",
                "assets": [{"name": asset_name,
                            "browser_download_url": "https://example.invalid/deno.zip"}],
            }

            manager._get_json = Mock(return_value=[payload])
            manager.ensure_deno(Mock(), check_now=True)

            manager._download.assert_not_called()


class ReleaseSelectionTests(unittest.TestCase):
    def test_ffmpeg_picks_highest_stable_branch(self) -> None:
        names = [
            "ffmpeg-master-latest-win64-gpl.zip",
            "ffmpeg-n8.1-latest-win64-gpl-8.1.zip",
            "ffmpeg-n9.0-latest-win64-gpl-9.0.zip",
            "ffmpeg-n9.0-latest-win64-gpl-shared-9.0.zip",
            "ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz",
        ]
        assets = [{"name": name} for name in names]
        self.assertEqual(pick_btbn_asset(assets, "win64")["name"],
                         "ffmpeg-n9.0-latest-win64-gpl-9.0.zip")
        self.assertEqual(pick_btbn_asset(assets, "x86_64")["name"],
                         "ffmpeg-n9.0-latest-linux64-gpl-9.0.tar.xz")

    def test_ffmpeg_without_stable_branch_is_an_error(self) -> None:
        with self.assertRaises(RuntimeError):
            pick_btbn_asset([{"name": "ffmpeg-master-latest-win64-gpl.zip"}], "win64")

    def test_deno_keeps_latest_supported_major(self) -> None:
        releases = [{"tag_name": "v3.0.0"}, {"tag_name": "v2.9.7"},
                    {"tag_name": "v2.10.1"}, {"tag_name": "v2.11.0", "prerelease": True}]
        self.assertEqual(pick_deno_release(releases)["tag_name"], "v2.10.1")


class IntegrityRepairTests(unittest.TestCase):
    def test_tampered_binary_is_removed_and_forces_download(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / ("yt-dlp.exe" if sys.platform.startswith("win") else "yt-dlp")
            binary.write_bytes(b"original")
            baseline_stat = binary.stat()
            with patch("baixador_ytdlp.tools.STATE_PATH", root / "state.json"):
                manager = ToolManager(bin_dir=root)
                manager._record_integrity(binary.name, binary)
                manager.state["ytdlp_checked_at"] = 1e12
                binary.write_bytes(b"alterado")
                # Os dois conteúdos têm o mesmo tamanho. Em NTFS, escritas no
                # mesmo tick podem manter o mtime; force a alteração que o
                # caminho rápido de integridade verifica em produção.
                os.utime(binary, ns=(baseline_stat.st_atime_ns,
                                     baseline_stat.st_mtime_ns + 1_000_000_000))
                messages = []
                repaired = manager.repair_tampered_tools(lambda msg, _pct: messages.append(msg))
            self.assertEqual(repaired, [binary.name])
            self.assertFalse(binary.exists())
            self.assertNotIn("ytdlp_checked_at", manager.state)
            self.assertIn("alterado fora do aplicativo", messages[0])

    def test_unchanged_binary_skips_full_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "deno"
            binary.write_bytes(b"x" * 1024)
            with patch("baixador_ytdlp.tools.STATE_PATH", root / "state.json"):
                manager = ToolManager(bin_dir=root)
                manager._record_integrity("deno", binary)
                with patch.object(ToolManager, "_sha256", side_effect=AssertionError("hash")):
                    self.assertTrue(manager._integrity_ok("deno", binary))


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

