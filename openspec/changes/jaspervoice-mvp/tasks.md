## 1. Project Scaffolding

- [ ] 1.1 Create `src/jaspervoice/` package layout with `__init__.py` and empty module files: `audio.py`, `transcription.py`, `injection.py`, `hotkey.py`, `tray.py`, `config.py`, `app.py`
- [ ] 1.2 Create `requirements.txt` with pinned versions: `PySide6`, `faster-whisper`, `sounddevice`, `keyboard`, `pyperclip`, `numpy`
- [ ] 1.3 Create `pyproject.toml` with package metadata and entry point `jaspervoice = jaspervoice.app:main`
- [ ] 1.4 Create `README.md` documenting: install, first-run model download, hotkey config, known limitations (clipboard overwrite, admin requirement)

## 2. Config Module

- [ ] 2.1 Implement `config.py`: `DEFAULT_CONFIG` dict with hotkey=`ctrl+shift+space`, language=`pt`, model_size=`small`, compute_type=`int8`, device=`auto`, sample_rate=16000
- [ ] 2.2 Implement `get_config_path()` returning `%APPDATA%/JasperVoice/config.json` (cross-platform-safe via `os.path.expandvars` and fallback to `~/.jaspervoice/` on non-Windows)
- [ ] 2.3 Implement `load_config()` returning the validated config dict; on missing file write defaults, on malformed JSON back up and rewrite defaults
- [ ] 2.4 Implement `save_config(cfg)` writing JSON with 2-space indent and atomic rename

## 3. Audio Capture

- [ ] 3.1 Implement `Recorder` class in `audio.py` wrapping `sounddevice.InputStream` at `sample_rate=16000`, mono, dtype=`float32`
- [ ] 3.2 Implement `start()` opening the default input device and appending samples to an internal buffer via callback
- [ ] 3.3 Implement `stop()` closing the stream and returning a `numpy.ndarray` concatenation of the buffer; raise `RuntimeError` if no device
- [ ] 3.4 Handle device-sample-rate mismatch by adding a resampling step (or document as known limitation if skipped)
- [ ] 3.5 Write a `tests/test_audio.py` smoke test that records 1s from the default mic and asserts array length is in expected range

## 4. Transcription

- [ ] 4.1 Implement `Transcriber` class in `transcription.py` taking `(model_size, device, compute_type, language)` in the constructor
- [ ] 4.2 Implement lazy model load on first `transcribe()` call; expose `is_loaded` property
- [ ] 4.3 Implement `transcribe(audio: np.ndarray) -> TranscriptionResult` calling `model.transcribe(audio, language=lang, beam_size=1, vad_filter=True)`
- [ ] 4.4 Implement `device` resolution: `auto` tries `cuda` and falls back to `cpu` on `RuntimeError`/`ValueError`, logging the fallback
- [ ] 4.5 Set `download_root` to `%APPDATA%/JasperVoice/models/` so weights are cached per-app

## 5. Text Injection

- [ ] 5.1 Implement `inject_text(text: str)` in `injection.py`: returns immediately if text is empty
- [ ] 5.2 Use `pyperclip.copy(text)` to set the clipboard
- [ ] 5.3 Use `ctypes` to call `user32.SendInput` synthesizing a Ctrl keydown, V keydown, V keyup, Ctrl keyup
- [ ] 5.4 Add a small sleep (~30ms) between `copy` and `SendInput` to let the clipboard settle
- [ ] 5.5 Wrap `SendInput` calls in a helper `send_paste()` with proper `INPUT` struct definitions

## 6. Global Hotkey (PTT)

- [ ] 6.1 Implement `HotkeyListener` class in `hotkey.py` taking a `keyboard`-style hotkey string and a callback pair `(on_press, on_release)`
- [ ] 6.2 Use `keyboard.hook` (low-level) to detect press and release of the configured combo; ignore auto-repeat
- [ ] 6.3 Debounce: ignore release if total press duration < 200 ms (call `on_release` only when duration >= threshold)
- [ ] 6.4 Implement `start()` and `stop()` to register/unregister the hook; `stop()` must be safe to call multiple times

## 7. Tray UI

- [ ] 7.1 Implement `TrayApp` class in `tray.py` using `PySide6.QtWidgets.QSystemTrayIcon`
- [ ] 7.2 Generate 4 simple icon variants (idle, recording, processing, error) as 16x16 PNGs via `QPainter` at runtime (no asset files needed)
- [ ] 7.3 Build the right-click menu: status label (disabled), separator, language submenu (pt, en, es, auto), separator, "Open config folder" action, separator, "Quit" action
- [ ] 7.4 Implement `set_state(state: Literal['idle','recording','processing','error'])` swapping the icon
- [ ] 7.5 Implement language submenu that updates `config.json` and the in-memory config
- [ ] 7.6 "Open config folder" action: opens `%APPDATA%/JasperVoice/` in Explorer via `os.startfile`
- [ ] 7.7 "Quit" action: emit a signal the app loop catches for clean shutdown

## 8. App Wiring

- [ ] 8.1 Implement `main()` in `app.py`: load config, build `Recorder`, `Transcriber`, `HotkeyListener`, `TrayApp`
- [ ] 8.2 Wire callbacks: `on_press` → `recorder.start()` + `tray.set_state('recording')`; `on_release` → `recorder.stop()` + `tray.set_state('processing')` + run transcription on a worker thread + inject result + `tray.set_state('idle')`
- [ ] 8.3 Use `QThread` (or `threading.Thread` + `QObject.moveToThread`) so inference does not block the Qt event loop
- [ ] 8.4 Handle exceptions in the pipeline: log, set `tray.set_state('error')` briefly, then return to idle
- [ ] 8.5 Run `QApplication.exec()`; on `aboutToQuit` unregister hotkey, stop recorder, join worker

## 9. Verification

- [ ] 9.1 Run `python -m jaspervoice` from a clean checkout; confirm tray icon appears, no exceptions
- [ ] 9.2 First-run test: delete `%APPDATA%/JasperVoice/`, relaunch, confirm model downloads and config is written
- [ ] 9.3 PTT smoke test: open Notepad, hold hotkey, say something, release; confirm text appears in Notepad
- [ ] 9.4 Switch language to `en` via tray menu, repeat PTT test, confirm English transcription
- [ ] 9.5 Inject into VS Code, terminal, browser address bar — all three should accept the paste

## 10. Packaging (stretch, if time)

- [ ] 10.1 Add `pyinstaller` to dev deps; create `jaspervoice.spec` with `--onefile --windowed --name jaspervoice`
- [ ] 10.2 Build and confirm the resulting `.exe` runs without an active Python install
- [ ] 10.3 Document install/uninstall steps in README
