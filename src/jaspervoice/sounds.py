"""Audible feedback cues for pipeline state changes (config `sound_feedback`).

Short sine tones are generated once into %APPDATA%/JasperVoice/sounds/ and
played asynchronously with winsound, so a cue can never block the UI thread or
the audio pipeline. Everything is failure-safe: a missing audio device or a
write error just means silence.

Modes:
    off     no cues
    subtle  recording started / recording stopped
    all     subtle + sent + error
"""

from __future__ import annotations

import logging
import math
import struct
import sys
import wave
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

SAMPLE_RATE = 22050

# event -> (filename, frequency Hz, duration ms, volume 0..1)
_TONES = {
    "record_start": ("record_start.wav", 880.0, 70, 0.28),
    "record_stop": ("record_stop.wav", 620.0, 70, 0.28),
    "sent": ("sent.wav", 990.0, 90, 0.24),
    "error": ("error.wav", 220.0, 160, 0.30),
}

# pipeline state -> cue event
_STATE_EVENTS = {
    "recording": "record_start",
    "processing": "record_stop",
    "send": "sent",
    "error": "error",
}

_SUBTLE_EVENTS = {"record_start", "record_stop"}


def _sounds_dir() -> Path:
    from .config import get_app_dir

    d = get_app_dir() / "sounds"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write_tone(path: Path, freq: float, duration_ms: int, volume: float) -> None:
    """Render a short sine tone with a fade envelope (no clicks) to a WAV file."""
    n = int(SAMPLE_RATE * duration_ms / 1000)
    fade = max(1, n // 6)
    frames = bytearray()
    for i in range(n):
        env = 1.0
        if i < fade:
            env = i / fade
        elif i > n - fade:
            env = (n - i) / fade
        sample = volume * env * math.sin(2.0 * math.pi * freq * i / SAMPLE_RATE)
        frames += struct.pack("<h", int(sample * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(bytes(frames))


def ensure_tone(event: str) -> Optional[Path]:
    """Return the WAV path for `event`, generating it on first use."""
    spec = _TONES.get(event)
    if spec is None:
        return None
    filename, freq, duration_ms, volume = spec
    try:
        path = _sounds_dir() / filename
        if not path.exists():
            _write_tone(path, freq, duration_ms, volume)
        return path
    except OSError as e:
        log.warning("Could not prepare cue %s: %s", event, e)
        return None


def _play_file(path: Path) -> None:
    if sys.platform != "win32":
        return
    import winsound

    winsound.PlaySound(
        str(path),
        winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
    )


def play_state_cue(state: str, mode: str) -> bool:
    """Play the cue for a pipeline state under the given feedback mode.

    Returns True if a cue was (asynchronously) started. Never raises.
    """
    if mode not in ("subtle", "all"):
        return False
    event = _STATE_EVENTS.get(state)
    if event is None:
        return False
    if mode == "subtle" and event not in _SUBTLE_EVENTS:
        return False
    try:
        path = ensure_tone(event)
        if path is None:
            return False
        _play_file(path)
        return True
    except Exception as e:  # audio must never break the pipeline
        log.warning("Sound cue failed: %s", e)
        return False
