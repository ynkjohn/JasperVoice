"""Local Whisper transcription via faster-whisper (CTranslate2)."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    text: str
    language: str
    duration: float  # seconds of audio processed


class TranscriberError(RuntimeError):
    """Raised when the model cannot be loaded or transcription fails."""


class Transcriber:
    """Lazy-loaded faster-whisper wrapper with device auto-resolution.

    The model is downloaded on first use to `download_root` (defaults to the
    app's models dir). `device="auto"` tries CUDA first, falls back to CPU
    if cuDNN is missing.
    """

    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: str = "pt",
        download_root: Optional[Path] = None,
    ):
        self._requested_model_size = model_size
        self._requested_device = device
        self._compute_type = compute_type
        self._language = (language or "auto").lower()
        self._download_root = Path(download_root) if download_root else None

        self._model = None
        self._resolved_device: Optional[str] = None
        self._load_lock = threading.Lock()

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def resolved_device(self) -> Optional[str]:
        return self._resolved_device

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        self._language = (language or "auto").lower()

    def _try_load(self, device: str) -> "object":
        from faster_whisper import WhisperModel  # local import: heavy

        kwargs = {"device": device, "compute_type": self._compute_type}
        if self._download_root is not None:
            kwargs["download_root"] = str(self._download_root)
        log.info(
            "Loading faster-whisper model=%s device=%s compute_type=%s",
            self._requested_model_size, device, self._compute_type,
        )
        return WhisperModel(self._requested_model_size, **kwargs)

    def _ensure_loaded(self) -> "object":
        if self._model is not None:
            return self._model
        with self._load_lock:
            if self._model is not None:
                return self._model
            devices = ["cuda", "cpu"] if self._requested_device == "auto" else [self._requested_device]
            last_err: Optional[Exception] = None
            for dev in devices:
                try:
                    self._model = self._try_load(dev)
                    self._resolved_device = dev
                    if self._requested_device == "auto" and dev == "cpu":
                        log.warning("CUDA unavailable; running on CPU")
                    return self._model
                except Exception as e:
                    last_err = e
                    log.warning("Failed to load model on %s: %s", dev, e)
            raise TranscriberError(
                f"Could not load faster-whisper model on any device: {last_err}"
            )

    def transcribe(self, audio: np.ndarray, sample_rate: int = 16000) -> TranscriptionResult:
        if audio is None or audio.size == 0:
            return TranscriptionResult(text="", language=self._language, duration=0.0)
        model = self._ensure_loaded()
        lang = None if self._language in ("auto", "") else self._language
        try:
            return self._do_transcribe(model, audio, lang, sample_rate)
        except Exception as e:
            if self._requested_device == "auto" and self._resolved_device == "cuda":
                log.warning(
                    "CUDA transcription failed: %s. Falling back to CPU.", e
                )
                return self._retry_on_cpu(audio, lang, sample_rate, e)
            raise TranscriberError(f"Transcription failed: {e}") from e

    def _do_transcribe(self, model, audio, lang, sample_rate) -> TranscriptionResult:
        segments, info = model.transcribe(
            audio,
            language=lang,
            beam_size=1,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 300},
        )
        text_parts = [seg.text.strip() for seg in segments]
        text = " ".join(p for p in text_parts if p).strip()
        return TranscriptionResult(
            text=text,
            language=getattr(info, "language", self._language),
            duration=float(getattr(info, "duration", audio.size / float(sample_rate))),
        )

    def _retry_on_cpu(self, audio, lang, sample_rate, original_error):
        with self._load_lock:
            self._model = None
            self._resolved_device = None
        try:
            cpu_model = self._try_load("cpu")
            self._resolved_device = "cpu"
            self._model = cpu_model
            return self._do_transcribe(cpu_model, audio, lang, sample_rate)
        except Exception as cpu_err:
            raise TranscriberError(
                f"Transcription failed on CUDA ({original_error}) and CPU retry also failed ({cpu_err})"
            ) from cpu_err
