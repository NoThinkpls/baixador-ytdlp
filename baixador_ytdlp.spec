# -*- mode: python ; coding: utf-8 -*-
"""Receita do PyInstaller. Uso: pyinstaller baixador_ytdlp.spec --noconfirm"""

block_cipher = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('assets/icon.ico', 'assets')],
    hiddenimports=['qfluentwidgets', 'qframelesswindow'],
    hookspath=[],
    runtime_hooks=[],
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
