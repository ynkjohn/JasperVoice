"""Global push-to-talk hotkey listener backed by the `keyboard` library.

Strategy: use `keyboard.hook` (low-level) so we can implement the
press→release state machine ourselves. This is more flexible than
`keyboard.add_hotkey` for hold-to-talk semantics and for debouncing short taps.

The `keyboard` library may require admin privileges on Windows for the low-level
hook to install. We surface that as a logged error but do not crash the app —
the user can still use the tray menu to quit.

Threading model
---------------
`keyboard.hook` invokes its callback on the OS's low-level hook thread, NOT
on the main thread and NOT on any Qt thread. If the user's callbacks touch
Qt widgets (e.g. show a QWidget, start a QTimer, set window opacity), this
triggers cross-thread access to QObjects, which Qt forbids and which manifests
as a frozen app on Windows.

The fix is to route user callbacks through a Qt `Signal` living on a QObject
that was constructed on the Qt main thread. Qt delivers signals across threads
via a queued connection, which is reliable (no event coalescing) and
guarantees the slot runs on the main thread. A previous attempt used
`QTimer.singleShot(0, fn)`, which proved unreliable under load and made the
hotkey feel dead.

The state-machine bookkeeping in this class is thread-safe (lock-guarded)
regardless.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

import keyboard

log = logging.getLogger(__name__)

DEFAULT_DEBOUNCE_MS = 200


def parse_hotkey(hk: str) -> set[str]:
    """Normalize a `keyboard`-style hotkey string into the set of scan names."""
    if not hk:
        raise ValueError("Empty hotkey")
    parts = [p.strip().lower() for p in hk.split("+") if p.strip()]
    if not parts:
        raise ValueError("Empty hotkey")
    return set(parts)


try:
    from PySide6.QtCore import QObject, Signal
    HAS_QT = True
except ImportError:
    HAS_QT = False
    QObject = object  # type: ignore
    Signal = None     # type: ignore


if HAS_QT:
    class _QtBridge(QObject):
        """QObject that lives on the Qt main thread. Emits signals when the
        keyboard hook detects events. Connecting user callbacks to these
        signals (auto, default connection = QueuedConnection across threads)
        ensures the callbacks run on the Qt main thread."""

        pressed = Signal()
        released = Signal()
        cancelled = Signal()
else:
    class _QtBridge:  # type: ignore[no-redef]
        """Stand-in bridge when Qt is not available. Behaves as a thread-safe
        synchronous dispatcher; tests can still drive the state machine."""

        def __init__(self) -> None:
            self._on_press: Optional[Callable[[], None]] = None
            self._on_release: Optional[Callable[[], None]] = None
            self._on_cancel: Optional[Callable[[], None]] = None

        def wire(self, on_press, on_release, on_cancel) -> None:
            self._on_press = on_press
            self._on_release = on_release
            self._on_cancel = on_cancel

        def _invoke(self, which: str) -> None:
            fn = {
                "press": self._on_press,
                "release": self._on_release,
                "cancel": self._on_cancel,
            }.get(which)
            if fn is not None:
                try:
                    fn()
                except Exception:
                    log.exception("Bridge callback %s raised", which)


class HotkeyListener:
    """PTT listener. Calls `on_press()` when combo is fully held, `on_release()`
    after the combo is released and the debounce window has passed.

    Debounce: presses shorter than `debounce_ms` are reported via `on_cancel()`
    (or silently dropped if None) without invoking `on_press`/`on_release`.
    """

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
        on_cancel: Optional[Callable[[], None]] = None,
        debounce_ms: int = DEFAULT_DEBOUNCE_MS,
        hotkey_mode: str = "push_to_talk",
    ):
        self._hotkey_str = hotkey
        self._combo = parse_hotkey(hotkey)
        self._on_press = on_press
        self._on_release = on_release
        self._on_cancel = on_cancel
        self._debounce_s = max(0, debounce_ms) / 1000.0
        self._mode = hotkey_mode

        self._held: set[str] = set()
        self._combo_active = False
        self._press_time: Optional[float] = None
        self._toggle_active = False
        self._lock = threading.Lock()
        self._hook_handle = None
        self._running = False

        # Build the cross-thread bridge. If Qt is available, the bridge is
        # a real QObject and the user callbacks are connected to its signals
        # (auto = QueuedConnection across threads). Otherwise we fall back to
        # the thread-safe stub above.
        if HAS_QT:
            self._bridge = _QtBridge()
            # The bridge QObject lives on whichever thread constructed it.
            # We require construction on the Qt main thread because the
            # signal-slot delivery depends on Qt's event loop running there.
            from PySide6.QtCore import QThread, QCoreApplication
            from PySide6.QtWidgets import QApplication
            app = QApplication.instance()
            if app is not None and QThread.currentThread() is not app.thread():
                # Move bridge to main thread. Slots connected to its signals
                # will then be invoked on the main thread.
                self._bridge.moveToThread(app.thread())
            self._bridge.pressed.connect(self._safe(self._on_press))
            self._bridge.released.connect(self._safe(self._on_release))
            if self._on_cancel is not None:
                self._bridge.cancelled.connect(self._safe(self._on_cancel))
        else:
            self._bridge = _QtBridge()
            self._bridge.wire(
                self._safe(self._on_press),
                self._safe(self._on_release),
                self._safe(self._on_cancel) if self._on_cancel else None,
            )

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def combo(self) -> set[str]:
        return set(self._combo)

    @staticmethod
    def _safe(fn: Callable[[], None]) -> Callable[[], None]:
        def wrapper() -> None:
            try:
                fn()
            except Exception:
                log.exception("Hotkey callback raised")
        return wrapper

    def _on_event(self, event: "keyboard.KeyboardEvent") -> None:
        if not self._running:
            return
        if event.name is None:
            return
        name = event.name.lower()
        # Decide which signal to emit, on the hook thread. The signal-slot
        # mechanism then marshals the call onto the Qt main thread (auto
        # connection, QueuedConnection for cross-thread).
        action: Optional[str] = None
        with self._lock:
            if event.event_type == "down":
                self._held.add(name)
                if not self._combo_active and self._combo.issubset(self._held):
                    self._combo_active = True
                    self._press_time = time.monotonic()
                    if self._mode == "push_to_talk":
                        # PTT: emit press immediately on combo-down for
                        # responsiveness; release fires on key-up.
                        action = "press"
                    # Toggle: defer the decision to key-up so a short tap can
                    # be reported as a cancel instead of toggling state.
            elif event.event_type == "up":
                self._held.discard(name)
                if self._combo_active and not self._combo.issubset(self._held):
                    self._combo_active = False
                    press_time = self._press_time
                    self._press_time = None
                    held_for = (time.monotonic() - press_time) if press_time else 0.0
                    if held_for < self._debounce_s:
                        action = "cancel"
                    elif self._mode == "toggle":
                        # First long press → toggle ON (start recording),
                        # second long press → toggle OFF (stop recording).
                        if not self._toggle_active:
                            self._toggle_active = True
                            action = "press"
                        else:
                            self._toggle_active = False
                            action = "release"
                    else:
                        action = "release"
        if action is None:
            return
        if HAS_QT:
            if action == "press":
                self._bridge.pressed.emit()
            elif action == "release":
                self._bridge.released.emit()
            elif action == "cancel":
                self._bridge.cancelled.emit()
        else:
            self._bridge._invoke(action)

    def start(self) -> None:
        # Idempotent: if a hook is already registered, unregister it first.
        if self._running:
            self.stop()
        try:
            self._hook_handle = keyboard.hook(self._on_event, suppress=False)
            self._running = True
            log.info("Hotkey listener started for %s", self._hotkey_str)
        except Exception as e:
            self._running = False
            self._hook_handle = None
            log.error(
                "Failed to install global keyboard hook. "
                "On Windows, try running the app as administrator. Error: %s",
                e,
            )
            raise

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        try:
            if self._hook_handle is not None:
                keyboard.unhook(self._hook_handle)
                self._hook_handle = None
        except Exception as e:
            log.warning("Error removing specific hook: %s", e)
        with self._lock:
            self._held.clear()
            self._combo_active = False
            self._press_time = None
            self._toggle_active = False
        log.info("Hotkey listener stopped")
