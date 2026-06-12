from pathlib import Path
import json

import pytest

from jaspervoice.config import (
    DEFAULT_CONFIG,
    get_config_path,
    load_config,
    save_config,
    get_models_dir,
)


def test_defaults_written_on_first_run(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg == DEFAULT_CONFIG
    assert get_config_path().exists()


def test_loads_existing_valid_config(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"hotkey": "ctrl+alt+x", "language": "en"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey"] == "ctrl+alt+x"
    assert cfg["language"] == "en"
    assert cfg["model_size"] == DEFAULT_CONFIG["model_size"]


def test_malformed_json_resets_with_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text("{not valid json", encoding="utf-8")
    cfg = load_config()
    assert cfg == DEFAULT_CONFIG
    assert p.with_suffix(".json.bak").exists()


def test_invalid_values_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(
        json.dumps(
            {
                "hotkey": "",
                "model_size": "huge",
                "compute_type": "int4",
                "device": "tpu",
                "sample_rate": -1,
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg["hotkey"] == DEFAULT_CONFIG["hotkey"]
    assert cfg["model_size"] == "small"
    assert cfg["compute_type"] == "int8"
    assert cfg["device"] == "auto"
    assert cfg["sample_rate"] == 16000


def test_save_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    save_config({"hotkey": "f1"})
    assert get_config_path().read_text(encoding="utf-8").strip().startswith("{")


def test_update_keys_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["update_check_enabled"] is True
    assert cfg["update_repo"] == DEFAULT_CONFIG["update_repo"]


def test_update_keys_invalid_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(
        json.dumps({"update_check_enabled": "yes", "update_repo": "  "}),
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg["update_check_enabled"] is True
    assert cfg["update_repo"] == DEFAULT_CONFIG["update_repo"]


def test_models_dir_created(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    d = get_models_dir()
    assert d.is_dir()
    assert d == tmp_path / "JasperVoice" / "models"


def test_paste_delay_and_min_recording_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["paste_delay_ms"] == DEFAULT_CONFIG["paste_delay_ms"]
    assert cfg["min_recording_ms"] == DEFAULT_CONFIG["min_recording_ms"]

    save_config({"paste_delay_ms": 50, "min_recording_ms": 500})
    cfg = load_config()
    assert cfg["paste_delay_ms"] == 50
    assert cfg["min_recording_ms"] == 500


def test_invalid_delay_values_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"paste_delay_ms": -5, "min_recording_ms": "abc"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["paste_delay_ms"] == DEFAULT_CONFIG["paste_delay_ms"]
    assert cfg["min_recording_ms"] == DEFAULT_CONFIG["min_recording_ms"]


def test_paste_delay_above_range_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"paste_delay_ms": 999}), encoding="utf-8")
    cfg = load_config()
    assert cfg["paste_delay_ms"] == DEFAULT_CONFIG["paste_delay_ms"]


def test_min_recording_below_range_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"min_recording_ms": 10}), encoding="utf-8")
    cfg = load_config()
    assert cfg["min_recording_ms"] == DEFAULT_CONFIG["min_recording_ms"]


def test_min_recording_above_range_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"min_recording_ms": 9999}), encoding="utf-8")
    cfg = load_config()
    assert cfg["min_recording_ms"] == DEFAULT_CONFIG["min_recording_ms"]


def test_sample_rate_unsupported_falls_back_to_16000(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"sample_rate": 48000}), encoding="utf-8")
    cfg = load_config()
    assert cfg["sample_rate"] == 16000


def test_new_defaults_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["output_mode"] == "raw"
    assert cfg["post_processing_enabled"] is False
    assert cfg["post_processing_provider"] == "none"


