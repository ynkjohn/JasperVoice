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
  With a valid cache the full suite passes (212 tests at time of writing).
- **Known environmental failure**: the integration/e2e tests that drive the full
  record→transcribe pipeline (`test_integration.py`, `test_e2e.py`) call
  `Recorder.start()`, which resolves the default input device via
  `sd.default.device[0]` (`audio.py:48`). If Windows has **no default microphone
  set** (the value is `-1`), ~10 integration tests fail with "No microphone
  detected" — this is NOT a code bug. Plug in / enable a mic and set it as the
  Windows default input device, then re-run. Verify with:
  ```powershell
  .venv\Scripts\python.exe -c "import sounddevice as sd; print(sd.default.device)"
  ```
  A first element `>= 0` means a default input exists.
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
  single_instance.py Named-mutex single-instance guard (matches installer AppMutex).
  updater.py        GitHub-Releases self-update: check → download → SHA-256 verify → launch installer. Offline file path too.
  tray.py           QSystemTrayIcon: states, language menu, settings/stats/updates/quit.
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

### Overlay spectrum bars are driven by real audio
During `recording`, `overlay._on_frame()` reads `self._levels` — the live
per-band FFT magnitudes that `audio.Recorder._compute_bands()` computes on the
audio thread and pushes through `level_callback → _LevelBridge →
overlay.levels_updated`. A small sine shimmer is layered on top so the bars
keep subtle motion during brief silences. `set_state("recording")` resets
`self._levels` to zeros so a new take doesn't flash stale levels. Other states
(`processing`/`send`) still use synthetic sine animation. Keep this pipeline
live — it was dead code once (FFT computed every block but never rendered).

### Config is the single source of truth
`config.py::_coerce()` validates and fills defaults. When adding a setting:
1. Add the key + default to `DEFAULT_CONFIG`.
2. Add validation/fallback in `_coerce()` (and a `VALID_*` set if enumerated).
3. Wire it into `ui.py` (SettingsWindow `_build_*_card` + `_load_values_into_ui`
   + `_collect_values` + `_all_input_widgets`).
4. Apply it live in `app.py::_on_config_changed` if it should hot-reload.

### Version is single-sourced in `__init__.py`
`src/jaspervoice/__init__.py::__version__` is the ONE place to bump a release.
Everything reads from it: `pyproject.toml` (`dynamic = ["version"]` →
`[tool.setuptools.dynamic]`), `jaspervoice.spec::_read_version()` (bakes a
Windows version resource into `JasperVoice.exe`), `scripts/build_release.ps1`
(names the installer + tag), and `updater.py` (compares against the latest
GitHub Release tag). Do NOT hardcode the version anywhere else.

### Atomic file writes
Both `config.py` and `history.py` write to a temp file then `replace()` for
atomicity. Do not introduce a "clear then write" step — `Path.replace()` already
overwrites atomically; a pre-clear only risks leaving an empty file on failure.

## GPU / CUDA in the frozen build

GPU works in the standalone `.exe`. The mechanism:
- `jaspervoice.spec::_collect_cuda_dlls()` bundles the cuBLAS DLLs from the pip
  `nvidia-*` packages and places them at the **bundle root** (`.`). cuDNN is
  **deliberately NOT bundled**: the CTranslate2 Whisper path is cuBLAS-driven
  only (verified by physically removing cuDNN from the venv — a full
  `device=cuda` transcription still succeeds). Skipping cuDNN saves ~1 GB. Set
  the env var `JV_CUDNN=1` at build time to opt back into bundling cuDNN.
- The spec also **filters the binaries TOC** to drop the `nvidia/<lib>/bin/`
  copies that PyInstaller's `hook-nvidia.*` hooks add automatically. Those are
  duplicates of the DLLs `_collect_cuda_dlls()` already ships at the root, and
  they used to bloat the bundle by ~931 MB. NOTE: `excludes=["nvidia"]` does
  NOT remove them — they enter via native hooks, not the Python module graph,
  so the TOC filter is required.
