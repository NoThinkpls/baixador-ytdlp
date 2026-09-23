from __future__ import annotations

import os
import tempfile
import unittest
import stat
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.cookies import import_cookie_file
from baixador_ytdlp.downloader import DownloadOptions, Transcoder, build_args
from baixador_ytdlp.media_tools import MediaToolOptions, build_command
from baixador_ytdlp.security import redact_sensitive, validate_media_url
from baixador_ytdlp.tools import IntegrityError, ToolManager, Toolchain


class SecurityRegressionTests(unittest.TestCase):
    def test_settings_coerce_types_and_backup_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            settings_path = Path(temporary) / "settings.json"
            settings_path.write_text(json.dumps({
                "settings_schema_version": 3,
                "concurrent_fragments": "8",
                "archive_enabled": "false",
                "download_profiles": "não é uma lista",
            }), encoding="utf-8")
            with patch("baixador_ytdlp.config.SETTINGS_PATH", settings_path):
                settings = Settings.load()
            self.assertEqual(settings.concurrent_fragments, 8)
            self.assertFalse(settings.archive_enabled)
            self.assertEqual(settings.download_profiles, [])

            settings_path.write_text("{inválido", encoding="utf-8")
            with patch("baixador_ytdlp.config.SETTINGS_PATH", settings_path):
                Settings.load()
            self.assertFalse(settings_path.exists())
            self.assertEqual(len(list(Path(temporary).glob("settings.corrompido-*.json"))), 1)

    def test_imported_cookies_are_user_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "exportado.txt"
            source.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            with patch("baixador_ytdlp.cookies.COOKIES_DIR", root / "privado"):
                destination, warning = import_cookie_file(source)
            self.assertEqual(destination.name, "cookies.txt")
            self.assertEqual(warning, "")
            self.assertEqual(destination.read_text(encoding="utf-8"), source.read_text(encoding="utf-8"))
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o600)

    def test_windows_acl_uses_sid_and_absolute_system32_paths(self) -> None:
        """O nome vindo do whoami quebrava com acentos (CP850 x CP1252)."""
        from baixador_ytdlp import cookies

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "exportado.txt"
            source.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            calls = []

            def fake_run(command, **kwargs):
                calls.append((command, kwargs))
                stdout = '"desktop\\joão","S-1-5-21-1-2-3-1001"' if "whoami" in command[0] else ""
                return SimpleNamespace(stdout=stdout, returncode=0)

            with patch("baixador_ytdlp.cookies.COOKIES_DIR", root / "privado"), \
                    patch("baixador_ytdlp.cookies.IS_WINDOWS", True), \
                    patch("baixador_ytdlp.cookies.subprocess.run", side_effect=fake_run):
                cookies.import_cookie_file(source)
        whoami, icacls = calls
        self.assertTrue(whoami[0][0].lower().endswith("whoami.exe"))
        self.assertTrue(icacls[0][0].lower().endswith("icacls.exe"))
        self.assertIn("*S-1-5-21-1-2-3-1001:(R,W)", icacls[0])
        self.assertIn("creationflags", icacls[1])

    def test_url_is_validated_and_placed_after_end_of_options(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions("https://example.invalid/watch?token=secret", "downloads"),
            Settings(), tools,
        )
        self.assertEqual(args[-2], "--")
        self.assertTrue(args[-1].startswith("https://"))
        with self.assertRaises(ValueError):
            validate_media_url("--exec=calc")

    def test_sensitive_values_are_redacted(self) -> None:
        text = redact_sensitive(
            "--proxy https://user:pass@proxy.invalid --cookies C:/secret.txt "
            "https://example.invalid/file?token=abc&sig=def Authorization:Bearer-secret"
        )
        self.assertNotIn("user:pass", text)
        self.assertNotIn("secret.txt", text)
        self.assertNotIn("token=abc", text)
        self.assertNotIn("sig=def", text)
        self.assertNotIn("Bearer-secret", text)

    def test_missing_or_wrong_checksum_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "tool"
            path.write_bytes(b"safe")
            with self.assertRaises(IntegrityError):
                ToolManager.require_sha256(path, "", "ferramenta")
            self.assertFalse(path.exists())
            path.write_bytes(b"safe")
            with self.assertRaises(IntegrityError):
                ToolManager.require_sha256(path, "0" * 64, "ferramenta")
            self.assertFalse(path.exists())

    def test_trim_end_is_interpreted_in_the_input_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "in.mp4"
            source.touch()
            tools = Toolchain(root / "yt-dlp", root / "ffmpeg", root / "ffprobe", root)
            command = build_command(MediaToolOptions(
                source, root / "out.mkv", "trim", start="3", end="5"
            ), tools)
        self.assertLess(command.index("-ss"), command.index("-i"))
        self.assertLess(command.index("-to"), command.index("-i"))

    def test_mp4_transcode_drops_incompatible_extra_streams(self) -> None:
        tools = Toolchain(Path("yt-dlp"), Path("ffmpeg"), Path("ffprobe"), Path("."))
        command = Transcoder(tools, Settings()).build_args(Path("in.mkv"), Path("out.mp4"))
        self.assertNotIn("-c:s", command)
        self.assertIn("-0:d?", command)
        self.assertIn("-0:t?", command)


if __name__ == "__main__":
    unittest.main()
