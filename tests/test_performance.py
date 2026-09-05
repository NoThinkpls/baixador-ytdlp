"""Regressões das otimizações que não podem alterar o resultado do trabalho."""
from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import DownloadOptions, DownloadRunner, Progress
from baixador_ytdlp.runtime import RuntimeManager
from baixador_ytdlp.tools import ToolManager, Toolchain


class ToolVersionCacheTests(unittest.TestCase):
    def test_reuses_persisted_version_when_binary_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "tool"
            binary.write_bytes(b"binary")
            stat = binary.stat()
            manager = ToolManager(bin_dir=root)
            manager.state = {"tool_version_cache": {
                str(binary.resolve()): {
                    "mtime_ns": stat.st_mtime_ns,
                    "size": stat.st_size,
                    "version": "9.9.9",
                },
            }}
            reader = Mock(return_value="deveria-nao-executar")

            self.assertEqual(manager._cached_version(binary, reader), "9.9.9")
            reader.assert_not_called()

    def test_invalidates_persisted_version_when_binary_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            binary = root / "tool"
            binary.write_bytes(b"binary nova")
            stat = binary.stat()
            manager = ToolManager(bin_dir=root)
            manager.state = {"tool_version_cache": {
                str(binary.resolve()): {
                    "mtime_ns": stat.st_mtime_ns - 1,
                    "size": stat.st_size,
                    "version": "antiga",
                },
            }}
            reader = Mock(return_value="nova")

            self.assertEqual(manager._cached_version(binary, reader), "nova")
            reader.assert_called_once_with(binary)
            self.assertEqual(
                manager.state["tool_version_cache"][str(binary.resolve())]["version"], "nova")

    def test_extracts_archives_in_a_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive = root / "tools.zip"
            payload = b"ffmpeg" * 300_000
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("bin/ffmpeg.exe", payload)

            destination = root / "bin" / "ffmpeg.exe.new"
            with zipfile.ZipFile(archive) as zf:
                ToolManager._extract_zip_member(zf, "bin/ffmpeg.exe", destination)

            self.assertEqual(destination.read_bytes(), payload)


class StartupRuntimeTests(unittest.TestCase):
    def test_startup_does_not_preload_cuda_dlls_in_the_ui_process(self) -> None:
        manager = RuntimeManager(check_hours=24)
        with patch("baixador_ytdlp.runtime.ensure_dirs"), \
                patch("baixador_ytdlp.runtime._has_nvidia_driver", return_value=True), \
                patch("baixador_ytdlp.runtime.deactivate_runtime"), \
                patch.object(manager, "_available_packages", return_value=True), \
                patch("baixador_ytdlp.runtime.embedded_cuda_available", return_value=True), \
                patch("baixador_ytdlp.runtime._versions", return_value={"faster-whisper": "1"}), \
                patch("baixador_ytdlp.runtime.prepare_embedded_cuda") as preload:
            info = manager.ensure(Mock())

        self.assertTrue(info.cuda_package)
        preload.assert_not_called()


class DownloadProgressTests(unittest.TestCase):
    def test_coalesces_rapid_progress_but_preserves_state_changes(self) -> None:
        options = DownloadOptions("https://example.invalid/video", ".")
        toolchain = Toolchain(Path("yt-dlp"), Path("ffmpeg"), Path("ffprobe"), Path("."))
        runner = DownloadRunner(options, Settings(), toolchain)
        received: list[Progress] = []
        progress = Progress(status="downloading", downloaded=10)

        with patch("baixador_ytdlp.downloader.time.monotonic", side_effect=(1.0, 1.05, 1.08, 1.25)):
            runner._emit_progress(received.append, progress)
            progress.downloaded = 20
            runner._emit_progress(received.append, progress)  # mesma etapa: descartado
            progress.status, progress.stage = "processing", "Juntando áudio e vídeo"
            runner._emit_progress(received.append, progress)  # etapa: imediato
            progress.status, progress.stage = "downloading", ""
            runner._emit_progress(received.append, progress)  # intervalo expirou

        self.assertEqual([item.downloaded for item in received], [10, 20, 20])
        self.assertEqual(received[1].stage, "Juntando áudio e vídeo")


if __name__ == "__main__":
    unittest.main()
