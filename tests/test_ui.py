"""Tests for the navigable settings window (shell, pages, search, tables)."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import copy
import json

import pytest
pytest.importorskip("PySide6")

from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import QApplication

from jaspervoice.config import DEFAULT_CONFIG
from jaspervoice.history import TranscriptionHistory
from jaspervoice.ui import (
    SettingsWindow,
    keyboard_to_qt,
    qt_to_keyboard,
)


@pytest.fixture
def default_cfg():
    return copy.deepcopy(DEFAULT_CONFIG)


@pytest.fixture
def appdata(tmp_path, monkeypatch):
    """Redirect %APPDATA% so Apply/persist never touches the real config."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def window(qapp, default_cfg, appdata):
    return SettingsWindow(default_cfg)


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


# --- Shell basics ---

def test_window_title_and_size(window):
    assert window.windowTitle() == "JasperVoice"
    assert window.minimumWidth() == 900
    assert window.minimumHeight() == 600


def test_all_pages_exist(window):
    for pid in ("overview", "history", "dictionary", "general", "audio",
                "model", "polish", "updates", "diagnostics"):
        assert window.page(pid) is not None


def test_initial_load_marks_clean(window):
    assert window._dirty is False
    assert not window.apply_btn.isEnabled()
    assert not window.discard_btn.isEnabled()


def test_navigation_switches_pages(window):
    window.show_page("model")
    assert window.current_page_id() == "model"
    assert window._nav_buttons["model"].property("navActive") is True
    assert window._nav_buttons["overview"].property("navActive") is False
    window.show_page("overview")
    assert window.current_page_id() == "overview"


def test_navigation_unknown_page_is_safe(window):
    window.show_page("nope")
    assert window.current_page_id() == "overview"


def test_closeEvent_hides_instead_of_quits(window):
    window.show()
    assert window.isVisible()
    from PySide6.QtGui import QCloseEvent
    window.closeEvent(QCloseEvent())
    assert not window.isVisible()


# --- Sidebar search ---

def test_search_filters_nav(window):
    # isHidden() reflects setVisible() even while the window itself is not shown.
    window.search_edit.setText("noise gate")
    assert window._nav_buttons["audio"].isHidden() is False
    assert window._nav_buttons["history"].isHidden() is True


def test_search_clear_restores_all(window):
    window.search_edit.setText("noise gate")
    window.search_edit.setText("")
    for btn in window._nav_buttons.values():
        assert btn.isHidden() is False


def test_search_enter_jumps_to_first_match(window):
    window.search_edit.setText("noise gate")
    window._go_to_first_match()
    assert window.current_page_id() == "audio"


def test_search_matches_page_title(window):
    window.search_edit.setText("diagnostics")
    assert window._nav_buttons["diagnostics"].isHidden() is False
    assert window._nav_buttons["general"].isHidden() is True


# --- Dirty / apply / discard ---

def test_change_marks_dirty_and_enables_apply(window):
    window.lang_combo.setCurrentIndex(1)  # en
    assert window._dirty is True
    assert window.apply_btn.isEnabled()
    assert window.discard_btn.isEnabled()


def test_apply_emits_configChanged_with_new_values(window):
    received = []
    window.configChanged.connect(lambda c: received.append(c))
    window.hotkey_edit.setKeySequence(QKeySequence("Ctrl+Alt+R"))
    window.lang_combo.setCurrentIndex(1)  # en
    window._on_apply()
    assert len(received) == 1
    cfg = received[0]
    assert cfg["hotkey"] == "ctrl+alt+r"
    assert cfg["language"] == "en"
    assert window.apply_btn.isEnabled() is False
    assert window._dirty is False


def test_apply_updates_internal_cfg(window):
    window.lang_combo.setCurrentIndex(1)  # en
    window._on_apply()
    assert window._cfg["language"] == "en"
    # Discard after Apply must not revert the applied change
    window._on_discard()
    assert window.lang_combo.currentData() == "en"


