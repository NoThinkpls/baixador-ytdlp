"""Repetição de erros, progresso de trecho e estimativa de espaço."""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from baixador_ytdlp.downloader import DownloadOptions, DownloadRunner, Progress, is_retryable_error


class RetryableErrorTests(unittest.TestCase):
    def test_ssl_tls_so_como_palavra(self) -> None:
        self.assertTrue(is_retryable_error("[SSL: UNEXPECTED_EOF_WHILE_READING]"))
        self.assertTrue(is_retryable_error("TLS handshake failed"))
        self.assertFalse(is_retryable_error("ERROR: Invalid subtitles format"))
        self.assertFalse(is_retryable_error("ERROR: Unsupported URL: https://postls.example"))


class SectionProgressTests(unittest.TestCase):
    def _feed(self, opts: DownloadOptions, seconds: list[int]) -> list[int]:
        runner = DownloadRunner(opts, MagicMock(), MagicMock())
        progress, seen = Progress(), []
        for value in seconds:
            runner._apply_ffmpeg_progress(f"out_time_us={value * 1_000_000}", progress)
            seen.append(round(progress.percent))
        return seen

    def test_trecho_ate_o_fim_usa_a_duracao_da_analise(self) -> None:
        opts = DownloadOptions("u", "/tmp", selector="18", section_start="00:00:10",
                               media_duration=110)
        self.assertEqual(self._feed(opts, [0, 50, 100]), [0, 50, 99])

    def test_segunda_passada_nao_volta_a_barra(self) -> None:
        opts = DownloadOptions("u", "/tmp", section_end="00:01:40")
        seen = self._feed(opts, [0, 50, 100, 0, 50, 100])
        self.assertEqual(seen, sorted(seen))
        self.assertEqual(seen[-1], 99)


class PlaylistItemsTests(unittest.TestCase):
    def test_contagem_de_itens(self) -> None:
        try:
            from baixador_ytdlp.ui.home_page import _count_items
        except ImportError:
            self.skipTest("requer PySide6")
        self.assertEqual(_count_items("1-3,7"), 4)
        self.assertEqual(_count_items(""), 0)


if __name__ == "__main__":
    unittest.main()


class EncoderCacheTests(unittest.TestCase):
    def test_ausencia_de_encoder_fica_em_cache_ate_nova_deteccao(self) -> None:
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        from baixador_ytdlp import gpu

        with tempfile.TemporaryDirectory() as folder:
            ffmpeg = Path(folder) / "ffmpeg"
            ffmpeg.write_bytes(b"x")
            gpu._ENCODER_CACHE.clear()
            gpu.forget_negative_cache()
            with patch.object(gpu, "_candidate_encoders", return_value=("h264_nvenc",)), \
                    patch.object(gpu, "_encoder_probe", return_value=(False, "sem GPU")) as probe:
                gpu._usable_encoders(ffmpeg, " V....D h264_nvenc NVIDIA NVENC")
                gpu._usable_encoders(ffmpeg, " V....D h264_nvenc NVIDIA NVENC")
                self.assertEqual(probe.call_count, 1)
                gpu.forget_negative_cache()
                gpu._usable_encoders(ffmpeg, " V....D h264_nvenc NVIDIA NVENC")
                self.assertEqual(probe.call_count, 2)
