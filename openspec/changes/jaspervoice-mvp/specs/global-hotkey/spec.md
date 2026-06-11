## ADDED Requirements

### Requirement: Global Push-to-Talk Hotkey
The system SHALL listen for a configurable global hotkey (default `ctrl+shift+space`). When the hotkey is pressed, the system SHALL start recording. When the hotkey is released, the system SHALL stop recording and trigger the transcription → injection pipeline.

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
- **THEN** the system logs a warning on startup indicating the conflict; the user is expected to reconfigure via `config.json`

#### Scenario: Hotkey change requires restart
- **WHEN** the hotkey is changed in `config.json`
- **THEN** the new hotkey takes effect on the next application launch