def test_discard_reverts_changes(window):
    window.lang_combo.setCurrentIndex(1)  # en
    assert window._dirty is True
    window._on_discard()
    assert window.lang_combo.currentData() == "pt"
    assert window._dirty is False
    assert not window.apply_btn.isEnabled()


def test_load_values_does_not_mark_dirty(window, default_cfg):
    new_cfg = copy.deepcopy(default_cfg)
    new_cfg["language"] = "en"
    new_cfg["hotkey"] = "ctrl+alt+r"
    window.update_config(new_cfg)
    assert window._dirty is False
    assert not window.apply_btn.isEnabled()
    assert window.lang_combo.currentData() == "en"
    assert qt_to_keyboard(window.hotkey_edit.keySequence()) == "ctrl+alt+r"


def test_apply_with_empty_hotkey_falls_back_to_default(window):
    window.hotkey_edit.setKeySequence(QKeySequence())
    window._on_apply()
    assert window._cfg["hotkey"] == DEFAULT_CONFIG["hotkey"]


# --- General / Model / Polish collect ---

def test_collect_picks_selected_model_device_compute(window):
    model_page = window.page("model")
    model_page.select_model("medium")
    model_page.device_seg.set_current_key("cuda")
    model_page.compute_seg.set_current_key("float16")
    collected = window._collect_values()
    assert collected["model_size"] == "medium"
    assert collected["device"] == "cuda"
    assert collected["compute_type"] == "float16"


def test_model_selection_marks_dirty(window):
    window.page("model").select_model("tiny")
    assert window._dirty is True


def test_paste_delay_and_min_recording_in_config(window):
    window.paste_delay.setValue(80)
    window.min_duration.setValue(350)
    received = []
    window.configChanged.connect(lambda c: received.append(c))
    window._on_apply()
    assert received[0]["paste_delay_ms"] == 80
    assert received[0]["min_recording_ms"] == 350


def test_hotkey_mode_in_collect_values(window):
    window.mode_seg.set_current_key("toggle")
    collected = window._collect_values()
    assert collected["hotkey_mode"] == "toggle"


def test_new_general_keys_collect(window):
    page = window.page("general")
    page.launch_login.setChecked(True)
    page.start_minimized.setChecked(False)
    page.show_overlay.setChecked(False)
    page.overlay_pos.set_current_key("top_left")
    collected = window._collect_values()
    assert collected["launch_at_login"] is True
    assert collected["start_minimized"] is False
    assert collected["show_overlay"] is False
    assert collected["overlay_position"] == "top_left"


def test_audio_keys_collect(window):
    page = window.page("audio")
    page.noise_gate.setChecked(True)
    page.sound_feedback.set_current_key("subtle")
    collected = window._collect_values()
    assert collected["noise_gate_enabled"] is True
    assert collected["sound_feedback"] == "subtle"
    assert collected["input_device"] == "default"


def test_warmup_collects(window):
    window.page("model").warmup.setChecked(False)
    assert window._collect_values()["warmup_on_launch"] is False


def test_polish_page_collects(window):
    page = window.page("polish")
    page.enabled.setChecked(True)
    page.provider_combo.setCurrentIndex(1)  # opencode (OpenAI-compatible)
    page.base_url.setText("http://localhost:11434/v1")
    page.api_key_env.setText("MY_KEY_ENV")
    page.fast_model.setEditText("llama3.1:8b")
    page.smart_model.setEditText("qwen2.5:32b")
    page.timeout_spin.setValue(45)
    page.mode_seg.set_current_key("clean")
    collected = window._collect_values()
    assert collected["post_processing_enabled"] is True
    assert collected["post_processing_provider"] == "opencode"
    assert collected["opencode_base_url"] == "http://localhost:11434/v1"
    assert collected["opencode_api_key_env"] == "MY_KEY_ENV"
    assert collected["opencode_fast_model"] == "llama3.1:8b"
    assert collected["opencode_smart_model"] == "qwen2.5:32b"
    assert collected["opencode_timeout_s"] == 45
    assert collected["output_mode"] == "clean"


