"""Contratos da pilha CUDA embutida (CTranslate2 + cuDNN + cuBLAS).

A 1.10.x subiu o CTranslate2 para 4.8.2 mantendo o cuDNN 8. Nenhum teste
acusou e a transcrição passou a cair para CPU em máquinas NVIDIA. Estes testes
não precisam de GPU: conferem que as versões declaradas em todos os lugares
formam um conjunto que o CTranslate2 consegue carregar.
"""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from baixador_ytdlp import runtime

ROOT = Path(__file__).resolve().parents[1]
# cudnn64_9.dll distribuído dentro do wheel Windows de cada CTranslate2. O
# pacote nvidia-cudnn-cu12 precisa ter exatamente esta versão.
CT2_BUNDLED_CUDNN = {"4.8.2": "9.10.2.21"}


def _pins(text: str) -> dict[str, str]:
    return {
        match.group(1).lower(): match.group(2)
        for match in re.finditer(r"(?m)^([A-Za-z0-9_.-]+)==([^\s\\;]+)", text)
    }


class CudaStackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirements = _pins((ROOT / "requirements.txt").read_text(encoding="utf-8"))
        self.lock = _pins((ROOT / "requirements/requirements-windows.lock").read_text(encoding="utf-8"))

    def test_major_do_cudnn_segue_o_ctranslate2(self) -> None:
        self.assertEqual(runtime.required_cudnn_major("4.4.0"), 8)
        self.assertEqual(runtime.required_cudnn_major("4.5.0"), 9)
        self.assertEqual(runtime.required_cudnn_major("4.8.2"), 9)
        self.assertEqual(runtime.cudnn_version_major(8907), 8)
        self.assertEqual(runtime.cudnn_version_major(91002), 9)

    def test_requirements_casam_ctranslate2_e_cudnn(self) -> None:
        ct2 = self.requirements["ctranslate2"]
        cudnn = self.requirements["nvidia-cudnn-cu12"]
        self.assertEqual(int(cudnn.split(".")[0]), runtime.required_cudnn_major(ct2))
        self.assertIn(ct2, CT2_BUNDLED_CUDNN,
                      "Nova versão do CTranslate2: confira o cudnn64_9.dll do wheel "
                      "Windows e registre a versão em CT2_BUNDLED_CUDNN.")
        self.assertEqual(cudnn, CT2_BUNDLED_CUDNN[ct2])

    def test_lock_windows_reflete_os_requirements(self) -> None:
        for name in ("ctranslate2", "faster-whisper", "nvidia-cuda-runtime-cu12",
                     "nvidia-cublas-cu12", "nvidia-cudnn-cu12"):
            self.assertEqual(self.lock.get(name), self.requirements[name], name)

    def test_constantes_do_runtime_refletem_os_requirements(self) -> None:
        for requirement in (*runtime.PACKAGES, *runtime.CUDA_PACKAGES):
            name, version = requirement.split("==")
            self.assertEqual(self.requirements[name.lower()], version, name)

    def test_build_confere_as_dlls_da_versao_certa(self) -> None:
        major = runtime.required_cudnn_major(self.requirements["ctranslate2"])
        wrong = 8 if major == 9 else 9
        for path in (ROOT / "build.ps1", ROOT / ".github" / "workflows" / "build.yml"):
            content = path.read_text(encoding="utf-8")
            self.assertIn(f"'cudnn64_{major}.dll'", content, path.name)
            self.assertIn(f"'cudnn_cnn64_{major}.dll'" if major == 9
                          else "'cudnn_cnn_infer64_8.dll'", content, path.name)
            self.assertNotIn(f"cudnn64_{wrong}.dll", content, path.name)

    def test_cuda_embutido_exige_a_variante_do_ctranslate2(self) -> None:
        core = ("cudart64_12.dll", "cublasLt64_12.dll", "cublas64_12.dll")
        cudnn8 = ("cudnn_ops_infer64_8.dll", "cudnn_cnn_infer64_8.dll", "cudnn64_8.dll")
        cudnn9 = runtime._CUDNN_VARIANTS[9][0]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder in runtime._cuda_dll_dirs(root)[1:]:
                folder.mkdir(parents=True)
            bin_dir = root / "nvidia" / "cudnn" / "bin"
            for name in (*core, *cudnn8):
                (bin_dir / name).write_bytes(b"")
            with patch.object(runtime, "IS_WINDOWS", True), \
                    patch.object(runtime, "_embedded_roots", return_value=[root]), \
                    patch.object(runtime, "required_cudnn_major", return_value=9):
                # Só cuDNN 8 com CTranslate2 >= 4.5: a interface não pode dizer CUDA.
                self.assertFalse(runtime.embedded_cuda_available())
                self.assertIn("cudnn_cnn64_9.dll",
                              runtime.missing_cudnn_files([bin_dir], 9))
                for name in cudnn9:
                    (bin_dir / name).write_bytes(b"")
                self.assertTrue(runtime.embedded_cuda_available())
                self.assertEqual(runtime.missing_cudnn_files([bin_dir], 9), [])


if __name__ == "__main__":
    unittest.main()
