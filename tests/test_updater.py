"""Tests for the GitHub-Releases self-updater.

These tests stub GitHub responses and never touch the network. Downloads
write local bytes, and installer launches are replaced with test doubles.
"""

from __future__ import annotations

import hashlib
import json
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.response import addinfourl

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


@pytest.mark.parametrize("has_manifest", [False, True], ids=["missing-manifest", "missing-entry"])
def test_check_for_update_reports_release_without_installer_checksum(monkeypatch, has_manifest):
    installer = {
        "name": "JasperVoice-Setup-1.0.0.exe",
        "browser_download_url": "https://example/JasperVoice-Setup-1.0.0.exe",
        "size": 1,
    }
    assets = [installer]
    sums_url = "https://example/SHA256SUMS"
    if has_manifest:
        assets.append({"name": "SHA256SUMS", "browser_download_url": sums_url})

    def fake_get(url, timeout_s, accept="application/json"):
        if url == sums_url:
            return f"{'a' * 64}  other-asset.exe\n".encode()
        return _release_json("v1.0.0", assets)

    monkeypatch.setattr(updater, "_http_get", fake_get)
    info = updater.check_for_update(current="0.1.0")
    assert info is not None
    assert info.sha256 is None


def test_check_for_update_bad_json_raises(monkeypatch):
    monkeypatch.setattr(updater, "_http_get", lambda *a, **k: b"{not json")
    with pytest.raises(UpdateError):
        updater.check_for_update(current="0.1.0")


@pytest.mark.parametrize("api_status", [403, 429])
@pytest.mark.parametrize("current", ["1.0.0", "1.1.0"])
def test_check_for_update_uses_public_redirect(monkeypatch, api_status, current):
    repo = "owner/JasperVoice"
    api_url = f"https://api.github.com/repos/{repo}/releases/latest"
    releases_url = f"https://github.com/{repo}/releases"
    latest_url = f"{releases_url}/latest"
    tag = "v1.1.0"
    asset_base = f"{releases_url}/download/{tag}"
    sums_url = f"{asset_base}/SHA256SUMS"
    name = "JasperVoice-Setup-1.1.0.exe"
    digest = "a" * 64
    requested = []

    def fake_urlopen(request, **kwargs):
        url = request.full_url
        requested.append(url)
        if url == api_url:
            raise HTTPError(url, api_status, "Rate limit exceeded", {}, None)
        if url == latest_url:
            return addinfourl(BytesIO(b""), {}, f"{releases_url}/tag/{tag}", 200)
        if url == sums_url:
            sums = f"{digest}  {name}\n".encode()
            return addinfourl(BytesIO(sums), {}, url, 200)
        pytest.fail(f"Unexpected update request: {url}")

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    info = updater.check_for_update(repo=repo, current=current)

    if current == "1.1.0":
        assert info is None
        assert requested == [api_url, latest_url]
    else:
        assert info is not None
        assert (info.version, info.tag) == ("1.1.0", tag)
        assert info.asset_name == name
        assert info.asset_url == f"{asset_base}/{name}"
        assert info.sha256 == digest
        assert requested == [api_url, latest_url, sums_url]


def test_check_for_update_reports_api_and_public_page_unavailable(monkeypatch):
    def fake_urlopen(request, **kwargs):
        url = request.full_url
        if url.startswith("https://api.github.com/"):
            raise HTTPError(url, 503, "Service Unavailable", {}, None)
        if url.startswith("https://github.com/") and url.endswith("/releases/latest"):
            raise URLError("Connection unavailable")
        pytest.fail(f"Unexpected update request: {url}")

    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(UpdateError, match="public GitHub release page") as exc:
        updater.check_for_update(current="1.0.0")
    assert "HTTP 503" in str(exc.value)


# --- download_installer ----------------------------------------------------

def _make_info(url, sha=None, name="JasperVoice-Setup-1.0.0.exe"):
    return UpdateInfo(
        version="1.0.0", tag="v1.0.0", asset_name=name,
        asset_url=url, asset_size=0, sha256=sha, notes="",
    )


def test_download_refuses_without_sha(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))

    def unexpected_download(*args, **kwargs):
        pytest.fail("Download started without a checksum")

    monkeypatch.setattr(updater.urllib.request, "urlopen", unexpected_download)
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


@pytest.mark.parametrize("sums", [None, "malformed  Setup.exe\n"], ids=["missing", "invalid"])
def test_stage_local_installer_requires_checksum(tmp_path, sums):
    installer = tmp_path / "Setup.exe"
    installer.write_bytes(b"installer-bytes")
    if sums is not None:
        installer.with_name("SHA256SUMS").write_text(sums, encoding="utf-8")

    with pytest.raises(UpdateError, match="SHA256SUMS"):
        updater.stage_local_installer(installer)


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


def test_launch_installer_refuses_missing_checksum(monkeypatch, tmp_path):
    installer = tmp_path / "Setup.exe"
    installer.write_bytes(b"installer-bytes")

    def unexpected_launch(*args, **kwargs):
        pytest.fail("Installer launched without a checksum")

    monkeypatch.setattr(updater.subprocess, "Popen", unexpected_launch)
    with pytest.raises(UpdateError, match="SHA256SUMS"):
        updater.launch_installer(installer)


@pytest.mark.parametrize("online", [True, False], ids=["online", "local"])
def test_launch_installer_rejects_file_modified_after_verification(monkeypatch, tmp_path, online):
    installer = tmp_path / "Setup.exe"
    data = b"installer-bytes"
    installer.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    expected_sha256 = digest if online else None
    if not online:
        installer.with_name("SHA256SUMS").write_text(f"{digest}  {installer.name}\n", encoding="utf-8")
    assert updater.stage_local_installer(installer, expected_sha256=expected_sha256) == installer
    installer.write_bytes(b"tampered")

    def unexpected_launch(*args, **kwargs):
        pytest.fail("Installer launched after its contents were modified")

    monkeypatch.setattr(updater.subprocess, "Popen", unexpected_launch)
    with pytest.raises(UpdateError, match="mismatch"):
        updater.launch_installer(installer, expected_sha256=expected_sha256)


def test_launch_installer_invokes_popen(monkeypatch, tmp_path):
    p = tmp_path / "Setup.exe"
    p.write_bytes(b"x")
    digest = hashlib.sha256(b"x").hexdigest()
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    updater.launch_installer(p, silent=True, expected_sha256=digest)
    assert calls["args"][0] == str(p.resolve())
    assert "/VERYSILENT" in calls["args"]
    assert "/SUPPRESSMSGBOXES" in calls["args"]
    assert "/NORESTART" in calls["args"]
    assert "/CloseApplications" in calls["args"]
    assert "/RestartApplications" in calls["args"]
    assert "/JasperVoiceAutoLaunch" in calls["args"]


def test_launch_installer_interactive_has_no_silent_flags(monkeypatch, tmp_path):
    p = tmp_path / "Setup.exe"
    p.write_bytes(b"x")
    digest = hashlib.sha256(b"x").hexdigest()
    p.with_name("SHA256SUMS").write_text(f"{digest}  {p.name}\n", encoding="utf-8-sig")
    calls = {}

    def fake_popen(args, **kwargs):
        calls["args"] = args
        return object()

    monkeypatch.setattr(updater.subprocess, "Popen", fake_popen)
    updater.launch_installer(p, silent=False)
    assert calls["args"] == [str(p.resolve())]
