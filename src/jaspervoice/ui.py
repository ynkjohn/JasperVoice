"""JasperVoice main settings window — a navigable shell with sidebar, pages,
working search, and a dirty-state save bar — plus the update dialog.

Layout:

    +------------+----------------------------------------------+
    | brand      |  page header                                 |
    | search     |  page content (scrollable)                   |
    | nav groups |                                              |
    | ...        |                                              |
    | status     |----------------------------------------------|
    +------------+  status bar: state · summary · save controls |

Pages live in `ui_pages.py`; shared primitives in `ui_widgets.py`. The window
is non-modal, X hides it (the app keeps running in the tray), and `configChanged`
is emitted with the full config dict whenever the user applies changes — the
app hot-reloads from that signal exactly as before.

Threading: the update check/download run on QThreads (`_CheckWorker`,
`_DownloadWorker`); the mic meter audio callback emits a Signal that is queued
to the UI thread. No widget is ever touched from a non-Qt thread.
"""

from __future__ import annotations

import logging
from copy import deepcopy
from typing import Callable, Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import config as cfg_mod
from .ui_pages import PAGE_CLASSES, BasePage
from .theme import COLORS
from .ui_widgets import (  # noqa: F401  (re-exported: tests import these from here)
    LANGUAGES,
    MicLevelSource,
    glyph_icon,
    keyboard_to_qt,
    qt_to_keyboard,
)

log = logging.getLogger(__name__)


# App-state shown in the window status areas: state -> (label, lamp color)
WINDOW_STATES = {
    "idle": ("READY", "#22c55e"),
    "recording": ("RECORDING", "#ef4444"),
    "processing": ("PROCESSING", "#f59e0b"),
    "send": ("SENT", "#22c55e"),
    "error": ("ERROR", "#ef4444"),
}

NAV_GROUPS = [
    ("WORKSPACE", ["overview", "history", "dictionary"]),
    ("CONFIGURE", ["general", "audio", "model", "polish", "updates"]),
    ("SYSTEM", ["diagnostics"]),
]

# page id -> painted glyph for the sidebar
NAV_GLYPHS = {
    "overview": "grid",
    "history": "clock",
    "dictionary": "book",
    "general": "sliders",
    "audio": "mic",
    "model": "chip",
    "polish": "spark",
    "updates": "download",
    "diagnostics": "pulse",
}

# Pages that participate in load_from/collect_into (the dirty/apply cycle).
SETTINGS_PAGE_IDS = ["general", "audio", "model", "polish", "updates"]


