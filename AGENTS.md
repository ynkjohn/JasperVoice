# AGENTS.md

Guidance for AI coding agents working on JasperVoice. Read this before making
changes — it captures conventions and non-obvious constraints that are easy to
break.

## What this project is

JasperVoice is a local, offline push-to-talk voice dictation app for Windows.
Hold a hotkey, speak, release — Whisper transcribes on-device and the text is
injected into whatever app has focus. No cloud, no telemetry. Built with
PySide6 (Qt) for the tray/overlay/settings UI and `faster-whisper`
(CTranslate2) for transcription.

## Environment

- **OS**: Windows. Shell is PowerShell 7+ (`pwsh`).
- **Python**: 3.11+ (dev machine runs 3.13).
- **venv**: `.venv\` at the repo root. `pip`/`pyinstaller` are NOT on the global
  PATH — always invoke through the venv:
  - Python: `.venv\Scripts\python.exe`
  - Tests: `.venv\Scripts\python.exe -m pytest tests/ -p no:cacheprovider`
  - Build: `.venv\Scripts\pyinstaller.exe jaspervoice.spec --noconfirm`
- **App data**: `%APPDATA%\JasperVoice\` holds `config.json`, `history.json`,
  `jaspervoice.log` (rotating, windowed build), and `models/`.

## Running

```powershell
.venv\Scripts\python.exe -m jaspervoice        # dev run (console)
```

The app lives in the system tray. Default hotkey `Ctrl+Shift+Space`.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest tests/ -p no:cacheprovider -q
```

- Tests run with the Qt `offscreen` platform (set in `conftest.py`).
- **Known environmental failure**: `test_device_auto_falls_back_gracefully`
  tries to reach the HuggingFace cache. If `HF_HOME` points at a missing drive
  it fails with an I/O error — this is NOT a code bug. Run with a valid cache:
  ```powershell
  $env:HF_HOME="$env:TEMP\hf_test"; .venv\Scripts\python.exe -m pytest tests/ -p no:cacheprovider -q
  ```
  With a valid cache the full suite passes (177 tests at time of writing).
- Always add/adjust tests when changing behavior. Each module has a matching
  `tests/test_<module>.py`.

## Architecture

```
src/jaspervoice/
  app.py            Main wiring: hotkey → record → transcribe → inject pipeline.
                    TranscriptionWorker runs off the Qt loop on its own QThread.
  config.py         JSON config load/save with validation + atomic writes.
  audio.py          Recorder (sounddevice InputStream → numpy). 7-band FFT for viz.
  transcription.py  Transcriber: faster-whisper with CUDA→CPU auto-fallback.
  injection.py      Clipboard + SendInput Ctrl+V text injection.
  hotkey.py         PTT + toggle state machine over the `keyboard` lib.
  history.py        Thread-safe transcription history (JSON, capped at 200).
  postprocessing.py Optional OpenCode/OpenAI-compatible text polish.
  dictionary.py     Offline phrase→replacement corrections (pre-compiled regex).
  tray.py           QSystemTrayIcon: states, language menu, settings/stats/quit.
  overlay.py        Frameless floating pill indicator (animated, state-colored).
  ui.py             SettingsWindow + StatsWindow (card-based dark UI).
  theme.py          Dark QSS + STATE_COLORS palette.
  assets.py         icon_path() resolution for dev + frozen runs.
  app_gui.py        Frozen entry point (windowed, no console).
```

## Critical constraints (these WILL bite you)

### Threading: keyboard hook → Qt must use Signals
`hotkey.py`'s `keyboard.hook` callback fires on the OS low-level hook thread,
NOT the Qt main thread. Touching any QObject/QWidget from there freezes the app
on Windows. **Route every callback through a Qt `Signal`** on a QObject built on
the main thread (auto = queued connection across threads). Do NOT use
`QTimer.singleShot(0, fn)` — it proved unreliable under load. The same pattern
applies to audio-thread band levels → overlay (see `_LevelBridge` in `app.py`).

### QTimer must be created on the owning thread
Create timers in `__init__` (main thread), not lazily inside a slot that might
run on another thread. Lazy creation triggered "Timers can only be used with
threads started with QThread" and froze the app.

