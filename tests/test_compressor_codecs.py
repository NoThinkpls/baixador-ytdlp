"""Reduzir tamanho: codec (CPU/GPU), método por porcentagem ou qualidade, aparelhos antigos
e formato final (MP4, MKV, WebM, MOV ou só o áudio)."""
from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from baixador_ytdlp.gpu import GpuInfo
from baixador_ytdlp.media_tools import (CHOICES, MediaToolError, MediaToolOptions, build_command,
                                        compress_budget_kbps, default_destination,
                                        gpu_encoder_for, uses_gpu, validate_compress)


class CompressCommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.source = self.tmp / "in.mp4"
        self.source.write_bytes(b"x" * 10_000_000)   # 10 MB
        self.tools = SimpleNamespace(ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _options(self, ext: str = "mp4", **extra) -> MediaToolOptions:
        return MediaToolOptions(self.source, self.tmp / f"out.{ext}", "compress", **extra)

    def _command(self, options: MediaToolOptions, encoder: str = "") -> list[str]:
        with patch("baixador_ytdlp.media_tools.media_duration", return_value=100.0):
            return build_command(options, self.tools, video_encoder=encoder)

    def test_formatos_finais_e_extensao_sugerida(self) -> None:
        self.assertEqual(CHOICES["compress"], ("mp4", "mkv", "webm", "mov", "mp3", "m4a", "opus"))
        for fmt in CHOICES["compress"]:
            self.assertEqual(default_destination(self.source, "compress", choice=fmt).suffix,
                             f".{fmt}")

    def test_combinacoes_invalidas_sao_recusadas(self) -> None:
        for ext, codec in (("webm", "h264"), ("webm", "hevc"), ("mov", "av1"), ("mp4", "vp9")):
            with self.subTest(ext=ext, codec=codec), self.assertRaises(MediaToolError):
                validate_compress(self._options(ext, video_codec=codec))
        with self.assertRaises(MediaToolError):
            validate_compress(self._options("mp4", video_codec="hevc", legacy=True))
        with self.assertRaises(MediaToolError):
            validate_compress(self._options("mp4", compress_mode="percent", target_percent=0))
        with self.assertRaises(MediaToolError):
            validate_compress(self._options("avi"))
        validate_compress(self._options("webm", video_codec="av1"))
        validate_compress(self._options("mkv", video_codec="vp9"))
        validate_compress(self._options("mp3", video_codec="vp9"))   # áudio ignora o codec

    def test_h265_cpu_em_mp4_marca_hvc1(self) -> None:
        command = self._command(self._options(video_codec="hevc", use_gpu=False))
        self.assertEqual(command[command.index("-c:v") + 1], "libx265")
        self.assertEqual(command[command.index("-crf") + 1], "26")
        self.assertEqual(command[command.index("-tag:v") + 1], "hvc1")
        self.assertIn("+faststart", command)

    def test_webm_usa_vp9_e_opus(self) -> None:
        command = self._command(self._options("webm", video_codec="vp9"))
        self.assertEqual(command[command.index("-c:v") + 1], "libvpx-vp9")
        self.assertEqual(command[command.index("-c:a") + 1], "libopus")
        self.assertEqual(command[command.index("-b:v") + 1], "0")
        self.assertNotIn("-movflags", command)

    def test_av1_na_gpu_troca_encoder_e_qualidade(self) -> None:
        command = self._command(self._options(video_codec="av1", quality_level="small"),
                                "av1_nvenc")
        self.assertEqual(command[command.index("-c:v") + 1], "av1_nvenc")
        self.assertEqual(command[command.index("-cq") + 1], "40")
        self.assertEqual(command[command.index("-preset") + 1], "p5")
        # Sem GPU (segunda tentativa do worker), o AV1 cai no SVT-AV1 da CPU.
        cpu = self._command(self._options(video_codec="av1"))
        self.assertEqual(cpu[cpu.index("-c:v") + 1], "libsvtav1")

    def test_porcentagem_calcula_o_bitrate(self) -> None:
        # 10 MB em 100 s = 800 kbps; 50% com a folga de 6% = 376 kbps no total.
        self.assertAlmostEqual(compress_budget_kbps(10_000_000, 100.0, 50), 376.0)
        command = self._command(self._options(compress_mode="percent", target_percent=50,
                                              use_gpu=False))
        self.assertNotIn("-crf", command)
        self.assertEqual(command[command.index("-b:a") + 1], "64k")
        self.assertEqual(command[command.index("-b:v") + 1], "312k")
        self.assertEqual(command[command.index("-maxrate") + 1], "468k")
        with self.assertRaises(MediaToolError):
            self._command(self._options(compress_mode="percent", target_percent=5))

    def test_porcentagem_na_gpu_mantem_o_bitrate(self) -> None:
        command = self._command(self._options(compress_mode="percent", target_percent=50),
                                "h264_nvenc")
        self.assertEqual(command[command.index("-c:v") + 1], "h264_nvenc")
        self.assertEqual(command[command.index("-b:v") + 1], "312k")
        self.assertNotIn("-cq", command)

    def test_aparelhos_antigos(self) -> None:
        command = self._command(self._options(legacy=True, use_gpu=False))
        self.assertEqual(command[command.index("-profile:v") + 1], "main")
        self.assertEqual(command[command.index("-level:v") + 1], "4.1")
        self.assertIn("format=yuv420p", command[command.index("-vf") + 1])
        self.assertEqual(command[command.index("-ac") + 1], "2")

    def test_formato_de_audio(self) -> None:
        command = self._command(self._options("mp3", quality_level="small"))
        self.assertIn("-vn", command)
        self.assertNotIn("-c:v", command)
        self.assertEqual(command[command.index("-c:a") + 1], "libmp3lame")
        self.assertEqual(command[command.index("-b:a") + 1], "96k")
        percent = self._command(self._options("opus", compress_mode="percent", target_percent=10))
        self.assertEqual(percent[percent.index("-b:a") + 1], "75k")

    def test_gpu_so_quando_faz_sentido(self) -> None:
        self.assertTrue(uses_gpu(self._options(video_codec="hevc")))
        self.assertFalse(uses_gpu(self._options(video_codec="hevc", use_gpu=False)))
        self.assertFalse(uses_gpu(self._options("webm", video_codec="vp9")))
        self.assertFalse(uses_gpu(self._options("m4a")))

    def test_escolha_do_encoder_de_gpu(self) -> None:
        encoders = ["h264_amf", "h264_nvenc", "hevc_qsv"]
        self.assertEqual(gpu_encoder_for("h264", encoders), "h264_nvenc")
        self.assertEqual(gpu_encoder_for("hevc", encoders), "hevc_qsv")
        self.assertEqual(gpu_encoder_for("av1", encoders), "")
        self.assertEqual(gpu_encoder_for("vp9", ["vp9_qsv"]), "")


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg não instalado")
class CompressRealTests(unittest.TestCase):
    """Executa o FFmpeg de verdade em cada formato e codec de CPU."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmp.name)
        cls.source = cls.tmp / "fonte.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=s=640x360:r=25:d=3",
                        "-f", "lavfi", "-i", "sine=f=440:d=3", "-c:v", "libx264", "-b:v", "3M",
                        "-c:a", "aac", "-shortest", str(cls.source)], check=True)
        cls.tools = SimpleNamespace(ffmpeg=Path(shutil.which("ffmpeg")),
                                    ffprobe=Path(shutil.which("ffprobe")))

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_cada_formato_gera_arquivo_valido(self) -> None:
        casos = [("mp4", "h264", {}), ("mp4", "hevc", {}), ("mkv", "vp9", {}),
                 ("webm", "vp9", {}), ("webm", "av1", {}), ("mov", "hevc", {}),
                 ("mp4", "h264", {"legacy": True}),
                 ("mp4", "h264", {"compress_mode": "percent", "target_percent": 40}),
                 ("mp3", "h264", {}), ("m4a", "h264", {}), ("opus", "h264", {})]
        for index, (ext, codec, extra) in enumerate(casos):
            with self.subTest(ext=ext, codec=codec, **extra):
                options = MediaToolOptions(self.source, self.tmp / f"saida{index}.{ext}",
                                           "compress", video_codec=codec, use_gpu=False, **extra)
                result = subprocess.run(build_command(options, self.tools), capture_output=True,
                                        text=True, check=False)
                self.assertEqual(result.returncode, 0, result.stdout[-800:])
                self.assertGreater(options.destination.stat().st_size, 0)
        porcentagem = self.tmp / "saida7.mp4"
        self.assertLess(porcentagem.stat().st_size, self.source.stat().st_size * 0.6)


class CompressPageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.ui.media_tools_page import MediaToolsPage
        self.page = MediaToolsPage(Settings())
        self.requested: list[bool] = []
        self.page.gpu_detection_requested.connect(lambda: self.requested.append(True))
        self.page._open_tool("compress")

    def tearDown(self) -> None:
        self.page.deleteLater()

    def _enabled(self) -> dict[str, bool]:
        model = self.page.codec_combo.model()
        return {self.page.codec_combo.itemData(i): model.item(i).isEnabled()
                for i in range(self.page.codec_combo.count())}

    def _select_format(self, fmt: str) -> None:
        combo = self.page.choice_combo
        combo.setCurrentIndex(combo.findData(fmt))

    def test_gpu_desligada_ate_detectar(self) -> None:
        self.assertEqual(self.requested, [True])
        enabled = self._enabled()
        self.assertTrue(enabled["h264_cpu"])
        self.assertFalse(enabled["h264_gpu"])
        self.page.set_gpu(GpuInfo(encoders=["h264_nvenc", "hevc_nvenc"]))
        enabled = self._enabled()
        self.assertTrue(enabled["h264_gpu"] and enabled["hevc_gpu"])
        self.assertFalse(enabled["av1_gpu"])
        self.assertIn("sem GPU", self.page.codec_combo.itemText(4))

    def test_webm_troca_para_vp9_e_audio_esconde_o_codec(self) -> None:
        self._select_format("webm")
        self.assertEqual(self.page.codec_combo.currentData(), "vp9_cpu")
        self.assertFalse(self._enabled()["h264_cpu"])
        self.assertFalse(self.page.legacy_row.isVisibleTo(self.page))
        self._select_format("mp3")
        self.assertFalse(self.page.codec_row.isVisibleTo(self.page))
        self._select_format("mp4")
        self.assertTrue(self.page.codec_row.isVisibleTo(self.page))
        self.assertTrue(self.page.legacy_row.isVisibleTo(self.page))

    def test_aparelhos_antigos_so_aceita_h264(self) -> None:
        self.page.codec_combo.setCurrentIndex(self.page.codec_combo.findData("hevc_cpu"))
        self.page.legacy_switch.setChecked(True)
        self.assertEqual(self.page.codec_combo.currentData(), "h264_cpu")
        self.assertFalse(self._enabled()["hevc_cpu"])

    def test_metodo_alterna_porcentagem_e_qualidade(self) -> None:
        self.assertTrue(self.page.percent_row.isVisibleTo(self.page))
        self.assertFalse(self.page.quality_row.isVisibleTo(self.page))
        self.page.method_combo.setCurrentIndex(self.page.method_combo.findData("quality"))
        self.assertFalse(self.page.percent_row.isVisibleTo(self.page))
        self.assertTrue(self.page.quality_row.isVisibleTo(self.page))
        self.page.percent_slider.setValue(35)
        self.assertEqual(self.page.percent_stepper.value(), 35)

    def test_executar_monta_as_opcoes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "video.mp4"
            source.write_bytes(b"x")
            self.page.toolchain = SimpleNamespace()
            self.page.set_media(str(source))
            self.page.set_gpu(GpuInfo(encoders=["hevc_nvenc"]))
            self.page.codec_combo.setCurrentIndex(self.page.codec_combo.findData("hevc_gpu"))
            self._select_format("mkv")
            self.page.percent_stepper.setValue(30)
            captured: list[MediaToolOptions] = []

            class FakeWorker:
                def __init__(self, options, *_args):
                    captured.append(options)
                    self.progress = self.progress_value = self.finished_ok = self.failed = \
                        self.finished = SimpleNamespace(connect=lambda *_: None)

                def start(self):
                    pass

                def deleteLater(self):  # noqa: N802
                    pass

                def isRunning(self):  # noqa: N802
                    return False

            with patch("baixador_ytdlp.ui.media_tools_page.MediaToolWorker", FakeWorker):
                self.page._run()
        options = captured[0]
        self.assertEqual(options.destination.suffix, ".mkv")
        expected = replace(options, video_codec="hevc", use_gpu=True, compress_mode="percent",
                           target_percent=30, legacy=False)
        self.assertEqual(options, expected)


if __name__ == "__main__":
    unittest.main()
