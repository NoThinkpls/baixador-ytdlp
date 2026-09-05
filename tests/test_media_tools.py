from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from baixador_ytdlp.media_tools import MediaToolOptions, build_command, default_destination
from baixador_ytdlp.tools import Toolchain


class MediaToolsTests(unittest.TestCase):
    def _toolchain(self, root: Path) -> Toolchain:
        return Toolchain(
            ytdlp=root / "yt-dlp",
            ffmpeg=root / "ffmpeg",
            ffprobe=root / "ffprobe",
            bin_dir=root,
        )

    def test_add_subtitles_escapes_windows_style_path_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "vídeo de origem.mp4"
            subtitles = root / "Renan Santos: ação | CNN [final].srt"
            source.touch()
            subtitles.touch()
            command = build_command(MediaToolOptions(
                source=source,
                destination=root / "resultado.mp4",
                operation="burn",
                subtitles=subtitles,
            ), self._toolchain(root))

        filter_value = command[command.index("-vf") + 1]
        self.assertIn(r"\:", filter_value)
        self.assertNotIn(r"\\:", filter_value)
        self.assertIn(r"\|", filter_value)
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")
        self.assertIn("0:a?", command)
        self.assertIn("aac", command)

    def test_subtitle_destination_has_clear_name(self) -> None:
        result = default_destination(Path("/tmp/video.mp4"), "burn")
        self.assertEqual(result.name, "video_com_legendas.mp4")
