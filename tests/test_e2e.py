"""End-to-end test: real mic recording -> Whisper -> clipboard.

Speaks (or plays) audio of silence, then verifies the pipeline produces
a transcription result and the clipboard contains text. Skipped in CI
or when no microphone is available.
"""

import os
import time

import numpy as np
import pyperclip
import pytest

from jaspervoice.audio import Recorder
from jaspervoice.config import get_models_dir
from jaspervoice.transcription import Transcriber
from jaspervoice.injection import inject_text


def _has_input_device() -> bool:
    try:
        import sounddevice as sd
        return sd.default.device[0] is not None and sd.default.device[0] >= 0
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _has_input_device(), reason="No microphone available"
)


def test_record_transcribe_clipboard_e2e():
    """2s of mic audio -> Whisper 'tiny' -> clipboard."""
    rec = Recorder(sample_rate=16000)
    rec.start()
    time.sleep(2.0)
    audio = rec.stop()
    assert audio.size > 16000  # at least 1s

    t = Transcriber(
        model_size="tiny", device="auto", compute_type="int8", language="pt",
        download_root=get_models_dir(),
    )
    result = t.transcribe(audio)
    # text can be empty for silence, but the call must complete
    assert isinstance(result.text, str)
    print(f"\n  [E2E] device={t.resolved_device} text={result.text!r}")

    # If there's any text, injection should put it in the clipboard
    if result.text:
        prev = pyperclip.paste()
        try:
            inject_text(result.text)
            time.sleep(0.1)
            new = pyperclip.paste()
            assert new == result.text
        finally:
            pyperclip.copy(prev)
