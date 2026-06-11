## ADDED Requirements

### Requirement: Settings Window
The system SHALL provide a non-modal settings window (800×560 default, 640×520 minimum) that exposes all user-configurable values. The window SHALL be styled in a dark theme and SHALL have four sections: General, Whisper, Behavior, Diagnostics.

#### Scenario: Window opens from tray or overlay
- **WHEN** the user activates the "Settings..." menu item in the tray OR left-clicks the overlay
- **THEN** the settings window is shown and brought to the foreground

#### Scenario: Close button hides instead of exits
- **WHEN** the user clicks the window's close (X) button
- **THEN** the window is hidden and the application keeps running

#### Scenario: Cancel discards changes
- **WHEN** the user clicks "Cancel" with unsaved changes
- **THEN** all form fields revert to the last applied values and the Apply button becomes disabled

#### Scenario: Apply persists and emits change signal
- **WHEN** the user clicks "Apply" with at least one field changed
- **THEN** the new config is written to `config.json` and a `configChanged(dict)` signal is emitted with the new config

#### Scenario: Apply button reflects dirty state
- **WHEN** no form field has changed since the last Apply/Cancel
- **THEN** the Apply button is disabled

#### Scenario: Sections render
- **WHEN** the window is shown
- **THEN** the user can see four labeled sections: "General" (hotkey, language), "Whisper" (model, device, compute), "Behavior" (paste delay, min recording duration), "Diagnostics" (config path, model path, version, mic test)

### Requirement: Hotkey Capture and Conversion
The system SHALL capture the hotkey combination via a `QKeySequenceEdit` widget. The captured Qt-format sequence SHALL be converted to `keyboard`-library format (lowercase tokens joined by `+`) before being written to config, and the reverse conversion SHALL populate the widget from existing config.

#### Scenario: Capture stores keyboard format
- **WHEN** the user enters `Ctrl+Shift+R` in the hotkey field and clicks Apply
- **THEN** `config.json` contains `"hotkey": "ctrl+shift+r"`

#### Scenario: Display loads from keyboard format
- **WHEN** the window opens and config contains `"hotkey": "ctrl+shift+r"`
- **THEN** the hotkey field shows the Qt sequence `Ctrl+Shift+R`

#### Scenario: All standard tokens supported
- **WHEN** the config contains any of `ctrl`, `shift`, `alt`, `meta`, `space`, `tab`, `enter`, `esc`, `escape`, `backspace`, `delete`, `home`, `end`, `pgup`, `pgdown`, `pageup`, `pagedown`, `up`, `down`, `left`, `right`, `f1`..`f24`, or any single letter/digit
- **THEN** the conversion to Qt format produces the correct title-cased sequence (e.g. `pgup` → `PgUp`, `ctrl` → `Ctrl`)

### Requirement: Live Apply (No Restart)
The system SHALL apply all settings changes without restarting the application. When config changes via Apply, the application SHALL restart the global hotkey listener (if the hotkey changed), recreate the `Transcriber` (if model/device/compute changed), and update the transcriber's language.

#### Scenario: Hotkey change applies live
- **WHEN** the user changes the hotkey and clicks Apply
- **THEN** the previous global keyboard hook is unregistered and a new one is registered with the new combo, all without user-visible interruption

#### Scenario: Model change applies on next transcription
- **WHEN** the user changes the model size to a different value and clicks Apply
- **THEN** the next `transcribe()` call loads the new model; no transcription is triggered immediately

#### Scenario: Language change applies immediately
- **WHEN** the user changes the language and clicks Apply
- **THEN** the active `Transcriber`'s language is updated and the next transcription uses the new language

#### Scenario: Settings window does not interrupt recording
- **WHEN** the user is mid-recording (hotkey held) and clicks Apply
- **THEN** the current recording completes normally; the in-flight pipeline uses the old config; subsequent uses use the new config
