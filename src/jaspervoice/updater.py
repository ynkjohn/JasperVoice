"""Self-update for JasperVoice via GitHub Releases (failure-safe, offline-capable).

Design goals:

- **Never break the app.** Every network/file operation is wrapped; a failed
  update check leaves the running app fully usable. Callers get ``None`` or a
  raised :class:`UpdateError`, never an unhandled exception.
- **Versioned artifacts only.** We query the GitHub *Releases* API and download
  the published installer asset (``JasperVoice-Setup-x.y.z.exe``). We never
  fetch raw source, never run ``git``, and never execute remote code beyond the
  checksum-verified installer the user chose to install.
- **Integrity checked.** Before an installer is ever launched its SHA-256 is
  verified against the ``SHA256SUMS`` asset published alongside it. A mismatch
  aborts the update.
- **No telemetry.** The only outbound request is to the public GitHub API and
  the asset download URL, and only when the user (or their opt-in setting)
  triggers a check. Nothing about the user is transmitted.
- **Offline path.** :func:`stage_local_installer` lets a user point at an
  installer ``.exe`` they downloaded by hand (air-gapped / mirrored), verify it
  against a SHA-256 they supply, and run it — no network at all.

The actual install is delegated to the Inno Setup installer, which handles the
"replace the installed app in place, recreate shortcuts, relaunch" flow. This
module's job ends at *download + verify + launch installer*.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional
from urllib.error import HTTPError, URLError

from . import __version__

log = logging.getLogger(__name__)

# Default upstream repo. Override via config (``update_repo``) so a fork can
# point its own builds at its own releases without touching code.
DEFAULT_REPO = "ynkjohn/JasperVoice"

# Asset naming convention produced by scripts/build_release.ps1:
#   JasperVoice-Setup-<version>.exe   (the Inno Setup installer)
#   SHA256SUMS                        (one line per artifact: "<hex>  <name>")
SHASUMS_NAME = "SHA256SUMS"

GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"
GITHUB_RELEASES = "https://github.com/{repo}/releases"
_REPO_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_STABLE_TAG = re.compile(r"v?(\d+\.\d+\.\d+)", re.IGNORECASE)

# A small, honest User-Agent (GitHub's API rejects requests without one). This
# is NOT telemetry — it carries no user data, only the app name + version that
# is already public in the release.
_USER_AGENT = f"JasperVoice-Updater/{__version__}"

_CHUNK = 1024 * 256  # 256 KiB download chunks


class UpdateError(RuntimeError):
    """Raised for any recoverable update failure (network, parse, integrity)."""


@dataclass(frozen=True)
class UpdateInfo:
    """A resolved, available update. All fields come from the GitHub release."""

    version: str  # normalized, no leading 'v' (e.g. "1.2.0")
    tag: str  # raw tag as published (e.g. "v1.2.0")
    asset_name: str
    asset_url: str
    asset_size: int
    sha256: Optional[str]  # expected hex digest, or None if SHA256SUMS missing
    notes: str  # release body (markdown), may be empty


# --- version comparison ----------------------------------------------------

_VER_RE = re.compile(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?")


def normalize_version(s: str) -> str:
    """Strip a leading 'v' and surrounding whitespace. 'v1.2.0' -> '1.2.0'."""
    return s.strip().lstrip("vV").strip()


def parse_version(s: str) -> tuple[int, int, int]:
    """Parse 'x.y.z' (lenient) into a 3-tuple of ints. Missing parts are 0.

    Pre-release/build suffixes (e.g. '1.2.0-rc1') are ignored for ordering;
    only the numeric core is compared. This is intentional: we don't ship
    pre-releases through the auto-updater.
    """
    m = _VER_RE.search(normalize_version(s))
    if not m:
        return (0, 0, 0)
    return (
        int(m.group(1) or 0),
        int(m.group(2) or 0),
        int(m.group(3) or 0),
    )


def is_newer(remote: str, local: str = __version__) -> bool:
    """True if ``remote`` is a strictly higher version than ``local``."""
    return parse_version(remote) > parse_version(local)


# --- GitHub release query --------------------------------------------------

def _http_get(url: str, timeout_s: int, accept: str = "application/json") -> bytes:
    """GET a URL with a sane UA + TLS, returning the body bytes.

    Wraps urllib errors into UpdateError so callers never see a raw exception.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": accept},
        method="GET",
    )
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            return resp.read()
    except HTTPError as e:
        raise UpdateError(f"GitHub returned HTTP {e.code} for {url}") from e
    except (URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"Network error contacting {url}: {e}") from e


def _parse_shasums(text: str) -> dict[str, str]:
    """Parse a SHA256SUMS file ('<hex>  <filename>' per line) into {name: hex}."""
    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) < 2:
            continue
        digest = parts[0].lower()
        # The filename may be prefixed with '*' (binary mode) per coreutils.
        name = parts[-1].lstrip("*")
        if re.fullmatch(r"[0-9a-f]{64}", digest):
            out[name] = digest
    return out


