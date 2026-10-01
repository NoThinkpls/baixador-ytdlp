"""Regressões da rodada 3 da caça a bugs (mensagens de erro e formatação do probe)."""
from __future__ import annotations

import unittest

from baixador_ytdlp.probe import _friendly_error_pt, human_size


class CodigosDeErroPorNumeroInteiroTests(unittest.TestCase):
    """``"winerror 5" in texto`` casava também WinError 53, 55, 59… (erros de rede)."""

    def test_winerror_de_rede_nao_vira_falta_de_permissao(self) -> None:
        for codigo in (50, 53, 55, 59):
            mensagem = _friendly_error_pt(f"ERROR: [WinError {codigo}] O caminho de rede não foi encontrado")
            self.assertNotIn("permissão", mensagem, codigo)

    def test_errno_360_nao_vira_caminho_longo_nem_disco_cheio(self) -> None:
        for codigo in (280, 360, 2800):
            mensagem = _friendly_error_pt(f"ERROR: unable to write: [Errno {codigo}] algo")
            self.assertNotIn("caminho do arquivo", mensagem)
            self.assertNotIn("sem espaço", mensagem)

    def test_codigos_exatos_continuam_traduzidos(self) -> None:
        self.assertIn("permissão", _friendly_error_pt("OSError: [WinError 5] Access is denied"))
        self.assertIn("sem espaço", _friendly_error_pt("[Errno 28] No space left on device"))
        self.assertIn("sem espaço", _friendly_error_pt("OSError: [WinError 112] x"))
        self.assertIn("longo demais", _friendly_error_pt("[Errno 36] File name too long"))
        self.assertIn("longo demais", _friendly_error_pt("OSError: [WinError 206] x"))


class TamanhoLegivelTests(unittest.TestCase):
    def test_arredondamento_nao_mostra_1024_na_unidade_menor(self) -> None:
        self.assertEqual("1.00 MB", human_size(1048575))
        self.assertEqual("1.00 MB", human_size(1023.6 * 1024))
        self.assertEqual("1.00 GB", human_size(1024 ** 3 - 1))

    def test_valores_normais(self) -> None:
        self.assertEqual("—", human_size(None))
        self.assertEqual("512 B", human_size(512))
        self.assertEqual("1 KB", human_size(1024))
        self.assertEqual("1.50 MB", human_size(1.5 * 1024 ** 2))
        self.assertEqual("2.00 TB", human_size(2 * 1024 ** 4))


if __name__ == "__main__":
    unittest.main()


class LimiteDeBandaTests(unittest.TestCase):
    """O yt-dlp recusa ``--limit-rate abc`` e o download inteiro falhava, sem explicar o motivo."""

    def test_validacao_segue_a_regra_do_ytdlp(self) -> None:
        from baixador_ytdlp.config import is_valid_rate_limit

        for bom in ("5M", "5m", "1.5M", "500k", "100K", "1G", "5MiB", "5 M", "300"):
            self.assertTrue(is_valid_rate_limit(bom), bom)
        for ruim in ("abc", "5MBps", "-1", "M", "5,5M", "1..5M"):
            self.assertFalse(is_valid_rate_limit(ruim), ruim)

    def test_limite_invalido_nao_chega_ao_ytdlp(self) -> None:
        from pathlib import Path

        from baixador_ytdlp.config import Settings
        from baixador_ytdlp.downloader import DownloadOptions, build_args
        from baixador_ytdlp.tools import Toolchain

        tc = Toolchain(ytdlp=Path("yt-dlp"), ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"),
                       bin_dir=Path("."))
        opts = DownloadOptions(url="https://youtu.be/x", output_dir="/tmp")
        self.assertNotIn("--limit-rate", build_args(opts, Settings(limit_rate="abc"), tc))
        args = build_args(opts, Settings(limit_rate="5M"), tc)
        self.assertEqual("5M", args[args.index("--limit-rate") + 1])
