"""JSON configuration at %APPDATA%/JasperVoice/config.json (Windows) or ~/.jaspervoice/ (fallback)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .postprocessing import OUTPUT_MODES

log = logging.getLogger(__name__)

APP_DIR_NAME = "JasperVoice"
CONFIG_FILENAME = "config.json"
MODELS_DIRNAME = "models"

DEFAULT_CONFIG: dict[str, Any] = {
    "hotkey": "ctrl+shift+space",
    "hotkey_mode": "push_to_talk",
    "language": "pt",
    "model_size": "small",
    "compute_type": "int8",
    "device": "auto",
    "sample_rate": 16000,
    "paste_delay_ms": 15,
    "min_recording_ms": 200,
    "output_mode": "raw",
    "post_processing_enabled": False,
    "post_processing_provider": "none",
    "opencode_base_url": "",
    "opencode_api_key_env": "OPENCODE_API_KEY",
    "opencode_fast_model": "DeepSeek V4 Flash",
    "opencode_smart_model": "Qwen3.7 Max",
    "opencode_timeout_s": 20,
    "dictionary": [],
    # --- Updates (GitHub Releases). All optional; the app runs fine offline. ---
    "update_check_enabled": True,
    "update_repo": "ynkjohn/JasperVoice",
    # --- Startup & system ---
    "launch_at_login": False,
    "start_minimized": True,
    # --- Overlay ---
    "show_overlay": True,
    "overlay_position": "bottom_right",
    # --- Audio capture ---
    "input_device": "default",
    "noise_gate_enabled": False,
    "sound_feedback": "off",
    # --- Engine ---
    "warmup_on_launch": True,
}

VALID_PROVIDERS = {"none", "opencode"}

VALID_HOTKEY_MODES = {"push_to_talk", "toggle"}

VALID_OVERLAY_POSITIONS = {"top_left", "top_right", "bottom_left", "bottom_right"}
VALID_SOUND_FEEDBACK = {"off", "subtle", "all"}

VALID_MODEL_SIZES = {"tiny", "base", "small", "medium", "large-v3"}
VALID_COMPUTE_TYPES = {"int8", "int16", "float16", "float32"}
VALID_DEVICES = {"auto", "cpu", "cuda"}


def get_app_dir() -> Path:
    """Return the per-user app directory, creating it if missing."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata) / APP_DIR_NAME
    else:
        base = Path.home() / f".{APP_DIR_NAME.lower()}"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILENAME


def get_models_dir() -> Path:
    p = get_app_dir() / MODELS_DIRNAME
    p.mkdir(parents=True, exist_ok=True)
    return p


