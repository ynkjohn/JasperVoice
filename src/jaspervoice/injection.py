"""Inject text into the focused window by pasting or Unicode typing.

The INPUT struct must match the exact layout that the Windows API expects:
  - 32-bit: sizeof(INPUT) == 28
  - 64-bit: sizeof(INPUT) == 40

The 64-bit size is larger because ULONG_PTR becomes 8 bytes and the union
(anchored by MOUSEINPUT which contains ULONG_PTR) forces 8-byte alignment
with 4 bytes of padding after the DWORD `type` field.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
from ctypes import wintypes

import pyperclip

log = logging.getLogger(__name__)

USER32 = ctypes.WinDLL("user32", use_last_error=True)

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
VK_RETURN = 0x0D
INPUT_KEYBOARD = 1

if sys.platform == "win32":
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        ULONG_PTR = ctypes.c_ulonglong
    else:
        ULONG_PTR = wintypes.ULONG

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ULONG_PTR),
        ]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD),
            ("wParamH", wintypes.WORD),
        ]

    class INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
            ("hi", HARDWAREINPUT),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("u", INPUT_UNION),
        ]

    # Configure ctypes signatures once at import time (hot path: avoid
    # reassigning these on every paste).
    USER32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    USER32.SendInput.restype = wintypes.UINT
    USER32.GetForegroundWindow.argtypes = []
    USER32.GetForegroundWindow.restype = wintypes.HWND

else:
    ULONG_PTR = None  # type: ignore
    MOUSEINPUT = None  # type: ignore
    KEYBDINPUT = None  # type: ignore
    HARDWAREINPUT = None  # type: ignore
    INPUT_UNION = None  # type: ignore
    INPUT = None  # type: ignore


def _send_paste_win32() -> bool:
    if not sys.platform == "win32":
        return False
    if INPUT is None:
        return False
    n_inputs = 4
    arr = (INPUT * n_inputs)()
    arr[0].type = INPUT_KEYBOARD
    arr[0].u.ki.wVk = VK_CONTROL
    arr[0].u.ki.dwFlags = 0
    arr[1].type = INPUT_KEYBOARD
    arr[1].u.ki.wVk = VK_V
    arr[1].u.ki.dwFlags = 0
    arr[2].type = INPUT_KEYBOARD
    arr[2].u.ki.wVk = VK_V
    arr[2].u.ki.dwFlags = KEYEVENTF_KEYUP
    arr[3].type = INPUT_KEYBOARD
    arr[3].u.ki.wVk = VK_CONTROL
    arr[3].u.ki.dwFlags = KEYEVENTF_KEYUP
    sent = USER32.SendInput(n_inputs, arr, ctypes.sizeof(INPUT))
    if sent != n_inputs:
        err = ctypes.get_last_error()
        log.warning("SendInput delivered %d/%d events (last error: %d)", sent, n_inputs, err)
    return sent == n_inputs


def _send_text_win32(text: str) -> bool:
    """Type Unicode text with SendInput without reading or writing the clipboard."""
    if INPUT is None:
        return False
    # Line breaks are sent as real Enter key presses: many apps ignore a
    # Unicode "\n" character event.
    events: list[tuple[int, int, int]] = []  # (wVk, wScan, dwFlags)
    for line_no, line in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n")):
        if line_no:
            events.append((VK_RETURN, 0, 0))
            events.append((VK_RETURN, 0, KEYEVENTF_KEYUP))
        units = line.encode("utf-16-le")
        for i in range(0, len(units), 2):
            unit = int.from_bytes(units[i:i + 2], "little")
            events.append((0, unit, KEYEVENTF_UNICODE))
            events.append((0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    if not events:
        return False
    arr = (INPUT * len(events))()
    for ev, (vk, scan, flags) in zip(arr, events):
        ev.type = INPUT_KEYBOARD
        ev.u.ki.wVk = vk
        ev.u.ki.wScan = scan
        ev.u.ki.dwFlags = flags
    sent = USER32.SendInput(len(arr), arr, ctypes.sizeof(INPUT))
    if sent != len(arr):
        err = ctypes.get_last_error()
        log.warning("SendInput delivered %d/%d typing events (last error: %d)", sent, len(arr), err)
    return sent == len(arr)


def foreground_window() -> int | None:
    return USER32.GetForegroundWindow() if sys.platform == "win32" else None


def _has_focused_window() -> bool:
    return bool(foreground_window())


def inject_text(text: str, settle_ms: int = 30, mode: str = "paste") -> bool:
    """Insert text into the focused window using the configured mode.

    Returns True if the keypress was sent. Empty text is a no-op.
    """
    if text is None or text == "":
        return False
    if mode == "type":
        if not _has_focused_window():
            log.debug("No focused window; typing skipped")
            return False
        return _send_text_win32(text)
    pyperclip.copy(text)
    if settle_ms > 0:
        time.sleep(settle_ms / 1000.0)
    if not _has_focused_window():
        log.debug("No focused window; clipboard updated, paste skipped")
        return False
    ok = _send_paste_win32()
    if not ok:
        err = ctypes.get_last_error()
        log.warning("SendInput failed (last error: %d). Text was copied to clipboard.", err)
    return ok
