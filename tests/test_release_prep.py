"""Release local: hashes, assinatura e notas antes do gh release create."""
from __future__ import annotations

import base64
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import prepare_release  # noqa: E402
import release_signing  # noqa: E402

from baixador_ytdlp import signing  # noqa: E402


class ReleasePrepTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        (self.folder / "BaixadorYtdlp-1.0.0-setup.exe").write_bytes(b"MZ-setup")
        (self.folder / "notas.txt").write_text("fora", encoding="utf-8")
        self.secret = bytes(range(32))
        self.public = base64.b64encode(signing.public_key(self.secret)).decode()
        self.env = patch.dict(os.environ, {
            "RELEASE_SIGNING_KEY": "",
            "RELEASE_SIGNING_KEY_FILE": str(self.folder / "chave.key")})
        self.env.start()

    def tearDown(self) -> None:
        self.env.stop()
        self.temp.cleanup()

    def test_hashes_so_dos_pacotes(self) -> None:
        sums = prepare_release.write_sums(self.folder).read_text(encoding="ascii")
        self.assertIn("BaixadorYtdlp-1.0.0-setup.exe", sums)
        self.assertNotIn("notas.txt", sums)

    def test_assinatura_confere_com_a_chave_do_app(self) -> None:
        (self.folder / "chave.key").write_text(base64.b64encode(self.secret).decode())
        sums = prepare_release.write_sums(self.folder)
        signature = prepare_release.sign_sums(sums, (self.public,))
        self.assertTrue(signing.verify_detached(
            (self.public,), sums.read_bytes(), signature.read_text(encoding="ascii")))

    def test_bloqueia_release_sem_chave_quando_o_app_exige(self) -> None:
        sums = prepare_release.write_sums(self.folder)
        with self.assertRaises(SystemExit):
            prepare_release.sign_sums(sums, (self.public,))

    def test_bloqueia_chave_que_nao_corresponde(self) -> None:
        (self.folder / "chave.key").write_text(base64.b64encode(bytes(32)).decode())
        sums = prepare_release.write_sums(self.folder)
        with self.assertRaises(SystemExit):
            prepare_release.sign_sums(sums, (self.public,))
        self.assertFalse((self.folder / "SHA256SUMS.txt.sig").exists())

    def test_generate_nao_sobrescreve_nem_imprime_a_privada(self) -> None:
        with patch("builtins.print") as printed:
            self.assertEqual(release_signing.main(["generate"]), 0)
        output = " ".join(str(arg) for call in printed.call_args_list for arg in call.args)
        stored = (self.folder / "chave.key").read_text(encoding="ascii").strip()
        self.assertNotIn(stored, output)
        with patch("builtins.print"):
            self.assertEqual(release_signing.main(["generate"]), 1)

    def test_notas_saem_da_secao_da_versao(self) -> None:
        changelog = self.folder / "CHANGELOG.md"
        changelog.write_text("# Log\n\n## [2.0.0] - x\n\n- novo\n\n## [1.0.0]\n\n- velho\n")
        notes = prepare_release.release_notes("2.0.0", changelog)
        self.assertIn("- novo", notes)
        self.assertNotIn("velho", notes)


if __name__ == "__main__":
    unittest.main()
