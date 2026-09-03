# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        *collect_data_files('reportlab'),
        *collect_data_files('openpyxl'),
    ],
    hiddenimports=[
        *collect_submodules('reportlab'),
        *collect_submodules('openpyxl'),
        *collect_submodules('flask'),
        *collect_submodules('werkzeug'),
        'tomllib',
        'tomli',
        'jinja2',
        'click',
        'itsdangerous',
        'markupsafe',
        'blinker',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='trust-account-webapp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
