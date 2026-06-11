## MODIFIED Requirements

### Requirement: Global Push-to-Talk Hotkey
The system SHALL listen for a configurable global hotkey (default `ctrl+shift+space`). When the hotkey is pressed, the system SHALL start recording. When the hotkey is released, the system SHALL stop recording and trigger the transcription → injection pipeline. The hotkey MAY be changed at runtime via the settings UI; the new hotkey takes effect on Apply, without restarting the application.

#### Scenario: Press starts recording
- **WHEN** the hotkey is pressed down
- **THEN** the recorder starts within 50 ms and the tray icon changes to a "recording" visual state

#### Scenario: Release triggers pipeline
- **WHEN** the hotkey is released after being held for at least 200 ms
- **THEN** the recorder stops, audio is sent to the transcriber, and on success the resulting text is injected into the focused window

#### Scenario: Short tap ignored
- **WHEN** the hotkey is pressed and released within 200 ms
- **THEN** no recording, no transcription, no injection occurs (debounce against accidental taps)

#### Scenario: Hotkey conflict
- **WHEN** another application has registered the same global hotkey
- **THEN** the system logs a warning on startup indicating the conflict; the user is expected to reconfigure via the settings UI

#### Scenario: Hotkey change applies on Apply
- **WHEN** the hotkey is changed in the settings UI and the user clicks Apply
- **THEN** the previous global keyboard hook is unregistered and a new hook is registered with the new combo before the next event loop tick; the new hotkey is active immediately

#### Scenario: Hotkey listener start is idempotent
- **WHEN** `HotkeyListener.start()` is called while a hook is already registered
- **THEN** the previous hook is unregistered first, and only one hook is active after the call returns

#### Scenario: Hotkey change via config.json
- **WHEN** the hotkey is changed directly in `config.json` while the app is running
- **THEN** the change is NOT applied to the running instance; it takes effect on next launch (documented behavior)