def _asset_checksum(url: str, name: str, timeout_s: int) -> str | None:
    if not url:
        return None
    try:
        return _parse_shasums(_http_get(url, timeout_s, "text/plain").decode("utf-8-sig")).get(name)
    except (UpdateError, UnicodeDecodeError) as e:
        log.warning("Could not read the published checksum: %s", e)
        return None


def _check_public_release(repo: str, timeout_s: int, current: str) -> UpdateInfo | None:
    releases = GITHUB_RELEASES.format(repo=repo)
    req = urllib.request.Request(f"{releases}/latest", headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            url = response.geturl()
    except (URLError, TimeoutError, OSError) as e:
        raise UpdateError(f"Could not reach the public GitHub release page: {e}") from e

    prefix, _, tag = url.rpartition("/tag/")
    match = _STABLE_TAG.fullmatch(tag)
    if prefix.casefold() != releases.casefold() or not match:
        raise UpdateError("GitHub did not return a stable release with a version tag.")
    version = match[1]
    if not is_newer(version, current):
        return None
    name = f"JasperVoice-Setup-{version}.exe"
    assets = f"{releases}/download/{tag}"
    checksum = _asset_checksum(f"{assets}/{SHASUMS_NAME}", name, timeout_s)
    return UpdateInfo(version, tag, name, f"{assets}/{name}", 0, checksum, "")


def check_for_update(
    repo: str = DEFAULT_REPO,
    timeout_s: int = 10,
    current: str = __version__,
) -> Optional[UpdateInfo]:
    """Query GitHub for the latest release. Returns UpdateInfo if a newer
    version with a usable installer asset exists, else None.

    Raises UpdateError on network/parse failure so the caller can show a
    message — but callers in the app treat that as a soft failure and keep
    running. This function performs NO writes and downloads nothing heavy
    (only the small JSON + the tiny SHA256SUMS text).
    """
    if not _REPO_RE.fullmatch(repo) or any(part in (".", "..") for part in repo.split("/")):
        raise UpdateError("Use a GitHub repository in owner/repo format.")
    try:
        raw = _http_get(GITHUB_API.format(repo=repo), timeout_s)
    except UpdateError as api_error:
        log.info("Release API unavailable; trying the public release page: %s", api_error)
        try:
            return _check_public_release(repo, timeout_s, current)
        except UpdateError as page_error:
            raise UpdateError(f"{page_error}\n{api_error}") from page_error
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise UpdateError(f"Could not parse GitHub release JSON: {e}") from e

    tag = str(data.get("tag_name") or "").strip() if isinstance(data, dict) else ""
    match = _STABLE_TAG.fullmatch(tag)
    if not match:
        raise UpdateError("GitHub did not return a stable release with a version tag.")
    remote_version = match[1]
    if not is_newer(remote_version, current):
        log.info("Up to date (local=%s, latest=%s)", current, remote_version)
        return None

    assets = data.get("assets")
    if not isinstance(assets, list):
        raise UpdateError("Release JSON has no assets array")

    installer = None
    shasums_url = None
    installer_name = f"JasperVoice-Setup-{remote_version}.exe"
    for a in assets:
        if not isinstance(a, dict):
            continue
        name = str(a.get("name") or "")
        dl = str(a.get("browser_download_url") or "")
        if name == installer_name and dl:
            size = a.get("size")
            installer = (name, dl, size if isinstance(size, int) else 0)
        elif name == SHASUMS_NAME:
            shasums_url = dl

    if installer is None:
        raise UpdateError(
            f"Release {tag} has no {installer_name} asset."
        )

    sha256 = _asset_checksum(shasums_url or "", installer[0], timeout_s)

    return UpdateInfo(
        version=remote_version,
        tag=tag,
        asset_name=installer[0],
        asset_url=installer[1],
        asset_size=installer[2],
        sha256=sha256,
        notes=str(data.get("body") or ""),
    )


# --- download + verify -----------------------------------------------------

def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_sha256(path: Path, expected_hex: str) -> bool:
    """True if the file's SHA-256 matches ``expected_hex`` (case-insensitive)."""
    return _sha256_file(path) == expected_hex.strip().lower()


def updates_dir() -> Path:
    """Where downloaded installers are staged: %APPDATA%/JasperVoice/updates/."""
    from .config import get_app_dir

    d = get_app_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def download_installer(
    info: UpdateInfo,
    timeout_s: int = 60,
    progress: Optional[Callable[[int, int], None]] = None,
    cancelled: Optional[Callable[[], bool]] = None,
) -> Path:
    """Download the installer asset to the updates dir and verify its SHA-256.

    Returns the path to the verified installer. Raises UpdateError on any
    failure (network, integrity mismatch, missing digest). The partial file is
    always cleaned up on failure so a retry starts clean.

    """
    if not info.sha256:
        raise UpdateError(
            "Refusing to download: no SHA256SUMS entry found for "
            f"{info.asset_name}. Cannot verify integrity."
        )

    dest = updates_dir() / info.asset_name
    # Stage to a temp file in the same dir, then atomically move on success.
    req = urllib.request.Request(
        info.asset_url,
        headers={"User-Agent": _USER_AGENT, "Accept": "application/octet-stream"},
        method="GET",
    )
    ctx = ssl.create_default_context()
    fd, tmp_name = tempfile.mkstemp(prefix=".dl-", suffix=".part", dir=str(dest.parent))
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=timeout_s, context=ctx) as resp:
            total = int(resp.headers.get("Content-Length") or info.asset_size or 0)
            got = 0
            while chunk := resp.read(_CHUNK):
                if cancelled and cancelled():
                    raise UpdateError("Download cancelled.")
                out.write(chunk)
                got += len(chunk)
                if progress:
                    try:
                        progress(got, total)
                    except Exception:  # progress callbacks must never abort a download
                        pass
    except UpdateError:
        _silent_unlink(tmp)
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as e:
        _silent_unlink(tmp)
        raise UpdateError(f"Download failed: {e}") from e
    except Exception as e:
        _silent_unlink(tmp)
        raise UpdateError(f"Unexpected download error: {e}") from e

    if info.sha256:
        try:
            ok = verify_sha256(tmp, info.sha256)
        except OSError as e:
            _silent_unlink(tmp)
            raise UpdateError(f"Could not hash downloaded file: {e}") from e
        if not ok:
            _silent_unlink(tmp)
            raise UpdateError(
                "SHA-256 mismatch — the download is corrupt or tampered with. "
                "Aborting update."
            )

    try:
        os.replace(tmp, dest)
    except OSError as e:
        _silent_unlink(tmp)
        raise UpdateError(f"Could not finalize download: {e}") from e

    log.info("Downloaded + verified installer: %s", dest)
    return dest