def test_polish_enable_selects_provider_and_api_mode(window):
    page = window.page("polish")
    page.provider_combo.setCurrentIndex(0)
    page.mode_seg.set_current_key("raw")
    page.enabled.setChecked(True)
    assert page.provider_combo.currentData() == "opencode"
    assert page.mode_seg.current_key() == "clean"


def test_polish_collect_normalizes_enabled_raw_disabled_provider(window):
    page = window.page("polish")
    page.enabled.setChecked(True)
    page.provider_combo.setCurrentIndex(0)
    page.mode_seg.set_current_key("raw")
    collected = window._collect_values()
    assert collected["post_processing_provider"] == "opencode"
    assert collected["output_mode"] == "clean"


def test_polish_api_key_env_blank_falls_back(window):
    window.page("polish").api_key_env.setText("   ")
    assert window._collect_values()["opencode_api_key_env"] == DEFAULT_CONFIG["opencode_api_key_env"]


def test_polish_apply_fetched_models_fills_both_combos(window):
    page = window.page("polish")
    page.fast_model.setEditText("already-typed")
    page._apply_fetched_models(["model-a", "model-b", "model-c"])
    assert [page.fast_model.itemText(i) for i in range(page.fast_model.count())] == \
        ["model-a", "model-b", "model-c"]
    assert [page.smart_model.itemText(i) for i in range(page.smart_model.count())] == \
        ["model-a", "model-b", "model-c"]
    # The user's typed value survives the refresh
    assert page.fast_model.currentText() == "already-typed"
    assert "3 models" in page.fetch_status.text()


def test_polish_fetch_requires_endpoint(window):
    page = window.page("polish")
    page.base_url.setText("")
    page._fetch_models()
    assert "endpoint" in page.fetch_status.text().lower()
    assert page._thread is None  # no worker started


def test_polish_fetch_error_reenables_button(window):
    page = window.page("polish")
    page.fetch_btn.setEnabled(False)
    page._on_fetch_error("connection refused")
    assert page.fetch_btn.isEnabled()
    assert "connection refused" in page.fetch_status.text()


# --- Model & Engine page ---

def test_model_hardware_recommendation_cuda(window):
    page = window.page("model")
    page._apply_hardware({"cuda_devices": 1})
    assert "CUDA" in page.recommend_label.text()
    assert "float16" in page.recommend_label.text()


def test_model_hardware_recommendation_cpu(window):
    page = window.page("model")
    page._apply_hardware({"cuda_devices": 0})
    assert "CPU" in page.recommend_label.text()
    assert "int8" in page.recommend_label.text()


def test_model_actions_reflect_installed_state(window, appdata):
    from jaspervoice.config import get_models_dir
    page = window.page("model")
    page.select_model("small")
    page._refresh_card_states()
    # Not installed: download enabled, delete disabled
    assert page.download_btn.isEnabled()
    assert not page.delete_btn.isEnabled()
    # Create a fake local cache for "small"
    (get_models_dir() / "models--Systran--faster-whisper-small").mkdir(parents=True)
    page._refresh_card_states()
    assert not page.download_btn.isEnabled()
    assert page.delete_btn.isEnabled()
    assert "installed" in page.model_status.text()


