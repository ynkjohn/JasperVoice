# Development and releases

## Run from source

From the repository root, use Python 3.11 or newer on Windows.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
.venv\Scripts\python.exe -m jaspervoice
```

Configuration is in `%APPDATA%\JasperVoice\config.json`. Use **General** to change the hotkey or language. The `device` setting accepts `auto`, `cpu`, and `cuda`. With `auto`, JasperVoice tries CUDA first and retries on CPU if GPU inference fails.

## Test and build

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q --ignore=tests/test_e2e.py
.venv\Scripts\pyinstaller.exe jaspervoice.spec --noconfirm
```

The standalone build is at `dist\JasperVoice\JasperVoice.exe`. Keep `_internal` beside the executable. For an NVIDIA CUDA build, install the CUDA runtime packages before packaging. The spec bundles cuBLAS when available.

```powershell
.venv\Scripts\python.exe -m pip install nvidia-cublas-cu12
```

## Build an installer

Install Inno Setup 6, update `__version__` in `src/jaspervoice/__init__.py`, then run the installer build.

```powershell
.\scripts\build_release.ps1
```

Publish both `JasperVoice-Setup-<version>.exe` and `SHA256SUMS` from `dist\installer\` under the corresponding GitHub Release tag. The updater requires both files.

## Project structure

- `audio.py`, `hotkey.py`, and `overlay.py` handle capture, hotkeys, and feedback.
- `transcription.py`, `dictionary.py`, and `postprocessing.py` implement Whisper, local replacements, and optional AI Polish.
- `injection.py` and `voice_commands.py` handle output and configured actions.
- `ui.py`, `ui_pages.py`, and `ui_widgets.py` implement the desktop UI.
- `updater.py` verifies and launches GitHub Release installers.
