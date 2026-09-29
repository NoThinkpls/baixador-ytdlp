"""Intel Quick Sync e VAAPI ao lado de NVENC, AMF e VideoToolbox."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp import gpu
from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import Transcoder
from baixador_ytdlp.media_tools import MediaToolOptions, build_command


class BackendTests(unittest.TestCase):
    def test_backend_of_and_quality_args(self) -> None:
        self.assertEqual(gpu.backend_of("h264_qsv"), "qsv")
        self.assertEqual(gpu.backend_of("hevc_vaapi"), "vaapi")
        self.assertEqual(gpu.backend_of("libx264"), "")
        self.assertEqual(gpu.quality_args("h264_nvenc", 23), ["-cq", "23", "-b:v", "0"])
        self.assertEqual(gpu.quality_args("h264_qsv", 23), ["-global_quality", "23"])
        self.assertEqual(gpu.quality_args("h264_vaapi", 23), ["-rc_mode", "CQP", "-qp", "23"])
        self.assertEqual(gpu.quality_args("h264_amf", 23),
                         ["-rc", "cqp", "-qp_i", "23", "-qp_p", "23"])

    def test_candidates_by_platform(self) -> None:
        with patch("baixador_ytdlp.gpu.is_macos", return_value=False), \
                patch("baixador_ytdlp.gpu.sys.platform", "win32"):
            windows = gpu._candidate_encoders()
        self.assertIn("h264_qsv", windows)
        self.assertNotIn("h264_vaapi", windows)
        with patch("baixador_ytdlp.gpu.is_macos", return_value=False), \
                patch("baixador_ytdlp.gpu.sys.platform", "linux"):
            linux = gpu._candidate_encoders()
        self.assertIn("h264_vaapi", linux)
        self.assertIn("h264_qsv", linux)

    def test_vaapi_probe_uploads_frames_and_needs_a_device(self) -> None:
        calls = []

        def fake_run(args, timeout=20):
            calls.append(args)
            return SimpleNamespace(returncode=0, stderr="", stdout="")

        with patch("baixador_ytdlp.gpu.vaapi_device", return_value="/dev/dri/renderD128"), \
                patch("baixador_ytdlp.gpu.run_hidden", side_effect=fake_run):
            self.assertEqual(gpu._encoder_probe(Path("ffmpeg"), "h264_vaapi"), (True, ""))
            self.assertEqual(gpu._encoder_probe(Path("ffmpeg"), "h264_qsv"), (True, ""))
        vaapi, qsv = calls
        self.assertEqual(vaapi[vaapi.index("-vaapi_device") + 1], "/dev/dri/renderD128")
        self.assertEqual(vaapi[vaapi.index("-vf") + 1], "format=nv12,hwupload")
        self.assertEqual(qsv[qsv.index("-vf") + 1], "format=nv12")
        self.assertNotIn("-pix_fmt", vaapi + qsv)
        with patch("baixador_ytdlp.gpu.vaapi_device", return_value=""), \
                patch("baixador_ytdlp.gpu.run_hidden", side_effect=AssertionError("sem dispositivo")):
            works, detail = gpu._encoder_probe(Path("ffmpeg"), "h264_vaapi")
        self.assertFalse(works)
        self.assertIn("renderD", detail)

    def test_summary_names_the_backend(self) -> None:
        info = gpu.GpuInfo(name="Intel", encoders=["h264_qsv", "hevc_qsv"])
        with patch("baixador_ytdlp.gpu.is_macos", return_value=False):
            self.assertIn("Intel Quick Sync", info.summary)
            self.assertIn("H264, HEVC", info.summary)


def _options(operation: str, tmp: Path) -> MediaToolOptions:
    source = tmp / "in.mp4"
    source.write_bytes(b"x")
    return MediaToolOptions(source=source, destination=tmp / "out.mp4", operation=operation)


class MediaToolsTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.tools = SimpleNamespace(ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_qsv_swaps_encoder_and_quality(self) -> None:
        command = build_command(_options("compress", self.tmp), self.tools, video_encoder="h264_qsv")
        self.assertEqual(command[command.index("-c:v") + 1], "h264_qsv")
        self.assertEqual(command[command.index("-global_quality") + 1], "23")
        self.assertNotIn("-crf", command)
        self.assertNotIn("-preset", command)

    def test_vaapi_uploads_after_filters_and_sets_the_device(self) -> None:
        with patch("baixador_ytdlp.gpu.vaapi_device", return_value="/dev/dri/renderD128"):
            command = build_command(_options("compress", self.tmp), self.tools,
                                    video_encoder="h264_vaapi")
        self.assertEqual(command[command.index("-vaapi_device") + 1], "/dev/dri/renderD128")
        self.assertLess(command.index("-vaapi_device"), command.index("-i"))
        self.assertEqual(command[command.index("-vf") + 1], "format=nv12,hwupload")
        self.assertEqual(command[command.index("-rc_mode") + 1], "CQP")

    def test_vaapi_keeps_the_complex_filter_on_the_cpu(self) -> None:
        import dataclasses

        options = dataclasses.replace(_options("shorts", self.tmp), shorts_blur=True)
        with patch("baixador_ytdlp.gpu.vaapi_device", return_value="/dev/dri/renderD128"):
            command = build_command(options, self.tools, video_encoder="h264_vaapi")
        self.assertEqual(command[command.index("-c:v") + 1], "libx264")
        self.assertNotIn("-vaapi_device", command)


class TranscoderTests(unittest.TestCase):
    def _args(self, codec: str, hwaccel: bool) -> list[str]:
        cfg = Settings(transcode_codec=codec, transcode_cq=23)
        tools = SimpleNamespace(ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"))
        with patch("baixador_ytdlp.gpu.vaapi_device", return_value="/dev/dri/renderD128"):
            return Transcoder(tools, cfg).build_args(Path("a.mp4"), Path("b.mp4"), hwaccel=hwaccel)

    def test_qsv_decodes_on_gpu_then_retries_without(self) -> None:
        with_gpu = self._args("hevc_qsv", True)
        self.assertEqual(with_gpu[with_gpu.index("-hwaccel") + 1], "qsv")
        self.assertEqual(with_gpu[with_gpu.index("-global_quality") + 1], "23")
        self.assertNotIn("-hwaccel", self._args("hevc_qsv", False))

    def test_vaapi_uses_gpu_frames_or_uploads_them(self) -> None:
        with_gpu = self._args("h264_vaapi", True)
        self.assertEqual(with_gpu[with_gpu.index("-hwaccel_output_format") + 1], "vaapi")
        self.assertNotIn("-vf", with_gpu)
        without = self._args("h264_vaapi", False)
        self.assertNotIn("-hwaccel", without)
        self.assertEqual(without[without.index("-vf") + 1], "format=nv12,hwupload")
        self.assertLess(without.index("-vaapi_device"), without.index("-i"))


if __name__ == "__main__":
    unittest.main()
