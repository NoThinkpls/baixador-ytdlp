from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions
from baixador_ytdlp.filename_preview import render_filename_preview
from baixador_ytdlp.media_tools import (MediaToolOptions, build_command, default_destination,
                                        operation_duration)
from baixador_ytdlp.queue_state import QueueState
from baixador_ytdlp.tools import Toolchain
from baixador_ytdlp.transcription import (FASTER_MODEL_SPECS, MLX_MODEL_SPECS,
                                          TranscriptionOptions)


class ExperienceReleaseTests(unittest.TestCase):
    def test_filename_preview_renders_common_fields_without_network(self) -> None:
        result = render_filename_preview(
            "%(upload_date)s - %(uploader)s - %(title).180B [%(height)sp].%(ext)s",
            {"title": "Vídeo", "uploader": "Canal", "upload_date": "20260923", "height": 1080},
            "mp4",
        )
        self.assertEqual(result, "20260923 - Canal - Vídeo [1080p].mp4")

    def test_download_to_transcription_flags_survive_queue_restore(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state = QueueState(Path(directory) / "queue.json")
            original = DownloadOptions(
                "https://example.com/video",
                directory,
                transcribe_after=True,
                embed_transcription=True,
            )
            state.save([original])
            restored = state.load()
        self.assertTrue(restored[0].transcribe_after)
        self.assertTrue(restored[0].embed_transcription)

    def test_soft_subtitle_keeps_media_streams_and_adds_progress(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "video.mp4"
            subtitle = root / "video.srt"
            source.touch()
            subtitle.touch()
            destination = default_destination(source, "soft_sub")
            tc = Toolchain(root / "yt-dlp", root / "ffmpeg", root / "ffprobe", root)
            command = build_command(
                MediaToolOptions(source, destination, "soft_sub", subtitles=subtitle),
                tc,
            )
        self.assertIn("-progress", command)
        self.assertIn("pipe:1", command)
        self.assertIn("mov_text", command)
        self.assertEqual(command[-1], str(destination))

    def test_trim_progress_uses_only_the_requested_interval(self) -> None:
        options = MediaToolOptions(Path("video.mp4"), Path("out.mkv"), "trim", "00:00:03", "00:00:05")
        with patch("baixador_ytdlp.media_tools.media_duration", return_value=10.0):
            self.assertEqual(operation_duration(options, SimpleNamespace()), 2.0)

    def test_turbo_models_are_pinned_to_full_revisions(self) -> None:
        for specs in (FASTER_MODEL_SPECS, MLX_MODEL_SPECS):
            repository, revision = specs["large-v3-turbo"]
            self.assertIn("large-v3-turbo", repository)
            self.assertRegex(revision, r"^[0-9a-f]{40}$")

    def test_transcription_options_expose_context_and_readability_limits(self) -> None:
        options = TranscriptionOptions(
            Path("input.mp4"),
            Path("output.srt"),
            task="translate",
            initial_prompt="Wazuh, FFmpeg",
            max_chars_per_line=42,
            min_duration=1.0,
            max_duration=5.0,
        )
        self.assertEqual(options.task, "translate")
        self.assertEqual(options.initial_prompt, "Wazuh, FFmpeg")
        self.assertEqual(options.max_chars_per_line, 42)

    def test_new_background_behaviour_is_opt_in(self) -> None:
        settings = Settings()
        self.assertTrue(settings.tray_notifications)
        self.assertFalse(settings.close_to_tray)


if __name__ == "__main__":
    unittest.main()