class SettingsWindow(QMainWindow):
    """Navigable settings/main window. Non-modal; X hides; Apply persists."""

    configChanged = Signal(dict)
    testDictationRequested = Signal()

    def __init__(self, cfg: dict, history=None, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setWindowTitle("JasperVoice")
        self.setMinimumSize(900, 600)
        self.resize(1120, 720)

        self._cfg = deepcopy(cfg)
        self._history = history
        self._dirty = False
        self._loading = False
        self._runtime_provider: Optional[Callable[[], dict]] = None
        self._update_dialog = None
        self._meter_paused = False

        self.mic_source = MicLevelSource(self)

        self._pages: dict[str, BasePage] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._nav_group_labels: list[tuple[QLabel, list[str]]] = []
        self._current_page_id = "overview"

        self._build_ui()
        self._load_values_into_ui()
        self.set_app_state("idle")
        self.show_page("overview")

    # --- Shell surface used by pages ---

    @property
    def saved_cfg(self) -> dict:
        return self._cfg

    @property
    def history(self):
        return self._history

    def page(self, page_id: str) -> Optional[BasePage]:
        return self._pages.get(page_id)

    def set_runtime_provider(self, provider: Callable[[], dict]) -> None:
        """`provider` is called on the UI thread and returns live app info,
        e.g. {"resolved_device": "cuda", "model_loaded": True, "last_duration_s": 3.2}."""
        self._runtime_provider = provider

    def runtime_info(self) -> dict:
        if self._runtime_provider is None:
            return {}
        try:
            info = self._runtime_provider()
            return info if isinstance(info, dict) else {}
        except Exception as e:
            log.warning("Runtime provider failed: %s", e)
            return {}

    def request_test_dictation(self) -> None:
        self.testDictationRequested.emit()

    def show_test_result(self, text: str) -> None:
        overview = self._pages.get("overview")
        if overview is not None:
            overview.set_test_result(text)

    def persist_config_now(self) -> None:
        """Persist self._cfg immediately (Dictionary page edits) and notify the app."""
        cfg_mod.save_config(self._cfg)
        self.configChanged.emit(deepcopy(self._cfg))

    def shutdown_workers(self) -> None:
        """Stop page-owned background threads and the mic meter. Called by the
        app on shutdown so no QThread is destroyed while running."""
        for page in self._pages.values():
            stop = getattr(page, "shutdown", None)
            if stop is not None:
                try:
                    stop()
                except Exception:
                    pass
        self.mic_source.stop()

    def open_update_dialog(self, repo: str) -> None:
        dlg = UpdateDialog(repo=repo, parent=self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self._update_dialog = dlg  # keep a reference

    # --- Construction ---

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_sidebar(), 0)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        self._stack = QStackedWidget()
        for cls in PAGE_CLASSES:
            page = cls(self)
            self._pages[page.page_id] = page
            self._stack.addWidget(self._wrap_page(page))
        right.addWidget(self._stack, 1)
        right.addWidget(self._build_status_bar(), 0)
        root.addLayout(right, 1)

        # Convenience aliases so app code/tests can reach common controls.
        general = self._pages["general"]
        self.hotkey_edit = general.hotkey_edit
        self.lang_combo = general.lang_combo
        self.mode_seg = general.mode_seg
        self.paste_delay = general.paste_delay
        self.min_duration = general.min_duration
        updates = self._pages["updates"]
        self.update_check_enabled = updates.update_check_enabled
        self.update_repo_edit = updates.update_repo_edit

        # Toast overlay
        self._toast_label = QLabel("", central)
        self._toast_label.setProperty("role", "toast")
        self._toast_label.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.setInterval(2200)
        self._toast_timer.timeout.connect(self._toast_label.hide)

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("sideBar")
        side.setFixedWidth(244)
        box = QVBoxLayout(side)
        box.setContentsMargins(0, 20, 0, 16)
        box.setSpacing(0)

        brand = QVBoxLayout()
        brand.setContentsMargins(16, 0, 16, 14)
        brand.setSpacing(3)
        name = QLabel("JASPERVOICE")
        name.setProperty("role", "brandname")
        brand.addWidget(name)
        sub = QLabel(f"Offline dictation · v{__version__}")
        sub.setProperty("role", "brandsub")
        brand.addWidget(sub)
        box.addLayout(brand)

        search_wrap = QHBoxLayout()
        search_wrap.setContentsMargins(14, 0, 14, 6)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search settings…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setAccessibleName("Search settings")
        self.search_edit.textChanged.connect(self._apply_search)
        self.search_edit.returnPressed.connect(self._go_to_first_match)
        search_wrap.addWidget(self.search_edit)
        box.addLayout(search_wrap)

        for group_title, page_ids in NAV_GROUPS:
            lbl = QLabel(group_title)
            lbl.setProperty("role", "navgroup")
            box.addWidget(lbl)
            self._nav_group_labels.append((lbl, page_ids))
            for pid in page_ids:
                cls = next(c for c in PAGE_CLASSES if c.page_id == pid)
                # QPushButton treats "&" as a mnemonic marker; escape it.
                btn = QPushButton(cls.title.replace("&", "&&"))
                btn.setProperty("nav", True)
                glyph = NAV_GLYPHS.get(pid)
                if glyph:
                    btn.setIcon(glyph_icon(glyph))
                btn.setCursor(Qt.CursorShape.PointingHandCursor)
                btn.clicked.connect(lambda _=False, p=pid: self.show_page(p))
                box.addWidget(btn)
                self._nav_buttons[pid] = btn

        box.addStretch(1)

        status = QVBoxLayout()
        status.setContentsMargins(16, 10, 16, 0)
        status.setSpacing(4)
        lamp_row = QHBoxLayout()
        lamp_row.setSpacing(6)
        self._side_lamp = QLabel("")
        self._side_lamp.setProperty("role", "statelamp")
        lamp_row.addWidget(self._side_lamp, 0)
        self._side_state = QLabel("READY")
        lamp_row.addWidget(self._side_state, 1)
        status.addLayout(lamp_row)
        self._side_summary = QLabel("")
        self._side_summary.setProperty("role", "brandsub")
        self._side_summary.setWordWrap(True)
        status.addWidget(self._side_summary)
        box.addLayout(status)
        return side

    @staticmethod
    def _wrap_page(page: BasePage) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        # Center the content column in the viewport; cap its width so wide
        # windows get balanced whitespace on both sides instead of a page
        # glued to the top-left corner.
        page.setMaximumWidth(980)
        row.addStretch(1)
        row.addWidget(page, 24)
        row.addStretch(1)
        scroll.setWidget(holder)
        return scroll

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("statusBar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(20, 10, 20, 10)
        row.setSpacing(10)

        self._bar_lamp = QLabel("")
        self._bar_lamp.setProperty("role", "statelamp")
        row.addWidget(self._bar_lamp, 0)
        self._bar_state = QLabel("READY")
        row.addWidget(self._bar_state, 0)
        row.addWidget(QLabel("·"), 0)
        self._bar_summary = QLabel("")
        row.addWidget(self._bar_summary, 0)
        self._bar_last_take = QLabel("")
        row.addWidget(self._bar_last_take, 0)
        row.addStretch(1)

        self.dirty_hint = QLabel("All changes saved")
        row.addWidget(self.dirty_hint, 0)
        self.discard_btn = QPushButton("Discard")
        self.discard_btn.setEnabled(False)
        self.discard_btn.clicked.connect(self._on_discard)
        row.addWidget(self.discard_btn, 0)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("primary", True)
        self.apply_btn.setEnabled(False)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        row.addWidget(self.apply_btn, 0)
        return bar

    # --- Navigation + search ---

    def show_page(self, page_id: str) -> None:
        if page_id not in self._pages:
            log.warning("Unknown page %r", page_id)
            return
        self._current_page_id = page_id
        index = list(self._pages.keys()).index(page_id)
        self._stack.setCurrentIndex(index)
        for pid, btn in self._nav_buttons.items():
            active = pid == page_id
            btn.setProperty("navActive", active)
            glyph = NAV_GLYPHS.get(pid)
            if glyph:
                btn.setIcon(glyph_icon(glyph, COLORS["accent"] if active else None))
            btn.style().unpolish(btn)
            btn.style().polish(btn)
        self._pages[page_id].on_shown()
        self._update_mic_state()

    def current_page_id(self) -> str:
        return self._current_page_id

    def _apply_search(self, text: str) -> None:
        query = text.strip().lower()
        for pid, btn in self._nav_buttons.items():
            page = self._pages[pid]
            visible = not query or any(query in term.lower() for term in page.search_terms())
            btn.setVisible(visible)
        # isHidden() reflects the explicit setVisible flag even while the
        # window itself is not shown (isVisible() would be False for all).
        for lbl, page_ids in self._nav_group_labels:
            lbl.setVisible(any(not self._nav_buttons[p].isHidden() for p in page_ids))

    def _go_to_first_match(self) -> None:
        for _group, page_ids in NAV_GROUPS:
            for pid in page_ids:
                if not self._nav_buttons[pid].isHidden():
                    self.show_page(pid)
                    return

    # --- Load / collect / dirty state ---

    def mark_dirty(self) -> None:
        if self._loading or self._dirty:
            return
        self._dirty = True
        self.apply_btn.setEnabled(True)
        self.discard_btn.setEnabled(True)
        self.dirty_hint.setText("Unsaved changes")
        self.dirty_hint.setProperty("role", "dirtyhint")
        self._repolish(self.dirty_hint)

    def _clear_dirty(self, message: str) -> None:
        self._dirty = False
        self.apply_btn.setEnabled(False)
        self.discard_btn.setEnabled(False)
        self.dirty_hint.setText(message)
        self.dirty_hint.setProperty("role", "")
        self._repolish(self.dirty_hint)

    @staticmethod
    def _repolish(widget: QWidget) -> None:
        widget.style().unpolish(widget)
        widget.style().polish(widget)

    def _load_values_into_ui(self) -> None:
        self._loading = True
        try:
            for page in self._pages.values():
                page.load_from(self._cfg)
        finally:
            self._loading = False
        self._clear_dirty("All changes saved")
        self._refresh_summary()

    def _collect_values(self) -> dict:
        out = deepcopy(self._cfg)
        for pid in SETTINGS_PAGE_IDS:
            self._pages[pid].collect_into(out)
        return out

    def _on_apply(self) -> None:
        new_cfg = self._collect_values()
        self._cfg = new_cfg
        cfg_mod.save_config(new_cfg)
        self.configChanged.emit(deepcopy(new_cfg))
        self._clear_dirty("All changes saved")
        self._refresh_summary()
        # Saved values changed: refresh the read-only views that show them.
        for pid in ("overview", "model"):
            self._pages[pid].on_shown()
        self.toast("Settings applied")

    def _on_discard(self) -> None:
        self._load_values_into_ui()
        self.toast("Changes discarded")

    # Backwards-compatible name (the previous window called this Cancel).
    def _on_cancel(self) -> None:
        self._on_discard()

    def update_config(self, cfg: dict) -> None:
        """Replace the saved config (e.g. tray language change) without marking dirty."""
        self._cfg = deepcopy(cfg)
        self._load_values_into_ui()

    # --- Status areas ---

    def set_app_state(self, state: str) -> None:
        label, color = WINDOW_STATES.get(state, WINDOW_STATES["idle"])
        for lamp in (self._side_lamp, self._bar_lamp):
            lamp.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self._side_state.setText(label)
        self._bar_state.setText(label)
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        summary = (
            f"whisper {self._cfg.get('model_size', '?')} · "
            f"{self._cfg.get('device', '?')} · {self._cfg.get('compute_type', '?')}"
        )
        self._side_summary.setText(summary)
        self._bar_summary.setText(summary)
        info = self.runtime_info()
        last = info.get("last_duration_s")
        self._bar_last_take.setText(f"· last take {last:.1f}s" if last else "")

    # --- Toast ---

    def toast(self, message: str) -> None:
        self._toast_label.setText(message)
        self._toast_label.adjustSize()
        central = self.centralWidget()
        if central is not None:
            x = (central.width() - self._toast_label.width()) // 2
            y = central.height() - self._toast_label.height() - 52
            self._toast_label.move(max(0, x), max(0, y))
        self._toast_label.show()
        self._toast_label.raise_()
        self._toast_timer.start()

    # --- Mic meter lifecycle ---

    def set_meter_paused(self, paused: bool) -> None:
        self._meter_paused = paused
        for pid in ("overview", "audio"):
            page = self._pages.get(pid)
            if page is not None:
                page.sync_meter_button(paused)
        self._update_mic_state()

    def restart_mic_meter(self) -> None:
        self.mic_source.stop()
        self._update_mic_state()

    def _update_mic_state(self) -> None:
        # The meter opens a real input stream; never auto-start it headless
        # (offscreen platform = tests/CI), only on explicit user resume.
        want = (
            self.isVisible()
            and not self._meter_paused
            and self._current_page_id in ("overview", "audio")
            and QApplication.platformName() != "offscreen"
        )
        if want and not self.mic_source.is_running:
            audio_page = self._pages.get("audio")
            device = audio_page.current_device() if audio_page is not None else "default"
            self.mic_source.start(device)
        elif not want and self.mic_source.is_running:
            self.mic_source.stop()

    # --- Window lifecycle ---

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._pages[self._current_page_id].on_shown()
        self._update_mic_state()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._update_mic_state()

    def closeEvent(self, event) -> None:  # noqa: ARG002, N802
        # Hide instead of closing. App keeps running in the tray.
        self.hide()


# --- Update dialog + background workers ---

def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Titled panel container used by the update dialog."""
    frame = QFrame()
    frame.setProperty("role", "panel")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 14, 18, 16)
    box.setSpacing(10)
    header = QLabel(title)
    header.setProperty("role", "grouptitle")
    box.addWidget(header)
    return frame, box


class _CheckWorker(QObject):
    """Runs updater.check_for_update off the UI thread."""

    done = Signal(object)   # UpdateInfo or None
    error = Signal(str)

    def __init__(self, repo: str) -> None:
        super().__init__()
        self._repo = repo

    def run(self) -> None:
        from . import updater

        try:
            info = updater.check_for_update(repo=self._repo)
            self.done.emit(info)
        except updater.UpdateError as e:
            self.error.emit(str(e))
        except Exception as e:  # never crash the thread
            self.error.emit(f"Unexpected error: {e}")


class _DownloadWorker(QObject):
    """Downloads + verifies the installer off the UI thread."""

    progress = Signal(int, int)  # got, total
    done = Signal(str)           # installer path
    error = Signal(str)

    def __init__(self, info) -> None:
        super().__init__()
        self._info = info

    def run(self) -> None:
        from . import updater

        try:
            path = updater.download_installer(
                self._info, progress=lambda g, t: self.progress.emit(g, t)
            )
            self.done.emit(str(path))
        except updater.UpdateError as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")


class UpdateDialog(QMainWindow):
    """Manual update flow: check → show result → download+verify → install.

    Every step is failure-safe — errors are shown inline and the dialog can be
    closed at any time without affecting the running app.
    """

    def __init__(self, repo: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setWindowTitle("JasperVoice — Updates")
        self.setMinimumSize(460, 280)
        self.resize(520, 340)
        self._repo = repo
        self._info = None
        self._installer_path: Optional[str] = None
        self._thread: Optional[QThread] = None
        self._worker = None
        self._build_ui()
        self._start_check()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        frame, box = _card("SOFTWARE UPDATE")
        self._status = QLabel("Checking for updates…")
        self._status.setWordWrap(True)
        self._status.setProperty("role", "fieldlabel")
        box.addWidget(self._status)

        self._notes = QLabel("")
        self._notes.setWordWrap(True)
        self._notes.setProperty("role", "muted")
        self._notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        box.addWidget(self._notes)

        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        self._progress.setVisible(False)
        box.addWidget(self._progress)
        root.addWidget(frame)

        row = QHBoxLayout()
        row.addStretch(1)
        self._action_btn = QPushButton("Checking…")
        self._action_btn.setProperty("primary", True)
        self._action_btn.setEnabled(False)
        self._action_btn.clicked.connect(self._on_action)
        self._close_btn = QPushButton("Close")
        self._close_btn.clicked.connect(self.close)
        row.addWidget(self._close_btn)
        row.addWidget(self._action_btn)
        root.addLayout(row)

    # --- Check phase ---

    def _start_check(self) -> None:
        self._thread = QThread()
        self._worker = _CheckWorker(self._repo)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_check_done, Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(self._on_check_error, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _on_check_done(self, info) -> None:
        self._teardown_thread()
        if info is None:
            self._status.setText("You're on the latest version.")
            self._action_btn.setText("Up to date")
            self._action_btn.setEnabled(False)
            return
        self._info = info
        self._status.setText(
            f"Version {info.version} is available."
            + ("" if info.sha256 else "\n\nWarning: no checksum published for this release.")
        )
        notes = (info.notes or "").strip()
        if notes:
            self._notes.setText(notes[:600] + ("…" if len(notes) > 600 else ""))
        self._action_btn.setText("Download && Update")
        self._action_btn.setEnabled(bool(info.sha256))
        if not info.sha256:
            self._status.setText(
                self._status.text()
                + "\n\nInstall blocked: integrity cannot be verified."
            )

    def _on_check_error(self, msg: str) -> None:
        self._teardown_thread()
        self._status.setText(
            "Could not check for updates. JasperVoice keeps working normally.\n\n"
            f"{msg}"
        )
        self._action_btn.setText("Retry")
        self._action_btn.setEnabled(True)
        self._retry = True

    # --- Action button ---

    def _on_action(self) -> None:
        if getattr(self, "_retry", False) and self._info is None:
            self._retry = False
            self._status.setText("Checking for updates…")
            self._action_btn.setEnabled(False)
            self._start_check()
            return
        if self._installer_path:
            self._launch_install()
            return
        if self._info is not None:
            self._start_download()

    # --- Download phase ---

    def _start_download(self) -> None:
        self._action_btn.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setValue(0)
        self._status.setText(f"Downloading version {self._info.version}…")
        self._thread = QThread()
        self._worker = _DownloadWorker(self._info)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        self._worker.done.connect(self._on_download_done, Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(self._on_download_error, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _on_progress(self, got: int, total: int) -> None:
        if total > 0:
            self._progress.setValue(int(got * 100 / total))

    def _on_download_done(self, path: str) -> None:
        self._teardown_thread()
        self._installer_path = path
        self._progress.setValue(100)
        self._status.setText(
            "Downloaded and verified. Click Update now — JasperVoice will close, "
            "update silently, and relaunch."
        )
        self._action_btn.setText("Update now")
        self._action_btn.setEnabled(True)

    def _on_download_error(self, msg: str) -> None:
        self._teardown_thread()
        self._progress.setVisible(False)
        self._status.setText(
            f"Download failed. Nothing was changed.\n\n{msg}"
        )
        self._action_btn.setText("Retry")
        self._action_btn.setEnabled(True)

    def _launch_install(self) -> None:
        from . import updater
        from . import single_instance

        # Release our single-instance named mutex BEFORE launching the
        # installer. Inno's AppMutex gate runs at the installer's startup —
        # before its CloseApplications phase — so if the mutex is still held it
        # aborts a /VERYSILENT update with "JasperVoice is currently running"
        # (the suppressed prompt defaults to Cancel). Releasing it first lets
        # the installer past that gate; CloseApplications then closes this
        # process to unlock the _internal\*.dll files.
        single_instance.release_active()
        try:
            updater.launch_installer(self._installer_path, silent=True)
        except updater.UpdateError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not launch installer:\n{e}")
            return
        QApplication.quit()

    # --- Lifecycle ---

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None

    def closeEvent(self, event) -> None:  # noqa: ARG002, N802
        self._teardown_thread()
        super().closeEvent(event)