def test_model_delete_removes_cache_dir(window, appdata, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from jaspervoice.config import get_models_dir
    target = get_models_dir() / "models--Systran--faster-whisper-small"
    (target / "snapshots").mkdir(parents=True)
    page = window.page("model")
    page.select_model("small")
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    page._delete_selected()
    assert not target.exists()


def test_model_delete_declined_keeps_dir(window, appdata, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from jaspervoice.config import get_models_dir
    target = get_models_dir() / "models--Systran--faster-whisper-small"
    target.mkdir(parents=True)
    page = window.page("model")
    page.select_model("small")
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    page._delete_selected()
    assert target.exists()


# --- Updates page ---

def test_update_settings_in_collect_values(window):
    window.update_check_enabled.setChecked(False)
    window.update_repo_edit.setText("someone/Fork")
    collected = window._collect_values()
    assert collected["update_check_enabled"] is False
    assert collected["update_repo"] == "someone/Fork"


def test_update_repo_blank_falls_back_to_default(window):
    window.update_repo_edit.setText("   ")
    collected = window._collect_values()
    assert collected["update_repo"] == DEFAULT_CONFIG["update_repo"]


def test_updates_page_shows_version(window):
    from jaspervoice import __version__
    assert __version__ in window.page("updates").version_label.text()


# --- Dictionary page ---

def test_dictionary_add_rule_persists(window):
    page = window.page("dictionary")
    received = []
    window.configChanged.connect(lambda c: received.append(c))
    page.phrase_edit.setText("py side")
    page.replacement_edit.setText("PySide6")
    page._add_rule()
    assert window._cfg["dictionary"] == [{"phrase": "py side", "replacement": "PySide6"}]
    assert len(received) == 1
    assert page.table.rowCount() == 1


def test_dictionary_add_requires_both_fields(window):
    page = window.page("dictionary")
    page.phrase_edit.setText("only phrase")
    page.replacement_edit.setText("")
    page._add_rule()
    assert window._cfg["dictionary"] == []
    assert page.table.rowCount() == 0


def test_dictionary_rejects_duplicate_phrase(window):
    page = window.page("dictionary")
    window._cfg["dictionary"] = [{"phrase": "py side", "replacement": "PySide6"}]
    page.refresh()
    page.phrase_edit.setText("PY SIDE")
    page.replacement_edit.setText("Other")
    page._add_rule()
    assert len(window._cfg["dictionary"]) == 1


def test_dictionary_delete_persists(window):
    window._cfg["dictionary"] = [
        {"phrase": "a", "replacement": "A"},
        {"phrase": "b", "replacement": "B"},
    ]
    page = window.page("dictionary")
    page.refresh()
    received = []
    window.configChanged.connect(lambda c: received.append(c))
    page._delete(0)
    assert window._cfg["dictionary"] == [{"phrase": "b", "replacement": "B"}]
    assert len(received) == 1


def test_dictionary_toggle_enabled_persists(window):
    window._cfg["dictionary"] = [{"phrase": "a", "replacement": "A"}]
    page = window.page("dictionary")
    page.refresh()
    page._set_enabled(0, False)
    assert window._cfg["dictionary"][0] == {"phrase": "a", "replacement": "A", "enabled": False}
    page._set_enabled(0, True)
    assert window._cfg["dictionary"][0] == {"phrase": "a", "replacement": "A"}


def test_dictionary_export_import_roundtrip(window, tmp_path, monkeypatch):
    rules = [
        {"phrase": "a", "replacement": "A"},
        {"phrase": "b", "replacement": "B", "enabled": False},
    ]
    window._cfg["dictionary"] = copy.deepcopy(rules)
    page = window.page("dictionary")
    page.refresh()

    out = tmp_path / "dict.json"
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "JSON (*.json)")),
    )
    page._export()
    assert json.loads(out.read_text(encoding="utf-8")) == rules

    window._cfg["dictionary"] = []
    page.refresh()
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QFileDialog.getOpenFileName",
        staticmethod(lambda *a, **k: (str(out), "JSON (*.json)")),
    )
    page._import()
    assert window._cfg["dictionary"] == rules


# --- History page ---

@pytest.fixture
def history(appdata):
    h = TranscriptionHistory()
    h.add("alpha bravo charlie", duration_s=3.0, mode="push_to_talk")
    h.add("delta echo", duration_s=2.0, mode="toggle")
    h.add("foxtrot golf hotel india", duration_s=4.0, mode="push_to_talk")
    return h


@pytest.fixture
def hwindow(qapp, default_cfg, history):
    w = SettingsWindow(default_cfg, history=history)
    w.show_page("history")
    return w


def test_history_table_shows_latest_first(hwindow):
    page = hwindow.page("history")
    assert page.table.rowCount() == 3
    assert page.table.item(0, 1).text() == "foxtrot golf hotel india"
    assert page.table.item(2, 1).text() == "alpha bravo charlie"


def test_history_search_filters(hwindow):
    page = hwindow.page("history")
    page.search_edit.setText("echo")
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "delta echo"
    page.search_edit.setText("")
    assert page.table.rowCount() == 3