- If the `nvidia-*` packages are absent, `_collect_cuda_dlls()` returns an empty
  list and the build is CPU-only without failing.
- `scripts/rthook_cuda.py` is a **runtime hook** that runs before heavy imports
  and calls `os.add_dll_directory` on the bundle root so `ctranslate2.dll`
  (which lives in `_internal/ctranslate2/`) can find the CUDA DLLs at
  `_internal/`. The Windows loader does NOT search the bundle root on its own.
- Verify GPU after a build by checking the log for:
  `Model warmup complete: loaded on device=cuda`
- Bundle size: the default cuBLAS-only GPU build is **~1.06 GB** (cuBLAS DLLs
  ~735 MB). A CPU-only build (no `nvidia-*` packages) is also ~1 GB. Adding
  cuDNN back via `JV_CUDNN=1` pushes it to ~2 GB.

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

## Installer + auto-update (Inno Setup + GitHub Releases)

The end-user distribution is a Discord-style installer plus an in-app updater.
PyInstaller still produces the bundle; the installer wraps it.

### One-command release
```powershell
.\scripts\build_release.ps1
```
Runs PyInstaller, compiles `installer\JasperVoice.iss` with Inno Setup (ISCC),
and writes two artifacts to `dist\installer\`:
- `JasperVoice-Setup-<version>.exe` — the per-user installer/bootstrapper.
- `SHA256SUMS` — `<hex>  <installer-name>`, consumed by the updater.

Release flow: bump `__version__`, run the script, create a GitHub Release tagged
`v<version>`, upload **both** files as assets. Done.

### Installer constraints (`installer/JasperVoice.iss`)
- **Per-user** (`PrivilegesRequired=lowest`) → installs under
  `%LocalAppData%\Programs\JasperVoice`, no UAC for install or update.
- `AppMutex` **must** equal `single_instance.MUTEX_NAME`
  (`JasperVoice_SingleInstance_Mutex`). The installer uses it (with
  `CloseApplications=yes`) to close the running app before replacing the locked
  `_internal\*.dll` files during an update. If you rename the mutex in code,
  rename it here too.
- `AppId` is a fixed GUID — never change it, or upgrades won't find the prior
  install and will stack a second copy.
- `[UninstallDelete]` removes only `%APPDATA%\JasperVoice\updates\`; config,
  history, and the downloaded model are intentionally preserved.

### Updater (`updater.py`) — failure-safe contract
- `check_for_update()` hits the GitHub *Releases* API only, matches the
  installer asset by name (`JasperVoice-Setup-*.exe`), and reads `SHA256SUMS`.
- `download_installer()` stages to `%APPDATA%\JasperVoice\updates\`, **refuses
  to proceed without a SHA-256**, verifies the digest, and cleans up partials
  on any failure. `launch_installer()` then hands off to Inno (with
  `/SILENT /RestartApplications` for the silent path).
- Every network/file error raises `UpdateError` (never a raw exception); the UI
  treats that as a soft failure so the app stays usable offline.
- Offline path: `stage_local_installer()` validates a user-provided `.exe`
  (optionally against a supplied SHA-256) with NO network access.
- Config keys `update_check_enabled` (bool) and `update_repo` (`owner/repo`)
  drive it. The default repo is `ynkjohn/JasperVoice`.
- Constraints honored: versioned artifacts only, never raw source, no `git` at
  runtime, no telemetry.

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
- **Keep this file current.** Whenever you add or remove anything that changes
  how the project is built, structured, or behaves (a module, a config key, a
  build flag, a constraint, a dependency), update `AGENTS.md` in the same change
  so it stays the single source of truth for future agents.
- Don't commit `config.json`, `history.json`, logs, `build/`, or `dist/` (see
  `.gitignore`).
