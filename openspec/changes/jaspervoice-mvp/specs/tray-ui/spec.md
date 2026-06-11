## ADDED Requirements

### Requirement: System Tray Icon and Menu
The system SHALL display a system tray icon while running. The tray icon SHALL reflect the current state (idle, recording, processing, error). A right-click menu SHALL provide: status text, current model and language, language submenu, "Open config folder" action, and "Quit" action.

#### Scenario: Idle state
- **WHEN** the application is running and no recording or processing is active
- **THEN** the tray icon is the idle variant and the menu status reads "JasperVoice — idle"

#### Scenario: Recording state
- **WHEN** a recording is in progress
- **THEN** the tray icon is the recording variant (e.g., red) and the menu status reads "JasperVoice — recording"

#### Scenario: Processing state
- **WHEN** a recording has ended and transcription is running
- **THEN** the tray icon is the processing variant (e.g., spinner or yellow) and the menu status reads "JasperVoice — transcribing"

#### Scenario: Error state
- **WHEN** any pipeline step fails
- **THEN** the tray icon is the error variant (e.g., red exclamation) and the menu status includes a short error message; the state returns to idle within 5 seconds or on user menu interaction

#### Scenario: Language selection
- **WHEN** the user selects a language from the language submenu
- **THEN** the configuration is updated and the new language is used for the next transcription

#### Scenario: Quit
- **WHEN** the user selects "Quit" from the tray menu
- **THEN** the global hotkey listener is unregistered, the recorder is stopped, and the process exits with code 0
