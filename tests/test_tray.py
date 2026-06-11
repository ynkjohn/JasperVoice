"""Smoke test for the tray icon — uses the offscreen QPA platform."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6", reason="PySide6 required")

from PySide6.QtWidgets import QApplication

from jaspervoice.tray import TrayController


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def test_tray_controller_starts_in_idle(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    t.set_state("idle")
    assert t._status_text.startswith("JasperVoice")


def test_state_transitions_swap_icon(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    t.set_state("recording")
    assert "recording" in t._status_text.lower()
    t.set_state("processing")
    assert "transcrib" in t._status_text.lower()
    t.set_state("error")
    assert "error" in t._status_text.lower()
    t.set_state("idle")


def test_language_change_emits_signal(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    received = []
    t.language_changed.connect(lambda c: received.append(c))
    t._on_language_selected("en")
    assert received == ["en"]
    t._on_language_selected("pt")
    assert received == ["en", "pt"]


def test_unknown_state_is_ignored(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    before = t._state
    t.set_state("nonsense")
    assert t._state == before


def test_settings_requested_signal_exists(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    received = []
    t.settings_requested.connect(lambda: received.append("settings"))
    t.settings_requested.emit()
    assert received == ["settings"]


def test_menu_contains_settings_and_quit_actions(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    t = TrayController(qt_app)
    labels = [a.text() for a in t._menu.actions() if a.text()]
    assert "Settings..." in labels
    assert "Quit" in labels