def stage_local_installer(path: str | Path, expected_sha256: Optional[str] = None) -> Path:
    """Offline path: validate a user-provided installer file and return it.

    Verifies the file exists and matches the required SHA-256 from the caller
    or the adjacent SHA256SUMS. Does NO network access. The
    file is used in place (not copied) so a USB-stick / network-share install
    works without extra disk churn.
    """
    p = Path(path)
    if not p.is_file():
        raise UpdateError(f"Installer not found: {p}")
    if p.suffix.lower() != ".exe":
        raise UpdateError(f"Not an .exe installer: {p.name}")
    if expected_sha256 is None:
        try:
            sums = p.with_name(SHASUMS_NAME).read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as e:
            raise UpdateError("Place the release's SHA256SUMS file beside the installer.") from e
        expected_sha256 = _parse_shasums(sums).get(p.name)
    if not expected_sha256:
        raise UpdateError(f"SHA256SUMS has no valid entry for {p.name}.")
    try:
        if not verify_sha256(p, expected_sha256):
            raise UpdateError(
                "SHA-256 mismatch on the local installer. Refusing to run it."
            )
    except OSError as e:
        raise UpdateError(f"Could not read installer: {e}") from e
    return p


# --- launch ----------------------------------------------------------------

def launch_installer(
    installer: str | Path, silent: bool = False, *, expected_sha256: str | None = None
) -> None:
    """Launch the installer and let it take over the upgrade.

    The Inno Setup installer is configured with ``CloseApplications`` +
    ``AppMutex`` so it will close the running JasperVoice, replace the files,
    and (with our flag) relaunch it. The caller should quit the app shortly
    after invoking this so the installer can replace locked files.

    ``silent``: pass Inno's ``/VERYSILENT`` for an unattended in-app update. The
    interactive (wizard) mode is the default for first installs and the offline
    "install from file" button.
    """
    installer = str(installer)
    if not os.path.isfile(installer):
        raise UpdateError(f"Installer missing at launch time: {installer}")
    installer = str(stage_local_installer(installer, expected_sha256).resolve())
    args = [installer]
    if silent:
        # /VERYSILENT hides the installer UI completely; the custom flag lets
        # our installer relaunch JasperVoice after a silent in-app update.
        args += [
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/CloseApplications",
            "/RestartApplications",
            "/JasperVoiceAutoLaunch",
        ]
    from .single_instance import release_active

    guard = release_active()
    try:
        # Detached so the installer outlives this process when we quit. On
        # Windows, DETACHED_PROCESS + no wait lets the wizard run independently.
        creationflags = 0
        if sys.platform == "win32":
            creationflags = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(args, close_fds=True, creationflags=creationflags)
    except OSError as e:
        if guard is not None:
            guard.acquire()
        raise UpdateError(f"Could not launch installer: {e}") from e


def _silent_unlink(p: Path) -> None:
    try:
        p.unlink()
    except OSError:
        pass