def test_invalid_output_mode_falls_back_to_raw(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"output_mode": "super_mode"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["output_mode"] == "raw"


def test_invalid_post_processing_enabled_falls_back_to_false(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"post_processing_enabled": "yes"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["post_processing_enabled"] is False


def test_invalid_post_processing_provider_falls_back_to_none(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"post_processing_provider": "openai"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["post_processing_provider"] == "none"


def test_old_config_auto_migrates(tmp_path, monkeypatch):
    """Config without new keys should load successfully with defaults filled in."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"hotkey": "ctrl+alt+x", "language": "en"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey"] == "ctrl+alt+x"
    assert cfg["language"] == "en"
    assert cfg["output_mode"] == "raw"
    assert cfg["post_processing_enabled"] is False
    assert cfg["post_processing_provider"] == "none"


def test_provider_opencode_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"post_processing_provider": "opencode"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["post_processing_provider"] == "opencode"


def test_provider_invalid_falls_back_to_none(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"post_processing_provider": "openai"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["post_processing_provider"] == "none"


def test_opencode_defaults_exist(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["opencode_base_url"] == ""
    assert cfg["opencode_api_key_env"] == "OPENCODE_API_KEY"
    assert cfg["opencode_fast_model"] == "DeepSeek V4 Flash"
    assert cfg["opencode_smart_model"] == "Qwen3.7 Max"
    assert cfg["opencode_timeout_s"] == 20


def test_opencode_base_url_invalid_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"opencode_base_url": 123}), encoding="utf-8")
    cfg = load_config()
    assert cfg["opencode_base_url"] == ""


def test_opencode_api_key_env_empty_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"opencode_api_key_env": "   "}), encoding="utf-8")
    cfg = load_config()
    assert cfg["opencode_api_key_env"] == "OPENCODE_API_KEY"


def test_opencode_fast_model_empty_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"opencode_fast_model": ""}), encoding="utf-8")
    cfg = load_config()
    assert cfg["opencode_fast_model"] == DEFAULT_CONFIG["opencode_fast_model"]


def test_opencode_smart_model_empty_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"opencode_smart_model": ""}), encoding="utf-8")
    cfg = load_config()
    assert cfg["opencode_smart_model"] == DEFAULT_CONFIG["opencode_smart_model"]


def test_opencode_timeout_out_of_range_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"opencode_timeout_s": 999}), encoding="utf-8")
    cfg = load_config()
    assert cfg["opencode_timeout_s"] == 20


def test_default_dictionary_is_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["dictionary"] == []


def test_old_config_migrates_with_empty_dictionary(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"hotkey": "ctrl+alt+x"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == []


def test_valid_dictionary_entries_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [
            {"phrase": "open code", "replacement": "OpenCode"},
            {"phrase": "use effect", "replacement": "useEffect"},
        ]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [
        {"phrase": "open code", "replacement": "OpenCode"},
        {"phrase": "use effect", "replacement": "useEffect"},
    ]


def test_invalid_dictionary_value_falls_back_to_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"dictionary": "not_a_list"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == []


def test_invalid_entries_inside_dictionary_dropped(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [
            {"phrase": "", "replacement": "Foo"},
            {"phrase": "bar", "replacement": ""},
            "not_a_dict",
            {"phrase": "valid", "replacement": "Valid"},
        ]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [{"phrase": "valid", "replacement": "Valid"}]


def test_dictionary_whitespace_is_stripped(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [
            {"phrase": "  foo  ", "replacement": "  Bar  "},
        ]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [{"phrase": "foo", "replacement": "Bar"}]


def test_unknown_keys_in_dictionary_entries_ignored(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [
            {"phrase": "foo", "replacement": "Bar", "color": "blue", "priority": 1},
        ]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [{"phrase": "foo", "replacement": "Bar"}]


def test_hotkey_mode_default_is_push_to_talk(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["hotkey_mode"] == "push_to_talk"


def test_hotkey_mode_toggle_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"hotkey_mode": "toggle"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey_mode"] == "toggle"


def test_hotkey_mode_invalid_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"hotkey_mode": "voice"}), encoding="utf-8")
    cfg = load_config()
    assert cfg["hotkey_mode"] == "push_to_talk"


# --- New shell/UI keys ---

def test_new_ui_keys_have_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    cfg = load_config()
    assert cfg["launch_at_login"] is False
    assert cfg["start_minimized"] is True
    assert cfg["show_overlay"] is True
    assert cfg["overlay_position"] == "bottom_right"
    assert cfg["input_device"] == "default"
    assert cfg["noise_gate_enabled"] is False
    assert cfg["sound_feedback"] == "off"
    assert cfg["warmup_on_launch"] is True


def test_new_ui_keys_persist(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    save_config({
        "launch_at_login": True,
        "start_minimized": False,
        "show_overlay": False,
        "overlay_position": "top_left",
        "input_device": "Yeti X Microphone",
        "noise_gate_enabled": True,
        "sound_feedback": "subtle",
        "warmup_on_launch": False,
    })
    cfg = load_config()
    assert cfg["launch_at_login"] is True
    assert cfg["start_minimized"] is False
    assert cfg["show_overlay"] is False
    assert cfg["overlay_position"] == "top_left"
    assert cfg["input_device"] == "Yeti X Microphone"
    assert cfg["noise_gate_enabled"] is True
    assert cfg["sound_feedback"] == "subtle"
    assert cfg["warmup_on_launch"] is False


def test_new_ui_keys_invalid_fall_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "launch_at_login": "yes",
        "start_minimized": 1,
        "show_overlay": "on",
        "overlay_position": "center",
        "input_device": 5,
        "noise_gate_enabled": "loud",
        "sound_feedback": "blaring",
        "warmup_on_launch": "always",
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["launch_at_login"] is False
    assert cfg["start_minimized"] is True
    assert cfg["show_overlay"] is True
    assert cfg["overlay_position"] == "bottom_right"
    assert cfg["input_device"] == "default"
    assert cfg["noise_gate_enabled"] is False
    assert cfg["sound_feedback"] == "off"
    assert cfg["warmup_on_launch"] is True


def test_input_device_blank_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({"input_device": "   "}), encoding="utf-8")
    cfg = load_config()
    assert cfg["input_device"] == "default"


# --- Dictionary "enabled" coercion ---

def test_dictionary_enabled_true_is_omitted(tmp_path, monkeypatch):
    """enabled=True entries keep the old two-key shape for backward compat."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [{"phrase": "foo", "replacement": "Bar", "enabled": True}]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [{"phrase": "foo", "replacement": "Bar"}]


def test_dictionary_enabled_false_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [
            {"phrase": "foo", "replacement": "Bar", "enabled": False},
            {"phrase": "baz", "replacement": "Qux"},
        ]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [
        {"phrase": "foo", "replacement": "Bar", "enabled": False},
        {"phrase": "baz", "replacement": "Qux"},
    ]


def test_dictionary_enabled_falsy_value_disables(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    p = get_config_path()
    p.write_text(json.dumps({
        "dictionary": [{"phrase": "foo", "replacement": "Bar", "enabled": 0}]
    }), encoding="utf-8")
    cfg = load_config()
    assert cfg["dictionary"] == [{"phrase": "foo", "replacement": "Bar", "enabled": False}]
