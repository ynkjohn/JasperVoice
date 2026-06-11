## 1. Theme Module

- [ ] 1.1 Create `src/jaspervoice/theme.py` with `COLORS` dict (bg, bg_alt, border, border_strong, fg, fg_muted, accent, state palette) and `FONTS` dict (mono, sans)
- [ ] 1.2 Add `STYLESHEET` constant with full QSS for QMainWindow, QLabel, QPushButton, QLineEdit, QComboBox, QSpinBox, QKeySequenceEdit, QRadioButton, QCheckBox, QFormLayout
- [ ] 1.3 Add `apply_theme(app)` helper that installs the stylesheet and forces dark palette
- [ ] 1.4 Test in `tests/test_theme.py`: assert all expected classes are styled, palette is dark

## 2. Hotkey Hot-Reload

- [ ] 2.1 Modify `src/jaspervoice/hotkey.py` `start()`: if `self._running`, call `self.stop()` first
- [ ] 2.2 Add test in `tests/test_hotkey.py`: `test_double_start_unregisters_previous` — call `start()` twice with different combos, verify only one hook is registered and it matches the second combo
- [ ] 2.3 Add test: `test_stop_when_not_running_is_noop` — call `stop()` on fresh listener, no exception

## 3. Recording Overlay

- [ ] 3.1 Create `src/jaspervoice/overlay.py` with `RecordingOverlay(QWidget)`
- [ ] 3.2 Set frameless, top-most, tool window flags; translucent background; fixed 48px size
- [ ] 3.3 Implement `paintEvent` drawing the circle + inner dot (or X for error) with state-specific colors
- [ ] 3.4 Implement `set_state(state)`: hide in idle, show + paint in other states; manage pulse animation
- [ ] 3.5 Pulse: `QPropertyAnimation` on `windowOpacity` looping 0.4 ↔ 1.0 every 800ms, started on entering `recording`, stopped on leaving
- [ ] 3.6 Position in bottom-right of primary screen with 16px margin via `QGuiApplication.primaryScreen().availableGeometry()`
- [ ] 3.7 `mousePressEvent`: left → emit `clicked`, right → show context menu (Settings..., Quit)
- [ ] 3.8 Add `clicked` and `settingsRequested` signals
- [ ] 3.9 Tests in `tests/test_overlay.py`: initial state is hidden; set_state("recording") shows window; set_state("idle") hides; click event emits correct signal; position is bottom-right of primary screen

## 4. Settings Window

- [ ] 4.1 Create `src/jaspervoice/ui.py` with `SettingsWindow(QMainWindow)`
- [ ] 4.2 Implement `keyboard_to_qt(s)` using `split("+")` + explicit token title map (handles `pgup`→`PgUp`, `ctrl`→`Ctrl`, etc.) + `QKeySequence`
- [ ] 4.3 Implement `qt_to_keyboard(seq)` using `seq.toString().lower()` (no `.replace("+", ", ")`)
- [ ] 4.4 Build four sections with `QFormLayout` and `_section_label()` helper (uppercase mono with underline border)
- [ ] 4.5 Wire General section: `QKeySequenceEdit` (hotkey), `QComboBox` (language)
- [ ] 4.6 Wire Whisper section: `QButtonGroup` of radio buttons for model_size, device, compute_type
- [ ] 4.7 Wire Behavior section: `QSpinBox` for paste_delay (0-200ms) and min_duration_ms (50-2000ms)
- [ ] 4.8 Wire Diagnostics section: read-only labels for config path, model path, app version; "Open config folder" push button
- [ ] 4.9 Footer: "Cancel" and "Apply" buttons. Apply is `default` + `primary` and disabled by default
- [ ] 4.10 Implement `_load_values_into_ui(self)` blocking all input signals during population, then reset `_dirty = False` and disable Apply
- [ ] 4.11 Implement `_collect_values()` reading from UI back into a config dict
- [ ] 4.12 Implement `_on_apply`: collect, write to `self._cfg`, `save_config`, emit `configChanged`, set `_dirty=False`, disable Apply
- [ ] 4.13 Implement `_on_cancel`: reload values, set `_dirty=False`, disable Apply
- [ ] 4.14 `closeEvent`: ignore event, call `hide()`
- [ ] 4.15 Add `configChanged = Signal(dict)`
- [ ] 4.16 Tests in `tests/test_ui.py`: defaults load correctly; change + Apply emits signal with new values; Cancel reverts; X hides; keyboard_to_qt handles all standard tokens; qt_to_keyboard roundtrips; signals are blocked during initial load

## 5. Tray Integration

- [ ] 5.1 Modify `src/jaspervoice/tray.py`: add `settings_requested = Signal()`
- [ ] 5.2 In `_build_menu`, add "Settings..." `QAction` that emits the signal, inserted before the separator before "Quit"
- [ ] 5.3 Test in `tests/test_tray.py`: assert settings action exists and triggers signal

## 6. App Wiring

- [ ] 6.1 Modify `src/jaspervoice/app.py`: import `parse_hotkey` from `hotkey`, import `RecordingOverlay` from `overlay`, import `SettingsWindow` from `ui`, import `apply_theme` from `theme`
- [ ] 6.2 In `setup`: call `apply_theme(self._qt)` before constructing widgets
- [ ] 6.3 In `setup`: construct `self._overlay = RecordingOverlay()`, connect `clicked` and `settingsRequested` to `self._show_settings`
- [ ] 6.4 In `setup`: construct `self._settings = SettingsWindow(self._cfg)`, connect `configChanged` to `self._on_config_changed`
- [ ] 6.5 In `setup`: connect `self._tray.settings_requested` to `self._show_settings`
- [ ] 6.6 Update `_on_press`, `_on_release`, `_on_worker_finished`, `_on_worker_failed`, `_on_worker_state` to call `self._overlay.set_state(...)` matching the tray
- [ ] 6.7 Add `_show_settings()` method: show, raise, activateWindow on `self._settings`
- [ ] 6.8 Add `_on_config_changed(new_cfg)`: assign `self._cfg = new_cfg`; if hotkey changed, stop old listener and construct new; if model/device/compute changed, recreate `self._transcriber` (defer model load); update language via `set_language`
- [ ] 6.9 In `_shutdown`: hide overlay, close settings window
- [ ] 6.10 Integration test in `tests/test_integration.py`: instantiate App; verify overlay and settings are constructed; verify changing hotkey via mocked signal triggers listener recreation

## 7. Verification

- [ ] 7.1 Run `pytest tests/ -v` — all previous (28) + new tests (~12) green
- [ ] 7.2 Manual smoke: launch app; verify tray + overlay created; open settings from tray; change hotkey to `ctrl+shift+r`; click Apply; press new hotkey; verify transcription still works
- [ ] 7.3 Manual smoke: open settings, change language, close; verify subsequent transcriptions use new language
- [ ] 7.4 Manual smoke: close settings window with X, verify app keeps running and tray menu still has Quit
