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

        self.assertFalse(settings.archive_enabled)
        self.assertTrue(settings.resume_queue)
        self.assertEqual(settings.settings_schema_version, 6)

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
    def test_old_archive_setting_never_skips_a_new_request(self) -> None:
        cfg = Settings(archive_enabled=True)
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        opts = DownloadOptions("https://example.invalid/video", "downloads")
        args = build_args(opts, cfg, tools)
        self.assertNotIn("--download-archive", args)
        self.assertIn("--continue", args)
        opts.repeat_index = 2
        args = build_args(opts, cfg, tools)
        self.assertIn(" (2).%(ext)s", args[args.index("--output") + 1])

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

    def test_video_cut_uses_stream_copy_and_reports_progress(self) -> None:
        cfg = Settings(transcode_enabled=True, transcode_codec="h264_nvenc")
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions(
                "https://example.invalid/video", "downloads",
                section_start="01:04:30", section_end="01:46:00",
            ),
            cfg, tools,
        )

        self.assertNotIn("--force-keyframes-at-cuts", args)
        downloader_args = [
            args[index + 1]
            for index, value in enumerate(args)
            if value == "--downloader-args"
        ]
        self.assertEqual(downloader_args, ["ffmpeg_o:-progress pipe:1 -nostats"])
        self.assertFalse(any("nvenc" in value or "cuda" in value for value in args))

    def test_section_download_only_adds_download_sections(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        full = DownloadOptions("https://www.youtube.com/live/example", "downloads")
        cut = DownloadOptions("https://www.youtube.com/live/example", "downloads",
                              section_start="00:53:45", section_end="02:16:30")
        cfg = Settings()
        base = build_args(full, cfg, tools)
        args = build_args(cut, cfg, tools)

        self.assertEqual(args[args.index("--download-sections") + 1], "*00:53:45-02:16:30")
        # Sem seletor de protocolo nem recodificação: o corte é só o argumento do yt-dlp.
        self.assertNotIn("proto:m3u8", args)
        self.assertNotIn("--force-keyframes-at-cuts", args)
        self.assertEqual(args[args.index("-f") + 1], full.selector)
        self.assertEqual([a for a in args if a not in base],
                         ["--download-sections", "*00:53:45-02:16:30",
                          "--downloader-args", "ffmpeg_o:-progress pipe:1 -nostats"])

    def test_exact_cut_runs_once_without_probing_gpu(self) -> None:
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
        with patch.object(runner, "_run_once", return_value=expected) as run_once:
            self.assertEqual(runner.run(callback), expected)
        run_once.assert_called_once_with(callback)

    def test_section_never_reports_success_without_output_file(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"), env=Mock(return_value={}))
        runner = DownloadRunner(
            DownloadOptions("https://example.invalid/video", "downloads",
                            section_start="10", section_end="20"), Settings(), tools,
        )
        process = Mock(stdout=iter(()))
        process.wait.return_value = 0
        with patch("baixador_ytdlp.downloader.popen_isolated", return_value=process), \
                patch("baixador_ytdlp.downloader.log_event"):
            with self.assertRaisesRegex(DownloadError, "sem informar um arquivo"):
                runner.run(Mock())

    def test_audio_cut_does_not_force_a_pointless_video_reencode(self) -> None:
        tools = SimpleNamespace(ytdlp=Path("yt-dlp"), bin_dir=Path("bin"))
        args = build_args(
            DownloadOptions(
                "https://example.invalid/audio", "downloads", audio_only=True,
                section_start="10", section_end="20",
            ),
            Settings(), tools,
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

    def test_pause_and_resume_persist_pending_item(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            page = QueuePage(Settings())
            page._state = QueueState(Path(temporary) / "queue.json")
            options = DownloadOptions("https://example.invalid/video", temporary)
            self.assertTrue(page._add(options))
            job_id = next(iter(page.jobs))

            page.pause(job_id)

            self.assertTrue(page.jobs[job_id].paused)
            self.assertNotIn(job_id, page.pending)
            self.assertTrue(page._state.load_entries()[0][1])
            with patch.object(page, "_pump"):
                page.resume(job_id)
            self.assertFalse(page.jobs[job_id].paused)
            self.assertIn(job_id, page.pending)
            self.assertFalse(page._state.load_entries()[0][1])
            page.deleteLater()

    def test_pause_active_worker_waits_for_cancel_before_resuming(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            page = QueuePage(Settings())
            page._state = QueueState(Path(temporary) / "queue.json")
            self.assertTrue(page._add(DownloadOptions("https://example.invalid/video", temporary)))
            job_id = next(iter(page.jobs))
            page.pending.remove(job_id)
            job = page.jobs[job_id]
            job.active = True
            job.worker = Mock()

            page.pause(job_id)
            job.worker.cancel.assert_called_once()
            self.assertTrue(job.pause_requested)
            self.assertNotIn(job_id, page.pending)
            page._on_failed(job_id, "Cancelado")
            self.assertTrue(job.paused)
            self.assertFalse(job.active)
            self.assertTrue(page._state.load_entries()[0][1])
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

