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
- CUDA DLLs are deduplicated and trimmed:
  * ``_collect_cuda_dlls()`` ships cuBLAS at the bundle root (cuDNN is excluded
    by default — the Whisper path doesn't use it; set JV_CUDNN=1 to include it).
  * The binaries TOC is filtered to drop the ``nvidia/<lib>/bin/`` copies that
    PyInstaller's nvidia hooks would otherwise add, which used to duplicate
    ~931 MB.
  Net effect: GPU bundle ~1.0 GB (was ~3.0 GB), still loads on device=cuda.
"""

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_data_files

import importlib.util
import os

block_cipher = None


def _read_version() -> str:
    """Read the single source of truth: src/jaspervoice/__init__.py::__version__.

    We parse the literal instead of importing the package so the spec stays
    importable even if the package's runtime deps aren't on PyInstaller's path.
    """
    init_path = os.path.join("src", "jaspervoice", "__init__.py")
    try:
        with open(init_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("__version__"):
                    return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return "0.0.0"


def _version_info(version: str):
    """Build a PyInstaller VSVersionInfo so JasperVoice.exe carries a real
    Windows version resource (shown in file properties; read by the installer).
    """
    parts = [int(p) for p in version.split(".")[:3]]
    while len(parts) < 3:
        parts.append(0)
    parts.append(0)  # build number
    filevers = tuple(parts)
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo,
        FixedFileInfo,
        StringFileInfo,
        StringTable,
        StringStruct,
        VarFileInfo,
        VarStruct,
    )

    return VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=filevers,
            prodvers=filevers,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable("040904B0", [
                    StringStruct("CompanyName", "JasperVoice"),
                    StringStruct("FileDescription", "JasperVoice — push-to-talk voice dictation"),
                    StringStruct("FileVersion", version),
                    StringStruct("InternalName", "JasperVoice"),
                    StringStruct("OriginalFilename", "JasperVoice.exe"),
                    StringStruct("ProductName", "JasperVoice"),
                    StringStruct("ProductVersion", version),
                ]),
            ]),
            VarFileInfo([VarStruct("Translation", [0x0409, 0x04B0])]),
        ],
    )


APP_VERSION = _read_version()

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
    ``nvidia/<lib>/bin``. CTranslate2's Whisper path is **cuBLAS-driven only**:
    GPU inference (encoder + decoder) runs through cuBLAS and does NOT touch
    cuDNN. This was verified by physically removing cuDNN from the environment
    and confirming a full ``device=cuda`` transcription still succeeds.

    We therefore ship cuBLAS (cublas64_12 + cublasLt64_12) by default and SKIP
    cuDNN, which alone is ~1 GB (cudnn_engines_precompiled64_9.dll is 460 MB).
    Set ``JV_CUDNN=1`` to opt back into bundling cuDNN if a future model or
    code path needs a cuDNN-backed op.

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
    # cuBLAS is mandatory for GPU inference. cuDNN (~1 GB) is unused by the
    # Whisper path, so it is excluded unless JV_CUDNN=1 is set.
    subs = ("cublas", "cudnn") if os.environ.get("JV_CUDNN") == "1" else ("cublas",)
    for sub in subs:
        bin_dir = os.path.join(nv_root, sub, "bin")
        if not os.path.isdir(bin_dir):
            continue
        for fn in os.listdir(bin_dir):
            if fn.lower().endswith(".dll"):
                out.append((os.path.join(bin_dir, fn), "."))
    print(f"Bundling {len(out)} CUDA DLLs from {nv_root} (subs={subs})")
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

# Drop the duplicate CUDA DLLs that PyInstaller's bundled nvidia hooks
# (hook-nvidia.cublas / hook-nvidia.cudnn) collect under ``nvidia/<lib>/bin/``.
# ``_collect_cuda_dlls()`` already ships the same ~931 MB of DLLs at the bundle
# root (where rthook_cuda.py registers them on the DLL search path), so the
# nvidia/ tree is pure dead weight. ``excludes`` can't remove these because they
# enter via native hooks, not the Python module graph — we filter the TOC here.
_orig_binaries_count = len(a.binaries)
a.binaries = [
    (name, path, typecode)
    for (name, path, typecode) in a.binaries
    if not name.lower().replace("\\", "/").startswith("nvidia/")
]
print(
    f"Filtered duplicate nvidia DLLs from binaries: "
    f"{_orig_binaries_count} -> {len(a.binaries)}"
)

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
    version=_version_info(APP_VERSION),
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
