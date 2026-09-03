"""Configura DLLs CUDA empacotadas antes de carregar CTranslate2."""
from __future__ import annotations

import os
import sys

_DLL_DIRECTORY_HANDLES = []

if getattr(sys, "frozen", False):
    root = getattr(sys, "_MEIPASS", "")
    folders = []
    for relative in ("nvidia/cuda_runtime/bin", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
        folder = os.path.join(root, relative)
        if os.path.isdir(folder) and hasattr(os, "add_dll_directory"):
            # O objeto devolvido remove o diretório ao ser coletado. Mantê-lo
            # vivo é indispensável porque cuBLAS/cuDNN são carregadas depois,
            # na primeira inferência, e não no import do aplicativo.
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(folder))
            folders.append(folder)
    if folders:
        os.environ["PATH"] = os.pathsep.join([*folders, os.environ.get("PATH", "")])