### Overlay animations
The overlay fades out via `QPropertyAnimation` on `windowOpacity`. The
`_hide_after_fade` slot is connected ONCE in `__init__` and guards on
`self._state == "idle"` internally. Do NOT connect/disconnect it per-transition
— that stacks duplicate slots and emits "Failed to disconnect" RuntimeWarnings.
Because hide is animated, synchronous visibility assertions in tests must force
the animation to completion first (stop anim, set opacity 0, call
`_hide_after_fade()`).

### Config is the single source of truth
`config.py::_coerce()` validates and fills defaults. When adding a setting:
1. Add the key + default to `DEFAULT_CONFIG`.
2. Add validation/fallback in `_coerce()` (and a `VALID_*` set if enumerated).
3. Wire it into `ui.py` (SettingsWindow `_build_*_card` + `_load_values_into_ui`
   + `_collect_values` + `_all_input_widgets`).
4. Apply it live in `app.py::_on_config_changed` if it should hot-reload.

### Atomic file writes
Both `config.py` and `history.py` write to a temp file then `replace()` for
atomicity. Do not introduce a "clear then write" step — `Path.replace()` already
overwrites atomically; a pre-clear only risks leaving an empty file on failure.

## GPU / CUDA in the frozen build

GPU works in the standalone `.exe`. The mechanism:
- `jaspervoice.spec::_collect_cuda_dlls()` bundles cuBLAS + cuDNN DLLs from the
  pip `nvidia-*` packages. If those packages are absent, it builds a CPU-only
  bundle without failing.
- `scripts/rthook_cuda.py` is a **runtime hook** that runs before heavy imports
  and calls `os.add_dll_directory` on the bundle root so `ctranslate2.dll`
  (which lives in `_internal/ctranslate2/`) can find the CUDA DLLs at
  `_internal/`. The Windows loader does NOT search the bundle root on its own.
- Verify GPU after a build by checking the log for:
  `Model warmup complete: loaded on device=cuda`
- Trade-off: bundling CUDA makes the one-folder build ~3 GB (cuBLAS alone is
  ~735 MB). The CPU-only build is ~1 GB.

When running the dev process, GPU "just works" if the `nvidia-*` packages are
installed in the venv — `transcription.py` resolves `device="auto"` to CUDA
first, falling back to CPU.

## Build (PyInstaller)

```powershell
.venv\Scripts\pyinstaller.exe jaspervoice.spec --noconfirm
```

- One-folder bundle at `dist\JasperVoice\`. `JasperVoice.exe` MUST stay next to
  its `_internal\` folder.
- The Whisper model is NOT bundled — it downloads on first run to
  `%APPDATA%\JasperVoice\models\`.
- Windowed build (no console); logs go to `%APPDATA%\JasperVoice\jaspervoice.log`.
- Build takes ~75-110s.

## Visual / design conventions

- Dark only. Background `#0F0F0F`, single orange accent `#D97757`, foreground
  `#E8E6E6`. Technical minimalism — thin borders, no shadows, monospace headings.
- Overlay state colors live in `theme.py::STATE_COLORS` (idle/recording/
  processing/send/error). The overlay reads from there.
- SettingsWindow uses a centered fixed-width (720px) column so maximizing the
  window doesn't stretch cards across the screen.
- When making visual changes, render the UI offscreen to a PNG and review it
  before declaring done (the user expects to see renders for visual work).

## Icon

`scripts/make_icon.py` rasterizes `assets/icon.svg` → `assets/icon.ico` using Qt
(no cairosvg/Pillow). It encodes PNG frames through a temp file because
QBuffer-based in-memory encoding crashes under the offscreen platform.

## Conventions

- Match the existing style: module docstrings explaining the "why", small
  focused modules, type hints, `from __future__ import annotations`.
- Logging via the module `log = logging.getLogger(__name__)`, not print.
- Keep changes scoped. Don't refactor unrelated code while fixing a bug.
- Don't commit `config.json`, `history.json`, logs, `build/`, or `dist/` (see
  `.gitignore`).
