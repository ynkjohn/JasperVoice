# JasperVoice

Local push-to-talk voice dictation for Windows. Hold a hotkey, speak, release — your words land in whatever app has focus. Whisper runs entirely on your machine by default. No subscription, no telemetry.

## Features

- **Global push-to-talk hotkey** (default `Ctrl+Shift+Space`)
- **Toggle mode** — press once to start, again to stop (alternative to hold-to-talk)
- **Local Whisper transcription** via `faster-whisper` (offline, private)
- **GPU acceleration** — CUDA support in both the dev run and the standalone build
- **Universal text injection** — works in any app that accepts Ctrl+V
- **Animated overlay** — a floating pill with a live audio spectrum while you speak
- **Transcription history & statistics** — words, audio time, average WPM
- **Developer dictionary** — offline phrase corrections for technical terms
- **Optional AI post-processing** via any OpenAI-compatible API (with in-app model discovery)
- **Sound feedback** — optional quiet tones on recording start/stop, send, and error
- **System tray control** with language switching
- **Private by default** — audio never leaves your machine; text leaves only if you enable optional post-processing

## Quick start

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m jaspervoice
```

First run downloads the Whisper `small` model (~460 MB) to `%APPDATA%/JasperVoice/models/`.

## Standalone app (no terminal)

To run JasperVoice by double-clicking instead of launching from the terminal,
build a windowed executable with PyInstaller:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\pyinstaller.exe jaspervoice.spec --noconfirm
```

Output lands in `dist/JasperVoice/`. Launch `dist/JasperVoice/JasperVoice.exe` —
it boots straight to the system tray with no console window. Make a Desktop or
Start Menu shortcut to `JasperVoice.exe` for one-click access.

Notes:

- The build is a **one-folder** bundle. Keep `JasperVoice.exe` next to its
  `_internal/` folder; moving the exe alone will break it. To relocate, move
  the whole `JasperVoice` folder.
