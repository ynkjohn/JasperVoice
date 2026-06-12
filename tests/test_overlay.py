"""Tests for the recording overlay."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from jaspervoice.overlay import (
    RecordingOverlay,
    PILL_IDLE_SIZE,
    PILL_EXPANDED_WIDTH,
    PILL_EXPANDED_HEIGHT,
)


def test_initial_state_is_hidden(qapp):
    o = RecordingOverlay()
    assert o.state() == "idle"
    assert not o.isVisible()
    assert o.windowOpacity() == 0.0


def test_set_state_recording_shows_window(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    assert o.state() == "recording"
    assert o.isVisible()


def test_set_state_processing_shows_window(qapp):
    o = RecordingOverlay()
    o.set_state("processing")
    assert o.isVisible()
    assert o.state() == "processing"


def test_set_state_send_shows_window(qapp):
    o = RecordingOverlay()
    o.set_state("send")
    assert o.isVisible()
    assert o.state() == "send"


def test_set_state_error_shows_window(qapp):
    o = RecordingOverlay()
    o.set_state("error")
    assert o.isVisible()
    assert o.state() == "error"


def test_set_state_idle_hides(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    assert o.isVisible()
    o.set_state("idle")
    # After setting idle, opacity animation triggers hide
    # Force process the animation to completion
    o._opacity_anim.stop()
    o.setWindowOpacity(0.0)
    o._hide_after_fade()
    assert not o.isVisible()


def test_unknown_state_is_ignored(qapp):
    o = RecordingOverlay()
    o.set_state("nonsense")
    assert o.state() == "idle"
    assert not o.isVisible()


def test_left_click_emits_clicked_signal(qapp):
    o = RecordingOverlay()
    received = []
    o.clicked.connect(lambda: received.append("clicked"))
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(24, 24),
        QPointF(24, 24),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    o.mousePressEvent(ev)
    assert received == ["clicked"]


def test_right_click_does_not_emit_clicked(qapp, monkeypatch):
    o = RecordingOverlay()
    received = []
    o.clicked.connect(lambda: received.append("clicked"))
    monkeypatch.setattr(o, "_show_context_menu", lambda pos: None)
    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QMouseEvent
    ev = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPointF(24, 24),
        QPointF(24, 24),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.RightButton,
        Qt.KeyboardModifier.NoModifier,
    )
    o.mousePressEvent(ev)
    assert received == []


def test_initial_size(qapp):
    o = RecordingOverlay()
    assert o.width() == PILL_IDLE_SIZE
    assert o.height() == PILL_IDLE_SIZE


def test_window_flags_frameless_topmost_tool(qapp):
    o = RecordingOverlay()
    flags = o.windowFlags()
    assert bool(flags & Qt.WindowType.FramelessWindowHint)
    assert bool(flags & Qt.WindowType.WindowStaysOnTopHint)
    assert bool(flags & Qt.WindowType.Tool)


def test_frame_timer_starts_on_active_state(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    assert o._frame_timer.isActive()


def test_frame_timer_stops_on_idle(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    assert o._frame_timer.isActive()
    o.set_state("idle")
    assert not o._frame_timer.isActive()


def test_frame_timer_is_child_of_overlay(qapp):
    o = RecordingOverlay()
    assert o._frame_timer is not None
    assert o._frame_timer.parent() is o
    assert not o._frame_timer.isActive()


def test_settings_requested_signal_exists(qapp):
    o = RecordingOverlay()
    received = []
    o.settings_requested.connect(lambda: received.append("settings"))
    o.settings_requested.emit()
    assert received == ["settings"]


def test_set_state_recording_expands_overlay(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    # The width animation targets PILL_EXPANDED_WIDTH
    assert o._width_anim.endValue() == float(PILL_EXPANDED_WIDTH)


def test_set_state_idle_collapses_overlay(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    o.set_state("idle")
    assert o._width_anim.endValue() == float(PILL_IDLE_SIZE)


def test_levels_updated_signal(qapp):
    o = RecordingOverlay()
    o.set_state("recording")
    o.levels_updated.emit([0.1, 0.3, 0.5, 0.7, 0.4])
    qapp.processEvents()
    assert len(o._levels) == 5


def test_recording_bars_track_real_levels(qapp):
    """High audio levels must drive taller bars than near-silent levels.

    Guards the (previously dead) FFT -> levels_updated -> bar-height pipeline:
    _on_frame must read self._levels during recording, not just synthetic sine.
    """
    from jaspervoice.overlay import BAR_MIN_HEIGHT, NUM_BANDS

    o = RecordingOverlay()
    o.set_state("recording")

    # Feed loud levels and settle the smoothing for several frames.
    o.levels_updated.emit([1.0] * NUM_BANDS)
    qapp.processEvents()
    for _ in range(40):
        o._on_frame()
    loud = list(o._bar_heights)

    # Now feed silence and settle again.
    o.levels_updated.emit([0.0] * NUM_BANDS)
    qapp.processEvents()
    for _ in range(40):
        o._on_frame()
    quiet = list(o._bar_heights)

    assert max(loud) > max(quiet)
    assert max(loud) > BAR_MIN_HEIGHT + 1.0


def test_recording_resets_stale_levels(qapp):
    """Starting a new recording clears band levels from the previous take."""
    from jaspervoice.overlay import NUM_BANDS

    o = RecordingOverlay()
    o.set_state("recording")
    o.levels_updated.emit([0.9] * NUM_BANDS)
    qapp.processEvents()
    o.set_state("idle")
    o.set_state("recording")
    assert o._levels == [0.0] * NUM_BANDS
