# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for JasperVoice.

Build a windowed (no-console) standalone app:

    pyinstaller jaspervoice.spec --noconfirm

Output: dist/JasperVoice/JasperVoice.exe (one-folder build).

Notes
-----
- One-folder (not one-file) because the bundle is large (CTranslate2 + PySide6
  + PyAV). One-folder starts faster and avoids re-extracting to a temp dir on
  every launch.
- The Whisper model itself is NOT bundled. It is downloaded on first run to
  %APPDATA%/JasperVoice/models/ (same as the dev workflow).
- silero VAD asset (used by vad_filter=True) ships inside faster_whisper and
  must be collected explicitly.
"""

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

import importlib.util
import os

block_cipher = None

# faster-whisper bundles the Silero VAD onnx model under faster_whisper/assets.
fw_datas = collect_data_files("faster_whisper", includes=["assets/*"])

# Ship the brand icon so the tray/window can load it at runtime via
# jaspervoice.assets.icon_path() (it resolves sys._MEIPASS/assets).
app_datas = [("assets/icon.ico", "assets")]

# CTranslate2 and onnxruntime ship native libs that PyInstaller's static
# analysis can miss; collect them explicitly.
binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("av")


def _collect_cuda_dlls():
    """Bundle the CUDA runtime DLLs that CTranslate2 needs for GPU inference.

    The pip-installed ``nvidia-*`` packages ship the CUDA libraries under
    ``nvidia/<lib>/bin``. CTranslate2's Whisper path is cuBLAS-driven, so we
    ship cuBLAS (cublas64_12 + cublasLt64_12). cuDNN's dispatch stub
    (cudnn64_9.dll) already rides along via collect_dynamic_libs("ctranslate2").
    We also ship the cuDNN implementation DLLs so any cuDNN-backed op still
    resolves at runtime instead of silently falling back to CPU.

    Returns a list of (src, dest) tuples placing the DLLs at the bundle root
    (``.``) so they sit next to ctranslate2.dll where the Windows loader finds
    them. If the nvidia packages aren't installed (CPU-only dev env), this
    returns an empty list and the build still produces a working CPU app.
    """
    spec = importlib.util.find_spec("nvidia")
    if not spec or not spec.submodule_search_locations:
        print("WARNING: nvidia CUDA packages not found; building CPU-only bundle")
        return []
    nv_root = spec.submodule_search_locations[0]
    out = []
    # cuBLAS is mandatory for GPU inference; cuDNN is bundled for completeness.
    for sub in ("cublas", "cudnn"):
        bin_dir = os.path.join(nv_root, sub, "bin")
        if not os.path.isdir(bin_dir):
            continue
        for fn in os.listdir(bin_dir):
            if fn.lower().endswith(".dll"):
                out.append((os.path.join(bin_dir, fn), "."))
    print(f"Bundling {len(out)} CUDA DLLs from {nv_root}")
    return out


binaries += _collect_cuda_dlls()

hiddenimports = [
    "faster_whisper",
    "ctranslate2",
    "onnxruntime",
    "av",
    "tokenizers",
    "sounddevice",
    "numpy",
    "keyboard",
    "pyperclip",
]

a = Analysis(
    ["src/jaspervoice/app_gui.py"],
    pathex=["src"],
    binaries=binaries,
    datas=fw_datas + app_datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["scripts/rthook_cuda.py"],
    excludes=[
        "tkinter",
        "pytest",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtQuick",
        "PySide6.QtQml",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="JasperVoice",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # windowed: no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="JasperVoice",
)
