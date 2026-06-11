## ADDED Requirements

### Requirement: Floating Recording Indicator
The system SHALL display a frameless, top-most, transparent 48px circular window (the "overlay") that reflects the current pipeline state. The overlay SHALL be positioned at the bottom-right corner of the primary screen with a 16px margin.

#### Scenario: Overlay hidden when idle
- **WHEN** the pipeline state is `idle`
- **THEN** the overlay window is hidden (not shown on screen)

#### Scenario: Overlay visible during recording
- **WHEN** the pipeline state is `recording`
- **THEN** the overlay window is shown and painted with the recording colors (border `#A23E48`, fill `#D14E5A`, inner dot `#E66A78`)

#### Scenario: Overlay visible during processing
- **WHEN** the pipeline state is `processing`
- **THEN** the overlay window is shown and painted with the processing colors (border `#8C6B2A`, fill `#B8893E`, inner dot `#D49A6E`)

#### Scenario: Overlay visible on error
- **WHEN** the pipeline state is `error`
- **THEN** the overlay window is shown and painted with the error colors (border `#8B2A2A`, fill `#B23A3A`) and a white `X` mark in the center

#### Scenario: Pulse animation while recording
- **WHEN** the pipeline state is `recording` for more than 100 ms
- **THEN** the overlay's window opacity SHALL animate between 0.4 and 1.0 with an 800ms period, looping until the state leaves `recording`

#### Scenario: Left click opens settings
- **WHEN** the user left-clicks the overlay
- **THEN** the settings window is shown and brought to the foreground

#### Scenario: Right click shows context menu
- **WHEN** the user right-clicks the overlay
- **THEN** a context menu with "Settings..." and "Quit" items is shown at the cursor position
