"""Locate bundled asset files in both dev and PyInstaller-frozen runs.

In a normal checkout the assets live at ``<repo>/assets``. When frozen by
PyInstaller (one-folder build) data files are unpacked next to the executable
under ``_internal`` and exposed via ``sys._MEIPASS``. This module hides that
difference behind a single lookup.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

ICON_FILENAME = "icon.ico"


def _candidate_dirs() -> list[Path]:
    dirs: list[Path] = []
    # PyInstaller bundle root (datas are copied here, see jaspervoice.spec).
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        base = Path(meipass)
        dirs.append(base / "assets")
        dirs.append(base)
    # Dev checkout: this file is src/jaspervoice/assets.py -> repo/assets.
    repo_assets = Path(__file__).resolve().parent.parent.parent / "assets"
    dirs.append(repo_assets)
    return dirs


def asset_path(name: str) -> Path | None:
    """Locate a packaged asset or its source-tree equivalent."""
    for d in _candidate_dirs():
        candidate = d / name
        if candidate.is_file():
            return candidate
    return None


def icon_path() -> Optional[str]:
    path = asset_path(ICON_FILENAME)
    return str(path) if path is not None else None
