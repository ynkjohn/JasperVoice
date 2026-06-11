"""Inject text into the focused window via clipboard + SendInput Ctrl+V.

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
from typing import Optional

import pyperclip

log = logging.getLogger(__name__)

USER32 = ctypes.WinDLL("user32", use_last_error=True)

VK_CONTROL = 0x11
VK_V = 0x56
KEYEVENTF_KEYUP = 0x0002
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


def _has_focused_window() -> bool:
    if not sys.platform == "win32":
        return False
    hwnd = USER32.GetForegroundWindow()
    return bool(hwnd)


def inject_text(text: str, settle_ms: int = 30) -> bool:
    """Write `text` to the clipboard and trigger Ctrl+V on the focused window.

    Returns True if the keypress was sent. Empty text is a no-op.
    """
    if text is None or text == "":
        return False
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