def test_history_mode_filter(hwindow):
    page = hwindow.page("history")
    page.mode_seg.set_current_key("toggle")
    assert page.table.rowCount() == 1
    assert page.table.item(0, 1).text() == "delta echo"
    page.mode_seg.set_current_key("all")
    assert page.table.rowCount() == 3


def test_history_copy_row(hwindow):
    page = hwindow.page("history")
    page._copy("delta echo")
    assert QApplication.clipboard().text() == "delta echo"


def test_history_delete_row_persists(hwindow, history):
    page = hwindow.page("history")
    # Row 0 displays the newest entry, which is index 2 in the store.
    page._delete(2)
    assert history.count == 2
    assert page.table.rowCount() == 2
    assert page.table.item(0, 1).text() == "delta echo"
    # Persisted: a fresh instance sees the deletion
    assert TranscriptionHistory().count == 2


def test_history_clear_with_confirmation(hwindow, history, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes),
    )
    hwindow.page("history")._clear()
    assert history.count == 0
    assert hwindow.page("history").table.rowCount() == 0


def test_history_clear_declined_keeps_entries(hwindow, history, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QMessageBox.question",
        staticmethod(lambda *a, **k: QMessageBox.StandardButton.No),
    )
    hwindow.page("history")._clear()
    assert history.count == 3


def test_history_export(hwindow, tmp_path, monkeypatch):
    out = tmp_path / "export.json"
    monkeypatch.setattr(
        "jaspervoice.ui_pages.QFileDialog.getSaveFileName",
        staticmethod(lambda *a, **k: (str(out), "JSON (*.json)")),
    )
    hwindow.page("history")._export()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data) == 3
    assert data[0]["text"] == "alpha bravo charlie"


# --- Overview page ---

def test_overview_tiles_from_history(hwindow):
    page = hwindow.page("overview")
    page.refresh()
    assert page.tile_count.value_label.text() == "3"
    assert page.tile_words.value_label.text() == "9"


def test_overview_test_dictation_emits_signal(window):
    fired = []
    window.testDictationRequested.connect(lambda: fired.append(True))
    window.page("overview")._on_test_clicked()
    assert fired == [True]


def test_show_test_result_updates_label(window):
    window.show_test_result("hello world")
    assert "hello world" in window.page("overview").test_status.text()


def test_overview_pipeline_summary_reflects_cfg(window):
    page = window.page("overview")
    page.refresh()
    assert "whisper small" in page._pipe_values["transcribe"].text()
    assert "Ctrl" in page._pipe_values["trigger"].text()


# --- Diagnostics page ---

def test_diagnostics_self_test_produces_results(hwindow):
    page = hwindow.page("diagnostics")
    page._run_self_test()
    text = page.selftest_label.text()
    assert "Config file" in text
    assert "Models directory" in text
    assert "Injection module" in text


def test_diagnostics_copy_report(hwindow):
    page = hwindow.page("diagnostics")
    page._copy_report()
    report = QApplication.clipboard().text()
    assert "JasperVoice diagnostics report" in report
    assert "[runtime]" in report
    assert "[storage]" in report


def test_diagnostics_runtime_uses_provider(hwindow):
    hwindow.set_runtime_provider(lambda: {"resolved_device": "cuda", "model_loaded": True})
    rows = dict(hwindow.page("diagnostics")._runtime_rows())
    assert "cuda" in rows["Device"]


# --- Status / runtime provider ---

def test_set_app_state_updates_labels(window):
    window.set_app_state("recording")
    assert window._bar_state.text() == "RECORDING"
    window.set_app_state("idle")
    assert window._bar_state.text() == "READY"


def test_runtime_provider_failure_is_safe(window):
    def boom():
        raise RuntimeError("nope")
    window.set_runtime_provider(boom)
    assert window.runtime_info() == {}


def test_summary_shows_model_device_compute(window):
    assert "whisper small" in window._bar_summary.text()
    assert "int8" in window._bar_summary.text()