def _coerce(cfg: dict[str, Any]) -> dict[str, Any]:
    """Fill in missing keys from DEFAULT_CONFIG, validate ranges, drop unknowns.

    sample_rate is currently restricted to 16000 because the audio pipeline
    does not perform resampling before feeding data to faster-whisper.
    """
    out = deepcopy(DEFAULT_CONFIG)
    for k, v in cfg.items():
        if k in out:
            out[k] = v
    if out["model_size"] not in VALID_MODEL_SIZES:
        log.warning("Invalid model_size %r, falling back to 'small'", out["model_size"])
        out["model_size"] = "small"
    if out["compute_type"] not in VALID_COMPUTE_TYPES:
        log.warning("Invalid compute_type %r, falling back to 'int8'", out["compute_type"])
        out["compute_type"] = "int8"
    if out["device"] not in VALID_DEVICES:
        log.warning("Invalid device %r, falling back to 'auto'", out["device"])
        out["device"] = "auto"
    if not isinstance(out["sample_rate"], int) or out["sample_rate"] != 16000:
        log.warning("sample_rate %r is not supported; only 16000 is available. Falling back to 16000.", out.get("sample_rate"))
        out["sample_rate"] = 16000
    if not isinstance(out["hotkey"], str) or not out["hotkey"].strip():
        out["hotkey"] = DEFAULT_CONFIG["hotkey"]
    if out.get("hotkey_mode") not in VALID_HOTKEY_MODES:
        log.warning("Invalid hotkey_mode %r, falling back to 'push_to_talk'", out.get("hotkey_mode"))
        out["hotkey_mode"] = "push_to_talk"
    if not isinstance(out["language"], str) or not out["language"].strip():
        out["language"] = DEFAULT_CONFIG["language"]
    if not isinstance(out.get("paste_delay_ms"), int) or not (0 <= out["paste_delay_ms"] <= 200):
        log.warning("Invalid paste_delay_ms %r, falling back to %d", out.get("paste_delay_ms"), DEFAULT_CONFIG["paste_delay_ms"])
        out["paste_delay_ms"] = DEFAULT_CONFIG["paste_delay_ms"]
    if not isinstance(out.get("min_recording_ms"), int) or not (50 <= out["min_recording_ms"] <= 2000):
        log.warning("Invalid min_recording_ms %r, falling back to %d", out.get("min_recording_ms"), DEFAULT_CONFIG["min_recording_ms"])
        out["min_recording_ms"] = DEFAULT_CONFIG["min_recording_ms"]
    if not isinstance(out.get("output_mode"), str) or out["output_mode"] not in OUTPUT_MODES:
        log.warning("Invalid output_mode %r, falling back to %r", out.get("output_mode"), DEFAULT_CONFIG["output_mode"])
        out["output_mode"] = DEFAULT_CONFIG["output_mode"]
    if not isinstance(out.get("post_processing_enabled"), bool):
        log.warning("Invalid post_processing_enabled %r, falling back to False", out.get("post_processing_enabled"))
        out["post_processing_enabled"] = False
    if not isinstance(out.get("post_processing_provider"), str) or out["post_processing_provider"] not in VALID_PROVIDERS:
        log.warning("Invalid post_processing_provider %r, falling back to 'none'", out.get("post_processing_provider"))
        out["post_processing_provider"] = "none"
    if out["post_processing_enabled"] and out["post_processing_provider"] == "none":
        out["post_processing_provider"] = "opencode"
    if out["post_processing_enabled"] and out["output_mode"] == "raw":
        out["output_mode"] = "clean"
    if not isinstance(out.get("opencode_base_url"), str):
        log.warning("Invalid opencode_base_url %r, falling back to ''", out.get("opencode_base_url"))
        out["opencode_base_url"] = ""
    if not isinstance(out.get("opencode_api_key_env"), str) or not out["opencode_api_key_env"].strip():
        log.warning("Invalid opencode_api_key_env %r, falling back to 'OPENCODE_API_KEY'", out.get("opencode_api_key_env"))
        out["opencode_api_key_env"] = "OPENCODE_API_KEY"
    if not isinstance(out.get("opencode_fast_model"), str) or not out["opencode_fast_model"].strip():
        log.warning("Invalid opencode_fast_model %r, falling back to default", out.get("opencode_fast_model"))
        out["opencode_fast_model"] = DEFAULT_CONFIG["opencode_fast_model"]
    if not isinstance(out.get("opencode_smart_model"), str) or not out["opencode_smart_model"].strip():
        log.warning("Invalid opencode_smart_model %r, falling back to default", out.get("opencode_smart_model"))
        out["opencode_smart_model"] = DEFAULT_CONFIG["opencode_smart_model"]
    if not isinstance(out.get("opencode_timeout_s"), int) or not (1 <= out["opencode_timeout_s"] <= 120):
        log.warning("Invalid opencode_timeout_s %r, falling back to 20", out.get("opencode_timeout_s"))
        out["opencode_timeout_s"] = 20
    if not isinstance(out.get("dictionary"), list):
        log.warning("Invalid dictionary %r, falling back to []", out.get("dictionary"))
        out["dictionary"] = []
    else:
        cleaned: list[dict] = []
        for entry in out["dictionary"]:
            if not isinstance(entry, dict):
                continue
            phrase = str(entry.get("phrase", "")).strip()
            replacement = str(entry.get("replacement", "")).strip()
            if phrase and replacement:
                item = {"phrase": phrase, "replacement": replacement}
                # Entries without "enabled" behave as enabled=True; only the
                # disabled flag is serialized so old config files stay unchanged.
                if not bool(entry.get("enabled", True)):
                    item["enabled"] = False
                cleaned.append(item)
        out["dictionary"] = cleaned
    if not isinstance(out.get("update_check_enabled"), bool):
        log.warning("Invalid update_check_enabled %r, falling back to True", out.get("update_check_enabled"))
        out["update_check_enabled"] = True
    if not isinstance(out.get("update_repo"), str) or not out["update_repo"].strip():
        log.warning("Invalid update_repo %r, falling back to default", out.get("update_repo"))
        out["update_repo"] = DEFAULT_CONFIG["update_repo"]
    for key in ("launch_at_login", "start_minimized", "show_overlay",
                "noise_gate_enabled", "warmup_on_launch"):
        if not isinstance(out.get(key), bool):
            log.warning("Invalid %s %r, falling back to %r", key, out.get(key), DEFAULT_CONFIG[key])
            out[key] = DEFAULT_CONFIG[key]
    if out.get("overlay_position") not in VALID_OVERLAY_POSITIONS:
        log.warning("Invalid overlay_position %r, falling back to 'bottom_right'", out.get("overlay_position"))
        out["overlay_position"] = DEFAULT_CONFIG["overlay_position"]
    if not isinstance(out.get("input_device"), str) or not out["input_device"].strip():
        log.warning("Invalid input_device %r, falling back to 'default'", out.get("input_device"))
        out["input_device"] = DEFAULT_CONFIG["input_device"]
    if out.get("sound_feedback") not in VALID_SOUND_FEEDBACK:
        log.warning("Invalid sound_feedback %r, falling back to 'off'", out.get("sound_feedback"))
        out["sound_feedback"] = DEFAULT_CONFIG["sound_feedback"]
    return out


def load_config() -> dict[str, Any]:
    """Load config from disk. Writes defaults on first run. Backs up + resets on parse error."""
    path = get_config_path()
    if not path.exists():
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg)
        log.info("Wrote default config to %s", path)
        return cfg
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            raise ValueError("config root is not an object")
    except (json.JSONDecodeError, ValueError, OSError) as e:
        backup = path.with_suffix(".json.bak")
        try:
            path.replace(backup)
            log.error("Malformed config backed up to %s: %s", backup, e)
        except OSError:
            log.error("Malformed config at %s: %s", path, e)
        cfg = deepcopy(DEFAULT_CONFIG)
        save_config(cfg)
        return cfg
    return _coerce(raw)


def save_config(cfg: dict[str, Any]) -> None:
    """Atomic write: write to temp file in the same dir, then replace."""
    path = get_config_path()
    cfg = _coerce(cfg)
    fd, tmp_path = tempfile.mkstemp(
        prefix=".config.", suffix=".json.tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
