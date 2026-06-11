# JasperVoice

Local push-to-talk voice dictation for Windows. Hold a hotkey, speak, release — your words land in whatever app has focus. Whisper runs entirely on your machine. No cloud, no subscription, no telemetry.

## Features

- **Global push-to-talk hotkey** (default `Ctrl+Shift+Space`)
- **Toggle mode** — press once to start, again to stop (alternative to hold-to-talk)
- **Local Whisper transcription** via `faster-whisper` (offline, private)
- **GPU acceleration** — CUDA support in both the dev run and the standalone build
- **Universal text injection** — works in any app that accepts Ctrl+V
- **Animated overlay** — a floating pill with a live audio spectrum while you speak
- **Transcription history & statistics** — words, audio time, average WPM
- **Developer dictionary** — offline phrase corrections for technical terms
- **Optional AI post-processing** via an OpenAI-compatible API
- **System tray control** with language switching
- **No data leaves your machine**

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m jaspervoice
```

First run downloads the Whisper `small` model (~460 MB) to `%APPDATA%/JasperVoice/models/`.

## Standalone app (no terminal)

To run JasperVoice by double-clicking instead of launching from the terminal,
build a windowed executable with PyInstaller:

```bash
pip install -r requirements-dev.txt
pyinstaller jaspervoice.spec --noconfirm
```

Output lands in `dist/JasperVoice/`. Launch `dist/JasperVoice/JasperVoice.exe` —
it boots straight to the system tray with no console window. Make a Desktop or
Start Menu shortcut to `JasperVoice.exe` for one-click access.

Notes:

- The build is a **one-folder** bundle. Keep `JasperVoice.exe` next to its
  `_internal/` folder; moving the exe alone will break it. To relocate, move
  the whole `JasperVoice` folder.
- **Bundle size depends on GPU support.** If the `nvidia-*` CUDA packages are
  installed in your venv, the build bundles the CUDA runtime and the folder is
  ~3 GB (cuBLAS alone is ~735 MB). Without those packages it produces a
  CPU-only bundle of ~1 GB. See [GPU acceleration](#gpu-acceleration).
- The Whisper model is **not** bundled. It still downloads on first run to
  `%APPDATA%/JasperVoice/models/`, exactly like the dev workflow.
- Logs go to `%APPDATA%/JasperVoice/jaspervoice.log` (rotating) since the
  windowed build has no console to print to.

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

Most settings also live in the in-app **Settings** window (tray → Settings…),
which applies changes live. Available languages: `pt`, `en`, `es`, `auto` (and
any ISO 639-1 code).

### Hotkey modes

- `push_to_talk` (default): hold the hotkey to record, release to transcribe.
- `toggle`: press once to start recording, press again to stop. A short tap is
  ignored (debounced) so an accidental press won't start a take.

### History & statistics

Every transcription is stored locally in
`%APPDATA%/JasperVoice/history.json` (capped at 200 entries) with its word
count, audio duration, and the mode used. Open tray → **Statistics…** to see
totals, average words-per-minute, and a table of recent transcriptions. Use
**Clear history** in that window to wipe it.

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

### OpenCode Post-Processing

Optionally refine dictation with an OpenAI-compatible API after Whisper:

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

Set `OPENCODE_API_KEY` in your environment. Only the transcribed text is sent — never audio. The dictionary runs first, so corrected terms reach the API.

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
- **Single instance**: launching twice will fight for the hotkey. Use the tray "Quit" to close.

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
tray.py            QSystemTrayIcon with state icons + language/settings/stats menu
overlay.py         frameless floating pill indicator (animated, state-colored)
ui.py              SettingsWindow + StatsWindow (card-based dark UI)
theme.py           dark QSS + STATE_COLORS palette
app.py             wires it all together
```

Each module is small and replaceable. Working on the code with an AI agent? See
`AGENTS.md` for conventions and the non-obvious threading/animation constraints.
See `openspec/changes/jaspervoice-mvp/` for the original design rationale.
