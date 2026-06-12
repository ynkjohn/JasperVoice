"""Single-instance guard for JasperVoice.

Two JasperVoice processes fight over the global hotkey (see README "Known
limitations"), so we must allow only one. On Windows we use a named kernel
mutex created with ``CreateMutexW``. The mutex name is shared with the Inno
Setup installer's ``AppMutex`` directive so the installer can detect a running
instance and ask it to close before replacing files during an update.

The guard is best-effort: if the Win32 call fails for any reason (unexpected
platform, permission quirk), we log and allow the app to start rather than
blocking the user. Losing single-instance protection is strictly better than
refusing to launch.

On non-Windows (CI, tests) the guard is a no-op that always reports "acquired".
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

log = logging.getLogger(__name__)

# Must match AppMutex in installer/JasperVoice.iss exactly.
MUTEX_NAME = "JasperVoice_SingleInstance_Mutex"

# ERROR_ALREADY_EXISTS: the mutex was already created by another process.
_ERROR_ALREADY_EXISTS = 183


class SingleInstance:
    """Acquire a process-wide single-instance lock.

    Usage::

        guard = SingleInstance()
        if not guard.acquire():
            # another instance is running; bail out
            return

    Hold a reference to the instance for the app's lifetime — the OS releases
    the mutex when the handle closes (process exit), which is exactly the
    lifetime we want.
    """

    def __init__(self, name: str = MUTEX_NAME) -> None:
        self._name = name
        self._handle: Optional[int] = None
        self._acquired = False

    def acquire(self) -> bool:
        """Return True if this is the only instance; False if another holds it."""
        if sys.platform != "win32":
            # No global named mutex story we rely on outside Windows; the app
            # only ships for Windows. Don't block dev/test runs elsewhere.
            self._acquired = True
            return True
        try:
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.CreateMutexW.restype = wintypes.HANDLE
            kernel32.CreateMutexW.argtypes = [
                wintypes.LPVOID,
                wintypes.BOOL,
                wintypes.LPCWSTR,
            ]
            handle = kernel32.CreateMutexW(None, False, self._name)
            last_error = ctypes.get_last_error()
            if not handle:
                log.warning(
                    "CreateMutexW failed (err=%s); skipping single-instance guard",
                    last_error,
                )
                self._acquired = True  # fail open
                return True
            self._handle = handle
            if last_error == _ERROR_ALREADY_EXISTS:
                # Another instance owns the mutex. Close our duplicate handle so
                # we don't keep the kernel object alive past our exit.
                kernel32.CloseHandle(handle)
                self._handle = None
                self._acquired = False
                return False
            self._acquired = True
            return True
        except Exception as e:  # never let the guard crash startup
            log.warning("Single-instance guard error: %s; allowing launch", e)
            self._acquired = True
            return True

    def release(self) -> None:
        """Close the mutex handle (the OS also does this automatically on exit)."""
        if self._handle and sys.platform == "win32":
            try:
                import ctypes

                ctypes.WinDLL("kernel32", use_last_error=True).CloseHandle(self._handle)
            except Exception:
                pass
        self._handle = None
        self._acquired = False
