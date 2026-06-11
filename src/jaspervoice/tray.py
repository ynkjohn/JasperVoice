"""System tray icon and menu for JasperVoice."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from copy import deepcopy
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .config import get_app_dir, load_config, save_config

log = logging.getLogger(__name__)

LANGUAGES = [
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("auto", "Auto-detect"),
]


def _build_icon(color: QColor) -> QIcon:
    """Render a 32x32 round dot icon at runtime — no asset files needed."""
    size = 32
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(color)
    p.setPen(Qt.NoPen)
    p.drawEllipse(4, 4, size - 8, size - 8)
    p.setBrush(QColor(255, 255, 255, 220))
    p.drawEllipse(size // 2 - 4, size // 2 - 4, 8, 8)
    p.end()
    return QIcon(pm)


STATE_COLORS = {
    "idle": QColor("#4a90e2"),
    "recording": QColor("#d0021b"),
    "processing": QColor("#f5a623"),
    "send": QColor("#22c55e"),
    "error": QColor("#9013fe"),
}

STATE_LABELS = {
    "idle": "JasperVoice — idle",
    "recording": "JasperVoice — recording",
    "processing": "JasperVoice — transcribing",
    "send": "JasperVoice — sent",
    "error": "JasperVoice — error",
}


class TrayController(QObject):
    """Owns the QSystemTrayIcon, menu, and state transitions."""

    quit_requested = Signal()
    language_changed = Signal(str)
    settings_requested = Signal()
    stats_requested = Signal()

    def __init__(self, app: QApplication, cfg: Optional[dict] = None, on_open_config: Optional[Callable[[], None]] = None):
        super().__init__()
        self._app = app
        self._on_open_config = on_open_config
        self._state = "idle"
        self._status_text = STATE_LABELS["idle"]
        self._cfg = deepcopy(cfg) if cfg is not None else load_config()

        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("System tray not available on this platform; running headless")

        self._icons = {state: _build_icon(color) for state, color in STATE_COLORS.items()}

        # Prefer the bundled brand icon for the idle state so the tray matches
        # the taskbar/window icon. Active states keep the colored dots for at-a
        # -glance feedback.
        from .assets import icon_path
        _icon_file = icon_path()
        if _icon_file:
            brand = QIcon(_icon_file)
            if not brand.isNull():
                self._icons["idle"] = brand

        self._tray = QSystemTrayIcon(self._icons["idle"])
        self._tray.setToolTip("JasperVoice — push to talk")

        self._menu = QMenu()
        self._build_menu()
        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)
        self._tray.show()

    def _build_menu(self) -> None:
        self._menu.clear()
        self._lang_actions: dict[str, QAction] = {}
        self._status_action = QAction(self._status_text, self._menu)
        self._status_action.setEnabled(False)
        self._menu.addAction(self._status_action)

        self._info_action = QAction(
            f"Model: {self._cfg['model_size']}  •  Device: {self._cfg['device']}", self._menu
        )
        self._info_action.setEnabled(False)
        self._menu.addAction(self._info_action)
        self._menu.addSeparator()

        lang_menu = self._menu.addMenu("Language")
        for code, label in LANGUAGES:
            act = QAction(label, self._menu)
            act.setCheckable(True)
            act.setChecked(self._cfg["language"] == code)
            act.triggered.connect(lambda _checked=False, c=code: self._on_language_selected(c))
            lang_menu.addAction(act)
            self._lang_actions[code] = act
        self._menu.addSeparator()

        open_cfg = QAction("Open config folder", self._menu)
        open_cfg.triggered.connect(self._open_config_folder)
        self._menu.addAction(open_cfg)

        self._menu.addSeparator()
        settings_act = QAction("Settings...", self._menu)
        settings_act.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(settings_act)
        stats_act = QAction("Statistics...", self._menu)
        stats_act.triggered.connect(self.stats_requested.emit)
        self._menu.addAction(stats_act)
        self._menu.addSeparator()
        quit_act = QAction("Quit", self._menu)
        quit_act.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(quit_act)

    def _on_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.Trigger:
            self._menu.popup(self._tray.geometry().center())

    def _on_language_selected(self, code: str) -> None:
        self._cfg["language"] = code
        save_config(self._cfg)
        self.language_changed.emit(code)
        # Incremental update: just sync the check marks instead of rebuilding
        # the whole menu (which would recreate every QAction).
        self._sync_language_checks()

    def _sync_language_checks(self) -> None:
        actions = getattr(self, "_lang_actions", None)
        if not actions:
            return
        current = self._cfg["language"]
        for code, act in actions.items():
            act.setChecked(code == current)

    def _open_config_folder(self) -> None:
        path = str(get_app_dir())
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as e:
            log.error("Could not open config folder %s: %s", path, e)

    def set_state(self, state: str) -> None:
        if state not in STATE_COLORS:
            log.warning("Unknown tray state %r", state)
            return
        self._state = state
        self._status_text = STATE_LABELS[state]
        self._tray.setIcon(self._icons[state])
        self._tray.setToolTip(self._status_text)
        self._status_action.setText(self._status_text)

    def set_status_detail(self, detail: str) -> None:
        self._status_action.setText(f"{STATE_LABELS.get(self._state, self._status_text)} — {detail}")

    def update_config(self, cfg: dict) -> None:
        self._cfg = deepcopy(cfg)
        self._build_menu()

    def show_message(self, title: str, body: str, msec: int = 3000) -> None:
        if self._tray.isVisible() and self._tray.supportsMessages():
            self._tray.showMessage(title, body, QSystemTrayIcon.Information, msec)

    def shutdown(self) -> None:
        try:
            self._tray.hide()
        except Exception:
            pass
