"""yt-dlp em pasta no macOS/Linux: extração, permissões, migração e cache de integridade.

Até a 1.13.8 o macOS usava o executável único (que se descompacta a cada chamada) e o
Linux o zipimport, sem curl_cffi, mutagen e secretstorage e dependente do Python do sistema.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import stat
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from baixador_ytdlp import tools
from baixador_ytdlp.tools import YTDLP_ASSET, YTDLP_DIR_EXE, YTDLP_EXE, IntegrityError, ToolManager

UNIX_ONEDIR = bool(tools.YTDLP_ONEDIR) and not sys.platform.startswith("win")


def _zip_oficial(path: Path, *, symlink: bool = False) -> str:
    with zipfile.ZipFile(path, "w") as output:
        executable = zipfile.ZipInfo(YTDLP_DIR_EXE)
        executable.external_attr = (stat.S_IFREG | 0o755) << 16
        output.writestr(executable, b"#!/bin/sh\necho 2026.09.01\n")
        library = zipfile.ZipInfo("_internal/libpython.so")
        library.external_attr = (stat.S_IFREG | 0o644) << 16
        output.writestr(library, b"library")
        if symlink:
            link = zipfile.ZipInfo("_internal/atalho")
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            output.writestr(link, "/etc/passwd")
    return hashlib.sha256(path.read_bytes()).hexdigest()


@unittest.skipUnless(UNIX_ONEDIR, "distribuição em pasta do macOS/Linux")
class YtdlpPastaUnixTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.archive = self.root / "oficial.zip"
        self.digest = _zip_oficial(self.archive)
        self.manager = ToolManager(bin_dir=self.root / "bin")
        self.manager._save_state = Mock()

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _baixar(self, digest: str | None = None) -> None:
        self.manager._latest_ytdlp = Mock(return_value=(
            "2026.09.01", "https://example.invalid/" + YTDLP_ASSET,
            {YTDLP_ASSET: digest or self.digest}))
        self.manager._download = Mock(
            side_effect=lambda _url, path, *_: shutil.copyfile(self.archive, path))
        self.manager.ensure_ytdlp(Mock())

    def test_extrai_a_pasta_com_o_executavel_executavel(self) -> None:
        self._baixar()
        executable = self.root / "bin" / "yt-dlp" / YTDLP_DIR_EXE
        self.assertTrue(executable.is_file())
        self.assertTrue(os.access(executable, os.X_OK))
        self.assertTrue((executable.parent / "_internal" / "libpython.so").is_file())
        self.assertEqual(self.manager._resolve_ytdlp(), executable)

    def test_migra_o_executavel_unico_antigo(self) -> None:
        legacy = self.root / "bin" / YTDLP_EXE
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"antigo")
        self.manager._record_integrity(YTDLP_EXE, legacy)

        self._baixar()

        self.assertTrue((legacy / YTDLP_DIR_EXE).is_file())
        self.assertNotIn(YTDLP_EXE, self.manager.state.get("tool_sha256", {}))
        # A pasta com o mesmo nome do arquivo antigo não pode ser tratada como binário adulterado.
        self.assertEqual(self.manager.repair_tampered_tools(Mock()), [])

    def test_sem_rede_mantem_o_executavel_unico_antigo(self) -> None:
        legacy = self.root / "bin" / YTDLP_EXE
        legacy.parent.mkdir(parents=True)
        legacy.write_bytes(b"antigo")
        self.manager.local_ytdlp_version = Mock(return_value="2026.08.19")
        self.manager._latest_ytdlp = Mock(side_effect=urllib.error.URLError("offline"))
        progress = Mock()

        self.manager.ensure_ytdlp(progress)

        self.assertIn("2026.08.19", progress.call_args.args[0])
        self.assertEqual(self.manager._resolve_ytdlp(), legacy)

    def test_recusa_link_simbolico_no_zip(self) -> None:
        digest = _zip_oficial(self.archive, symlink=True)
        with self.assertRaises(IntegrityError):
            self._baixar(digest)
        self.assertFalse((self.root / "bin" / "yt-dlp").exists())

    def test_conferencia_completa_so_quando_os_arquivos_mudam(self) -> None:
        self._baixar()
        self.assertTrue(self.manager._ytdlp_bundle_ok())
        with patch.object(ToolManager, "_sha256", side_effect=AssertionError("hash")):
            self.assertTrue(self.manager._ytdlp_bundle_ok())
        library = self.root / "bin" / "yt-dlp" / "_internal" / "libpython.so"
        library.write_bytes(b"alterado")
        self.assertFalse(self.manager._ytdlp_bundle_ok())
        self.assertTrue(str(self.manager._resolve_ytdlp()).endswith(".integrity-failed"))


if __name__ == "__main__":
    unittest.main()
