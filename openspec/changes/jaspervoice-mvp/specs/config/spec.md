## ADDED Requirements

### Requirement: JSON Configuration
The system SHALL persist user configuration as a JSON file at `%APPDATA%/JasperVoice/config.json` on Windows. On startup, the system SHALL load this file if present, or create one with default values otherwise.

#### Scenario: First run
- **WHEN** the application starts and `config.json` does not exist
- **THEN** a default config is written to `%APPDATA%/JasperVoice/config.json` and loaded into memory

#### Scenario: Load existing config
- **WHEN** the application starts and `config.json` exists and is valid JSON matching the schema
- **THEN** the values from the file are used

#### Scenario: Invalid config
- **WHEN** the application starts and `config.json` exists but is malformed JSON
- **THEN** the system backs up the malformed file to `config.json.bak`, writes a fresh default config, and logs a warning

#### Scenario: Config schema
- **WHEN** the config is loaded
- **THEN** it contains the keys: `hotkey` (string), `language` (string, ISO 639-1), `model_size` (one of `tiny`, `base`, `small`, `medium`, `large-v3`), `compute_type` (one of `int8`, `int16`, `float16`, `float32`), `device` (one of `auto`, `cpu`, `cuda`), `sample_rate` (integer)

#### Scenario: Runtime reload not required
- **WHEN** the config file is edited externally while the app is running
- **THEN** the change is NOT applied to the running instance; it takes effect on next launch (documented behavior)
