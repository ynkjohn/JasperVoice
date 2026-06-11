"""Shared pytest fixtures for JasperVoice tests."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def _stub_model_warmup(request, monkeypatch):
    """Prevent the TranscriptionWorker model warmup from loading (and possibly
    downloading) a real Whisper model during integration tests.

    The worker thread now calls ``Transcriber._ensure_loaded()`` as its first
    action (eager warmup, so the first real dictation is fast). In tests that
    construct a full ``App`` we don't want that to hit disk or the network.

    Scoped to integration tests only. Unit tests in ``test_transcription.py``
    exercise ``_ensure_loaded`` / ``_try_load`` directly, and ``test_e2e``
    drives a real ``Transcriber`` end-to-end, so both keep real behavior.
    """
    module = request.node.module.__name__ if request.node.module else ""
    if module.endswith("test_integration"):
        from jaspervoice.transcription import Transcriber

        monkeypatch.setattr(
            Transcriber, "_ensure_loaded", lambda self: object(), raising=True
        )
    yield
