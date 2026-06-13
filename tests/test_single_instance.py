"""Tests for the single-instance guard.

On non-Windows CI the guard is a no-op that always acquires; on Windows it uses
a named kernel mutex. We test the platform-agnostic contract and the Windows
"already running" path via a light ctypes stub.
"""

from __future__ import annotations

import sys

import pytest

from jaspervoice.single_instance import SingleInstance, MUTEX_NAME, _ERROR_ALREADY_EXISTS
from jaspervoice import single_instance


def test_acquire_returns_true_on_non_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    g = SingleInstance()
    assert g.acquire() is True
    g.release()


def test_mutex_name_is_stable():
    # The installer's AppMutex must match this exactly.
    assert MUTEX_NAME == "JasperVoice_SingleInstance_Mutex"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex path")
def test_first_instance_acquires_real_mutex():
    g = SingleInstance(name="JasperVoice_Test_Mutex_First")
    try:
        assert g.acquire() is True
    finally:
        g.release()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows-only mutex path")
def test_second_instance_is_blocked():
    name = "JasperVoice_Test_Mutex_Second"
    first = SingleInstance(name=name)
    second = SingleInstance(name=name)
    try:
        assert first.acquire() is True
        # Same name, second handle sees ERROR_ALREADY_EXISTS.
        assert second.acquire() is False
    finally:
        first.release()
        second.release()


def test_guard_fails_open_on_error(monkeypatch):
    """If the Win32 call throws, the guard must allow launch (fail open)."""
    monkeypatch.setattr(sys, "platform", "win32")

    g = SingleInstance()

    # Force the ctypes import inside acquire() to blow up.
    import builtins

    real_import = builtins.__import__

    def boom(name, *args, **kwargs):
        if name == "ctypes":
            raise RuntimeError("simulated")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom)
    assert g.acquire() is True


def test_acquire_tracks_active_instance(monkeypatch):
    """acquire() registers the guard as the process-wide active instance so
    release_active() can free the named mutex before launching the updater."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(single_instance, "_active_instance", None)
    g = SingleInstance()
    assert g.acquire() is True
    assert single_instance._active_instance is g
    g.release()
    assert single_instance._active_instance is None


def test_release_active_is_safe_with_no_guard(monkeypatch):
    """release_active() must be a no-op (never raise) when nothing is held."""
    monkeypatch.setattr(single_instance, "_active_instance", None)
    single_instance.release_active()  # should not raise


def test_release_active_releases_held_guard(monkeypatch):
    """release_active() releases the currently-held guard (the updater path)."""
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(single_instance, "_active_instance", None)
    g = SingleInstance()
    g.acquire()
    assert single_instance._active_instance is g
    single_instance.release_active()
    assert single_instance._active_instance is None
    assert g._acquired is False
