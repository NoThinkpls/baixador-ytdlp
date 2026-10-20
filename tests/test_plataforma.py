"""Contratos da camada de plataforma, sem depender da máquina do runner."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp.plataforma import (
    asset_deno,
    asset_ytdlp,
    is_apple_silicon,
    liberar_caminhos_qt_do_pacote,
    nome_binario,
    pasta_do_executavel,
    pasta_dados_usuario,
    restaurar_bibliotecas_do_sistema,
    sistema,
    ytdlp_em_pasta,
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

    def test_yt_dlp_em_pasta_nas_tres_plataformas(self) -> None:
        self.assertEqual(ytdlp_em_pasta("win32", "AMD64"), ("yt-dlp_win.zip", "yt-dlp.exe"))
        self.assertEqual(ytdlp_em_pasta("darwin", "arm64"), ("yt-dlp_macos.zip", "yt-dlp_macos"))
        self.assertEqual(ytdlp_em_pasta("linux", "x86_64"), ("yt-dlp_linux.zip", "yt-dlp_linux"))
        self.assertEqual(ytdlp_em_pasta("linux", "aarch64"),
                         ("yt-dlp_linux_aarch64.zip", "yt-dlp_linux_aarch64"))
        # Sem pasta publicada: continua o executável único (zipimport).
        self.assertIsNone(ytdlp_em_pasta("linux", "riscv64"))

    def test_linux_empacotado_devolve_o_ambiente_original_aos_filhos(self) -> None:
        env = {"LD_LIBRARY_PATH": "/opt/app/_internal:/usr/local/lib",
               "LD_LIBRARY_PATH_ORIG": "/usr/local/lib"}
        restaurar_bibliotecas_do_sistema(env, frozen=True, platform_name="linux")
        self.assertEqual(env, {"LD_LIBRARY_PATH": "/usr/local/lib"})

        env = {"LD_LIBRARY_PATH": "/opt/app/_internal"}
        restaurar_bibliotecas_do_sistema(env, frozen=True, platform_name="linux")
        self.assertEqual(env, {})

        env = {"QT_PLUGIN_PATH": "/opt/app/_internal/PySide6/Qt/plugins",
               "QML2_IMPORT_PATH": "/opt/app/_internal/PySide6/Qt/qml", "HOME": "/home/x"}
        liberar_caminhos_qt_do_pacote(["/opt/app/plugins"], env, frozen=True,
                                      platform_name="linux")
        self.assertEqual(env, {"HOME": "/home/x"})

    def test_ambiente_intacto_fora_do_linux_empacotado(self) -> None:
        original = {"LD_LIBRARY_PATH": "/x", "QT_PLUGIN_PATH": "/y"}
        for frozen, name in ((False, "linux"), (True, "darwin"), (True, "win32")):
            env = dict(original)
            restaurar_bibliotecas_do_sistema(env, frozen=frozen, platform_name=name)
            liberar_caminhos_qt_do_pacote(["/p"], env, frozen=frozen, platform_name=name)
            self.assertEqual(env, original)

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

        executavel = Path.cwd() / "Apps" / "Baixador" / "baixador-ytdlp"
        with patch.object(plataforma.sys, "executable", str(executavel)), \
                patch.object(plataforma.sys, "frozen", True, create=True):
            self.assertEqual(pasta_do_executavel(), executavel.parent)


if __name__ == "__main__":
    unittest.main()
