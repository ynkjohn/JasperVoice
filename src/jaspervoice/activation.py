"""Hand a manual launch to the existing instance in this Windows session."""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

from PySide6.QtNetwork import QLocalServer, QLocalSocket


def _server_name() -> str:
    session = wintypes.DWORD()
    ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session))
    return f"JasperVoice.Activate.{session.value}"


def listen(parent, show_window) -> QLocalServer | None:
    if sys.platform != "win32":
        return None
    server = QLocalServer(parent)
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)

    def connected() -> None:
        while server.hasPendingConnections():
            peer = server.nextPendingConnection()
            peer.disconnected.connect(peer.deleteLater)
            # Disconnect is also the activation request. The launcher first
            # reads our PID and hands over its Windows foreground permission.
            peer.disconnected.connect(show_window)
            peer.write(f"{os.getpid()}\n".encode("ascii"))

    server.newConnection.connect(connected)
    if not server.listen(_server_name()):
        server.deleteLater()
        return None
    return server


def request_activation() -> bool:
    if sys.platform != "win32":
        return False
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        peer = QLocalSocket()
        peer.connectToServer(_server_name())
        if peer.waitForConnected(100):
            while not peer.canReadLine() and time.monotonic() < deadline:
                peer.waitForReadyRead(100)
            pid = bytes(peer.readLine()).strip()
            if pid.isdigit():
                ctypes.windll.user32.AllowSetForegroundWindow(int(pid))
            peer.disconnectFromServer()
            return bool(pid)
        time.sleep(0.05)  # The first process may still be building its window.
    return False


def foreground(window) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.SetForegroundWindow(wintypes.HWND(int(window.winId())))
