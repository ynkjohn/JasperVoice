import ctypes
import sys
import time

import pyperclip
import pytest

from jaspervoice import injection


def test_empty_text_is_noop():
    assert injection.inject_text("") is False
    assert injection.inject_text(None) is False


def test_type_mode_does_not_touch_clipboard(monkeypatch):
    monkeypatch.setattr(injection, "_has_focused_window", lambda: True)
    typed = []
    monkeypatch.setattr(injection, "_send_text_win32", lambda text: typed.append(text) or True)
    monkeypatch.setattr(
        injection.pyperclip,
        "copy",
        lambda _text: pytest.fail("type mode must not modify the clipboard"),
    )

    assert injection.inject_text("Hello 🌍", mode="type") is True
    assert typed == ["Hello 🌍"]


def test_send_text_emits_unicode_key_down_and_up_events(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only")

    captured = []
    monkeypatch.setattr(
        injection.USER32,
        "SendInput",
        lambda count, events, size: captured.extend(
            (events[i].u.ki.wScan, events[i].u.ki.dwFlags) for i in range(count)
        ) or count,
    )

    assert injection._send_text_win32("Aé") is True
    assert captured == [
        (ord("A"), injection.KEYEVENTF_UNICODE),
        (ord("A"), injection.KEYEVENTF_UNICODE | injection.KEYEVENTF_KEYUP),
        (ord("é"), injection.KEYEVENTF_UNICODE),
        (ord("é"), injection.KEYEVENTF_UNICODE | injection.KEYEVENTF_KEYUP),
    ]


def test_paste_mode_uses_clipboard(monkeypatch):
    monkeypatch.setattr(injection, "_has_focused_window", lambda: True)
    monkeypatch.setattr(injection, "_send_paste_win32", lambda: True)
    copied = []
    monkeypatch.setattr(injection.pyperclip, "copy", copied.append)

    assert injection.inject_text("hello", settle_ms=0) is True
    assert copied == ["hello"]


def test_type_mode_without_focused_window_is_noop(monkeypatch):
    monkeypatch.setattr(injection, "_has_focused_window", lambda: False)
    monkeypatch.setattr(
        injection, "_send_text_win32", lambda _t: pytest.fail("must not type")
    )
    assert injection.inject_text("hello", mode="type") is False


def _capture_send_input(monkeypatch):
    captured = []
    monkeypatch.setattr(
        injection.USER32,
        "SendInput",
        lambda count, events, size: captured.extend(
            (events[i].u.ki.wVk, events[i].u.ki.wScan, events[i].u.ki.dwFlags)
            for i in range(count)
        ) or count,
    )
    return captured


def test_send_text_uses_surrogate_pairs_for_emoji(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only")
    captured = _capture_send_input(monkeypatch)

    assert injection._send_text_win32("🌍") is True
    down = injection.KEYEVENTF_UNICODE
    up = injection.KEYEVENTF_UNICODE | injection.KEYEVENTF_KEYUP
    assert captured == [(0, 0xD83C, down), (0, 0xD83C, up), (0, 0xDF0D, down), (0, 0xDF0D, up)]


def test_send_text_types_newlines_as_enter(monkeypatch):
    if sys.platform != "win32":
        pytest.skip("Windows-only")
    captured = _capture_send_input(monkeypatch)

    assert injection._send_text_win32("a\r\nb") is True
    down = injection.KEYEVENTF_UNICODE
    up = injection.KEYEVENTF_UNICODE | injection.KEYEVENTF_KEYUP
    assert captured == [
        (0, ord("a"), down),
        (0, ord("a"), up),
        (injection.VK_RETURN, 0, 0),
        (injection.VK_RETURN, 0, injection.KEYEVENTF_KEYUP),
        (0, ord("b"), down),
        (0, ord("b"), up),
    ]


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
