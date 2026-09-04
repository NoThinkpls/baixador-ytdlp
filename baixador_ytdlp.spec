# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller. Uso: pyinstaller baixador_ytdlp.spec --noconfirm"""
from PyInstaller.utils.hooks import collect_all

# O faster-whisper roda sobre CTranslate2. As bibliotecas CUDA entram no
# instalador: o usuário precisa apenas do driver NVIDIA, não do toolkit CUDA.
fw_datas, fw_binaries, fw_hidden = collect_all('faster_whisper')
ct_datas, ct_binaries, ct_hidden = collect_all('ctranslate2')
av_datas, av_binaries, av_hidden = collect_all('av')
pip_datas, pip_binaries, pip_hidden = collect_all('pip')
cudart_datas, cudart_binaries, cudart_hidden = collect_all('nvidia.cuda_runtime')
cublas_datas, cublas_binaries, cublas_hidden = collect_all('nvidia.cublas')
cudnn_datas, cudnn_binaries, cudnn_hidden = collect_all('nvidia.cudnn')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=(fw_binaries + ct_binaries + av_binaries + pip_binaries + cudart_binaries
              + cublas_binaries + cudnn_binaries),
    datas=([('assets/icon.ico', 'assets')] + fw_datas + ct_datas + av_datas + pip_datas
           + cudart_datas + cublas_datas + cudnn_datas),
    hiddenimports=(['qfluentwidgets', 'qframelesswindow'] + fw_hidden + ct_hidden + av_hidden
                   + pip_hidden + cudart_hidden + cublas_hidden + cudnn_hidden),
    hookspath=[],
    runtime_hooks=['pyinstaller_runtime.py'],
    excludes=[
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore',
        'PySide6.QtQuick3D', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtPdf', 'PySide6.QtQuick', 'PySide6.QtQml',
        'PySide6.QtOpenGL', 'PySide6.QtTest', 'PySide6.QtSql', 'PySide6.QtDesigner',
        'PySide6.QtBluetooth', 'PySide6.QtNetworkAuth', 'PySide6.QtPositioning',
        'torch', 'torchvision', 'torchaudio', 'triton',
        'tkinter', 'unittest', 'pydoc', 'doctest', 'pdb', 'lib2to3',
        'matplotlib', 'scipy', 'pandas', 'IPython', 'notebook', 'setuptools._distutils',
    ],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='baixador-ytdlp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # sem janela preta de console
    icon='assets/icon.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, upx_exclude=[],
    name='baixador-ytdlp',
)
