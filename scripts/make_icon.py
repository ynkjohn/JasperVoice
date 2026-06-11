"""Rasterize assets/icon.svg into a multi-resolution Windows .ico.

Uses Qt (already a project dependency) to render the SVG, so no extra native
libraries (cairo, Pillow) are required. The .ico is assembled by hand from
PNG-encoded frames, which Windows Vista+ accepts natively.

Usage:
    python scripts/make_icon.py

Output: assets/icon.ico
"""

from __future__ import annotations

import os
import struct
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

# Standard Windows icon sizes (px). 256 is stored as PNG; smaller sizes too.
SIZES = [16, 24, 32, 48, 64, 128, 256]

ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "icon.svg"
ICO_PATH = ROOT / "assets" / "icon.ico"


def render_png(renderer: QSvgRenderer, size: int) -> bytes:
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()

    # NOTE: QBuffer-based in-memory encoding crashes under the offscreen
    # platform on this build, so we round-trip through a temp file instead.
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        if not img.save(tmp_path, "PNG"):
            raise RuntimeError(f"Failed to encode PNG at size {size}")
        return Path(tmp_path).read_bytes()
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def build_ico(frames: list[tuple[int, bytes]], out_path: Path) -> None:
    count = len(frames)
    # ICONDIR header: reserved(2)=0, type(2)=1 (icon), count(2)
    header = struct.pack("<HHH", 0, 1, count)

    entries = b""
    image_data = b""
    offset = 6 + count * 16  # header + directory entries

    for size, png in frames:
        dim = 0 if size >= 256 else size  # 0 means 256 in ICO spec
        # ICONDIRENTRY: width(1) height(1) colorCount(1) reserved(1)
        #               planes(2) bitCount(2) bytesInRes(4) imageOffset(4)
        entries += struct.pack(
            "<BBBBHHII",
            dim, dim, 0, 0, 1, 32, len(png), offset,
        )
        image_data += png
        offset += len(png)

    out_path.write_bytes(header + entries + image_data)


def main() -> int:
    if not SVG_PATH.is_file():
        print(f"SVG not found: {SVG_PATH}", file=sys.stderr)
        return 1

    _app = QApplication.instance() or QApplication(sys.argv)
    renderer = QSvgRenderer(str(SVG_PATH))
    if not renderer.isValid():
        print(f"Invalid SVG: {SVG_PATH}", file=sys.stderr)
        return 1

    frames = [(size, render_png(renderer, size)) for size in SIZES]
    build_ico(frames, ICO_PATH)
    print(f"Wrote {ICO_PATH} ({ICO_PATH.stat().st_size} bytes, {len(frames)} sizes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
