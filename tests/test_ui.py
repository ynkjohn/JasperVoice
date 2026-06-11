"""Tests for the settings window."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import pytest
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from jaspervoice.config import DEFAULT_CONFIG
from jaspervoice.ui import (
    SettingsWindow,
    keyboard_to_qt,
    qt_to_keyboard,
)


@pytest.fixture
def default_cfg():
    return copy.deepcopy(DEFAULT_CONFIG)


# --- Hotkey conversion ---

def test_keyboard_to_qt_basic():
    seq = keyboard_to_qt("ctrl+shift+r")
    assert seq.toString() == "Ctrl+Shift+R"


def test_keyboard_to_qt_with_special_tokens():
    assert keyboard_to_qt("ctrl+space").toString() == "Ctrl+Space"
    assert keyboard_to_qt("pgup").toString() == "PgUp"
    assert keyboard_to_qt("pagedown").toString() == "PgDown"
    assert keyboard_to_qt("alt+f4").toString() == "Alt+F4"
    assert keyboard_to_qt("ctrl+alt+delete").toString() == "Ctrl+Alt+Del"
    assert keyboard_to_qt("shift+tab").toString() == "Shift+Tab"


def test_keyboard_to_qt_empty_returns_empty():
    seq = keyboard_to_qt("")
    assert seq.toString() == ""


def test_qt_to_keyboard_basic():
    assert qt_to_keyboard(QKeySequence("Ctrl+Shift+R")) == "ctrl+shift+r"


def test_qt_to_keyboard_with_special_tokens():
    assert qt_to_keyboard(QKeySequence("Ctrl+Space")) == "ctrl+space"
    assert qt_to_keyboard(QKeySequence("PgUp")) == "pgup"
    assert qt_to_keyboard(QKeySequence("Alt+F4")) == "alt+f4"


def test_qt_to_keyboard_empty():
    assert qt_to_keyboard(QKeySequence()) == ""


def test_roundtrip():
    for original in [
        "ctrl+shift+space",
        "ctrl+alt+r",
        "alt+f12",
        "ctrl+shift+pgup",
    ]:
        assert qt_to_keyboard(keyboard_to_qt(original)) == original


# --- SettingsWindow basics ---

def test_window_title_and_size(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    assert w.windowTitle() == "JasperVoice — Settings"
    assert w.minimumWidth() == 640
    assert w.minimumHeight() == 520


def test_initial_load_marks_clean(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    assert w._dirty is False
    assert not w.apply_btn.isEnabled()


def test_change_marks_dirty_and_enables_apply(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    # Simulate user changing the language combo
    w.lang_combo.setCurrentIndex(1)  # en
    assert w._dirty is True
    assert w.apply_btn.isEnabled()


def test_apply_emits_configChanged_with_new_values(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    received = []
    w.configChanged.connect(lambda c: received.append(c))
    # Change hotkey
    w.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+R"))
    # Change language
    w.lang_combo.setCurrentIndex(1)  # en
    w._on_apply()
    assert len(received) == 1
    cfg = received[0]
    assert cfg["hotkey"] == "ctrl+alt+r"
    assert cfg["language"] == "en"
    # Apply button should be disabled again
    assert w.apply_btn.isEnabled() is False
    assert w._dirty is False


def test_apply_updates_internal_cfg(qapp, default_cfg):
    """After Apply, _cfg must reflect new values (not the old ones)."""
    w = SettingsWindow(default_cfg)
    w.lang_combo.setCurrentIndex(1)  # en
    w._on_apply()
    assert w._cfg["language"] == "en"
    # Cancel after Apply should not revert the applied change
    w._on_cancel()
    assert w.lang_combo.currentData() == "en"


def test_cancel_reverts_changes(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    w.lang_combo.setCurrentIndex(1)  # en
    assert w._dirty is True
    w._on_cancel()
    # Language should be back to pt
    assert w.lang_combo.currentData() == "pt"
    assert w._dirty is False
    assert not w.apply_btn.isEnabled()


def test_closeEvent_hides_instead_of_quits(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    w.show()
    assert w.isVisible()
    from PySide6.QtGui import QCloseEvent
    ev = QCloseEvent()
    w.closeEvent(ev)
    assert not w.isVisible()
    # Widget still alive (not destroyed)
    assert w is not None


def test_signals_blocked_during_load(qapp, default_cfg):
    """Filling the form on _load_values_into_ui must not mark the form dirty."""
    w = SettingsWindow(default_cfg)
    # Recreate the window with a different cfg to force a load cycle
    new_cfg = copy.deepcopy(default_cfg)
    new_cfg["language"] = "en"
    new_cfg["hotkey"] = "ctrl+alt+r"
    w._cfg = new_cfg
    w._load_values_into_ui()
    assert w._dirty is False
    assert not w.apply_btn.isEnabled()
    assert w.lang_combo.currentData() == "en"
    assert qt_to_keyboard(w.hotkey_edit.keySequence()) == "ctrl+alt+r"


def test_apply_with_empty_hotkey_falls_back_to_default(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    # Clear the hotkey by setting an empty sequence
    w.hotkey_edit.setKeySequence(QKeySequence())
    w._on_apply()
    assert w._cfg["hotkey"] == DEFAULT_CONFIG["hotkey"]


def test_collect_picks_checked_radio(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    w._model_radios["medium"].setChecked(True)
    w._device_radios["cuda"].setChecked(True)
    w._compute_radios["float16"].setChecked(True)
    collected = w._collect_values()
    assert collected["model_size"] == "medium"
    assert collected["device"] == "cuda"
    assert collected["compute_type"] == "float16"


def test_paste_delay_and_min_recording_in_config(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    w.paste_delay.setValue(80)
    w.min_duration.setValue(350)
    received = []
    w.configChanged.connect(lambda c: received.append(c))
    w._on_apply()
    assert received[0]["paste_delay_ms"] == 80
    assert received[0]["min_recording_ms"] == 350


def test_hotkey_mode_in_collect_values(qapp, default_cfg):
    w = SettingsWindow(default_cfg)
    w.hotkey_mode_combo.setCurrentIndex(1)  # toggle
    collected = w._collect_values()
    assert collected["hotkey_mode"] == "toggle"
