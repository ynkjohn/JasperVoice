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
from typing import Optional

from PySide6.QtCore import QObject, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QIcon,
    QKeySequence,
    QLinearGradient,
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


# --- Languages ---

LANGUAGES = [
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("auto", "Auto-detect"),
]


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
    p.drawRoundedRect(QRectF(4.2, 4.2, 7.6, 7.6), 1.2, 1.2)
    p.drawRect(QRectF(6.7, 6.7, 2.6, 2.6))
    for c in (5.8, 8.0, 10.2):
        p.drawLine(QPointF(c, 1.6), QPointF(c, 4.2))
        p.drawLine(QPointF(c, 11.8), QPointF(c, 14.4))
        p.drawLine(QPointF(1.6, c), QPointF(4.2, c))
        p.drawLine(QPointF(11.8, c), QPointF(14.4, c))


def _draw_spark(p: QPainter) -> None:
    path = QPainterPath(QPointF(8, 1.8))
    for x, y in ((9.6, 6.4), (14.2, 8), (9.6, 9.6), (8, 14.2), (6.4, 9.6), (1.8, 8), (6.4, 6.4)):
        path.lineTo(x, y)
    path.closeSubpath()
    p.drawPath(path)


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
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(3)
        lbl = QLabel(label)
        lbl.setProperty("role", "fieldlabel")
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
            p.setPen(QPen(QColor(COLORS["accent"]), 1, Qt.PenStyle.DotLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(track.adjusted(-0.5, -0.5, 0.5, 0.5), radius, radius)
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

METER_BARS = 28


class LevelMeter(QWidget):
    """Live input meter painted as a mirrored waveform: rounded bars extend
    up and down from the vertical center, tinted toward the accent color as
    the level rises, with slow-falling peak markers.

    Call set_levels() (on the UI thread, via a queued Signal) with per-band
    magnitudes in [0..1]; bars decay toward silence between updates.
    """

    def __init__(self, parent: Optional[QWidget] = None, bar_count: int = METER_BARS):
        super().__init__(parent)
        self._bars = [0.0] * bar_count
        self._peaks = [0.0] * bar_count
        self._active = True
        self.setMinimumHeight(76)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_active(self, active: bool) -> None:
        self._active = active
        if not active:
            self._bars = [0.0] * len(self._bars)
            self._peaks = [0.0] * len(self._peaks)
        self.update()

    def is_active(self) -> bool:
        return self._active

    def set_levels(self, bands: list) -> None:
        if not self._active or not bands:
            return
        n = len(self._bars)
        src = len(bands)
        for i in range(n):
            # Spread the (few) FFT bands across the (many) visual bars,
            # mirrored around the middle so the shape reads as a waveform.
            mirrored = i if i < n // 2 else n - 1 - i
            v = float(bands[min(int(mirrored * 2 * src / n), src - 1)])
            v = max(0.0, min(v, 1.0))
            # Fast attack, slow decay; peaks fall even slower.
            self._bars[i] = v if v > self._bars[i] else self._bars[i] * 0.78
            self._peaks[i] = max(self._bars[i], self._peaks[i] * 0.95)
        self.update()

    @staticmethod
    def _lerp(c1: QColor, c2: QColor, t: float) -> QColor:
        return QColor(
            int(c1.red() + (c2.red() - c1.red()) * t),
            int(c1.green() + (c2.green() - c1.green()) * t),
            int(c1.blue() + (c2.blue() - c1.blue()) * t),
        )

    def paintEvent(self, event) -> None:  # noqa: ARG002, N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # Recessed rounded background with a soft top-to-bottom gradient.
        bg_path = QPainterPath()
        bg_path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 8, 8)
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#0B0B0B"))
        grad.setColorAt(1.0, QColor("#121212"))
        p.fillPath(bg_path, grad)
        p.setPen(QPen(QColor(COLORS["border"]), 1))
        p.drawPath(bg_path)

        n = len(self._bars)
        gap = 3.0
        bar_w = max(2.0, (w - 24 - gap * (n - 1)) / n)
        cy = h / 2.0
        max_half = h / 2.0 - 12
        quiet = QColor(COLORS["border_strong"])
        accent = QColor(COLORS["accent"])
        bright = QColor(COLORS["accent_hover"])

        # Faint center baseline so silence still reads as "alive".
        p.setPen(QPen(QColor(255, 255, 255, 16), 1))
        p.drawLine(QPointF(12, cy), QPointF(w - 12, cy))

        p.setPen(Qt.PenStyle.NoPen)
        x = 12.0
        for i in range(n):
            v = self._bars[i] if self._active else 0.0
            half = max(1.5, v * max_half)
            color = self._lerp(quiet, accent, min(1.0, v * 1.6)) if self._active else quiet
            p.setBrush(color)
            p.drawRoundedRect(QRectF(x, cy - half, bar_w, half * 2), bar_w / 2, bar_w / 2)
            peak = self._peaks[i] if self._active else 0.0
            if peak > 0.12 and peak > v + 0.05:
                p.setBrush(bright)
                py = cy - peak * max_half
                p.drawRoundedRect(QRectF(x, py - 1, bar_w, 2), 1, 1)
            x += bar_w + gap

        if not self._active:
            p.setPen(QPen(QColor(COLORS["fg_muted"])))
            p.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "Meter paused — press Resume")
        p.end()


class MicLevelSource(QObject):
    """Opens its own sounddevice InputStream for the mic-check meters.

    The PortAudio callback runs on an audio thread; it only emits the
    `levels` Signal — every connected widget must use a queued connection
    (automatic for cross-thread connections) so painting stays on the UI
    thread. Completely independent from the dictation Recorder.
    """

    levels = Signal(list)
    error = Signal(str)

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._stream = None

    @property
    def is_running(self) -> bool:
        return self._stream is not None

    def start(self, device: Optional[str] = None) -> None:
        if self._stream is not None:
            return
        try:
            import sounddevice as sd

            from .audio import Recorder

            dev = None if device in (None, "", "default") else device

            def _callback(indata, frames, time_info, status) -> None:  # noqa: ARG001
                try:
                    audio = indata.reshape(-1)
                    bands = Recorder._compute_bands(audio, 16000)
                    self.levels.emit(bands)
                except Exception:
                    pass  # never raise inside the audio callback

            self._stream = sd.InputStream(
                samplerate=16000, channels=1, dtype="float32",
                device=dev, callback=_callback,
            )
            self._stream.start()
        except Exception as e:
            self._stream = None
            log.warning("Mic meter could not start: %s", e)
            self.error.emit(str(e))

    def stop(self) -> None:
        if self._stream is None:
            return
        try:
            self._stream.stop()
            self._stream.close()
        except Exception:
            pass
        self._stream = None


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
        box.setContentsMargins(20, 16, 20, 16)
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
