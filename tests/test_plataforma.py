"""Contratos da camada de plataforma, sem depender da máquina do runner."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.plataforma import (
    asset_deno,
    asset_ytdlp,
    is_apple_silicon,
    nome_binario,
    pasta_do_executavel,
    pasta_dados_usuario,
    sistema,
)


class PlataformaTests(unittest.TestCase):
    def test_normaliza_os_tres_sistemas_suportados(self) -> None:
        self.assertEqual(sistema("win32"), "windows")
        self.assertEqual(sistema("darwin"), "macos")
        self.assertEqual(sistema("linux"), "linux")

    def test_nomes_de_executaveis_e_assets_seguem_a_plataforma(self) -> None:
        self.assertEqual(nome_binario("yt-dlp", "win32"), "yt-dlp.exe")
        self.assertEqual(nome_binario("yt-dlp", "darwin"), "yt-dlp")
        self.assertEqual(asset_ytdlp("win32"), "yt-dlp.exe")
        self.assertEqual(asset_ytdlp("darwin"), "yt-dlp_macos")
        self.assertEqual(asset_ytdlp("linux"), "yt-dlp")
        self.assertEqual(asset_deno("win32", "AMD64"), "deno-x86_64-pc-windows-msvc.zip")
        self.assertEqual(asset_deno("darwin", "arm64"), "deno-aarch64-apple-darwin.zip")
        self.assertEqual(asset_deno("linux", "aarch64"), "deno-aarch64-unknown-linux-gnu.zip")

    def test_pasta_de_dados_respeita_as_convencoes_do_sistema(self) -> None:
        self.assertEqual(
            pasta_dados_usuario(
                "BaixadorYtdlp", environ={"LOCALAPPDATA": "C:/Dados"}, platform_name="win32"
            ),
            Path("C:/Dados") / "BaixadorYtdlp",
        )
        self.assertEqual(
            pasta_dados_usuario("BaixadorYtdlp", home=Path("/Users/ana"), platform_name="darwin"),
            Path("/Users/ana/Library/Application Support/BaixadorYtdlp"),
        )
        self.assertEqual(
            pasta_dados_usuario(
                "BaixadorYtdlp", environ={"XDG_DATA_HOME": "/dados"}, platform_name="linux"
            ),
            Path("/dados/BaixadorYtdlp"),
        )

    def test_apple_silicon_exige_macos_arm(self) -> None:
        self.assertTrue(is_apple_silicon("darwin", "arm64"))
        self.assertTrue(is_apple_silicon("darwin", "aarch64"))
        self.assertFalse(is_apple_silicon("darwin", "x86_64"))
        self.assertFalse(is_apple_silicon("linux", "arm64"))

    def test_pasta_do_executavel_usa_o_proprio_executavel_empacotado(self) -> None:
        from baixador_ytdlp import plataforma

        with patch.object(plataforma.sys, "executable", "C:/Apps/Baixador/baixador-ytdlp.exe"), \
                patch.object(plataforma.sys, "frozen", True, create=True):
            self.assertEqual(pasta_do_executavel(), Path("C:/Apps/Baixador"))


if __name__ == "__main__":
    unittest.main()
