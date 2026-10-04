"""O bundle macOS precisa sair com o selo de assinatura íntegro."""
from __future__ import annotations

import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "build.yml"


class AssinaturaMacosTests(unittest.TestCase):
    def test_bundle_e_assinado_depois_de_editar_o_info_plist(self) -> None:
        # Editar o Info.plist depois da assinatura do PyInstaller invalida o selo
        # e o macOS passa a dizer que o app "está danificado".
        texto = WORKFLOW.read_text(encoding="utf-8")
        plist = texto.index("PlistBuddy")
        assinatura = texto.index("codesign --force --deep --sign -")
        empacotar = texto.index("name: Empacotar o aplicativo")
        self.assertLess(plist, assinatura)
        self.assertLess(assinatura, empacotar)
        self.assertIn("codesign --verify --deep --strict", texto)


if __name__ == "__main__":
    unittest.main()
