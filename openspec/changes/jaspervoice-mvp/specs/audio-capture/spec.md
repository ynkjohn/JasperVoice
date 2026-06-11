## ADDED Requirements

### Requirement: Microphone Recording Lifecycle
The system SHALL capture audio from the default input device when recording is started, and SHALL stop capturing when recording is stopped. Audio SHALL be delivered as mono 16-bit PCM at 16 kHz (resampled if device native rate differs).

#### Scenario: Start recording
- **WHEN** `recorder.start()` is called
- **THEN** the input stream opens on the default device and a background buffer begins accumulating samples

#### Scenario: Stop recording
- **WHEN** `recorder.stop()` is called
- **THEN** the input stream closes and the accumulated audio is returned as a single `numpy.ndarray` of dtype `float32` in range [-1.0, 1.0]

#### Scenario: Device not available
- **WHEN** `recorder.start()` is called and no input device exists
- **THEN** a `RuntimeError` is raised with a clear message naming the missing device

#### Scenario: Short recording discarded
- **WHEN** `recorder.stop()` is called and total duration is under 200 ms
- **THEN** the returned audio array length corresponds to the actual recorded duration (caller decides whether to discard)
