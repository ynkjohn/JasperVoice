"""Tests for TranscriptionHistory."""

from jaspervoice.history import TranscriptionHistory


def test_add_and_entries(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory()
    h.add("hello world", duration_s=2.5, mode="push_to_talk")
    h.add("foo bar baz", duration_s=3.0, mode="toggle")
    assert h.count == 2
    assert h.total_words == 5
    assert h.total_duration_s == 5.5
    entries = h.entries()
    assert entries[0].text == "hello world"
    assert entries[1].text == "foo bar baz"


def test_persists_to_disk(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory()
    h.add("saved text", duration_s=1.0)
    h2 = TranscriptionHistory()
    assert h2.count == 1
    assert h2.entries()[0].text == "saved text"


def test_max_entries_capped(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory(max_entries=5)
    for i in range(10):
        h.add(f"entry {i}", duration_s=0.5)
    assert h.count == 5
    entries = h.entries()
    assert entries[0].text == "entry 5"
    assert entries[4].text == "entry 9"


def test_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory()
    h.add("to be cleared")
    assert h.count == 1
    h.clear()
    assert h.count == 0
    h2 = TranscriptionHistory()
    assert h2.count == 0


def test_empty_text_not_added(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory()
    h.add("")
    assert h.count == 0


def test_wpm_calculation(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    h = TranscriptionHistory()
    h.add("one two three four five", duration_s=10.0)
    # 5 words / (10s / 60) = 30 WPM
    assert h.total_words == 5
    assert h.total_duration_s == 10.0
    avg_wpm = h.total_words / (h.total_duration_s / 60.0)
    assert abs(avg_wpm - 30.0) < 0.1
