"""Regressões do suporte de codificação AMD AMF."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import Transcoder
from baixador_ytdlp.gpu import detect


class AmdEncodingTests(unittest.TestCase):
    def test_detects_amf_without_nvidia_driver(self):
        def fake_run(command, **_kwargs):
            if command[0] == "nvidia-smi":
                return SimpleNamespace(stdout="")
            if "-encoders" in command:
                return SimpleNamespace(stdout=" V.... h264_amf\n V.... hevc_amf\n")
            return SimpleNamespace(stdout="Hardware acceleration methods:\nd3d11va\n")

        with patch("baixador_ytdlp.gpu.sys.platform", "win32"), \
             patch("baixador_ytdlp.gpu.run_hidden", side_effect=fake_run), \
             patch("baixador_ytdlp.gpu.Path.exists", return_value=True):
            info = detect(Path("ffmpeg.exe"))

        self.assertEqual(info.name, "GPU AMD")
        self.assertEqual(info.encoders, ["h264_amf", "hevc_amf"])
        self.assertTrue(info.decoders_d3d11)

    def test_amf_uses_amd_encoder_options(self):
        cfg = Settings(transcode_codec="hevc_amf", transcode_cq=20)
        tools = SimpleNamespace(ffmpeg=Path("ffmpeg.exe"), ffprobe=Path("ffprobe.exe"))
        command = Transcoder(tools, cfg).build_args(Path("entrada.mp4"), Path("saida.mp4"))
        self.assertIn("hevc_amf", command)
        self.assertIn("-quality", command)
        self.assertIn("-qp_i", command)
        self.assertNotIn("cuda", command)


if __name__ == "__main__":
    unittest.main()
