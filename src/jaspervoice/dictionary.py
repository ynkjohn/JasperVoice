"""Local, offline developer dictionary — replaces spoken phrases with exact
technical terms before optional OpenCode post-processing.

Runs entirely on the machine. No cloud call, no API involved.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Union

log = logging.getLogger(__name__)


@dataclass
class DictionaryEntry:
    phrase: str
    replacement: str
    enabled: bool = True


class DeveloperDictionary:
    """Case-insensitive phrase replacer. Applies longer phrases first to
    avoid partial-replacement conflicts (e.g. "react query" before "react").

    Patterns are compiled once at construction time. ``apply()`` is on the
    hot path (runs on every transcription), so it must not recompile regexes.
    """

    def __init__(
        self,
        entries: Optional[list[Union[dict, DictionaryEntry]]] = None,
    ) -> None:
        self._entries: list[DictionaryEntry] = []
        self._compiled: list[tuple[re.Pattern[str], str]] = []
        if entries is not None:
            parsed = sorted(self._parse_entries(entries), key=lambda e: -len(e.phrase))
            self._entries = parsed
            # Disabled rules are kept in _entries (so callers can list them)
            # but never compiled, so apply() ignores them.
            self._compiled = [
                (
                    re.compile(rf"(?<!\w){re.escape(e.phrase)}(?!\w)", re.IGNORECASE),
                    e.replacement,
                )
                for e in parsed
                if e.enabled
            ]

    @staticmethod
    def _parse_entries(raw: list) -> list[DictionaryEntry]:
        parsed: list[DictionaryEntry] = []
        for item in raw:
            entry = DeveloperDictionary._parse_single(item)
            if entry is not None:
                parsed.append(entry)
        return parsed

    @staticmethod
    def _parse_single(item) -> Optional[DictionaryEntry]:
        if isinstance(item, DictionaryEntry):
            phrase = item.phrase.strip()
            replacement = item.replacement.strip()
            enabled = bool(item.enabled)
        elif isinstance(item, dict):
            phrase = str(item.get("phrase", "")).strip()
            replacement = str(item.get("replacement", "")).strip()
            enabled = bool(item.get("enabled", True))
        else:
            log.warning("Skipping invalid dictionary entry: %r", item)
            return None
        if not phrase or not replacement:
            log.warning("Skipping dictionary entry with empty phrase or replacement: %r", item)
            return None
        return DictionaryEntry(phrase=phrase, replacement=replacement, enabled=enabled)

    def apply(self, text: str) -> str:
        """Apply all dictionary replacements to `text`.

        Matching is case-insensitive and respects word boundaries so that
        sub-words are not accidentally replaced.
        Returns the text unchanged if it is empty or there are no entries.
        """
        if not text or not self._compiled:
            return text
        result = text
        for pattern, replacement in self._compiled:
            result = pattern.sub(replacement, result)
        return result
