"""O .app do macOS precisa sair com assinatura válida (senão abre como "danificado")."""
from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"


class AssinaturaDoAppMacTests(unittest.TestCase):
    def test_bundle_e_assinado_depois_de_editar_o_info_plist_e_antes_de_empacotar(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        plist = text.index("PlistBuddy")
        sign = text.index('codesign --force --deep --sign - "$app"')
        verify = text.index("codesign --verify --deep --strict")
        package = text.index("hdiutil create")
        self.assertLess(plist, sign)
        self.assertLess(sign, verify)
        self.assertLess(verify, package)

    def test_bundle_inclui_os_dados_do_mlx_whisper_e_confere_no_ci(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("--collect-all mlx_whisper", text)
        for asset in ("mel_filters.npz", "multilingual.tiktoken", "gpt2.tiktoken"):
            self.assertIn(asset, text)


if __name__ == "__main__":
    unittest.main()
