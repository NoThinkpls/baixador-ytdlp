"""Regressões da rodada 4 da caça a bugs (estado das ferramentas e argumentos do yt-dlp)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp import tools as tools_module
from baixador_ytdlp.config import Settings, usable_extractor_args
from baixador_ytdlp.downloader import DownloadOptions, build_args
from baixador_ytdlp.tools import ToolManager, Toolchain


class EstadoDasFerramentasCorrompidoTests(unittest.TestCase):
    """Um JSON válido que não é objeto (``[]``, ``null``) derrubava a preparação do ambiente."""

    def test_estado_que_nao_e_objeto_volta_vazio(self) -> None:
        for conteudo in ("[]", "null", "[1]", "5", '"texto"'):
            with self.subTest(conteudo=conteudo), tempfile.TemporaryDirectory() as pasta:
                estado = Path(pasta) / "tools_state.json"
                estado.write_text(conteudo, encoding="utf-8")
                with patch.object(tools_module, "STATE_PATH", estado):
                    manager = ToolManager(bin_dir=Path(pasta))
                self.assertEqual({}, manager.state)
                self.assertTrue(manager._should_check("ytdlp", 12))

    def test_estado_valido_continua_lido(self) -> None:
        with tempfile.TemporaryDirectory() as pasta:
            estado = Path(pasta) / "tools_state.json"
            estado.write_text('{"ytdlp_version": "2026.08.19"}', encoding="utf-8")
            with patch.object(tools_module, "STATE_PATH", estado):
                manager = ToolManager(bin_dir=Path(pasta))
            self.assertEqual("2026.08.19", manager.state["ytdlp_version"])


class ArgumentosDeExtratorTests(unittest.TestCase):
    """O yt-dlp recusa ``--extractor-args lixo`` e toda análise e download falhava."""

    def test_regra_do_ytdlp(self) -> None:
        for bom in ("youtube:player_client=web", "youtube:", "Youtube:a=b;c=d", "  youtube:x=1  "):
            self.assertTrue(usable_extractor_args(bom), bom)
        for ruim in ("lixo", ":a", "a b:c=d", "youtube;x", "", "   "):
            self.assertEqual("", usable_extractor_args(ruim), ruim)

    def test_valor_invalido_nao_chega_ao_ytdlp(self) -> None:
        tc = Toolchain(ytdlp=Path("yt-dlp"), ffmpeg=Path("ffmpeg"), ffprobe=Path("ffprobe"),
                       bin_dir=Path("."))
        opts = DownloadOptions(url="https://youtu.be/x", output_dir="/tmp")
        self.assertNotIn("--extractor-args", build_args(opts, Settings(extractor_args="lixo"), tc))
        args = build_args(opts, Settings(extractor_args=" youtube:player_client=web "), tc)
        self.assertEqual("youtube:player_client=web", args[args.index("--extractor-args") + 1])


if __name__ == "__main__":
    unittest.main()
