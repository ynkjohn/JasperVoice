"""Tests for the sound-feedback cues."""

import wave

import pytest

from jaspervoice import sounds


@pytest.fixture(autouse=True)
def appdata(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def played(monkeypatch):
    calls = []
    monkeypatch.setattr(sounds, "_play_file", lambda path: calls.append(path.name))
    return calls


def test_ensure_tone_creates_valid_wav():
    path = sounds.ensure_tone("record_start")
    assert path is not None and path.exists()
    with wave.open(str(path), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == sounds.SAMPLE_RATE
        assert w.getnframes() > 0


def test_ensure_tone_unknown_event_returns_none():
    assert sounds.ensure_tone("nope") is None


def test_off_mode_plays_nothing(played):
    for state in ("recording", "processing", "send", "error"):
        assert sounds.play_state_cue(state, "off") is False
    assert played == []


def test_subtle_mode_plays_start_and_stop_only(played):
    assert sounds.play_state_cue("recording", "subtle") is True
    assert sounds.play_state_cue("processing", "subtle") is True
    assert sounds.play_state_cue("send", "subtle") is False
    assert sounds.play_state_cue("error", "subtle") is False
    assert played == ["record_start.wav", "record_stop.wav"]


def test_all_mode_plays_every_event(played):
    for state in ("recording", "processing", "send", "error"):
        assert sounds.play_state_cue(state, "all") is True
    assert played == ["record_start.wav", "record_stop.wav", "sent.wav", "error.wav"]


def test_idle_state_has_no_cue(played):
    assert sounds.play_state_cue("idle", "all") is False
    assert played == []


def test_invalid_mode_is_silent(played):
    assert sounds.play_state_cue("recording", "loud") is False
    assert played == []


def test_play_failure_is_swallowed(monkeypatch):
    def boom(path):
        raise RuntimeError("no audio device")

    monkeypatch.setattr(sounds, "_play_file", boom)
    assert sounds.play_state_cue("recording", "all") is False
