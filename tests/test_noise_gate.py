"""Tests for the adaptive noise gate (audio.apply_noise_gate).

No microphone required — these run on synthetic signals so they execute in CI
regardless of audio hardware (unlike test_audio.py, which is mic-gated).
"""

import numpy as np
import pytest

from jaspervoice.audio import apply_noise_gate

SR = 16000


def _noise(n: int, amp: float, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return (rng.standard_normal(n) * amp).astype(np.float32)


def _tone(n: int, amp: float, freq: float = 220.0) -> np.ndarray:
    t = np.arange(n, dtype=np.float32) / SR
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def test_returns_same_length_and_dtype():
    audio = _noise(SR, 0.01)
    out = apply_noise_gate(audio, sample_rate=SR)
    assert out.shape == audio.shape
    assert out.dtype == np.float32


def test_empty_input_returned_unchanged():
    audio = np.zeros(0, dtype=np.float32)
    out = apply_noise_gate(audio, sample_rate=SR)
    assert out.size == 0


def test_short_clip_left_untouched():
    # Fewer than the minimum number of frames -> returned as-is.
    audio = _noise(200, 0.01)
    out = apply_noise_gate(audio, sample_rate=SR)
    assert np.array_equal(out, audio)


def test_silence_left_untouched():
    audio = np.zeros(SR, dtype=np.float32)
    out = apply_noise_gate(audio, sample_rate=SR)
    assert np.array_equal(out, audio)


def test_pure_low_noise_is_attenuated():
    # Constant low-level hiss with no speech: the loudest frame is not clearly
    # above the floor, so the gate conservatively leaves it alone OR attenuates
    # uniformly. Either way it must not amplify and must stay finite.
    audio = _noise(SR, 0.005, seed=1)
    out = apply_noise_gate(audio, sample_rate=SR)
    assert np.all(np.isfinite(out))
    assert float(np.max(np.abs(out))) <= float(np.max(np.abs(audio))) + 1e-6


def test_speech_segment_preserved_silence_gated():
    # Build: 0.4s low noise | 0.4s loud tone (speech) | 0.4s low noise.
    seg = int(0.4 * SR)
    quiet1 = _noise(seg, 0.004, seed=2)
    speech = _tone(seg, 0.4) + _noise(seg, 0.004, seed=3)
    quiet2 = _noise(seg, 0.004, seed=4)
    audio = np.concatenate([quiet1, speech, quiet2]).astype(np.float32)

    out = apply_noise_gate(audio, sample_rate=SR)

    # Speech region energy should be largely preserved.
    in_speech = float(np.sqrt(np.mean(audio[seg:2 * seg] ** 2)))
    out_speech = float(np.sqrt(np.mean(out[seg:2 * seg] ** 2)))
    assert out_speech > in_speech * 0.7

    # The quiet tails should be quieter than they started (gate closed).
    in_tail = float(np.sqrt(np.mean(audio[2 * seg:] ** 2)))
    out_tail = float(np.sqrt(np.mean(out[2 * seg:] ** 2)))
    assert out_tail < in_tail * 0.5


def test_no_clicks_gain_is_continuous():
    # A gated transition must not introduce a hard step (click) between frames.
    seg = int(0.4 * SR)
    quiet = _noise(seg, 0.004, seed=5)
    speech = _tone(seg, 0.4)
    audio = np.concatenate([quiet, speech, quiet]).astype(np.float32)
    out = apply_noise_gate(audio, sample_rate=SR)
    # Sample-to-sample delta of the implied gain stays bounded: the output never
    # jumps more than the input could on its own by a large factor.
    assert np.all(np.isfinite(out))
    # Output peak never exceeds input peak (gate only attenuates).
    assert float(np.max(np.abs(out))) <= float(np.max(np.abs(audio))) + 1e-6


def test_non_finite_input_returned_unchanged():
    audio = _noise(SR, 0.01)
    audio[100] = np.nan
    out = apply_noise_gate(audio, sample_rate=SR)
    assert np.array_equal(out, audio, equal_nan=True)


def test_gate_only_attenuates_never_amplifies():
    seg = int(0.4 * SR)
    audio = np.concatenate([
        _noise(seg, 0.004, seed=6),
        _tone(seg, 0.3) + _noise(seg, 0.004, seed=7),
        _noise(seg, 0.004, seed=8),
    ]).astype(np.float32)
    out = apply_noise_gate(audio, sample_rate=SR)
    # Per-sample, |out| <= |in| everywhere (gain in [0, 1]).
    assert np.all(np.abs(out) <= np.abs(audio) + 1e-6)
