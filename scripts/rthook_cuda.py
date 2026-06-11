"""PyInstaller runtime hook: make bundled CUDA DLLs discoverable.

In the frozen one-folder build, CTranslate2's ``ctranslate2.dll`` lives under
``_internal/ctranslate2/`` while the bundled CUDA runtime DLLs (cuBLAS/cuDNN)
land at the bundle root (``_internal/``). The Windows loader resolves a DLL's
dependencies from the dependent DLL's own directory first, then the standard
search path — it does NOT automatically look in the bundle root.

This hook runs before any heavy import and registers the relevant directories
with ``os.add_dll_directory`` so cuBLAS/cuDNN resolve at load time. On a CPU
build (no CUDA DLLs bundled) the calls are harmless no-ops.
"""
from __future__ import annotations

import os
import sys

if hasattr(sys, "_MEIPASS"):
    meipass = sys._MEIPASS  # type: ignore[attr-defined]
    candidates = [
        meipass,
        os.path.join(meipass, "ctranslate2"),
    ]
    for d in candidates:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except (OSError, AttributeError):
                pass
    # Also prepend to PATH as a belt-and-suspenders fallback for older loaders.
    os.environ["PATH"] = meipass + os.pathsep + os.environ.get("PATH", "")
