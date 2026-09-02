"""Configura DLLs empacotadas antes de carregar PyTorch/CTranslate2."""
from __future__ import annotations

import os
import sys

if getattr(sys, "frozen", False):
    root = getattr(sys, "_MEIPASS", "")
    for relative in ("torch/lib", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
        folder = os.path.join(root, relative)
        if os.path.isdir(folder) and hasattr(os, "add_dll_directory"):
            os.add_dll_directory(folder)
