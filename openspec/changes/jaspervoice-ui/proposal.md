# Proposal: JasperVoice UI v1 (Settings + Overlay)

## Why

The MVP shipped a working PTT pipeline but exposed configuration only via raw `config.json` editing. As the app gains state (hotkey, model, device, language, paste timing), users need a discoverable UI to change those values without restarting, and a visible indicator of when the microphone is hot. This change adds a dark-themed settings window and a frameless floating overlay that pulses while recording.

## What Changes

- **New module `theme.py`**: dark-only color palette + QSS string loaded by Qt widgets.
- **New module `overlay.py`**: `RecordingOverlay` — frameless, top-most, 48px circle. Four states (idle/recording/processing/error) with the colors you provided. Visible only during recording/processing/error; hidden in idle. Pulse animation on the recording state. Left click → opens settings; right click → context menu.
- **New module `ui.py`**: `SettingsWindow` — 800×560, non-modal, four sections (General, Whisper, Behavior, Diagnostics). Apply/Cancel footer; X hides instead of closes. Bidirectional Qt ↔ `keyboard` hotkey conversion. Applies changes live (no restart).
- **Modified `tray.py`**: adds "Settings..." menu item that emits a new `settings_requested` signal.
- **Modified `app.py`**: instantiates overlay and settings window, wires state transitions, handles hot-reload of hotkey/model/device/compute/language when settings change.
- **Modified `hotkey.py`**: `start()` now calls `stop()` if already running, preventing hook accumulation on hot-reload. **Spec delta**: `global-hotkey/spec.md` requirement "Hotkey change requires restart" is replaced with "Hotkey change applies on Apply; listener restarts automatically".
- **New tests**: `test_overlay.py`, `test_ui.py`, additional cases in `test_hotkey.py`.

## Capabilities

### New Capabilities

- `settings-ui`: dark-themed settings window with General/Whisper/Behavior/Diagnostics sections, live apply, hotkey conversion.
- `recording-overlay`: frameless floating circular indicator with four visual states, pulse animation, click-to-settings.

### Modified Capabilities

- `global-hotkey`: hot-reload of hotkey on Apply is now supported (was: restart required). The `HotkeyListener.start()` guard prevents hook accumulation.

## Impact

- **New files**: `src/jaspervoice/theme.py`, `overlay.py`, `ui.py`, `assets/jv.svg` (placeholder), plus three new test files.
- **Modified files**: `tray.py`, `app.py`, `hotkey.py`, `tests/test_hotkey.py`.
- **No new runtime dependencies** — QSS, QPropertyAnimation, QGraphicsOpacityEffect, QKeySequenceEdit all in PySide6 6.8.1.
- **Config schema**: no new keys; existing schema covers everything the UI exposes.
- **Backwards compat**: `config.json` from MVP works unchanged. New UI fields (paste_delay, min_recording_ms) get sane defaults on first run if missing.
- **OpenSpec archive**: this change archives alongside `jaspervoice-mvp` once shipped.
