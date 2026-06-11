## ADDED Requirements

### Requirement: Text Injection via Clipboard Paste
The system SHALL inject transcribed text into whichever application currently has keyboard focus by writing the text to the system clipboard and then synthesizing a Ctrl+V keypress via `SendInput`.

#### Scenario: Successful injection
- **WHEN** `inject_text("hello world")` is called
- **THEN** the clipboard contains "hello world" and a Ctrl+V keypress is sent to the focused window

#### Scenario: Empty text
- **WHEN** `inject_text("")` is called
- **THEN** no clipboard write and no keypress are performed

#### Scenario: No focused window
- **WHEN** `inject_text("hello")` is called and no window has focus (e.g., desktop is active)
- **THEN** the clipboard is still updated but the keypress is a no-op

#### Scenario: Previous clipboard is overwritten
- **WHEN** the clipboard previously contained other content
- **THEN** that content is replaced (MVP does not restore; documented behavior)
