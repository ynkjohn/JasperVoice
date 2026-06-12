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
