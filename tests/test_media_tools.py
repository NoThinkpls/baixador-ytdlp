from __future__ import annotations

import tempfile
import unittest
import shutil
import subprocess
from pathlib import Path

from baixador_ytdlp.media_tools import (MediaToolError, MediaToolOptions, build_command,
                                        default_destination, operation_duration)
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

    def test_trim_rejects_end_before_start(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.mp4"
            source.touch()
            with self.assertRaisesRegex(MediaToolError, "posterior"):
                build_command(MediaToolOptions(source, root / "out.mkv", "trim", "5", "3"),
                              self._toolchain(root))

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg ausente")
    def test_trim_creates_decodable_clip_at_non_keyframe(self) -> None:
        """Uma busca no meio de um GOP longo precisa produzir só o trecho verde."""
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, output = root / "source.mp4", root / "trecho.mkv"
            tc = Toolchain(root / "yt-dlp", Path(shutil.which("ffmpeg")),
                           Path(shutil.which("ffprobe")), root)
            subprocess.run([
                str(tc.ffmpeg), "-v", "error", "-f", "lavfi", "-i",
                "color=c=red:s=64x64:r=25:d=2", "-f", "lavfi", "-i",
                "color=c=green:s=64x64:r=25:d=2", "-f", "lavfi", "-i",
                "color=c=blue:s=64x64:r=25:d=2", "-f", "lavfi", "-i",
                "sine=frequency=440:duration=6", "-filter_complex",
                "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]",
                "-map", "3:a", "-c:v", "mpeg4", "-g", "150", "-q:v", "2",
                "-c:a", "aac", str(source),
            ], check=True, capture_output=True)
            command = build_command(MediaToolOptions(
                source, output, "trim", "2.2", "3.4"), tc)
            subprocess.run(command, check=True, capture_output=True)
            duration = subprocess.check_output([
                str(tc.ffprobe), "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", str(output),
            ], text=True)
            self.assertAlmostEqual(float(duration), 1.2, delta=0.08)
            first = subprocess.check_output([
                str(tc.ffmpeg), "-v", "error", "-i", str(output), "-frames:v", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
            ])
            self.assertEqual(len(first), 64 * 64 * 3)
            self.assertGreater(first[64 * 64 * 3 // 2 + 1], 90)  # verde no centro
            streams = subprocess.check_output([
                str(tc.ffprobe), "-v", "error", "-show_entries", "stream=codec_type",
                "-of", "csv=p=0", str(output),
            ], text=True)
            self.assertEqual(streams.splitlines(), ["video", "audio"])
            with self.assertRaisesRegex(MediaToolError, "dentro da duração"):
                operation_duration(MediaToolOptions(
                    source, root / "fora.mkv", "trim", "10", "12"), tc)
