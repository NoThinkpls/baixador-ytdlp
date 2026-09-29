"""Contratos das rotas de distribuição Windows."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp import runtime


class NuitkaBuildTests(unittest.TestCase):
    def test_runtime_encontra_a_raiz_da_distribuicao_nuitka(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch("baixador_ytdlp.runtime.pasta_do_executavel", return_value=root):
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
        spec = (Path(__file__).resolve().parents[1] / "baixador_ytdlp.spec").read_text(
            encoding="utf-8"
        )
        for distribution in (
            "faster-whisper", "ctranslate2", "av", "onnxruntime", "tokenizers", "huggingface-hub",
        ):
            self.assertIn(f"'{distribution}'", spec)
        self.assertIn("copy_metadata(name)", spec)

    def test_build_inclui_todos_os_dados_do_faster_whisper(self) -> None:
        root = Path(__file__).resolve().parents[1]
        spec = (root / "baixador_ytdlp.spec").read_text(encoding="utf-8")
        self.assertIn("collect_all('faster_whisper')", spec)
        for path in (root / "build.ps1", root / ".github" / "workflows" / "build.yml"):
            self.assertIn("faster_whisper\\assets", path.read_text(encoding="utf-8"))

    def test_build_valida_assets_reais_e_executa_self_test(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for path in (root / "build.ps1", root / ".github" / "workflows" / "build.yml"):
            content = path.read_text(encoding="utf-8")
            self.assertIn("get_assets_path", content)
            self.assertIn("BAIXADOR_YTDLP_SELF_TEST_REPORT", content)
            self.assertIn("selfTestExitCode", content)
            self.assertIn("Start-Process -FilePath $exe -PassThru -Wait", content)
        entrypoint = (root / "main.py").read_text(encoding="utf-8")
        self.assertIn("--self-test", entrypoint)
        self.assertIn("BAIXADOR_YTDLP_SELF_TEST_REPORT", entrypoint)

    def test_pyinstaller_e_padrao_e_nuitka_continua_opcional(self) -> None:
        build_script = (Path(__file__).resolve().parents[1] / "build.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("[string]$Packager = 'PyInstaller'", build_script)
        self.assertIn("if ($Packager -eq 'Nuitka')", build_script)
        self.assertIn("NUITKA_CACHE_DIR", build_script)
        self.assertIn("'dist\\main.dist'", build_script)
        self.assertIn("'dist\\baixador-ytdlp'", build_script)
        self.assertIn("Move-Item -LiteralPath $nuitkaBundle -Destination $releaseBundle", build_script)


if __name__ == "__main__":
    unittest.main()
