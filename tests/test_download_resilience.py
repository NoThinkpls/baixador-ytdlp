"""Regressões da retomada, anti-duplicidade e metadados da análise."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import (
    DownloadError, DownloadOptions, DownloadRunner, build_args, is_retryable_error,
)
from baixador_ytdlp.probe import _audio_languages, _caption_languages
from baixador_ytdlp.queue_state import QueueState

try:
    from PySide6.QtWidgets import QApplication
    from baixador_ytdlp.ui.queue_page import QueuePage
except ModuleNotFoundError:
    QApplication = None


class QueueStateTests(unittest.TestCase):
    def test_legacy_settings_enable_duplicate_protection_on_migration(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "settings.json"
            path.write_text('{"archive_enabled": false}', encoding="utf-8")
            with patch("baixador_ytdlp.config.SETTINGS_PATH", path):
                settings = Settings.load()

        self.assertTrue(settings.archive_enabled)
        self.assertTrue(settings.resume_queue)
        self.assertEqual(settings.settings_schema_version, 4)

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
        self.assertEqual(args[args.index("--socket-timeout") + 1], "30")
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

    def test_exact_video_cut_reports_progress_and_uses_nvenc(self) -> None:
        cfg = Settings(transcode_enabled=False)
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions(
                "https://example.invalid/video", "downloads",
                section_start="01:04:30", section_end="01:46:00",
            ),
            cfg, tools, section_encoder="h264_nvenc",
        )

        self.assertIn("--force-keyframes-at-cuts", args)
        downloader_args = [
            args[index + 1]
            for index, value in enumerate(args)
            if value == "--downloader-args"
        ]
        self.assertIn(
            "ffmpeg_i:-hwaccel cuda -hwaccel_output_format cuda",
            downloader_args,
        )
        output_args = next(value for value in downloader_args if value.startswith("ffmpeg_o:"))
        self.assertIn("-progress pipe:1", output_args)
        self.assertIn("-c:v h264_nvenc", output_args)
        self.assertIn("-cq 18", output_args)

    def test_exact_video_cut_can_keep_gpu_encoder_without_gpu_decoder(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions(
                "https://example.invalid/video", "downloads",
                section_start="10", section_end="20",
            ),
            Settings(), tools, section_encoder="h264_nvenc", section_hwaccel=False,
        )

        downloader_args = [
            args[index + 1]
            for index, value in enumerate(args)
            if value == "--downloader-args"
        ]
        self.assertFalse(any(value.startswith("ffmpeg_i:") for value in downloader_args))
        self.assertTrue(any("-c:v h264_nvenc" in value for value in downloader_args))

    def test_exact_cut_retries_nvenc_without_gpu_decoder_before_cpu_fallback(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        runner = DownloadRunner(
            DownloadOptions(
                "https://example.invalid/video", "downloads",
                section_start="10", section_end="20",
            ),
            Settings(), tools,
        )
        callback = Mock()
        expected = [Path("downloads/trecho.mp4")]
        with patch.object(
            runner, "_run_once", side_effect=[DownloadError("nvcuda falhou"), expected],
        ) as run_once, patch.object(runner, "_is_encoder_failure", return_value=True), \
                patch("baixador_ytdlp.downloader.log_event"):
            self.assertEqual(runner._run_section(callback, "h264_nvenc"), expected)

        self.assertEqual(run_once.call_count, 2)
        self.assertTrue(run_once.call_args_list[0].kwargs["section_hwaccel"])
        self.assertFalse(run_once.call_args_list[1].kwargs["section_hwaccel"])
        self.assertEqual(run_once.call_args_list[1].args[1], "h264_nvenc")

    def test_audio_cut_does_not_force_a_pointless_video_reencode(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions(
                "https://example.invalid/audio", "downloads", audio_only=True,
                section_start="10", section_end="20",
            ),
            Settings(), tools, section_encoder="h264_nvenc",
        )

        self.assertIn("--download-sections", args)
        self.assertNotIn("--force-keyframes-at-cuts", args)
        self.assertNotIn("--downloader-args", args)


@unittest.skipUnless(QApplication is not None, "PySide6 não está instalado neste ambiente")
class QueuePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_pending_item_is_removed_from_ui_and_persisted_state(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            page = QueuePage(Settings())
            page._state = QueueState(Path(temporary) / "queue.json")
            options = DownloadOptions("https://example.invalid/video", temporary)
            self.assertTrue(page._add(options))
            job_id = next(iter(page.jobs))

            page.cancel(job_id)

            self.assertNotIn(job_id, page.jobs)
            self.assertEqual(page._state.load(), [])
            self.assertFalse(page.empty.isHidden())
            page.deleteLater()

    def test_confirmed_duplicate_can_be_added_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            page = QueuePage(Settings())
            page._state = QueueState(Path(temporary) / "queue.json")
            options = DownloadOptions("https://example.invalid/video", temporary)

            self.assertTrue(page._add(options))
            self.assertFalse(page._add(options))
            self.assertTrue(page._add(options, allow_duplicate=True))
            self.assertEqual(len(page._state.load()), 2)
            page.deleteLater()

    def test_active_item_disappears_and_is_not_restored_while_worker_stops(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            page = QueuePage(Settings())
            page._state = QueueState(Path(temporary) / "queue.json")
            options = DownloadOptions("https://example.invalid/video", temporary)
            self.assertTrue(page._add(options))
            job_id = next(iter(page.jobs))
            job = page.jobs[job_id]
            page.pending.remove(job_id)
            job.active = True
            job.worker = Mock()
            page._persist()

            page.cancel(job_id)

            job.worker.cancel.assert_called_once_with()
            self.assertTrue(job.removing)
            self.assertTrue(job.card.isHidden())
            self.assertEqual(page._state.load(), [])
            self.assertEqual(page._running(), 0)

            page._on_failed(job_id, "Cancelado")
            self.assertNotIn(job_id, page.jobs)
            page.deleteLater()


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
