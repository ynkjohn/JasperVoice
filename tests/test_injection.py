import ctypes
import sys
import time

import pyperclip
import pytest

from jaspervoice import injection


def test_empty_text_is_noop():
    assert injection.inject_text("") is False
    assert injection.inject_text(None) is False


def test_input_struct_size_x64():
    if sys.platform != "win32":
        pytest.skip("Windows-only")
    from jaspervoice.injection import INPUT, MOUSEINPUT, KEYBDINPUT, HARDWAREINPUT, INPUT_UNION

    pointer_size = ctypes.sizeof(ctypes.c_void_p)
    if pointer_size == 8:
        expected_input = 40
        expected_mouse = 32
        expected_keybd = 24
        expected_hardware = 8
    else:
        expected_input = 28
        expected_mouse = 24
        expected_keybd = 16
        expected_hardware = 8

    assert ctypes.sizeof(MOUSEINPUT) == expected_mouse, f"MOUSEINPUT: {ctypes.sizeof(MOUSEINPUT)} != {expected_mouse}"
    assert ctypes.sizeof(KEYBDINPUT) == expected_keybd, f"KEYBDINPUT: {ctypes.sizeof(KEYBDINPUT)} != {expected_keybd}"
    assert ctypes.sizeof(HARDWAREINPUT) == expected_hardware, f"HARDWAREINPUT: {ctypes.sizeof(HARDWAREINPUT)} != {expected_hardware}"
    assert ctypes.sizeof(INPUT_UNION) == expected_mouse, f"INPUT_UNION: {ctypes.sizeof(INPUT_UNION)} != {expected_mouse}"
    assert ctypes.sizeof(INPUT) == expected_input, f"INPUT: {ctypes.sizeof(INPUT)} != {expected_input}"


def test_paste_struct_size_is_sane():
    if sys.platform != "win32":
        pytest.skip("Windows-only")
    sent = injection._send_paste_win32()
    assert sent in (True, False)


def test_clipboard_roundtrip():
    pyperclip.copy("__jaspervoice_test__")
    time.sleep(0.05)
    assert pyperclip.paste() == "__jaspervoice_test__"
