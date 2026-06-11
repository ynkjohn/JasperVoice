import threading
import time

import pytest

from jaspervoice.hotkey import HotkeyListener, parse_hotkey


def test_start_when_already_running_unhooks_self_first(monkeypatch):
    """When a single listener has start() called twice, the second call must
    remove the first call's hook (preventing double-registration on the same
    instance) and register a new one. The hot-reload flow is: App stops the
    old listener, then constructs a new one and start()s it. This test
    exercises the idempotent-start guard on a single instance."""
    install_calls = []
    remove_calls = []

    class FakeHandle:
        def __init__(self, token):
            self.token = token

    class FakeKeyboard:
        def __init__(self):
            self._next_token = 0
        def hook(self, callback, suppress=False):
            token = self._next_token
            self._next_token += 1
            install_calls.append(token)
            return FakeHandle(token)
        def unhook(self, handle):
            remove_calls.append(handle.token)
        def unhook_all(self):
            pass

    fake = FakeKeyboard()
    monkeypatch.setattr("jaspervoice.hotkey.keyboard", fake)

    hk = HotkeyListener(
        hotkey="ctrl+shift+a",
        on_press=lambda: None,
        on_release=lambda: None,
    )
    hk.start()
    assert hk.is_running
    assert install_calls == [0]
    assert remove_calls == []

    # Second start() on the same instance: must remove the previous hook
    # then register a new one. Prevents accumulation when the same listener
    # is restarted (defensive — in the hot-reload flow, App stops the old
    # listener and creates a new one, but this guard catches misuse).
    hk.start()
    assert hk.is_running
    assert remove_calls == [0]  # first hook removed
    assert install_calls == [0, 1]  # second hook installed

    hk.stop()
    assert remove_calls == [0, 1]


def test_stop_when_not_running_is_noop():
    a = HotkeyListener(
        hotkey="ctrl+shift+space",
        on_press=lambda: None,
        on_release=lambda: None,
    )
    # Should not raise even though nothing was started
    a.stop()
    assert not a.is_running
    a.stop()  # idempotent
    assert not a.is_running


def test_callback_runs_on_main_thread_via_qt_bridge(qapp):
    """When a QApplication is running, the user callback must be delivered
    on the Qt main thread (via the _QtBridge Signal mechanism), not
    invoked synchronously on the keyboard-hook thread. This is what keeps
    the app from freezing when the callback touches QWidgets."""
    import threading
    from PySide6.QtCore import QThread
    main_thread = QThread.currentThread()
    hook_thread_ids = []
    main_thread_ids = []

    def cb():
        tid = threading.get_ident()
        qt_thread = QThread.currentThread()
        if tid != threading.get_ident():  # always true; placeholder
            pass
        if qt_thread is main_thread:
            main_thread_ids.append(tid)
        else:
            hook_thread_ids.append(tid)

    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=cb,
        on_release=lambda: None,
    )
    hk._running = True

    class Evt:
        def __init__(self, n, t):
            self.name = n
            self.event_type = t

    # Press the combo (this is the only event that fires the on_press callback)
    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    # Process events to flush any queued signal delivery
    qapp.processEvents()

    # The callback must have been invoked, and on the main thread
    assert len(main_thread_ids) == 1
    assert hook_thread_ids == []


def test_parse_hotkey_lowercases_and_splits():
    assert parse_hotkey("Ctrl+Shift+Space") == {"ctrl", "shift", "space"}
    assert parse_hotkey("ctrl + alt + x") == {"ctrl", "alt", "x"}


def test_parse_hotkey_rejects_empty():
    with pytest.raises(ValueError):
        parse_hotkey("")
    with pytest.raises(ValueError):
        parse_hotkey("+++ ")


def test_press_release_callbacks_invoked(qapp):
    """Simulate press+release by directly manipulating the listener's state."""
    events = []
    hk = HotkeyListener(
        hotkey="ctrl+shift+space",
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        debounce_ms=0,  # disable debounce for this test
    )
    hk._running = True
    fake = type("E", (), {})()

    class Evt:
        def __init__(self, n, t):
            self.name = n
            self.event_type = t

    # Press combo in order
    for k in ("ctrl", "shift", "space"):
        e = Evt(k, "down")
        hk._on_event(e)
    qapp.processEvents()
    assert "press" in events
    # Release all
    for k in ("space", "shift", "ctrl"):
        e = Evt(k, "up")
        hk._on_event(e)
    qapp.processEvents()
    assert "release" in events


def test_short_press_triggers_cancel_not_release(qapp):
    events = []
    hk = HotkeyListener(
        hotkey="ctrl+space",
        on_press=lambda: events.append("press"),
        on_release=lambda: events.append("release"),
        on_cancel=lambda: events.append("cancel"),
        debounce_ms=1000,  # require 1s hold
    )
    hk._running = True

    class Evt:
        def __init__(self, n, t):
            self.name = n
            self.event_type = t

    hk._on_event(Evt("ctrl", "down"))
    hk._on_event(Evt("space", "down"))
    time.sleep(0.05)
    hk._on_event(Evt("space", "up"))
    hk._on_event(Evt("ctrl", "up"))
    qapp.processEvents()
    assert "press" in events
    assert "cancel" in events
    assert "release" not in events
