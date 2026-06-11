## ADDED Requirements

### Requirement: Local Whisper Transcription
The system SHALL transcribe audio to text using a local `faster-whisper` model. The model SHALL be loaded once on first use and reused for subsequent transcriptions. No network calls SHALL be made in steady state.

#### Scenario: First-time model load
- **WHEN** `Transcriber` is instantiated and the model weights are not yet cached locally
- **THEN** the model is downloaded to the configured cache directory and loaded into memory; progress is reported via a callback

#### Scenario: Cached model load
- **WHEN** `Transcriber` is instantiated and the model weights are already cached
- **THEN** the model is loaded from local cache without network access

#### Scenario: Successful transcription
- **WHEN** `transcriber.transcribe(audio)` is called with a non-empty audio array
- **THEN** a `TranscriptionResult` containing the transcribed text and detected (or configured) language is returned within 5 seconds for a 10-second audio clip on CPU

#### Scenario: Empty audio
- **WHEN** `transcriber.transcribe(empty_array)` is called
- **THEN** a `TranscriptionResult` with empty text is returned (no exception)

#### Scenario: Device fallback
- **WHEN** `device="auto"` is configured and CUDA initialization fails (e.g., cuDNN missing)
- **THEN** the system logs a warning and continues with CPU inference
