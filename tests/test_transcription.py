"""Smoke tests for the Transcriber. Downloads model on first run (~460MB)."""

import numpy as np
import pytest

from jaspervoice.transcription import Transcriber, TranscriberError
from jaspervoice.config import get_models_dir


def test_empty_audio_returns_empty_text():
    t = Transcriber(model_size="tiny", device="cpu", compute_type="int8", language="pt",
                    download_root=get_models_dir())
    # We force lazy load: empty audio should NOT trigger model download
    r = t.transcribe(np.zeros(0, dtype=np.float32))
    assert r.text == ""
    assert not t.is_loaded


def test_silence_audio_returns_empty_or_low_text():
    t = Transcriber(model_size="tiny", device="cpu", compute_type="int8", language="en",
                    download_root=get_models_dir())
    # 1s of near-silence at 16kHz
    audio = (np.random.default_rng(0).normal(0, 0.001, 16000)).astype(np.float32)
    r = t.transcribe(audio)
    assert isinstance(r.text, str)
    # Tiny model on silence can return stray tokens; we just assert it ran
    assert r.duration > 0.5


def test_device_auto_falls_back_gracefully(tmp_path, caplog):
    """If CUDA is missing, auto must fall back to cpu without raising."""
    import logging
    caplog.set_level(logging.WARNING)
    t = Transcriber(model_size="tiny", device="auto", compute_type="int8", language="pt",
                    download_root=tmp_path)
    audio = np.zeros(16000, dtype=np.float32)
    r = t.transcribe(audio)
    assert t.resolved_device in ("cpu", "cuda")
    assert r.text == "" or isinstance(r.text, str)


def test_set_language_changes_value():
    t = Transcriber(language="pt")
    assert t.language == "pt"
    t.set_language("EN")
    assert t.language == "en"
    t.set_language("")
    assert t.language == "auto"


def test_auto_falls_back_to_cpu_when_transcription_fails_on_cuda(tmp_path, monkeypatch, caplog):
    """When device='auto' resolves to CUDA but actual transcription fails,
    it must retry on CPU and succeed."""
    import logging
    from unittest.mock import MagicMock

    caplog.set_level(logging.WARNING)

    cuda_load_calls = []
    cpu_load_calls = []

    def make_segments(text):
        class Seg:
            def __init__(self, t):
                self.text = t
        return iter([Seg(text)])

    def make_info(lang="en", duration=0.5):
        class Info:
            pass
        info = Info()
        info.language = lang
        info.duration = duration
        return info

    cuda_model = MagicMock()
    cuda_model.transcribe = MagicMock(side_effect=RuntimeError("Library cublas64_12.dll is not found"))

    cpu_model = MagicMock()
    cpu_model.transcribe = MagicMock(return_value=(make_segments("  cpu result  "), make_info()))

    def controlled_try_load(self, device):
        if device == "cuda":
            cuda_load_calls.append(1)
            return cuda_model
        else:
            cpu_load_calls.append(1)
            return cpu_model

    monkeypatch.setattr(Transcriber, "_try_load", controlled_try_load)

    t = Transcriber(model_size="tiny", device="auto", compute_type="int8", language="en", download_root=tmp_path)
    audio = np.zeros(16000, dtype=np.float32)
    r = t.transcribe(audio)

    assert r.text == "cpu result"
    assert t.resolved_device == "cpu"
    assert len(cuda_load_calls) >= 1
    assert len(cpu_load_calls) >= 1
    assert "CUDA transcription failed" in caplog.text


def test_explicit_cuda_does_not_fallback(tmp_path, monkeypatch):
    """When device='cuda', transcription failure must propagate, not fallback."""
    from unittest.mock import MagicMock

    cuda_model = MagicMock()
    cuda_model.transcribe = MagicMock(side_effect=RuntimeError("cuda fail"))

    monkeypatch.setattr(Transcriber, "_try_load", lambda self, device: cuda_model)

    t = Transcriber(model_size="tiny", device="cuda", compute_type="int8", language="en", download_root=tmp_path)
    audio = np.zeros(16000, dtype=np.float32)

    with pytest.raises(TranscriberError, match="Transcription failed"):
        t.transcribe(audio)


def test_empty_audio_no_model_load_on_fallback(tmp_path, monkeypatch):
    """Empty audio must still short-circuit and never trigger fallback logic."""
    load_attempts = []

    def fake_load(self, device):
        load_attempts.append(device)
        raise RuntimeError("fail")

    monkeypatch.setattr(Transcriber, "_try_load", fake_load)
    t = Transcriber(model_size="tiny", device="auto", compute_type="int8", language="en", download_root=tmp_path)
    r = t.transcribe(np.zeros(0, dtype=np.float32))
    assert r.text == ""
    assert len(load_attempts) == 0
