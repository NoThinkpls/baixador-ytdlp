# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller. Uso: pyinstaller baixador_ytdlp.spec --noconfirm"""
from PyInstaller.utils.hooks import collect_all

fw_datas, fw_binaries, fw_hidden = collect_all('faster_whisper')
ct_datas, ct_binaries, ct_hidden = collect_all('ctranslate2')
torch_datas, torch_binaries, torch_hidden = collect_all('torch')
av_datas, av_binaries, av_hidden = collect_all('av')
pip_datas, pip_binaries, pip_hidden = collect_all('pip')

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=fw_binaries + ct_binaries + torch_binaries + av_binaries + pip_binaries,
    datas=[('assets/icon.ico', 'assets')] + fw_datas + ct_datas + torch_datas + av_datas + pip_datas,
    hiddenimports=(['qfluentwidgets', 'qframelesswindow'] + fw_hidden + ct_hidden + torch_hidden + av_hidden
                   + pip_hidden),
    hookspath=[],
    runtime_hooks=['pyinstaller_runtime.py'],
    excludes=[
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.Qt3DCore',
        'PySide6.QtQuick3D', 'PySide6.QtCharts', 'PySide6.QtDataVisualization',
        'PySide6.QtMultimedia', 'PySide6.QtPdf', 'tkinter', 'unittest', 'pydoc',
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
