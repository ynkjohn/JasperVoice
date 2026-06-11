# Design: JasperVoice MVP

## Context

Greenfield Windows desktop app for personal voice dictation. User wants push-to-talk global hotkey, local Whisper transcription, automatic text injection into the focused app. Reference product BridgeVoice is closed-source/proprietary; we extract UX patterns (PTT, tray control, universal injection) but implement independently in Python.

Hardware target: i5-12500H, 16GB RAM, RTX 3050 Laptop. Python 3.13 available, no Rust, no CUDA toolkit confirmed. Node 24 also available but not selected (Whisper ergonomics worse in Node).

User explicitly wants a layered architecture from day 1 ("no futuro quero estruturar um app"), so even though MVP is small, modules are separated cleanly.

## Goals / Non-Goals

**Goals:**
- Push-to-talk (hold-to-dictate) with single configurable hotkey.
- Local-only inference, no network calls in steady state.
- Text injection into any app that accepts Ctrl+V.
- Single-instance tray app, runs on startup optionally.
- Clean module boundaries: each capability in its own file with a small public surface.
- First-run model download handled gracefully with progress feedback.

**Non-Goals:**
- macOS / Linux support.
- Toggle/hands-free mode.
- Custom dictionary / vocabulary replacement.
- Transcription history with re-copy.
- Floating overlay widget.
- Cloud transcription providers.
- Auto-update mechanism.
- Installer / MSIX packaging (PyInstaller `--onefile` is enough for v1).

## Decisions

### D1. Python 3.13 + PySide6 over Tauri/Rust

- Whisper ecosystem (faster-whisper, whisper.cpp Python bindings) is most mature in Python.
- PySide6 gives system tray, QThread for non-blocking inference, QSettings for config.
- Single language across the stack; no Rust toolchain needed.
- PyInstaller produces a single `.exe` when distribution is needed.
- **Alternative considered**: Tauri + whisper.cpp. Rejected because user has no Rust installed and Whisper Python story is more direct.

### D2. `faster-whisper` (CTranslate2) over `openai-whisper`

- `faster-whisper` is 4x faster, lower memory, supports int8 quantization natively.
- Uses CTranslate2 — supports CUDA **if** cuDNN is available, but the prebuilt wheel on PyPI is CPU-only.
- We will use `device="auto"` logic: try `cuda`, catch the cuDNN/CMake build error, fall back to `cpu`. On this machine, default path is CPU.
- Model: `small` int8 (~460MB). Good PT-BR quality, ~1-2s CPU latency for 5s audio on i5-12500H.
- Configurable in `config.json` so user can switch to `base`/`medium`/`large-v3` later.

### D3. `sounddevice` over `pyaudio`

- `sounddevice` ships with PortAudio bundled in Windows wheel — no separate install.
- NumPy-buffer callback model fits naturally with `faster-whisper`'s array input.
- `pyaudio` requires manual PortAudio build steps on some Windows configs.

### D4. `keyboard` library for global hotkey (with caveat)

- `keyboard` is the most ergonomic Python global hotkey lib. Uses Windows low-level hooks.
- **Caveat**: requires admin elevation on some setups; first run may show UAC prompt. Acceptable for personal use.
- **Alternative considered**: `pynput`. Rejected because hotkey hold/release semantics are trickier (need state machine). `keyboard`'s `on_press_key`/`on_release_key` gives raw events we can use directly.

### D5. Clipboard + `SendInput` Ctrl+V for text injection

- `pyperclip` writes to clipboard; `ctypes` calls `user32.SendInput` with a virtual `VK_V` keypress to trigger paste.
- Works in 95%+ of Windows apps (editor, terminal, browser, Slack, VS Code).
- **Trade-off**: overwrites user clipboard. v1 does not restore. Documented in tray tooltip.
- **Alternative considered**: simulate unicode typing. Rejected: slow for long text, blocked by some apps.

### D6. Layered module structure

Even for MVP, split into:
- `audio.py` — `Recorder` class wrapping `sounddevice.InputStream`.
- `transcription.py` — `Transcriber` class wrapping `faster_whisper.WhisperModel`.
- `injection.py` — `inject_text(text)` function.
- `hotkey.py` — PTT state machine on top of `keyboard` events.
- `tray.py` — `QSystemTrayIcon` with menu.
- `config.py` — load/save JSON config.
- `app.py` — wires everything together, runs Qt event loop.

Reason: each piece can be replaced or extended in v2 without touching the others (e.g., swap `keyboard` for `pynput`, add `dictionary.py` post-processor).

### D7. Config at `%APPDATA%/JasperVoice/config.json`

- Standard Windows location for user app data.
- JSON (not TOML) for trivial parsing with stdlib.
- Schema:
  ```json
  {
    "hotkey": "ctrl+shift+space",
    "language": "pt",
    "model_size": "small",
    "compute_type": "int8",
    "device": "auto",
    "sample_rate": 16000
  }
  ```

### D8. Worker thread for inference

- Whisper inference must not block Qt event loop (would freeze tray).
- Use `QThread` (or plain `threading.Thread` with `pyqtSignal`) for the transcription worker.
- Recorder callback pushes raw audio to a `queue.Queue`; worker pulls chunks and transcribes.

## Risks / Trade-offs

- **CUDA unavailable out of the box** → falls back to CPU automatically. User can install cuDNN later and re-run.
- **First-run model download** (~460MB) takes 30-60s on typical broadband. Tray shows progress. **Mitigation**: explicit "downloading model..." status, blocking app until done.
- **Keyboard lib requires admin** on some Win10/11 configs. **Mitigation**: README documents how to create a scheduled task with highest privileges, or to mark the .exe as "run as admin" via PyInstaller manifest.
- **No clipboard restore** — overwrites user clipboard. **Mitigation**: documented in tray tooltip; can be added in v1.1.
- **`keyboard` lib can interfere with antivirus** (looks like a keylogger). **Mitigation**: clean open-source lib, no exfiltration, README explains why it's safe.
- **Single-instance**: not enforced in MVP. Running twice will fight for the hotkey. **Mitigation**: tray "Quit" is the only way out; documented.

## Migration Plan

N/A — greenfield. No existing data, no existing users. Deploy is `git clone && pip install -r requirements.txt && python -m jaspervoice`.

## Open Questions

- Should the tray show a brief "transcribed: <text>" notification on success, or stay silent? (Default: silent in MVP, just change tray icon to green tick for 2s.)
- Behavior on empty transcription (silence detected): inject nothing, flash red icon, or paste a newline? (Default: nothing, icon returns to idle, no paste.)
- Should `Esc` while recording cancel the current take? (Default: yes, for v1.1. MVP just ignores.)
