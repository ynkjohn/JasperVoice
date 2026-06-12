"""Tests for the GitHub-Releases self-updater.

These tests never touch the network: GitHub responses are stubbed by
monkeypatching ``updater._http_get``, and downloads write local bytes. The
focus is the failure-safe contract — every error path raises ``UpdateError``
(never a raw exception) and integrity is enforced before anything is launched.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from jaspervoice import updater
from jaspervoice.updater import (
    UpdateError,
    UpdateInfo,
    is_newer,
    normalize_version,
    parse_version,
    verify_sha256,
    _parse_shasums,
)


# --- version helpers -------------------------------------------------------

def test_normalize_version_strips_v():
    assert normalize_version("v1.2.3") == "1.2.3"
    assert normalize_version("  V0.1.0 ") == "0.1.0"
    assert normalize_version("2.0") == "2.0"


def test_parse_version_pads_and_ignores_suffix():
    assert parse_version("1.2.3") == (1, 2, 3)
    assert parse_version("v1.2") == (1, 2, 0)
    assert parse_version("3") == (3, 0, 0)
    assert parse_version("1.2.0-rc1") == (1, 2, 0)
    assert parse_version("garbage") == (0, 0, 0)


def test_is_newer():
    assert is_newer("1.2.0", "1.1.9")
    assert is_newer("2.0.0", "1.9.9")
    assert not is_newer("1.0.0", "1.0.0")
    assert not is_newer("0.9.0", "1.0.0")


# --- SHA256SUMS parsing ----------------------------------------------------

def test_parse_shasums_basic():
    h = "a" * 64
    text = f"{h}  JasperVoice-Setup-1.0.0.exe\n"
    parsed = _parse_shasums(text)
    assert parsed["JasperVoice-Setup-1.0.0.exe"] == h


def test_parse_shasums_handles_star_and_blank_lines():
    h = "b" * 64
    text = f"\n# comment\n{h} *Setup.exe\n"
    parsed = _parse_shasums(text)
    assert parsed["Setup.exe"] == h


def test_parse_shasums_rejects_non_hex():
    text = "nothex  Setup.exe\n"
    assert _parse_shasums(text) == {}


# --- verify_sha256 ---------------------------------------------------------

def test_verify_sha256_match(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    digest = hashlib.sha256(b"hello").hexdigest()
    assert verify_sha256(p, digest)
    assert verify_sha256(p, digest.upper())  # case-insensitive


def test_verify_sha256_mismatch(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello")
    assert not verify_sha256(p, "0" * 64)


# --- check_for_update ------------------------------------------------------

def _release_json(tag, assets):
    return json.dumps({"tag_name": tag, "body": "notes", "assets": assets}).encode()


def test_check_for_update_returns_none_when_current(monkeypatch):
    payload = _release_json("v0.0.1", [])
    monkeypatch.setattr(updater, "_http_get", lambda *a, **k: payload)
    # current is higher than remote -> no update
    assert updater.check_for_update(current="1.0.0") is None


def test_check_for_update_finds_installer_and_sha(monkeypatch):
    installer = {
        "name": "JasperVoice-Setup-1.0.0.exe",
        "browser_download_url": "https://example/JasperVoice-Setup-1.0.0.exe",
        "size": 123,
    }
    sums = {
        "name": "SHA256SUMS",
        "browser_download_url": "https://example/SHA256SUMS",
        "size": 80,
    }
    rel = _release_json("v1.0.0", [installer, sums])
    digest = "c" * 64

    def fake_get(url, timeout_s, accept="application/json"):
        if url.endswith("SHA256SUMS"):
            return f"{digest}  JasperVoice-Setup-1.0.0.exe\n".encode()
        return rel

    monkeypatch.setattr(updater, "_http_get", fake_get)
    info = updater.check_for_update(current="0.1.0")
    assert isinstance(info, UpdateInfo)
    assert info.version == "1.0.0"
    assert info.asset_name == "JasperVoice-Setup-1.0.0.exe"
    assert info.sha256 == digest


def test_check_for_update_raises_when_no_installer(monkeypatch):
    rel = _release_json("v1.0.0", [{"name": "notes.txt", "browser_download_url": "x", "size": 1}])
    monkeypatch.setattr(updater, "_http_get", lambda *a, **k: rel)
    with pytest.raises(UpdateError):
        updater.check_for_update(current="0.1.0")


def test_check_for_update_missing_sha_is_not_fatal(monkeypatch):
    installer = {
        "name": "JasperVoice-Setup-1.0.0.exe",
        "browser_download_url": "https://example/JasperVoice-Setup-1.0.0.exe",
        "size": 1,
    }
    rel = _release_json("v1.0.0", [installer])
    monkeypatch.setattr(updater, "_http_get", lambda *a, **k: rel)
    info = updater.check_for_update(current="0.1.0")
    assert info is not None
    assert info.sha256 is None


def test_check_for_update_bad_json_raises(monkeypatch):
    monkeypatch.setattr(updater, "_http_get", lambda *a, **k: b"{not json")
    with pytest.raises(UpdateError):
        updater.check_for_update(current="0.1.0")


# --- download_installer ----------------------------------------------------

def _make_info(url, sha=None, name="JasperVoice-Setup-1.0.0.exe"):
    return UpdateInfo(
        version="1.0.0", tag="v1.0.0", asset_name=name,
        asset_url=url, asset_size=0, sha256=sha, notes="",
    )


def test_download_refuses_without_sha(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    info = _make_info("https://example/x.exe", sha=None)
    with pytest.raises(UpdateError, match="SHA256"):
        updater.download_installer(info)


def test_download_verifies_and_saves(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data = b"installer-bytes"
    digest = hashlib.sha256(data).hexdigest()

    class _Resp:
        def __init__(self): self._d = data; self.headers = {"Content-Length": str(len(data))}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1):
            d, self._d = self._d, b""
            return d

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: _Resp())
    info = _make_info("https://example/x.exe", sha=digest)
    path = updater.download_installer(info)
    assert path.exists()
    assert path.read_bytes() == data


def test_download_detects_tamper(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    data = b"tampered"

    class _Resp:
        def __init__(self): self._d = data; self.headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self, n=-1):
            d, self._d = self._d, b""
            return d

    monkeypatch.setattr(updater.urllib.request, "urlopen", lambda *a, **k: _Resp())
    info = _make_info("https://example/x.exe", sha="d" * 64)  # wrong digest
    with pytest.raises(UpdateError, match="mismatch"):
        updater.download_installer(info)
    # The partial download must be cleaned up.
    assert list(updater.updates_dir().glob("*.part")) == []
    assert not (updater.updates_dir() / info.asset_name).exists()


# --- stage_local_installer -------------------------------------------------

def test_stage_local_installer_missing(tmp_path):
    with pytest.raises(UpdateError, match="not found"):
        updater.stage_local_installer(tmp_path / "nope.exe")


def test_stage_local_installer_wrong_ext(tmp_path):
    p = tmp_path / "thing.txt"
    p.write_text("x")
    with pytest.raises(UpdateError, match="exe"):
        updater.stage_local_installer(p)


def test_stage_local_installer_sha_mismatch(tmp_path):
    p = tmp_path / "Setup.exe"
    p.write_bytes(b"abc")
    with pytest.raises(UpdateError, match="mismatch"):
        updater.stage_local_installer(p, expected_sha256="0" * 64)


def test_stage_local_installer_ok(tmp_path):
    p = tmp_path / "Setup.exe"
    p.write_bytes(b"abc")
    digest = hashlib.sha256(b"abc").hexdigest()
    out = updater.stage_local_installer(p, expected_sha256=digest)
    assert out == p


# --- launch_installer -------------------------------------------------------

def test_launch_installer_missing_raises(tmp_path):
    with pytest.raises(UpdateError, match="missing"):
        updater.launch_installer(tmp_path / "absent.exe")


def test_launch_installer_invokes_popen(monkeypatch, tmp_path):
    p = tmp_path / "Setup.exe"
    p.write_bytes(b"x")
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    updater.launch_installer(p, silent=True)
    assert calls["args"][0] == str(p)
    assert "/SILENT" in calls["args"]
