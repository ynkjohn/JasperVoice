import time

import numpy as np
import pytest

from jaspervoice.audio import Recorder, RecorderError


def _has_input_device() -> bool:
    try:
        import sounddevice as sd
        default = sd.default.device[0]
        return default is not None and default >= 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_input_device(), reason="No microphone available in this environment"
)


def test_record_short_clip_returns_float32_array():
    rec = Recorder(sample_rate=16000)
    rec.start()
    time.sleep(0.5)
    audio = rec.stop()
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.ndim == 1
    assert 7000 < audio.size < 10000  # ~0.5s with tolerance


def test_double_start_is_idempotent():
    rec = Recorder()
    rec.start()
    try:
        rec.start()  # must not raise
        assert rec.is_active
    finally:
        rec.stop()


def test_stop_when_inactive_returns_empty():
    rec = Recorder()
    audio = rec.stop()
    assert audio.size == 0


def test_cancel_clears_buffer():
    rec = Recorder()
    rec.start()
    time.sleep(0.2)
    rec.cancel()
    assert not rec.is_active
    audio = rec.stop()
    assert audio.size == 0


def test_start_with_invalid_device_raises():
    rec = Recorder(device="__nonexistent_device__")
    with pytest.raises(RecorderError):
        rec.start()


# --- _compute_bands (no microphone required) ---

def test_compute_bands_returns_7_values():
    audio = np.random.default_rng(42).normal(0, 0.5, 16000).astype(np.float32)
    bands = Recorder._compute_bands(audio, sample_rate=16000)
    assert len(bands) == 7
    assert all(0.0 <= b <= 1.0 for b in bands)


def test_compute_bands_silence_returns_zeros():
    audio = np.zeros(16000, dtype=np.float32)
    bands = Recorder._compute_bands(audio, sample_rate=16000)
    assert all(b == 0.0 for b in bands)


def test_compute_bands_short_audio_returns_zeros():
    audio = np.zeros(10, dtype=np.float32)
    bands = Recorder._compute_bands(audio, sample_rate=16000)
    assert all(b == 0.0 for b in bands)