- **Bundle size depends on GPU support.** The default GPU build bundles cuBLAS
  (about 735 MB by itself), producing a one-folder bundle around 1.1 GB and a
  compressed installer around 514 MB. Without `nvidia-*` packages the build is
  CPU-only and omits the CUDA DLLs. See [GPU acceleration](#gpu-acceleration).
- The Whisper model is **not** bundled. It still downloads on first run to
  `%APPDATA%/JasperVoice/models/`, exactly like the dev workflow.
- Logs go to `%APPDATA%/JasperVoice/jaspervoice.log` (rotating) since the
  windowed build has no console to print to.

## Installer & updates

For a Discord-style experience — download a single installer, run it, and the
app behaves like a normal Windows application — JasperVoice ships an
[Inno Setup](https://jrsoftware.org/isinfo.php) installer plus an in-app
updater backed by GitHub Releases.

### Build a release

```powershell
# Requires Inno Setup 6. The script auto-detects PATH, Program Files,
# and winget's per-user install path.
.venv\Scripts\pip.exe install -r requirements-dev.txt
.\scripts\build_release.ps1
```

This runs PyInstaller, compiles the installer, and emits two artifacts to
`dist\installer\`:

- `JasperVoice-Setup-<version>.exe` — the installer/bootstrapper.
- `SHA256SUMS` — the checksum the in-app updater verifies before applying.

Publish a GitHub Release tagged `v<version>` and upload **both** files as
assets. That is the entire release flow — bump `__version__`, build, upload.

### How the installer behaves

- **Per-user install** (`%LocalAppData%\Programs\JasperVoice` by default) — no
  admin prompt for install or updates.
- Creates Start Menu and (optional) Desktop shortcuts. An optional checkbox
  adds a per-user **autostart** entry (Startup folder, no registry hacks).
- Settings, history, and the downloaded model live under
  `%APPDATA%\JasperVoice\` and are **preserved across updates and uninstalls**.
- Only one instance runs at a time (a named mutex shared with the installer so
  an update can close the running app before replacing files).

### Updating

Tray → **Check for updates...** (or Settings → Updates → *Check now*). The app
queries the configured GitHub repo's latest release, and if a newer version
exists it downloads the installer, **verifies its SHA-256**, then launches it.
The installer closes JasperVoice, replaces the files in place, and relaunches.

- **Failure-safe:** if the update check or download fails (offline, GitHub
  down, checksum mismatch), the running app is untouched and keeps working.
- **Versioned artifacts only:** the updater downloads the published installer
  asset, never raw source code, and never runs `git`.
- **No telemetry:** the only network call is to the public GitHub API and the
  asset URL, and only when you trigger a check (or enable check-on-startup).
- **Offline / air-gapped:** Settings → Updates → **Install from file...** runs
  an installer `.exe` you downloaded by hand. It is integrity-checked before
  running.

Disable the optional startup check entirely in Settings → Updates.

## Configuration

Edit `%APPDATA%/JasperVoice/config.json`:

```json
{
  "hotkey": "ctrl+shift+space",
  "hotkey_mode": "push_to_talk",
  "language": "pt",
  "model_size": "small",
  "compute_type": "int8",
  "device": "auto",
  "sample_rate": 16000,
  "paste_delay_ms": 15,
  "min_recording_ms": 200
}
```

Everything is also editable in the in-app window (tray → Settings…): a
navigable sidebar with Overview, History, Dictionary, General, Audio & Mic,
Model & Engine, AI Polish, Updates, and Diagnostics pages, plus a settings
search. Changes apply live on **Apply**; dictionary and history edits are
saved immediately. Available languages: `pt`, `en`, `es`, `auto` (and any
ISO 639-1 code).

### Hotkey modes

- `push_to_talk` (default): hold the hotkey to record, release to transcribe.
- `toggle`: press once to start recording, press again to stop. A short tap is
  ignored (debounced) so an accidental press won't start a take.

### History & statistics

Every transcription is stored locally in
`%APPDATA%/JasperVoice/history.json` (capped at 200 entries) with its word
count, audio duration, and the mode used. Open tray → **Statistics…** (or the
**History** page in the main window) to see totals, average words-per-minute,
and a searchable, filterable table of recent transcriptions with per-row copy
and delete. **Export…** writes the history to a JSON file of your choice;
**Clear** wipes it after confirmation.

### Developer Dictionary

The dictionary is a local, offline list of phrase→replacement mappings. It corrects spoken technical terms before optional OpenCode post-processing.

```json
{
  "dictionary": [
    {"phrase": "open code", "replacement": "OpenCode"},
    {"phrase": "use effect", "replacement": "useEffect"},
    {"phrase": "fast api", "replacement": "FastAPI"},
    {"phrase": "tail wind", "replacement": "Tailwind"}
  ]
}
```

Matching is case-insensitive, respects word boundaries, and applies longer phrases first. Replacements run entirely on your machine.

Rules can also be managed on the **Dictionary** page of the main window (add,
delete, enable/disable per rule, JSON import/export). A rule with
`"enabled": false` is kept but not applied; entries without the key are
enabled.

### AI Polish (post-processing)

Optionally refine dictation with **any OpenAI-compatible API** after Whisper —
local (Ollama, LM Studio, vLLM) or remote (OpenRouter, OpenCode, cloud). The
**AI Polish** page configures everything: provider, endpoint, API key env-var
name, output style, a **Test** button that diagnoses your setup locally (no
network — it reports whether the endpoint is filled in and whether the API key
env var is actually set in JasperVoice's process), and a **Fetch models** button
that queries the provider's `/v1/models` list so you can pick a Fast and a Smart
model. Put a variable name such as `OPENCODE_API_KEY` in the app, not the raw
`sk-...` key; the key itself is never stored. The equivalent `config.json` keys:

```json
{
  "post_processing_enabled": true,
  "post_processing_provider": "opencode",
  "output_mode": "prompt",
  "opencode_base_url": "https://your-api.example.com",
  "opencode_api_key_env": "OPENCODE_API_KEY",
  "opencode_fast_model": "DeepSeek V4 Flash",
  "opencode_smart_model": "Qwen3.7 Max",
  "opencode_timeout_s": 20
}
```

Set `OPENCODE_API_KEY` in your environment and restart JasperVoice so the
process can see it. If Polish returns 401/403, click **Test** to confirm the
env var is visible to the app. Only the transcribed text is sent — never audio.
The dictionary runs first, so corrected terms reach the API.

## GPU acceleration

JasperVoice runs on your NVIDIA GPU when CUDA is available, in both the dev run
and the standalone build.

### Dev run

GPU "just works" if the CUDA runtime packages are installed in your venv:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

With `"device": "auto"`, `transcription.py` tries CUDA first and falls back to
CPU if loading fails. Set `"device": "cuda"` to force GPU (errors will surface
instead of silently falling back), or `"device": "cpu"` to force CPU. On GPU,
`"compute_type": "float16"` is the recommended setting.

The **Model & Engine** page probes your hardware and shows a friendly
recommendation ("On this PC, GPU (CUDA) with float16 is recommended" / "CPU
with int8 is the best option"). It also manages the local Whisper models:
download any size ahead of time (in the background, without freezing the app)
or remove an installed model from disk.

### Standalone build

The PyInstaller build **bundles the CUDA runtime DLLs** when the `nvidia-*`
packages are present in the venv at build time (see `_collect_cuda_dlls()` in
`jaspervoice.spec`). A runtime hook (`scripts/rthook_cuda.py`) makes those DLLs
discoverable by `ctranslate2.dll` inside the bundle. After building, confirm GPU
is active by checking the log for:

```
Model warmup complete: loaded on device=cuda
```

If the `nvidia-*` packages are absent, the build falls back to a smaller
CPU-only bundle automatically.

### Runtime fallback

Even with `device="auto"`, if CUDA model loading succeeds but actual
transcription fails at runtime, the app falls back to CPU and retries the take,
so a single dictation is never lost.

Without GPU, `small` int8 on a modern Intel i5 takes ~1-2s per 5s audio clip —
fine for push-to-talk. For light local testing, use `"device": "cpu"` and
`"model_size": "tiny"`.

## Known limitations

- **Clipboard is overwritten** on every transcription. If you had something copied, it's gone. Restore is a planned v1.1 feature.
- **Global hotkey may require admin** on first run (Windows low-level keyboard hook). If PTT does not register, run from an elevated terminal.
- **Antivirus warnings** about the `keyboard` library are false positives — it's open-source and does not exfiltrate.
- **Single instance**: a named mutex prevents a second copy from running (a second launch shows a tray notice and exits). Use the tray "Quit" to close.

## Architecture

```
config.py          JSON config at %APPDATA%/JasperVoice/ (validated, atomic writes)
audio.py           sounddevice InputStream → numpy array; 7-band FFT for the overlay
transcription.py   faster-whisper with CUDA/CPU auto-fallback
injection.py       clipboard + SendInput Ctrl+V
hotkey.py          push-to-talk / toggle state machine on top of `keyboard` lib
history.py         thread-safe transcription history (JSON, capped at 200)
postprocessing.py  optional OpenCode/OpenAI-compatible text polish
dictionary.py      offline phrase→replacement corrections
tray.py            QSystemTrayIcon with state icons + language/settings/stats/update menu
overlay.py         frameless floating pill indicator (animated, state-colored)
ui.py              navigable main window shell (sidebar/search/pages) + UpdateDialog
ui_pages.py        the window's pages (Overview, History, Dictionary, …)
ui_widgets.py      shared UI primitives (Switch, SegmentedControl, LevelMeter, …)
single_instance.py named-mutex guard used by the app and installer
updater.py         GitHub Releases update check/download/verify/launch flow
assets.py          icon path resolution for dev and frozen runs
app_gui.py         frozen/windowed entry point with file logging
theme.py           dark QSS + STATE_COLORS palette
app.py             wires it all together
```

Each module is small and replaceable. See `openspec/changes/jaspervoice-mvp/`
for the original design rationale.
