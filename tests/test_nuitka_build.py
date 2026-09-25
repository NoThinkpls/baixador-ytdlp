"""Contratos da rota de distribuição Windows com Nuitka."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from baixador_ytdlp import runtime


class NuitkaBuildTests(unittest.TestCase):
    def test_runtime_encontra_a_raiz_da_distribuicao_nuitka(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            compiled = SimpleNamespace(containing_dir=str(root))
            with patch.dict(runtime.__dict__, {"__compiled__": compiled}):
                roots = runtime._embedded_roots()
        self.assertIn(root, roots)

    def test_configuracao_declara_dlls_cuda_dinamicas(self) -> None:
        config = (Path(__file__).resolve().parents[1] / "nuitka-package.config.yml").read_text(
            encoding="utf-8"
        )
        for package in ("nvidia.cuda_runtime", "nvidia.cublas", "nvidia.cudnn"):
            self.assertIn(package, config)
        for folder in ("nvidia/cuda_runtime/bin", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
            self.assertIn(folder, config)

    def test_build_inclui_metadados_do_runtime_de_transcricao(self) -> None:
        build_script = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(
            encoding="utf-8"
        )
        for distribution in ("faster-whisper", "ctranslate2"):
            self.assertIn(f"--include-distribution-metadata={distribution}", build_script)

    def test_build_inclui_modelo_vad_do_faster_whisper(self) -> None:
        root = Path(__file__).resolve().parents[1]
        expected = "--include-package-data=faster_whisper:assets/silero_encoder_v5.onnx"
        for path in (root / "build.ps1", root / ".github" / "workflows" / "build.yml"):
            self.assertIn(expected, path.read_text(encoding="utf-8"))

    def test_nuitka_e_padrao_e_normaliza_layout_do_instalador(self) -> None:
        build_script = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[string]$Packager = 'Nuitka'", build_script)
        self.assertIn("'dist\\main.dist'", build_script)
        self.assertIn("'dist\\baixador-ytdlp'", build_script)
        self.assertIn("Move-Item -LiteralPath $nuitkaBundle -Destination $releaseBundle", build_script)


if __name__ == "__main__":
    unittest.main()
