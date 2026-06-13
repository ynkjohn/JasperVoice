"""Audio capture from the default microphone via sounddevice."""

from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

NUM_BANDS = 7
BAND_EDGES = [80, 200, 400, 800, 1600, 3200, 6400, 16000]  # Hz


def apply_noise_gate(
    audio: np.ndarray,
    sample_rate: int = 16000,
    *,
    frame_ms: float = 20.0,
    open_ratio: float = 3.0,
    close_ratio: float = 1.8,
    floor_percentile: float = 10.0,
) -> np.ndarray:
    """Attenuate low-energy (background-noise) frames in a mono recording.

    Why: a soft constant hiss (fan, AC, mic self-noise) between words can make
    Whisper hallucinate filler tokens. A gate silences frames whose energy sits
    near the recording's own noise floor while leaving speech untouched.

    The gate is adaptive: it estimates the noise floor from the quietest frames
    of THIS take (so it works across mics/levels), then opens above
    ``floor * open_ratio`` and closes below ``floor * close_ratio`` (hysteresis,
    so it doesn't chatter on word boundaries). The resulting frame-level gain
    envelope is linearly interpolated to per-sample gain — continuous, so there
    are no click artifacts at frame edges.

    Returns a new float32 array the same length as ``audio``. Conservative by
    design: if the clip is too short, silent, or has no clear floor/speech
    separation, the input is returned unchanged.
    """
    if audio is None or audio.size == 0:
        return audio
    x = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not np.all(np.isfinite(x)):
        return audio

    frame_len = max(1, int(sample_rate * frame_ms / 1000.0))
    n_frames = x.size // frame_len
    if n_frames < 4:
        # Too short to estimate a floor reliably; leave it alone.
        return audio

    used = n_frames * frame_len
    frames = x[:used].reshape(n_frames, frame_len)
    frame_rms = np.sqrt(np.mean(frames.astype(np.float64) ** 2, axis=1))

    peak = float(frame_rms.max())
    if peak < 1e-5:
        # Essentially silent — nothing useful to gate.
        return audio

    floor = float(np.percentile(frame_rms, floor_percentile))
    open_thr = floor * open_ratio
    close_thr = floor * close_ratio
    # If the loudest frame isn't clearly above the floor, there's no reliable
    # speech/noise separation — don't risk clipping. Require ~6 dB of headroom.
    if peak < open_thr or peak < floor * 2.0:
        return audio

    # Hysteresis gate over frames: open above open_thr, stay open until we drop
    # below close_thr. A short release hold keeps the gate open briefly after
    # speech so trailing consonants aren't clipped.
    release_frames = max(1, int(round(60.0 / frame_ms)))  # ~60 ms hold
    gate = np.zeros(n_frames, dtype=np.float32)
    is_open = False
    hold = 0
    for i in range(n_frames):
        r = frame_rms[i]
        if r >= open_thr:
            is_open = True
            hold = release_frames
        elif is_open and r < close_thr:
            if hold > 0:
                hold -= 1
            else:
                is_open = False
        gate[i] = 1.0 if is_open else 0.0

    if gate.min() == 1.0:
        # Gate never closed — no change needed.
        return audio

    # Interpolate the frame-level gain to per-sample gain at frame centers so
    # the gain is continuous (no step at frame edges => no clicks).
    centers = (np.arange(n_frames, dtype=np.float64) + 0.5) * frame_len
    sample_idx = np.arange(x.size, dtype=np.float64)
    per_sample_gain = np.interp(sample_idx, centers, gate).astype(np.float32)
    return (x * per_sample_gain).astype(np.float32, copy=False)


class RecorderError(RuntimeError):
    """Raised when the recorder cannot start or has no usable device."""


class Recorder:
    """Mono 16 kHz float32 recorder. Buffers samples while active, returns
    a single concatenated numpy array on stop()."""

    def __init__(
        self,
        sample_rate: int = 16000,
        device: Optional[int | str] = None,
        level_callback: Optional[Callable[[list[float]], None]] = None,
    ):
        self.sample_rate = int(sample_rate)
        self._requested_device = device  # None => default
        self._stream: Optional[sd.InputStream] = None
        self._buffer: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._active = False
        self._level_callback = level_callback

    @property
    def is_active(self) -> bool:
        return self._active

    def set_device(self, device: Optional[int | str]) -> None:
        """Change the requested input device (None = system default).
        Takes effect on the next start(); an in-flight recording is untouched."""
        self._requested_device = device

    def _resolve_device(self) -> Optional[int | str]:
        if self._requested_device is not None:
            return self._requested_device
        try:
            default = sd.default.device[0]
        except Exception as e:
            raise RecorderError(f"Cannot query default input device: {e}") from e
        if default is None or default < 0:
            raise RecorderError(
                "No microphone detected. Open Windows Settings > Sound > Input "
                "and verify a microphone is connected and enabled."
            )
        return default

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            log.warning("sounddevice status: %s", status)
        if indata.size == 0:
            return
        with self._lock:
            if self._active:
                audio = indata.copy().reshape(-1).astype(np.float32, copy=False)
                self._buffer.append(audio)
                callback = self._level_callback
        if callback is not None:
            try:
                bands = self._compute_bands(audio, self.sample_rate)
                callback(bands)
            except Exception:
                pass  # never block audio capture on a UI error

    @staticmethod
    def _compute_bands(audio: np.ndarray, sample_rate: int = 16000) -> list[float]:
        """Compute per-band magnitude. Returns NUM_BANDS floats normalized to [0..1]."""
        if audio.size < 64:
            return [0.0] * NUM_BANDS
        window = np.hanning(audio.size)
        fft = np.abs(np.fft.rfft(audio * window))
        freqs = np.fft.rfftfreq(audio.size, 1.0 / sample_rate)
        band_rms: list[float] = []
        for i in range(NUM_BANDS):
            lo = BAND_EDGES[i]
            hi = BAND_EDGES[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if mask.any():
                rms = float(np.sqrt(np.mean(fft[mask] ** 2)))
            else:
                rms = 0.0
            band_rms.append(rms)
        max_val = max(band_rms) if any(band_rms) else 1.0
        if max_val < 1e-6:
            return [0.0] * NUM_BANDS
        return [min(b / max_val, 1.0) for b in band_rms]

    def start(self) -> None:
        if self._active:
            return
        device = self._resolve_device()
        with self._lock:
            self._buffer = []
            self._active = True
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=1,
                dtype="float32",
                device=device,
                callback=self._callback,
            )
            self._stream.start()
            log.info("Recording started on device=%s @ %d Hz", device, self.sample_rate)
        except Exception as e:
            with self._lock:
                self._active = False
                self._buffer = []
            raise RecorderError(f"Failed to start input stream: {e}") from e

    def stop(self) -> np.ndarray:
        if not self._active:
            return np.zeros(0, dtype=np.float32)
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception as e:
            log.warning("Error closing stream: %s", e)
        finally:
            self._stream = None
            with self._lock:
                self._active = False
                chunks = self._buffer
                self._buffer = []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        audio = np.concatenate(chunks).astype(np.float32, copy=False)
        log.info("Recording stopped, %d samples (%.2fs)", audio.size, audio.size / self.sample_rate)
        return audio

    def cancel(self) -> None:
        """Abort recording without returning audio (used for debounced short taps)."""
        if not self._active:
            return
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        finally:
            self._stream = None
            with self._lock:
                self._active = False
                self._buffer = []

    @staticmethod
    def duration_seconds(audio: np.ndarray, sample_rate: int) -> float:
        return audio.size / float(sample_rate) if sample_rate > 0 else 0.0
