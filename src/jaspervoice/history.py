"""Transcription history — stores recent transcriptions on disk.

Each entry: {text, timestamp, word_count, duration_s, mode}
Mode is "push_to_talk" or "toggle" so the user can see how they activated.
History is stored in %APPDATA%/JasperVoice/history.json, capped at MAX_ENTRIES.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone

from .config import get_app_dir

log = logging.getLogger(__name__)

MAX_ENTRIES = 200
HISTORY_FILENAME = "history.json"


def _word_count(text: str) -> int:
    return len(text.split()) if text else 0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HistoryEntry:
    __slots__ = ("text", "timestamp", "word_count", "duration_s", "mode")

    def __init__(self, text: str, timestamp: str, word_count: int, duration_s: float, mode: str):
        self.text = text
        self.timestamp = timestamp
        self.word_count = word_count
        self.duration_s = duration_s
        self.mode = mode

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "timestamp": self.timestamp,
            "word_count": self.word_count,
            "duration_s": self.duration_s,
            "mode": self.mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "HistoryEntry":
        return cls(
            text=d.get("text", ""),
            timestamp=d.get("timestamp", ""),
            word_count=d.get("word_count", 0),
            duration_s=d.get("duration_s", 0.0),
            mode=d.get("mode", "push_to_talk"),
        )


class TranscriptionHistory:
    """Thread-safe history manager. Saves to disk on every add()."""

    def __init__(self, max_entries: int = MAX_ENTRIES):
        self._max = max_entries
        self._entries: list[HistoryEntry] = []
        self._lock = threading.Lock()
        self._path = get_app_dir() / HISTORY_FILENAME
        self._load()

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            with self._path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                return
            self._entries = [HistoryEntry.from_dict(e) for e in data if isinstance(e, dict)]
            self._entries = self._entries[-self._max:]
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load history: %s", e)

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            data = [e.to_dict() for e in self._entries]
            tmp = self._path.with_suffix(".json.tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                f.write("\n")
            tmp.replace(self._path)
        except OSError as e:
            log.error("Failed to save history: %s", e)

    def add(self, text: str, duration_s: float = 0.0, mode: str = "push_to_talk") -> None:
        if not text:
            return
        entry = HistoryEntry(
            text=text,
            timestamp=_now_iso(),
            word_count=_word_count(text),
            duration_s=round(duration_s, 2),
            mode=mode,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self._max:
                self._entries = self._entries[-self._max:]
            self._save()

    def entries(self) -> list[HistoryEntry]:
        with self._lock:
            return list(self._entries)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()
            self._save()

    @property
    def total_words(self) -> int:
        with self._lock:
            return sum(e.word_count for e in self._entries)

    @property
    def total_duration_s(self) -> float:
        with self._lock:
            return round(sum(e.duration_s for e in self._entries), 2)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._entries)
