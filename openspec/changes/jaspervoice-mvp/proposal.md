# Proposal: JasperVoice MVP

## Why

Dictation tools for desktop either send audio to the cloud (Wispr Flow, Superwhisper cloud) or require paid licenses (BridgeVoice Pro $40/mo, Dragon). For personal use — coding prompts, commit messages, Slack replies, terminal commands — there is no simple, local-first, free push-to-talk app for Windows that just works. JasperVoice fills that gap: press a hotkey, speak, release, text appears wherever the cursor is. No cloud, no subscription, no telemetry.

## What Changes

- New desktop app: system tray icon, push-to-talk global hotkey (default `Ctrl+Shift+Space`).
- Audio capture from default microphone while hotkey is held.
- Local transcription using `faster-whisper` (Whisper CTranslate2, runs offline).
- Automatic text injection into the currently focused app via clipboard + `SendInput` (Ctrl+V).
- Tray menu with: status indicator, model/device info, language selector, quit.
- All state and config persisted to local files in `%APPDATA%/JasperVoice/`.
- Architecture is layered (audio → transcription → injection → hotkey → tray) so v2 features (custom dictionary, history, overlay, hotkey modes) can be added without restructuring.

## Capabilities

### New Capabilities

- `audio-capture`: microphone recording lifecycle (start/stop/buffer management, VAD-gated segmentation optional).
- `transcription`: Whisper model loading, language selection, device auto-detection (CUDA → CPU fallback), inference.
- `text-injection`: focused-window text insertion via clipboard + `SendInput` Ctrl+V.
- `global-hotkey`: system-wide keybind listener with PTT (hold) semantics.
- `tray-ui`: system tray icon, status menu, language/model/settings, quit.
- `config`: JSON settings at `%APPDATA%/JasperVoice/config.json` (hotkey, language, model size, device override).

### Modified Capabilities

_None — initial implementation._

## Impact

- **New project**: greenfield. No existing code affected.
- **Runtime deps**: `PySide6`, `faster-whisper`, `sounddevice`, `keyboard`, `pyperclip`, `numpy` (transitive).
- **System deps**: PortAudio (bundled with `sounddevice` wheel on Windows), no separate install.
- **First-run**: downloads Whisper model weights (~460MB for `small` int8) to `%APPDATA%/JasperVoice/models/`.
- **Permissions**: keyboard hook may require running as admin on some Windows configs; `keyboard` lib prompts UAC on first install.
- **OS**: Windows 10/11. Cross-platform out of scope for MVP.
