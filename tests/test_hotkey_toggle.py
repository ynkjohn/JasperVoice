"""Test toggle mode in HotkeyListener."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import time

import pytest
pytest.importorskip("PySide6")

from jaspervoice.hotkey import HotkeyListener


class Evt:
    def __init__(self, n, t):
        self.name = n
        self.event_type = t


def test_toggle_first_long_press_emits_press(qapp):
    events = []
    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        on_cancel=lambda: events.append("cancel"),
        debounce_ms=0,
        hotkey_mode="toggle",
    )
    hk._running = True
    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    hk._on_event(Evt("space", "up"))
    hk._on_event(Evt("ctrl", "up"))
    qapp.processEvents()
    assert "press" in events
    assert "release" not in events
    assert hk._toggle_active is True


def test_toggle_second_long_press_emits_release(qapp):
    events = []
    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        on_cancel=lambda: events.append("cancel"),
        debounce_ms=0,
        hotkey_mode="toggle",
    )
    hk._running = True
    # First tap
    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    hk._on_event(Evt("space", "up"))
    hk._on_event(Evt("ctrl", "up"))
    qapp.processEvents()
    # Second tap
    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    hk._on_event(Evt("space", "up"))
    hk._on_event(Evt("ctrl", "up"))
    qapp.processEvents()
    assert events.count("press") == 1
    assert events.count("release") == 1
    assert hk._toggle_active is False


def test_toggle_short_tap_emits_cancel(qapp):
    events = []
    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        on_cancel=lambda: events.append("cancel"),
        debounce_ms=1000,
        hotkey_mode="toggle",
    )
    hk._running = True
    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    time.sleep(0.05)
    hk._on_event(Evt("space", "up"))
    hk._on_event(Evt("ctrl", "up"))
    qapp.processEvents()
    assert "cancel" in events
    assert "press" not in events
    assert "release" not in events
    assert hk._toggle_active is False


def test_toggle_stops_resets_state(qapp):
    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: None,
        on_release=lambda: None,
        hotkey_mode="toggle",
    )
    hk._running = True
    hk._toggle_active = True
    hk.stop()
    assert hk._toggle_active is False
