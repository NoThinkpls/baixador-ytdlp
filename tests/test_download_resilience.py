"""Regressões da retomada, anti-duplicidade e metadados da análise."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, build_args, is_retryable_error
from baixador_ytdlp.probe import _audio_languages, _caption_languages
from baixador_ytdlp.queue_state import QueueState


class QueueStateTests(unittest.TestCase):
    def test_legacy_settings_enable_duplicate_protection_on_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text('{"archive_enabled": false}', encoding="utf-8")
            with patch("baixador_ytdlp.config.SETTINGS_PATH", path):
                settings = Settings.load()

        self.assertTrue(settings.archive_enabled)
        self.assertTrue(settings.resume_queue)
        self.assertEqual(settings.settings_schema_version, 2)

    def test_restores_only_valid_interrupted_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = QueueState(Path(temporary) / "queue.json")
            expected = DownloadOptions(
                url="https://example.invalid/watch?v=123", output_dir="/downloads",
                audio_only=True, audio_format="m4a", title="Faixa",
            )
            store.save([expected])
            store.path.write_text(
                store.path.read_text(encoding="utf-8")[:-1] + ", {\"url\": 4}]",
                encoding="utf-8",
            )
            restored = store.load()

        self.assertEqual(restored, [expected])

    def test_invalid_state_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = QueueState(Path(temporary) / "queue.json")
            store.path.write_text("not json", encoding="utf-8")
            self.assertEqual(store.load(), [])


class DownloadArgumentsTests(unittest.TestCase):
    def test_audio_keeps_metadata_cover_and_organized_name(self) -> None:
        cfg = Settings(embed_thumbnail=True, embed_metadata=True, embed_chapters=True,
                       organize_audio_by_uploader=True)
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions("https://example.invalid/video", "downloads", audio_only=True),
            cfg, tools,
        )

        self.assertIn("--continue", args)
        self.assertIn("--file-access-retries", args)
        self.assertIn("--embed-thumbnail", args)
        self.assertIn("--convert-thumbnails", args)
        self.assertIn("--embed-metadata", args)
        self.assertIn("--embed-chapters", args)
        template = args[args.index("--output") + 1]
        self.assertTrue(template.startswith("%(uploader|Canal desconhecido)s/"))

    def test_only_transient_failures_are_retried(self) -> None:
        self.assertTrue(is_retryable_error("ERROR: HTTP Error 503: Service Unavailable"))
        self.assertTrue(is_retryable_error("ERROR: connection reset by peer"))
        self.assertFalse(is_retryable_error("ERROR: Unsupported URL"))
        self.assertFalse(is_retryable_error("ERROR: Private video"))


class ProbeMetadataTests(unittest.TestCase):
    def test_extracts_audio_and_caption_languages_for_preview(self) -> None:
        payload = {
            "language": "pt-BR",
            "formats": [
                {"acodec": "opus", "language": "en"},
                {"acodec": "mp4a.40.2", "language": "pt-BR"},
                {"acodec": "none", "language": "es"},
            ],
        }
        captions = {"pt-BR": [{"ext": "vtt"}], "en": [{"ext": "json3"}], "es": []}

        self.assertEqual(_audio_languages(payload), ["en", "pt-BR"])
        self.assertEqual(_caption_languages(captions), ["en", "pt-BR"])


if __name__ == "__main__":
    unittest.main()
