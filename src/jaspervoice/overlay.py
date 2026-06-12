"""Frameless floating pill indicator that reflects the current pipeline state.

The overlay is a morphing pill anchored to the bottom-right corner of the
primary screen.  In `idle` it is a small 44px circle with a gray dot.
In active states (`recording`, `processing`, `send`) it expands to a rounded
pill with a colored status dot, animated spectrum bars, and a text label.

Left click  → emit `clicked` (caller decides what to do, typically open settings).
Right click → context menu with Settings and Quit.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

from PySide6.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    QSize,
    Qt,
    QTimer,
    Property,
    Signal,
    Slot,
)
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QMenu, QWidget

from .theme import STATE_COLORS

log = logging.getLogger(__name__)

# --- Dimensions tuned for the floating pill indicator ---
PILL_IDLE_SIZE = 44
PILL_EXPANDED_WIDTH = 160
PILL_EXPANDED_HEIGHT = 44
MARGIN_PX = 16

# Spectrum bars
NUM_BANDS = 5
BAR_WIDTH = 3
BAR_GAP = 2
BAR_MAX_HEIGHT = 18
BAR_MIN_HEIGHT = 2

# Animation
EXPAND_DURATION_MS = 400
FADE_DURATION_MS = 150


class RecordingOverlay(QWidget):
    """Floating pill indicator. See module docstring."""

    clicked = Signal()
    settings_requested = Signal()
    quit_requested = Signal()
    levels_updated = Signal(list)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setFixedSize(PILL_IDLE_SIZE, PILL_IDLE_SIZE)
        self.setWindowOpacity(0.0)

        self._state = "idle"
        self._corner = "bottom_right"
        self._pill_width = float(PILL_IDLE_SIZE)
        self._levels = [0.0] * NUM_BANDS
        self._bar_heights = [BAR_MIN_HEIGHT] * NUM_BANDS
        self._time = 0.0
        self._expanded = False

        self.levels_updated.connect(self._on_levels_updated)

        # Width animation (pill expansion)
        self._width_anim = QPropertyAnimation(self, b"pillWidth", self)
        self._width_anim.setDuration(EXPAND_DURATION_MS)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        # Opacity animation. `_hide_after_fade` is connected once here and
        # guards on `self._state` internally, so we never connect/disconnect it
        # per-transition (that stacked duplicate slots and emitted
        # "Failed to disconnect" RuntimeWarnings).
        self._opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._opacity_anim.setDuration(FADE_DURATION_MS)
        self._opacity_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._opacity_anim.finished.connect(self._hide_after_fade)

        # Animation frame timer (60fps for spectrum bars)
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(16)  # ~60fps
        self._frame_timer.timeout.connect(self._on_frame)

        self._position_in_corner()

    # --- Qt Property for animated pill width ---

    def _get_pill_width(self) -> float:
        return self._pill_width

    def _set_pill_width(self, w: float) -> None:
        self._pill_width = w
        self.setFixedSize(int(w), PILL_EXPANDED_HEIGHT if self._expanded else PILL_IDLE_SIZE)
        self._position_in_corner()
        self.update()

    pillWidth = Property(float, _get_pill_width, _set_pill_width)

    # --- Public API ---

    def state(self) -> str:
        return self._state

    def set_position(self, corner: str) -> None:
        """Anchor the pill to a screen corner: top_left, top_right,
        bottom_left, or bottom_right (config key `overlay_position`)."""
        if corner not in ("top_left", "top_right", "bottom_left", "bottom_right"):
            log.warning("Unknown overlay corner %r", corner)
            return
        self._corner = corner
        self._position_in_corner()

    @Slot(list)
    def _on_levels_updated(self, bands: list) -> None:
        if bands:
            self._levels = list(bands[:NUM_BANDS])
            # Pad if fewer bands received
            while len(self._levels) < NUM_BANDS:
                self._levels.append(0.0)

    def set_state(self, state: str) -> None:
        if state not in STATE_COLORS:
            log.warning("Unknown overlay state %r", state)
            return
        if state == self._state and self.isVisible() == (state != "idle"):
            return
        self._state = state

        if state == "idle":
            self._expanded = False
            self._frame_timer.stop()
            # Animate collapse
            self._width_anim.stop()
            self._width_anim.setStartValue(self._pill_width)
            self._width_anim.setEndValue(float(PILL_IDLE_SIZE))
            self._width_anim.start()
            # Fade out
            self._opacity_anim.stop()
            self._opacity_anim.setStartValue(self.windowOpacity())
            self._opacity_anim.setEndValue(0.0)
            self._opacity_anim.start()
        else:
            self._expanded = True
            self._time = 0.0
            # Drop any band levels left over from the previous take so the
            # spectrum starts from silence instead of flashing stale values.
            if state == "recording":
                self._levels = [0.0] * NUM_BANDS
            # Ensure visible
            if not self.isVisible():
                self.setFixedSize(PILL_IDLE_SIZE, PILL_EXPANDED_HEIGHT)
                self._pill_width = float(PILL_IDLE_SIZE)
                self._position_in_corner()
                self.show()
                self.raise_()
            # Fade in
            self._opacity_anim.stop()
            self._opacity_anim.setStartValue(self.windowOpacity())
            self._opacity_anim.setEndValue(1.0)
            self._opacity_anim.start()
            # Expand
            self._width_anim.stop()
            self._width_anim.setStartValue(self._pill_width)
            self._width_anim.setEndValue(float(PILL_EXPANDED_WIDTH))
            self._width_anim.start()
            # Start frame timer for bar animation
            if not self._frame_timer.isActive():
                self._frame_timer.start()
            self.show()
            self.raise_()
            self.update()

    def _hide_after_fade(self) -> None:
        if self._state == "idle":
            self.hide()

    # --- Geometry ---

    def _position_in_corner(self) -> None:
        screen = self.screen() or self._primary_screen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        w = self.width()
        h = self.height()
        if self._corner.endswith("left"):
            x = geom.left() + MARGIN_PX
        else:
            x = geom.right() - w - MARGIN_PX + 1
        if self._corner.startswith("top"):
            y = geom.top() + MARGIN_PX
        else:
            y = geom.bottom() - h - MARGIN_PX + 1
        self.move(QPoint(x, y))

    @staticmethod
    def _primary_screen():
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is None:
            return None
        return app.primaryScreen()

    # --- Animation frame ---

    def _on_frame(self) -> None:
        self._time += 0.016  # ~16ms per frame
        # Compute target bar heights based on state
        for i in range(NUM_BANDS):
            p = (i / NUM_BANDS) * math.pi * 2
            if self._state == "recording":
                # Drive the bars from the REAL per-band audio levels that the
                # recorder computes via FFT (see audio.Recorder._compute_bands)
                # and pushes through `levels_updated`. A small sine shimmer is
                # added so the bars keep a subtle motion during brief silences
                # instead of flat-lining at the minimum height.
                level = self._levels[i] if i < len(self._levels) else 0.0
                shimmer = (math.sin(self._time * 6.0 + p) * 0.5 + 0.5) * 0.12
                amp = min(1.0, level + shimmer)
                target = BAR_MIN_HEIGHT + amp * (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT)
            elif self._state == "processing":
                # Slow pulse
                target = BAR_MIN_HEIGHT + (
                    math.sin(self._time * 1.6 + p) * 0.5 + 0.5
                ) * (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT) * 0.52
            elif self._state == "send":
                # Decay to zero
                d = max(0.0, 1.0 - self._time * 3.0)
                target = BAR_MIN_HEIGHT + d * (BAR_MAX_HEIGHT - BAR_MIN_HEIGHT) * (
                    0.7 + abs(math.sin(p * 2.5)) * 0.3
                )
            else:
                target = BAR_MIN_HEIGHT
            # Smooth interpolation
            self._bar_heights[i] += (target - self._bar_heights[i]) * 0.28
        self.update()

    # --- Painting ---

    def paintEvent(self, event) -> None:  # noqa: ARG002
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, self._pill_width, self.height())
        colors = STATE_COLORS.get(self._state, STATE_COLORS["idle"])

        # Background pill
        bg_color = QColor(colors["fill"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        radius = self.height() / 2.0
        painter.drawRoundedRect(rect, radius, radius)

        # Border
        border_color = QColor(colors["border"])
        pen = QPen(border_color)
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        if self._state == "idle":
            # Draw center dot
            dot_color = QColor(colors["dot"])
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(dot_color)
            cx = rect.width() / 2.0
            cy = rect.height() / 2.0
            painter.drawEllipse(QRectF(cx - 4.5, cy - 4.5, 9, 9))
        elif self._expanded:
            self._paint_expanded(painter, rect, colors)

        painter.end()

    def _paint_expanded(self, painter: QPainter, rect: QRectF, colors: dict) -> None:
        """Draw the expanded pill content: dot + bars + text."""
        padding_left = 12.0
        cy = rect.height() / 2.0

        # Status dot (left side)
        dot_color = QColor(colors["dot"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(dot_color)
        dot_x = padding_left
        dot_r = 3.5
        painter.drawEllipse(QRectF(dot_x - dot_r, cy - dot_r, dot_r * 2, dot_r * 2))

        # Spectrum bars
        bars_x_start = dot_x + dot_r * 2 + 7.0
        bar_color = QColor(colors["dot"])
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(NUM_BANDS):
            h = self._bar_heights[i]
            x = bars_x_start + i * (BAR_WIDTH + BAR_GAP)
            y = cy - h / 2.0
            painter.setBrush(bar_color)
            painter.drawRoundedRect(QRectF(x, y, BAR_WIDTH, h), 1, 1)

        # Text label
        text_label = colors.get("text_label", "")
        if text_label:
            text_x = bars_x_start + NUM_BANDS * (BAR_WIDTH + BAR_GAP) + 6.0
            text_color = QColor(colors.get("text", "#ffffff"))
            font = QFont("Inter, Segoe UI, system-ui, sans-serif", 9)
            font.setPixelSize(11)
            painter.setFont(font)
            painter.setPen(text_color)
            text_rect = QRectF(text_x, 0, rect.width() - text_x - 12, rect.height())
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, text_label)

    # --- Interaction ---

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        elif event.button() == Qt.MouseButton.RightButton:
            self._show_context_menu(event.globalPosition().toPoint())

    def _show_context_menu(self, global_pos: QPoint) -> None:
        menu = QMenu(self)
        settings_act = QAction("Settings...", menu)
        settings_act.triggered.connect(self.settings_requested.emit)
        menu.addAction(settings_act)
        menu.addSeparator()
        quit_act = QAction("Quit", menu)
        quit_act.triggered.connect(self.quit_requested.emit)
        menu.addAction(quit_act)
        menu.exec(global_pos)
