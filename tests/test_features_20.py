"""Funcionalidades da 2.0: protocolo, playlist, ferramentas, canal e diagnóstico."""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, build_args
from baixador_ytdlp.media_tools import (MediaToolError, MediaToolOptions, build_command,
                                        target_video_kbps)
from baixador_ytdlp.probe import compress_indices
from baixador_ytdlp.security import media_url_from_argument
from baixador_ytdlp.tools import (YTDLP_NIGHTLY_API, YTDLP_RELEASE_API, Toolchain,
                                  ToolManager)


def _toolchain(root: Path) -> Toolchain:
    return Toolchain(ytdlp=root / "yt-dlp", ffmpeg=root / "ffmpeg",
                     ffprobe=root / "ffprobe", bin_dir=root)


class ProtocolTests(unittest.TestCase):
    def test_protocol_and_plain_urls(self) -> None:
        url = "https://youtu.be/abc"
        for value in (url, "baixador://baixar?url=https%3A%2F%2Fyoutu.be%2Fabc",
                      "baixador:https://youtu.be/abc", "baixador://https//youtu.be/abc"):
            self.assertEqual(media_url_from_argument(value), url, value)

    def test_protocol_never_accepts_other_schemes_or_options(self) -> None:
        for value in ("baixador://baixar?url=file:///etc/passwd", "--exec=calc",
                      "baixador://baixar?url=javascript:alert(1)", "baixador://"):
            self.assertEqual(media_url_from_argument(value), "", value)


class PlaylistItemsTests(unittest.TestCase):
    def test_compress_ranges(self) -> None:
        self.assertEqual(compress_indices([9, 1, 2, 3, 5, 8]), "1-3,5,8-9")

    def test_selected_items_reach_ytdlp_only_when_well_formed(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(DownloadOptions("https://example.invalid/playlist?list=x", "out",
                                          playlist=True, playlist_items="1-3,7"),
                          Settings(), tools)
        self.assertEqual(args[args.index("--playlist-items") + 1], "1-3,7")
        args = build_args(DownloadOptions("https://example.invalid/playlist?list=x", "out",
                                          playlist=True, playlist_items="1; --exec calc"),
                          Settings(), tools)
        self.assertNotIn("--playlist-items", args)


class MediaToolFeatureTests(unittest.TestCase):
    def test_target_bitrate_fits_with_margin(self) -> None:
        video = target_video_kbps(25, 120)
        total_mb = (video + 128) * 120 / 8_000
        self.assertLess(total_mb, 25)
        self.assertGreater(total_mb, 22)
        with self.assertRaises(MediaToolError):
            target_video_kbps(8, 3600)

    def test_shorts_blur_uses_single_video_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "video.mp4"
            source.touch()
            command = build_command(MediaToolOptions(source, root / "out.mp4", "shorts"),
                                    _toolchain(root))
        self.assertIn("-filter_complex", command)
        self.assertEqual(command[command.index("-filter_complex") + 2:][:2], ["-map", "[v]"])
        self.assertNotIn("0:v:0", command)


class ChannelAndDiagnosticsTests(unittest.TestCase):
    def test_nightly_channel_uses_nightly_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            manager = ToolManager(bin_dir=Path(temporary), ytdlp_channel="nightly")
            calls = []
            manager._get_json = lambda url: calls.append(url) or {"tag_name": "x", "assets": []}
            manager._latest_ytdlp()
            self.assertEqual(calls, [YTDLP_NIGHTLY_API])
            self.assertEqual(ToolManager(bin_dir=Path(temporary),
                                         ytdlp_channel="??").ytdlp_channel, "stable")
        self.assertNotEqual(YTDLP_NIGHTLY_API, YTDLP_RELEASE_API)

    def test_diagnostics_zip_is_redacted(self) -> None:
        from baixador_ytdlp import diagnostics

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "app.log").write_text(
                f"--proxy http://u:senha@h:1 {Path.home()}{os.sep}x.mp4 ?token=abc\n",
                encoding="utf-8")
            with patch.object(diagnostics, "LOG_DIR", root):
                target = diagnostics.export_diagnostics(
                    root / "diag", Settings(proxy="http://u:senha@h:1", cookies_file="c.txt"))
            with zipfile.ZipFile(target) as archive:
                content = archive.read("logs/app.log").decode("utf-8")
                settings = archive.read("configuracoes.json").decode("utf-8")
        self.assertNotIn("senha", content)
        self.assertNotIn("abc", content)
        self.assertNotIn(str(Path.home()), content)
        self.assertNotIn("proxy", settings)
        self.assertNotIn("cookies_file", settings)


@unittest.skipIf(os.environ.get("QT_QPA_PLATFORM") != "offscreen", "requer Qt offscreen")
class PlaylistPickerTests(unittest.TestCase):
    def test_selection_round_trip(self) -> None:
        from PySide6.QtWidgets import QApplication

        from baixador_ytdlp.probe import PlaylistEntry
        from baixador_ytdlp.ui.playlist_picker import PlaylistPickerDialog

        QApplication.instance() or QApplication([])
        entries = [PlaylistEntry(i, f"Vídeo {i}", "1:00", str(i)) for i in range(1, 7)]
        dialog = PlaylistPickerDialog(entries, "2-3,6")
        self.assertEqual(dialog.selection(), "2-3,6")
        dialog._set_visible(True)
        self.assertEqual(dialog.selection(), "")  # tudo marcado = playlist inteira


if __name__ == "__main__":
    unittest.main()
