"""Regressões do suporte de codificação AMD AMF."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp.config import Settings
from baixador_ytdlp.downloader import Transcoder
from baixador_ytdlp.gpu import GpuInfo, detect, select_section_encoder


class AmdEncodingTests(unittest.TestCase):
    def test_does_not_offer_an_encoder_that_only_exists_in_the_ffmpeg_build(self):
        def fake_run(command, **_kwargs):
            if command[0] == "nvidia-smi":
                raise FileNotFoundError("sem driver")
            if "-encoders" in command:
                return SimpleNamespace(stdout=" V.... h264_nvenc\n", returncode=0)
            if "-f" in command and "lavfi" in command:
                return SimpleNamespace(stdout="", returncode=1)
            return SimpleNamespace(stdout="Hardware acceleration methods:\ncuda\n", returncode=0)

        with patch("baixador_ytdlp.gpu.sys.platform", "win32"), \
             patch("baixador_ytdlp.gpu.run_hidden", side_effect=fake_run), \
             patch("baixador_ytdlp.gpu.Path.exists", return_value=True):
            info = detect(Path("ffmpeg-unavailable.exe"))

        self.assertEqual(info.encoders, [])

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

    def test_keeps_nvenc_when_nvidia_smi_is_unavailable(self):
        def fake_run(command, **_kwargs):
            if command[0] == "nvidia-smi":
                raise FileNotFoundError("nvidia-smi ausente")
            if "-encoders" in command:
                return SimpleNamespace(stdout=" V.... h264_nvenc\n")
            return SimpleNamespace(stdout="Hardware acceleration methods:\ncuda\n")

        with patch("baixador_ytdlp.gpu.sys.platform", "win32"), \
             patch("baixador_ytdlp.gpu.run_hidden", side_effect=fake_run), \
             patch("baixador_ytdlp.gpu.Path.exists", return_value=True):
            info = detect(Path("ffmpeg.exe"))

        self.assertEqual(info.name, "GPU detectada")
        self.assertEqual(info.encoders, ["h264_nvenc"])

    def test_section_tries_advertised_encoder_after_a_transient_probe_failure(self):
        # O DownloadRunner tem fallback para CPU. Portanto, não devemos perder
        # uma GPU real apenas porque o teste curto ocorreu enquanto o driver
        # ainda estava iniciando.
        for advertised in ("h264_nvenc", "h264_amf", "h264_videotoolbox"):
            with self.subTest(advertised=advertised), patch(
                "baixador_ytdlp.gpu.detect",
                return_value=GpuInfo(advertised_encoders=[advertised]),
            ):
                codec = select_section_encoder(Path("ffmpeg"))

            self.assertEqual(codec, advertised)


if __name__ == "__main__":
    unittest.main()
