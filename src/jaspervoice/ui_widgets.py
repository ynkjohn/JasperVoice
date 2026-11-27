"""Shared building blocks for the JasperVoice settings UI.

Original primitives drawn with plain Qt — no icon fonts, no images:

- Switch            painted on/off toggle (keyboard + mouse, focus ring)
- SegmentedControl  exclusive option strip backed by string keys
- LevelMeter        painted live input-level bars, fed through a Signal
- MicLevelSource    owns a sounddevice InputStream; audio-thread levels are
                    emitted via a Qt Signal so widgets repaint on the UI thread
- DotRating         five-dot accuracy indicator for model cards
- StatTile          big-number statistics tile
- helper labels / hairline / row builders shared by all pages
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from typing import Optional

import numpy as np

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from .config import LANGUAGES  # re-exported for existing UI callers
from .theme import COLORS

log = logging.getLogger(__name__)


# --- Hotkey format conversion (Qt <-> keyboard-lib) ---

# Tokens that don't title-case cleanly. Map them explicitly; anything else
# passes through .title() (handles single letters, f1-f24, digits).
_TOKEN_TITLE = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "altgr": "AltGr",
    "meta": "Meta",
    "super": "Super",
    "space": "Space",
    "tab": "Tab",
    "enter": "Enter",
    "return": "Return",
    "esc": "Esc",
    "escape": "Escape",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pgup": "PgUp",
    "pageup": "PgUp",
    "pgdown": "PgDown",
    "pagedown": "PgDown",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "capslock": "CapsLock",
    "numlock": "NumLock",
    "scrolllock": "ScrollLock",
    "printscreen": "PrintScreen",
    "menu": "Menu",
}


def keyboard_to_qt(s: str) -> QKeySequence:
    """Convert keyboard-lib format ('ctrl+shift+r') to QKeySequence."""
    parts = [p.strip() for p in s.lower().split("+") if p.strip()]
    qt_parts = [_TOKEN_TITLE.get(p, p.title()) for p in parts]
    return QKeySequence("+".join(qt_parts))


def qt_to_keyboard(seq: QKeySequence) -> str:
    """Convert QKeySequence to keyboard-lib format. Returns empty string if no keys set."""
    s = seq.toString()
    if not s:
        return ""
    # Qt's toString() returns tokens already separated by '+'. We need the
    # reverse of _TOKEN_TITLE, but .lower() works for every entry because
    # the canonical Qt names are the same words as the keyboard-lib tokens.
    return s.lower()


# --- Painted line glyphs (no icon fonts, no image assets) ---------------------

def _draw_grid(p: QPainter) -> None:
    for x, y in ((2.5, 2.5), (9, 2.5), (2.5, 9), (9, 9)):
        p.drawRoundedRect(QRectF(x, y, 4.5, 4.5), 1, 1)


def _draw_clock(p: QPainter) -> None:
    p.drawEllipse(QRectF(2.5, 2.5, 11, 11))
    p.drawLine(QPointF(8, 8), QPointF(8, 5))
    p.drawLine(QPointF(8, 8), QPointF(10.4, 9.4))


def _draw_book(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(2.8, 2.8, 10.4, 10.4), 1.5, 1.5)
    p.drawLine(QPointF(8, 2.8), QPointF(8, 13.2))


def _draw_sliders(p: QPainter) -> None:
    for y, cx in ((4.2, 10.2), (8.0, 5.4), (11.8, 11.0)):
        p.drawLine(QPointF(2.2, y), QPointF(13.8, y))
        p.drawEllipse(QRectF(cx - 1.7, y - 1.7, 3.4, 3.4))


def _draw_mic(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(5.8, 1.8, 4.4, 7.2), 2.2, 2.2)
    p.drawArc(QRectF(3.6, 4.2, 8.8, 8.2), 200 * 16, 140 * 16)
    p.drawLine(QPointF(8, 12.4), QPointF(8, 14.2))
    p.drawLine(QPointF(5.6, 14.2), QPointF(10.4, 14.2))


def _draw_chip(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(4, 4, 8, 8), 1.5, 1.5)
    p.drawRoundedRect(QRectF(6.5, 6.5, 3, 3), 0.5, 0.5)
    for c in (6, 10):
        p.drawLine(QPointF(c, 2), QPointF(c, 4))
        p.drawLine(QPointF(c, 12), QPointF(c, 14))
        p.drawLine(QPointF(2, c), QPointF(4, c))
        p.drawLine(QPointF(12, c), QPointF(14, c))


def _draw_spark(p: QPainter) -> None:
    path = QPainterPath(QPointF(8, 2))
    path.quadTo(9, 7, 14, 8)
    path.quadTo(9, 9, 8, 14)
    path.quadTo(7, 9, 2, 8)
    path.quadTo(7, 7, 8, 2)
    path.closeSubpath()
    p.drawPath(path)


def _draw_command(p: QPainter) -> None:
    path = QPainterPath(QPointF(2, 9))
    path.lineTo(2, 4.5)
    path.quadTo(2, 3, 3.5, 3)
    path.lineTo(12.5, 3)
    path.quadTo(14, 3, 14, 4.5)
    path.lineTo(14, 9)
    path.quadTo(14, 10.5, 12.5, 10.5)
    path.lineTo(7, 10.5)
    path.lineTo(3.5, 13.5)
    path.lineTo(3.5, 10.5)
    path.quadTo(2, 10.5, 2, 9)
    p.drawPath(path)
    p.drawLine(QPointF(5.5, 5.5), QPointF(7, 7))
    p.drawLine(QPointF(7, 7), QPointF(5.5, 8.5))
    p.drawLine(QPointF(9, 8.5), QPointF(11, 8.5))


def _draw_download(p: QPainter) -> None:
    p.drawLine(QPointF(8, 2), QPointF(8, 9.8))
    p.drawLine(QPointF(4.8, 7), QPointF(8, 10.2))
    p.drawLine(QPointF(11.2, 7), QPointF(8, 10.2))
    p.drawLine(QPointF(2.8, 13.6), QPointF(13.2, 13.6))


def _draw_pulse(p: QPainter) -> None:
    path = QPainterPath(QPointF(1.6, 8))
    for x, y in ((4.6, 8), (6.2, 3.6), (9.4, 12.4), (10.8, 8), (14.4, 8)):
        path.lineTo(x, y)
    p.drawPath(path)


def _draw_folder(p: QPainter) -> None:
    path = QPainterPath(QPointF(2, 5))
    path.lineTo(2, 12.6)
    path.lineTo(14, 12.6)
    path.lineTo(14, 5.8)
    path.lineTo(7.8, 5.8)
    path.lineTo(6.4, 3.6)
    path.lineTo(2.8, 3.6)
    path.closeSubpath()
    p.drawPath(path)


def _draw_wave(p: QPainter) -> None:
    for x, top, bottom in ((3.2, 6.2, 9.8), (5.8, 4.4, 11.6), (8.4, 2.4, 13.6), (11.0, 5.0, 11.0), (13.6, 6.8, 9.2)):
        p.drawLine(QPointF(x, top), QPointF(x, bottom))


_GLYPHS = {
    "grid": _draw_grid,
    "clock": _draw_clock,
    "book": _draw_book,
    "sliders": _draw_sliders,
    "mic": _draw_mic,
    "chip": _draw_chip,
    "spark": _draw_spark,
    "command": _draw_command,
    "download": _draw_download,
    "pulse": _draw_pulse,
    "folder": _draw_folder,
    "wave": _draw_wave,
}


def glyph_pixmap(kind: str, size: int = 16, color: Optional[str] = None) -> QPixmap:
    """Render a crisp line glyph at 2x device pixel ratio. Unknown kinds
    return an empty (transparent) pixmap rather than raising."""
    dpr = 2.0
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    drawer = _GLYPHS.get(kind)
    if drawer is not None:
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(color or COLORS["fg_muted"]), 1.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.scale(size / 16.0, size / 16.0)
        drawer(p)
        p.end()
    return pm


def glyph_icon(kind: str, color: Optional[str] = None) -> QIcon:
    return QIcon(glyph_pixmap(kind, 16, color))


def glyph_label(kind: str, size: int = 16, color: Optional[str] = None) -> QLabel:
    lbl = QLabel()
    lbl.setPixmap(glyph_pixmap(kind, size, color))
    lbl.setFixedSize(size, size)
    return lbl


# --- Small label / layout helpers -------------------------------------------

def page_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "pagetitle")
    return lbl


def page_desc(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "pagedesc")
    lbl.setWordWrap(True)
    return lbl


def group_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "grouptitle")
    return lbl


def hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "hint")
    lbl.setWordWrap(True)
    return lbl


def mono(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "mono")
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setWordWrap(True)
    return lbl


def hairline() -> QFrame:
    f = QFrame()
    f.setProperty("role", "hairline")
    f.setFixedHeight(1)
    return f


class SettingRow(QWidget):
    """One settings line: label (+ optional hint below) left, control right.

    `search_terms` lets the sidebar search index every row by its label.
    """

    def __init__(
        self,
        label: str,
        control: QWidget,
        hint_text: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.label_text = label
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 10, 0, 10)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(3)
        lbl = QLabel(label)
        lbl.setProperty("role", "fieldlabel")
        lbl.setWordWrap(True)
        control.setAccessibleName(label)
        grid.addWidget(lbl, 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(control, 0, 1, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        if hint_text:
            h = hint(hint_text)
            grid.addWidget(h, 1, 0, 1, 2)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        lbl.setBuddy(control)


class SettingsGroup(QWidget):
    """Titled flat group of SettingRows separated by hairlines (no card box)."""

    def __init__(self, title: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._box = QVBoxLayout(self)
        self._box.setContentsMargins(0, 0, 0, 8)
        self._box.setSpacing(0)
        self._box.addWidget(group_title(title))
        self._box.addWidget(hairline())
        self._rows: list[SettingRow] = []

    def add_row(self, label: str, control: QWidget, hint_text: str = "") -> SettingRow:
        if self._rows:
            self._box.addWidget(hairline())
        row = SettingRow(label, control, hint_text)
        self._box.addWidget(row)
        self._rows.append(row)
        return row

    def add_widget(self, w: QWidget) -> None:
        self._box.addWidget(w)

    def row_labels(self) -> list[str]:
        return [r.label_text for r in self._rows]


# --- Switch ------------------------------------------------------------------

class Switch(QAbstractButton):
    """Painted on/off toggle. Checked = accent track, knob right."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(46, 24)

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        track = QRectF(0.5, 0.5, w - 1, h - 1)
        radius = (h - 1) / 2.0

        if not self.isEnabled():
            track_color = QColor(COLORS["bg_hover"])
            knob_color = QColor(COLORS["fg_disabled"])
            border = QColor(COLORS["border"])
        elif self.isChecked():
            track_color = QColor(COLORS["accent"])
            knob_color = QColor(COLORS["bg"])
            border = QColor(COLORS["accent"])
        else:
            track_color = QColor(COLORS["bg_hover"])
            knob_color = QColor(COLORS["fg_muted"])
            border = QColor(COLORS["border_strong"])

        p.setPen(QPen(border, 1))
        p.setBrush(track_color)
        p.drawRoundedRect(track, radius, radius)

        knob_d = h - 7
        x = (w - knob_d - 4) if self.isChecked() else 4
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(knob_color)
        p.drawEllipse(QRectF(x, (h - knob_d) / 2.0, knob_d, knob_d))

        if self.hasFocus():
            p.setPen(QPen(QColor(COLORS["focus"]), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(1, 1, -1, -1), radius, radius)
        p.end()


# --- Segmented control ---------------------------------------------------------

class SegmentedControl(QWidget):
    """Exclusive option strip. Options are (key, label) pairs; the current
    selection is exposed as the string key."""

    changed = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: Optional[QWidget] = None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for i, (key, label) in enumerate(options):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setProperty("seg", True)
            btn.setProperty("segfirst", i == 0)
            btn.setProperty("seglast", i == len(options) - 1)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.toggled.connect(self._on_toggled)
            self._group.addButton(btn)
            self._buttons[key] = btn
            row.addWidget(btn)
        row.addStretch(0)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.changed.emit(self.current_key())

    def current_key(self) -> str:
        for key, btn in self._buttons.items():
            if btn.isChecked():
                return key
        return next(iter(self._buttons), "")

    def set_current_key(self, key: str) -> None:
        btn = self._buttons.get(key)
        if btn is None:
            btn = next(iter(self._buttons.values()), None)
        if btn is not None:
            btn.setChecked(True)

    def keys(self) -> list[str]:
        return list(self._buttons.keys())


# --- Live input meter ----------------------------------------------------------

METER_FLOOR_DB = -60


def _meter_scale(amplitude: float) -> float:
    if amplitude <= 0.001:
        return 0.0
    return min(1.0, 1.0 - 20 * math.log10(amplitude) / METER_FLOOR_DB)


class LevelMeter(QWidget):
    """RMS input level and sample peak, scaled in dBFS."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._rms = 0.0
        self._peak = 0.0
        self.setMinimumHeight(58)
        self.setAccessibleName("Microphone input level in dBFS")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def reset(self) -> None:
        self._rms = self._peak = 0.0
        self.update()

    def set_levels(self, rms: float, peak: float) -> None:
        if not self.isVisible():
            return
        level = _meter_scale(rms)
        next_rms = self._rms + (level - self._rms) * (0.78 if level > self._rms else 0.23)
        next_rms = next_rms if next_rms >= 0.004 else 0.0
        next_peak = max(next_rms, _meter_scale(peak), self._peak - 0.018)
        if (next_rms, next_peak) != (self._rms, self._peak):
            self._rms, self._peak = next_rms, next_peak
            self.update()

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(COLORS["bg"]))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), 8, 8)

        x, y, h = 12.0, 12.0, 14.0
        span = self.width() - 2 * x
        cells, gap = 30, 2.5
        step = span / cells
        for i in range(cells):
            cell = QRectF(x + i * step, y, step - gap, h)
            p.setBrush(QColor(COLORS["border_strong"]))
            p.drawRoundedRect(cell, 2, 2)
            filled = min(1.0, self._rms * cells - i)
            if filled > 0:
                color = "danger" if i >= 28 else "warning" if i >= 24 else "accent"
                p.setBrush(QColor(COLORS[color]))
                cell.setWidth(cell.width() * filled)
                p.drawRoundedRect(cell, 2, 2)

        if self._peak > 0.0:
            p.setBrush(QColor(COLORS["fg"]))
            marker = min(span - 2, span * self._peak)
            p.drawRoundedRect(QRectF(x + marker, y - 3, 2, h + 6), 1, 1)

        p.setPen(QColor(COLORS["fg_muted"]))
        for i, label in enumerate(("-60", "-45", "-30", "-15", "0 dBFS")):
            width = p.fontMetrics().horizontalAdvance(label)
            left = max(x, min(x + span - width, x + span * i / 4 - width / 2))
            p.drawText(QPointF(left, 45), label)


class MicLevelSource(QObject):
    """Publish a single level snapshot each frame while the input is open."""

    levels = Signal(float, float)
    status = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._stream = None
        self._pending = deque(maxlen=20)
        self._sample = (0.0, 0.0, 0.0)
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._publish)

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def _capture(self, indata, frames, _time_info, _status) -> None:
        if frames:
            audio = indata[:, 0]
            rms = math.sqrt(float(np.dot(audio, audio)) / frames)
            peak = max(float(audio.max()), -float(audio.min()))
            self._pending.append((rms, peak, time.monotonic()))

    def _publish(self) -> None:
        rms, peak, timestamp = self._sample
        if self._pending:
            peak = 0.0
            while self._pending:
                rms, sample_peak, timestamp = self._pending.popleft()
                peak = max(peak, sample_peak)
            self._sample = (rms, peak, timestamp)
        if time.monotonic() - timestamp > 0.2:
            rms = peak = 0.0
        self.levels.emit(rms, peak)

    def start(self, device: Optional[str] = None) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd

            dev = None if device in (None, "", "default") else device
            samplerate = sd.query_devices(dev, "input")["default_samplerate"]
            self._stream = sd.InputStream(
                samplerate=samplerate, channels=1, dtype="float32",
                device=dev, callback=self._capture,
                blocksize=round(samplerate * 0.025),
            )
            self._stream.start()
        except Exception as e:
            self.stop()
            log.warning("Mic meter could not start: %s", e)
            self.status.emit("Microphone unavailable. Check the device and Windows permissions.")
            return
        self.status.emit("Live · RMS and peak")
        self._timer.start()

    def stop(self) -> None:
        self._timer.stop()
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.close()
            except Exception:
                log.debug("Could not close mic meter stream", exc_info=True)
        self._sample = (0.0, 0.0, 0.0)
        self._pending.clear()


# --- Model card pieces ----------------------------------------------------------

class DotRating(QWidget):
    """Five painted dots; `filled` of them use the accent color."""

    def __init__(self, filled: int, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._filled = max(0, min(filled, 5))
        self.setFixedSize(76, 14)

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        on = QColor(COLORS["accent"])
        off = QColor(COLORS["border_strong"])
        for i in range(5):
            p.setBrush(on if i < self._filled else off)
            p.drawEllipse(i * 15, 2, 9, 9)
        p.end()


class ModelCard(QPushButton):
    """Selectable Whisper-model card: name, footprint, accuracy, local state."""

    def __init__(self, key: str, size_text: str, accuracy: int,
                 parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.key = key
        self.setCheckable(True)
        self.setProperty("modelcard", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        box.setSpacing(7)
        name = QLabel(key)
        name.setProperty("role", "cardname")
        box.addWidget(name)
        size_lbl = QLabel(size_text)
        size_lbl.setProperty("role", "hint")
        box.addWidget(size_lbl)
        box.addWidget(DotRating(accuracy))
        self.state_label = QLabel("")
        self.state_label.setProperty("role", "cardstate")
        box.addWidget(self.state_label)
        for child in (name, size_lbl, self.state_label):
            child.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

    def set_state_text(self, text: str, emphasized: bool = False) -> None:
        self.state_label.setText(text)
        self.state_label.setProperty("emph", emphasized)
        self.state_label.style().unpolish(self.state_label)
        self.state_label.style().polish(self.state_label)


# --- Stat tile -------------------------------------------------------------------

class StatTile(QFrame):
    """Big mono number + small caption, used on the Overview page."""

    def __init__(self, caption: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("role", "stattile")
        box = QVBoxLayout(self)
        box.setContentsMargins(14, 10, 14, 11)
        box.setSpacing(4)
        self.value_label = QLabel("—")
        self.value_label.setProperty("role", "statvalue")
        box.addWidget(self.value_label)
        cap = QLabel(caption)
        cap.setProperty("role", "statcaption")
        box.addWidget(cap)

    def set_value(self, text: str) -> None:
        self.value_label.setText(text)


# --- Device enumeration helper ------------------------------------------------------

def list_input_devices() -> list[str]:
    """Names of all input-capable audio devices (deduplicated, ordered)."""
    try:
        import sounddevice as sd

        names: list[str] = []
        for dev in sd.query_devices():
            try:
                if int(dev.get("max_input_channels", 0)) > 0:
                    name = str(dev.get("name", "")).strip()
                    if name and name not in names:
                        names.append(name)
            except Exception:
                continue
        return names
    except Exception as e:
        log.warning("Could not enumerate input devices: %s", e)
        return []
