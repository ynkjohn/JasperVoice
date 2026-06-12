"""Pages for the navigable JasperVoice settings window.

Every page receives the shell (`jaspervoice.ui.SettingsWindow`) and talks to it
through a small surface:

    shell.saved_cfg                 last-applied config dict (source of truth)
    shell.history                   TranscriptionHistory or None
    shell.mark_dirty()              flag unsaved changes (no-op while loading)
    shell.toast(msg)                transient feedback
    shell.persist_config_now()      save + emit configChanged (Dictionary page)
    shell.show_page(page_id)        navigate
    shell.runtime_info()            live info dict provided by app.App
    shell.request_test_dictation()  ask the app for a real test take
    shell.open_update_dialog(repo)  manual update check window
    shell.mic_source                shared MicLevelSource
    shell.restart_mic_meter()       re-open the meter stream (device change)
    shell.set_meter_paused(bool)    pause/resume the shared meter

Settings pages implement load_from(cfg) / collect_into(cfg); pages that act on
data directly (History, Dictionary) persist immediately instead.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import __version__
from . import config as cfg_mod
from .config import DEFAULT_CONFIG, get_app_dir, get_models_dir
from .postprocessing import OUTPUT_MODES, is_valid_env_var_name
from .theme import COLORS
from .ui_widgets import (
    LANGUAGES,
    LevelMeter,
    ModelCard,
    SegmentedControl,
    SettingsGroup,
    StatTile,
    Switch,
    glyph_label,
    hint,
    keyboard_to_qt,
    list_input_devices,
    mono,
    page_desc,
    page_title,
    qt_to_keyboard,
)

log = logging.getLogger(__name__)


# --- Shared helpers ----------------------------------------------------------

def _open_path(path: str) -> None:
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
    except Exception as e:
        log.error("Could not open %s: %s", path, e)


def _fmt_clock(timestamp: str) -> str:
    """ISO UTC timestamp -> local 'dd/mm HH:MM'. Falls back to raw slice."""
    try:
        dt = datetime.fromisoformat(timestamp).astimezone()
        return dt.strftime("%d/%m %H:%M")
    except Exception:
        return timestamp[11:16] if len(timestamp) >= 16 else timestamp


def _fmt_duration(total_s: float) -> str:
    total_s = int(total_s)
    if total_s >= 3600:
        return f"{total_s // 3600}h {(total_s % 3600) // 60:02d}m"
    if total_s >= 60:
        return f"{total_s // 60}m {total_s % 60:02d}s"
    return f"{total_s}s"


def _fmt_size(num_bytes: int) -> str:
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def _dir_size(path) -> int:
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    continue
    except OSError:
        pass
    return total


def _model_cache_name(size: str) -> str:
    return f"models--Systran--faster-whisper-{size}"


def model_dir_for(size: str):
    """Local cache directory for a faster-whisper model size, or None."""
    expected = get_models_dir() / _model_cache_name(size)
    if expected.is_dir():
        return expected
    try:
        needle = f"faster-whisper-{size}".lower()
        for child in get_models_dir().iterdir():
            if child.is_dir() and needle in child.name.lower():
                return child
    except OSError:
        pass
    return None


def _model_lock_dir_for(size: str):
    path = get_models_dir() / ".locks" / _model_cache_name(size)
    return path if path.exists() else None


def _snapshot_has_required_files(snapshot) -> bool:
    try:
        required = ("config.json", "model.bin", "tokenizer.json")
        if not all((snapshot / name).is_file() for name in required):
            return False
        model_file = snapshot / "model.bin"
        if model_file.stat().st_size <= 0:
            return False
        return (snapshot / "vocabulary.txt").is_file() or (snapshot / "vocabulary.json").is_file()
    except OSError:
        return False


def model_cache_state(size: str) -> tuple[str, Path | None]:
    """Return ('missing'|'installed'|'broken', cache_dir)."""
    cache_dir = model_dir_for(size)
    if cache_dir is None:
        return "missing", None
    snapshots = cache_dir / "snapshots"
    try:
        if snapshots.is_dir() and any(
            child.is_dir() and _snapshot_has_required_files(child)
            for child in snapshots.iterdir()
        ):
            return "installed", cache_dir
    except OSError:
        pass
    return "broken", cache_dir


def model_installed(size: str) -> bool:
    """True if the faster-whisper model cache for `size` exists locally."""
    state, _path = model_cache_state(size)
    return state == "installed"


def _on_rm_error(func, path, _exc_info) -> None:
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def remove_model_cache(size: str) -> list[str]:
    """Remove model cache and matching HuggingFace lock dir. Returns removed paths."""
    removed: list[str] = []
    paths = [p for p in (model_dir_for(size), _model_lock_dir_for(size)) if p is not None]
    for path in paths:
        if path.is_dir():
            shutil.rmtree(path, onerror=_on_rm_error)
        elif path.exists():
            path.unlink()
        removed.append(str(path))
    return removed


def download_whisper_model(size: str) -> str:
    """Download a Whisper model into the app's models dir (blocking; run it
    on a worker thread). Returns the local model path."""
    from faster_whisper import download_model

    return str(download_model(size, cache_dir=str(get_models_dir())))


def probe_hardware() -> dict:
    """Query CTranslate2 for CUDA devices. Never raises; safe off-thread."""
    try:
        import ctranslate2

        return {"cuda_devices": int(ctranslate2.get_cuda_device_count())}
    except Exception as e:
        return {"cuda_devices": 0, "note": f"CUDA query failed: {e}"}


def hardware_recommendation(info: dict) -> tuple[str, str, str]:
    """(device_key, compute_key, friendly message) for the probed hardware."""
    cuda = int(info.get("cuda_devices", 0))
    if cuda > 0:
        return (
            "cuda", "float16",
            f"On this PC, GPU (CUDA) with float16 is recommended — "
            f"{cuda} CUDA device{'s' if cuda > 1 else ''} detected.",
        )
    return (
        "cpu", "int8",
        "On this PC, CPU with int8 is the best option — no CUDA GPU detected.",
    )


class _BgWorker(QObject):
    """One-shot background worker: runs `fn` on its QThread, emits done/error."""

    done = Signal(object)
    error = Signal(str)

    def __init__(self, fn) -> None:
        super().__init__()
        self._fn = fn

    def run(self) -> None:
        try:
            self.done.emit(self._fn())
        except Exception as e:  # surface, never crash the thread
            self.error.emit(str(e))


def _panel() -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setProperty("role", "panel")
    box = QVBoxLayout(frame)
    box.setContentsMargins(20, 16, 20, 18)
    box.setSpacing(10)
    return frame, box


def _panel_header(text: str, glyph: Optional[str] = None) -> QWidget:
    """Panel section header: optional painted glyph + accent caption."""
    wrap = QWidget()
    wrap.setStyleSheet("background: transparent;")
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    if glyph:
        row.addWidget(glyph_label(glyph, 15, COLORS["accent"]), 0, Qt.AlignmentFlag.AlignVCenter)
    lbl = QLabel(text)
    lbl.setProperty("role", "panelheader")
    row.addWidget(lbl, 1)
    return wrap


def _populate_device_combo(combo: QComboBox, current: str) -> None:
    combo.blockSignals(True)
    combo.clear()
    combo.addItem("System default", "default")
    names = list_input_devices()
    for name in names:
        combo.addItem(name, name)
    if current != "default" and current not in names:
        combo.addItem(f"{current} (unavailable)", current)
    idx = combo.findData(current)
    combo.setCurrentIndex(idx if idx >= 0 else 0)
    combo.blockSignals(False)


# --- Base page ----------------------------------------------------------------

class BasePage(QWidget):
    page_id = ""
    title = ""
    description = ""

    def __init__(self, shell):
        super().__init__()
        self.shell = shell
        self._groups: list[SettingsGroup] = []
        self._extra_terms: list[str] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(44, 34, 44, 34)
        root.setSpacing(18)

        head = QHBoxLayout()
        head.setSpacing(16)
        title_col = QVBoxLayout()
        title_col.setSpacing(5)
        title_col.addWidget(page_title(self.title))
        if self.description:
            title_col.addWidget(page_desc(self.description))
        head.addLayout(title_col, 1)
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(10)
        head.addLayout(self.actions_row, 0)
        root.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        root.addLayout(self.body, 1)

        self._build()

    # subclasses override
    def _build(self) -> None: ...
    def load_from(self, cfg: dict) -> None: ...
    def collect_into(self, cfg: dict) -> None: ...

    def on_shown(self) -> None:
        """Called by the shell whenever this page becomes the current page."""

    def add_group(self, title: str) -> SettingsGroup:
        group = SettingsGroup(title)
        self.body.addWidget(group)
        self._groups.append(group)
        return group

    def add_action(self, btn: QPushButton) -> QPushButton:
        self.actions_row.addWidget(btn)
        return btn

    def search_terms(self) -> list[str]:
        terms = [self.title, self.description]
        for g in self._groups:
            terms.extend(g.row_labels())
        terms.extend(self._extra_terms)
        return [t for t in terms if t]


# --- Overview -------------------------------------------------------------------

class OverviewPage(BasePage):
    page_id = "overview"
    title = "Overview"
    description = "Everything runs on this machine. Hold the hotkey in any app and speak."

    def _build(self) -> None:
        self._extra_terms = ["statistics", "mic check", "test dictation", "recent transcriptions", "pipeline"]

        self.test_btn = self.add_action(QPushButton("Test dictation"))
        self.test_btn.clicked.connect(self._on_test_clicked)

        self.test_status = hint("")
        self.body.addWidget(self.test_status)

        # Pipeline summary strip
        strip = QFrame()
        strip.setProperty("role", "panel")
        srow = QHBoxLayout(strip)
        srow.setContentsMargins(20, 14, 20, 14)
        srow.setSpacing(14)
        self._pipe_values: dict[str, QLabel] = {}
        for i, (tag, key) in enumerate([
            ("TRIGGER", "trigger"), ("CAPTURE", "capture"),
            ("TRANSCRIBE", "transcribe"), ("INJECT", "inject"),
        ]):
            if i:
                arrow = QLabel("→")
                arrow.setProperty("role", "hint")
                srow.addWidget(arrow, 0)
            col = QVBoxLayout()
            col.setSpacing(2)
            tag_lbl = QLabel(tag)
            tag_lbl.setProperty("role", "statcaption")
            col.addWidget(tag_lbl)
            val = QLabel("—")
            val.setProperty("role", "fieldlabel")
            col.addWidget(val)
            self._pipe_values[key] = val
            srow.addLayout(col, 1)
        self.body.addWidget(strip)

        # Stat tiles
        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        self.tile_count = StatTile("TRANSCRIPTIONS")
        self.tile_words = StatTile("WORDS DICTATED")
        self.tile_audio = StatTile("AUDIO CAPTURED")
        self.tile_wpm = StatTile("AVG WPM")
        for t in (self.tile_count, self.tile_words, self.tile_audio, self.tile_wpm):
            tiles.addWidget(t, 1)
        self.body.addLayout(tiles)

        # Mic check + recent, side by side
        cols = QHBoxLayout()
        cols.setSpacing(12)

        mic_frame, mic_box = _panel()
        mic_box.addWidget(_panel_header("MIC CHECK", "mic"))
        self.meter = LevelMeter()
        mic_box.addWidget(self.meter)
        mic_row = QHBoxLayout()
        mic_row.setSpacing(8)
        self.device_combo = QComboBox()
        self.device_combo.setAccessibleName("Input device")
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        mic_row.addWidget(self.device_combo, 1)
        self.meter_btn = QPushButton("Pause")
        self.meter_btn.clicked.connect(self._toggle_meter)
        mic_row.addWidget(self.meter_btn, 0)
        mic_box.addLayout(mic_row)
        mic_box.addStretch(1)
        # Ignored width policy: the 50/50 split comes purely from the stretch
        # factors, not from whichever panel has the larger size hint.
        mic_frame.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cols.addWidget(mic_frame, 1)

        recent_frame, recent_box = _panel()
        head = QHBoxLayout()
        head.addWidget(_panel_header("RECENT", "clock"), 1)
        view_all = QPushButton("View all")
        view_all.clicked.connect(lambda: self.shell.show_page("history"))
        head.addWidget(view_all, 0)
        recent_box.addLayout(head)
        self._recent_box = QVBoxLayout()
        self._recent_box.setSpacing(8)
        recent_box.addLayout(self._recent_box)
        recent_box.addStretch(1)
        recent_frame.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cols.addWidget(recent_frame, 1)

        self.body.addLayout(cols)
        self.body.addStretch(1)

        self.shell.mic_source.levels.connect(self.meter.set_levels)

    # -- test dictation --

    def _on_test_clicked(self) -> None:
        self.test_status.setText("Listening… speak now (records about 4 seconds).")
        self.shell.request_test_dictation()

    def set_test_result(self, text: str) -> None:
        self.test_status.setText(f"Test result: {text}" if text else "Test result: (no speech detected)")

    # -- mic meter --

    def _toggle_meter(self) -> None:
        paused = self.meter.is_active()  # toggling: active -> pause
        self.shell.set_meter_paused(paused)

    def sync_meter_button(self, paused: bool) -> None:
        self.meter_btn.setText("Resume" if paused else "Pause")
        self.meter.set_active(not paused)

    def _on_device_changed(self) -> None:
        key = self.device_combo.currentData()
        if key is None:
            return
        audio_page = self.shell.page("audio")
        if audio_page is not None:
            audio_page.set_device_key(str(key))
        self.shell.restart_mic_meter()

    # -- refresh --

    def load_from(self, cfg: dict) -> None:
        _populate_device_combo(self.device_combo, str(cfg.get("input_device", "default")))
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        cfg = self.shell.saved_cfg
        hotkey = " + ".join(p.strip().title() for p in str(cfg.get("hotkey", "")).split("+") if p.strip())
        mode = "hold" if cfg.get("hotkey_mode") == "push_to_talk" else "toggle"
        self._pipe_values["trigger"].setText(f"{hotkey} ({mode})")
        device = cfg.get("input_device", "default")
        self._pipe_values["capture"].setText("System default mic" if device == "default" else str(device))
        info = self.shell.runtime_info()
        resolved = info.get("resolved_device") or cfg.get("device", "auto")
        self._pipe_values["transcribe"].setText(f"whisper {cfg.get('model_size')} · {resolved}")
        self._pipe_values["inject"].setText("Active window · Ctrl+V paste")

        history = self.shell.history
        if history is None:
            for t in (self.tile_count, self.tile_words, self.tile_audio, self.tile_wpm):
                t.set_value("—")
        else:
            count = history.count
            words = history.total_words
            dur = history.total_duration_s
            wpm = (words / (dur / 60.0)) if dur > 0 else 0.0
            self.tile_count.set_value(f"{count}")
            self.tile_words.set_value(f"{words:,}")
            self.tile_audio.set_value(_fmt_duration(dur))
            self.tile_wpm.set_value(f"{wpm:.0f}")
        self._refresh_recent()

    def _refresh_recent(self) -> None:
        while self._recent_box.count():
            item = self._recent_box.takeAt(0)
            w = item.widget()
            if w is not None:
                # Hide before deleteLater: removed-from-layout widgets stay
                # painted at their old geometry until the event loop runs.
                w.hide()
                w.deleteLater()
        history = self.shell.history
        entries = list(reversed(history.entries()[-5:])) if history is not None else []
        if not entries:
            self._recent_box.addWidget(hint("No transcriptions yet — hold the hotkey and speak."))
            return
        for e in entries:
            row = QHBoxLayout()
            row.setSpacing(8)
            time_lbl = QLabel(_fmt_clock(e.timestamp))
            time_lbl.setProperty("role", "mono")
            row.addWidget(time_lbl, 0)
            text = e.text if len(e.text) <= 48 else e.text[:45] + "…"
            txt_lbl = QLabel(text)
            txt_lbl.setProperty("role", "fieldlabel")
            # Allow shrinking below the text's natural width so long takes
            # never force the page wider than the viewport.
            txt_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
            row.addWidget(txt_lbl, 1)
            words = QLabel(f"{e.word_count}w")
            words.setProperty("role", "hint")
            row.addWidget(words, 0)
            copy_btn = QPushButton("Copy")
            copy_btn.setProperty("compact", True)
            copy_btn.clicked.connect(lambda _=False, t=e.text: self._copy(t))
            row.addWidget(copy_btn, 0)
            wrapper = QWidget()
            wrapper.setStyleSheet("background: transparent;")
            wrapper.setLayout(row)
            self._recent_box.addWidget(wrapper)

    def _copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.shell.toast("Copied to clipboard")


# --- History --------------------------------------------------------------------

class HistoryPage(BasePage):
    page_id = "history"
    title = "History"
    description = "Latest 200 transcriptions, stored locally. Nothing leaves this machine."

    def _build(self) -> None:
        self._extra_terms = ["transcriptions", "export", "clear", "search"]

        self.export_btn = self.add_action(QPushButton("Export…"))
        self.export_btn.clicked.connect(self._export)
        self.clear_btn = self.add_action(QPushButton("Clear"))
        self.clear_btn.clicked.connect(self._clear)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search transcriptions…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self.refresh)
        toolbar.addWidget(self.search_edit, 1)
        self.mode_seg = SegmentedControl([
            ("all", "All"), ("push_to_talk", "Push to talk"), ("toggle", "Toggle"),
        ])
        self.mode_seg.set_current_key("all")
        self.mode_seg.changed.connect(lambda _key: self.refresh())
        toolbar.addWidget(self.mode_seg, 0)
        self.body.addLayout(toolbar)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["Time", "Text", "Words", "Mode", "Actions"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        # Fixed width: ResizeToContents ignores cell widgets, clipping the buttons.
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(4, 156)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.body.addWidget(self.table, 1)

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        history = self.shell.history
        query = self.search_edit.text().strip().lower()
        mode = self.mode_seg.current_key()
        rows: list[tuple[int, object]] = []
        if history is not None:
            entries = history.entries()
            for idx in range(len(entries) - 1, -1, -1):
                e = entries[idx]
                if query and query not in e.text.lower():
                    continue
                if mode != "all" and e.mode != mode:
                    continue
                rows.append((idx, e))

        self.table.setRowCount(len(rows))
        for r, (idx, e) in enumerate(rows):
            self.table.setItem(r, 0, QTableWidgetItem(_fmt_clock(e.timestamp)))
            self.table.setItem(r, 1, QTableWidgetItem(e.text))
            self.table.setItem(r, 2, QTableWidgetItem(str(e.word_count)))
            mode_text = "PTT" if e.mode == "push_to_talk" else "Toggle"
            self.table.setItem(r, 3, QTableWidgetItem(mode_text))
            actions = QWidget()
            actions.setStyleSheet("background: transparent;")
            box = QHBoxLayout(actions)
            box.setContentsMargins(2, 2, 2, 2)
            box.setSpacing(4)
            copy_btn = QPushButton("Copy")
            copy_btn.setProperty("compact", True)
            copy_btn.clicked.connect(lambda _=False, t=e.text: self._copy(t))
            box.addWidget(copy_btn)
            del_btn = QPushButton("Delete")
            del_btn.setProperty("compact", True)
            del_btn.clicked.connect(lambda _=False, i=idx: self._delete(i))
            box.addWidget(del_btn)
            self.table.setCellWidget(r, 4, actions)

    def _copy(self, text: str) -> None:
        QApplication.clipboard().setText(text)
        self.shell.toast("Copied to clipboard")

    def _delete(self, index: int) -> None:
        history = self.shell.history
        if history is not None and history.remove_at(index):
            self.shell.toast("Entry deleted")
        self.refresh()

    def _clear(self) -> None:
        history = self.shell.history
        if history is None or history.count == 0:
            self.shell.toast("History is already empty")
            return
        confirm = QMessageBox.question(
            self, "JasperVoice",
            f"Delete all {history.count} transcriptions? This cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        history.clear()
        self.refresh()
        self.shell.toast("History cleared")

    def _export(self) -> None:
        history = self.shell.history
        if history is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export history", "history.json", "JSON (*.json)")
        if not path:
            return
        try:
            count = history.export_to(path)
        except OSError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not export history:\n{e}")
            return
        self.shell.toast(f"Exported {count} entries")


# --- Dictionary ------------------------------------------------------------------

class DictionaryPage(BasePage):
    page_id = "dictionary"
    title = "Dictionary"
    description = "Offline corrections applied after every transcription — names, jargon, technical terms."

    def _build(self) -> None:
        self._extra_terms = ["rules", "replacement", "phrase", "import", "export"]

        self.import_btn = self.add_action(QPushButton("Import…"))
        self.import_btn.clicked.connect(self._import)
        self.export_btn = self.add_action(QPushButton("Export…"))
        self.export_btn.clicked.connect(self._export)

        add_row = QHBoxLayout()
        add_row.setSpacing(10)
        self.phrase_edit = QLineEdit()
        self.phrase_edit.setPlaceholderText('When I say…  (e.g. "py side")')
        add_row.addWidget(self.phrase_edit, 1)
        arrow = QLabel("→")
        arrow.setProperty("role", "hint")
        add_row.addWidget(arrow, 0)
        self.replacement_edit = QLineEdit()
        self.replacement_edit.setPlaceholderText('Replace with…  (e.g. "PySide6")')
        add_row.addWidget(self.replacement_edit, 1)
        self.add_btn = QPushButton("Add rule")
        self.add_btn.setProperty("primary", True)
        self.add_btn.clicked.connect(self._add_rule)
        add_row.addWidget(self.add_btn, 0)
        self.body.addLayout(add_row)
        self.replacement_edit.returnPressed.connect(self._add_rule)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["When I say", "Replace with", "Enabled", ""])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        # Fixed widths: ResizeToContents ignores cell widgets (switch/button).
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 104)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(46)
        self.table.setShowGrid(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.body.addWidget(self.table, 1)

        self.body.addWidget(hint(
            "Rules are precompiled regexes applied in under a millisecond, fully offline. "
            "Changes here are saved immediately."
        ))

    def _rules(self) -> list[dict]:
        rules = self.shell.saved_cfg.setdefault("dictionary", [])
        return rules

    def load_from(self, cfg: dict) -> None:  # noqa: ARG002 — reads shell.saved_cfg
        self.refresh()

    def on_shown(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        rules = self._rules()
        self.table.setRowCount(len(rules))
        for r, rule in enumerate(rules):
            self.table.setItem(r, 0, QTableWidgetItem(str(rule.get("phrase", ""))))
            self.table.setItem(r, 1, QTableWidgetItem(str(rule.get("replacement", ""))))

            switch = Switch()
            switch.setChecked(bool(rule.get("enabled", True)))
            switch.setAccessibleName(f"Enable rule {rule.get('phrase', '')}")
            switch.toggled.connect(lambda checked, i=r: self._set_enabled(i, checked))
            cell = QWidget()
            cell.setStyleSheet("background: transparent;")
            cbox = QHBoxLayout(cell)
            cbox.setContentsMargins(8, 2, 8, 2)
            cbox.addWidget(switch, 0, Qt.AlignmentFlag.AlignCenter)
            self.table.setCellWidget(r, 2, cell)

            del_btn = QPushButton("Delete")
            del_btn.setProperty("compact", True)
            del_btn.clicked.connect(lambda _=False, i=r: self._delete(i))
            dcell = QWidget()
            dcell.setStyleSheet("background: transparent;")
            dbox = QHBoxLayout(dcell)
            dbox.setContentsMargins(2, 2, 2, 2)
            dbox.addWidget(del_btn)
            self.table.setCellWidget(r, 3, dcell)

    def _add_rule(self) -> None:
        phrase = self.phrase_edit.text().strip()
        replacement = self.replacement_edit.text().strip()
        if not phrase or not replacement:
            self.shell.toast("Fill both fields to add a rule")
            return
        rules = self._rules()
        if any(r.get("phrase", "").lower() == phrase.lower() for r in rules):
            self.shell.toast(f'A rule for "{phrase}" already exists')
            return
        rules.insert(0, {"phrase": phrase, "replacement": replacement})
        self.shell.persist_config_now()
        self.phrase_edit.clear()
        self.replacement_edit.clear()
        self.phrase_edit.setFocus()
        self.refresh()
        self.shell.toast("Rule added")

    def _set_enabled(self, index: int, enabled: bool) -> None:
        rules = self._rules()
        if not (0 <= index < len(rules)):
            return
        if enabled:
            rules[index].pop("enabled", None)
        else:
            rules[index]["enabled"] = False
        self.shell.persist_config_now()
        self.shell.toast("Rule enabled" if enabled else "Rule disabled")

    def _delete(self, index: int) -> None:
        rules = self._rules()
        if not (0 <= index < len(rules)):
            return
        removed = rules.pop(index)
        self.shell.persist_config_now()
        self.refresh()
        self.shell.toast(f'Removed "{removed.get("phrase", "")}"')

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Import dictionary", "", "JSON (*.json);;All files (*)")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("file root must be a JSON array of rules")
        except (OSError, ValueError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not import dictionary:\n{e}")
            return
        rules = self._rules()
        existing = {r.get("phrase", "").lower() for r in rules}
        added = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            phrase = str(item.get("phrase", "")).strip()
            replacement = str(item.get("replacement", "")).strip()
            if not phrase or not replacement or phrase.lower() in existing:
                continue
            rule = {"phrase": phrase, "replacement": replacement}
            if not bool(item.get("enabled", True)):
                rule["enabled"] = False
            rules.append(rule)
            existing.add(phrase.lower())
            added += 1
        if added:
            self.shell.persist_config_now()
            self.refresh()
        self.shell.toast(f"Imported {added} rule(s)")

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Export dictionary", "dictionary.json", "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._rules(), f, ensure_ascii=False, indent=2)
                f.write("\n")
        except OSError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not export dictionary:\n{e}")
            return
        self.shell.toast(f"Exported {len(self._rules())} rule(s)")


# --- General --------------------------------------------------------------------

class GeneralPage(BasePage):
    page_id = "general"
    title = "General"
    description = "How dictation is triggered, and where the app lives."

    def _build(self) -> None:
        dirty = self.shell.mark_dirty

        g = self.add_group("ACTIVATION")
        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumWidth(220)
        self.hotkey_edit.editingFinished.connect(dirty)
        g.add_row("Hotkey", self.hotkey_edit, "Global — works in any app. Hold (or toggle) to record.")
        self.mode_seg = SegmentedControl([("push_to_talk", "Push to talk"), ("toggle", "Toggle")])
        self.mode_seg.changed.connect(lambda _k: dirty())
        g.add_row("Mode", self.mode_seg,
                  "Push to talk: hold to record. Toggle: press once to start, again to stop.")
        self.lang_combo = QComboBox()
        for code, label in LANGUAGES:
            self.lang_combo.addItem(label, code)
        self.lang_combo.setMinimumWidth(180)
        self.lang_combo.currentIndexChanged.connect(dirty)
        g.add_row("Spoken language", self.lang_combo, "Auto-detect picks the language per recording.")

        g = self.add_group("STARTUP & SYSTEM")
        self.launch_login = Switch()
        self.launch_login.toggled.connect(dirty)
        g.add_row("Launch at login", self.launch_login,
                  "Registers JasperVoice in the Windows startup list (installed builds only).")
        self.start_minimized = Switch()
        self.start_minimized.toggled.connect(dirty)
        g.add_row("Start minimized to tray", self.start_minimized,
                  "When off, this window opens on startup.")

        g = self.add_group("OVERLAY")
        self.show_overlay = Switch()
        self.show_overlay.toggled.connect(dirty)
        g.add_row("Show floating indicator", self.show_overlay,
                  "The on-screen pill that shows recording/processing state.")
        self.overlay_pos = SegmentedControl([
            ("top_left", "Top left"), ("top_right", "Top right"),
            ("bottom_left", "Bottom left"), ("bottom_right", "Bottom right"),
        ])
        self.overlay_pos.changed.connect(lambda _k: dirty())
        g.add_row("Position", self.overlay_pos)

        g = self.add_group("INJECTION")
        self.paste_delay = QSpinBox()
        self.paste_delay.setRange(0, 200)
        self.paste_delay.setSuffix(" ms")
        self.paste_delay.setSingleStep(5)
        self.paste_delay.valueChanged.connect(dirty)
        g.add_row("Paste delay", self.paste_delay,
                  "Pause before pasting. Raise it if text arrives truncated.")
        self.min_duration = QSpinBox()
        self.min_duration.setRange(50, 2000)
        self.min_duration.setSuffix(" ms")
        self.min_duration.setSingleStep(50)
        self.min_duration.valueChanged.connect(dirty)
        g.add_row("Minimum recording", self.min_duration,
                  "Recordings shorter than this are discarded (accidental taps).")

        self.body.addStretch(1)

    def load_from(self, cfg: dict) -> None:
        try:
            self.hotkey_edit.setKeySequence(keyboard_to_qt(cfg["hotkey"]))
        except Exception:
            self.hotkey_edit.setKeySequence(keyboard_to_qt(DEFAULT_CONFIG["hotkey"]))
        self.mode_seg.set_current_key(str(cfg.get("hotkey_mode", "push_to_talk")))
        idx = self.lang_combo.findData(cfg.get("language", "pt"))
        self.lang_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.launch_login.setChecked(bool(cfg.get("launch_at_login", False)))
        self.start_minimized.setChecked(bool(cfg.get("start_minimized", True)))
        self.show_overlay.setChecked(bool(cfg.get("show_overlay", True)))
        self.overlay_pos.set_current_key(str(cfg.get("overlay_position", "bottom_right")))
        self.paste_delay.setValue(int(cfg.get("paste_delay_ms", 15)))
        self.min_duration.setValue(int(cfg.get("min_recording_ms", 200)))

    def collect_into(self, cfg: dict) -> None:
        hotkey = qt_to_keyboard(self.hotkey_edit.keySequence())
        cfg["hotkey"] = hotkey or DEFAULT_CONFIG["hotkey"]
        cfg["hotkey_mode"] = self.mode_seg.current_key()
        cfg["language"] = str(self.lang_combo.currentData() or DEFAULT_CONFIG["language"])
        cfg["launch_at_login"] = self.launch_login.isChecked()
        cfg["start_minimized"] = self.start_minimized.isChecked()
        cfg["show_overlay"] = self.show_overlay.isChecked()
        cfg["overlay_position"] = self.overlay_pos.current_key()
        cfg["paste_delay_ms"] = int(self.paste_delay.value())
        cfg["min_recording_ms"] = int(self.min_duration.value())


# --- Audio & Mic -----------------------------------------------------------------

class AudioPage(BasePage):
    page_id = "audio"
    title = "Audio & Mic"
    description = "Input device and capture quality."

    def _build(self) -> None:
        dirty = self.shell.mark_dirty
        self._extra_terms = ["microphone", "input level", "meter"]

        g = self.add_group("INPUT DEVICE")
        device_row = QWidget()
        drow = QHBoxLayout(device_row)
        drow.setContentsMargins(0, 0, 0, 0)
        drow.setSpacing(8)
        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(280)
        self.device_combo.setAccessibleName("Microphone")
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)
        drow.addWidget(self.device_combo)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self._refresh_devices)
        drow.addWidget(self.refresh_btn)
        g.add_row("Microphone", device_row,
                  '"System default" follows the Windows default input device automatically.')

        g = self.add_group("LIVE CHECK")
        meter_col = QWidget()
        mbox = QVBoxLayout(meter_col)
        mbox.setContentsMargins(0, 0, 0, 0)
        mbox.setSpacing(6)
        self.meter = LevelMeter()
        self.meter.setMinimumWidth(480)
        self.meter.setMinimumHeight(88)
        mbox.addWidget(self.meter)
        self.meter_btn = QPushButton("Pause")
        self.meter_btn.setMaximumWidth(110)
        self.meter_btn.clicked.connect(self._toggle_meter)
        mbox.addWidget(self.meter_btn)
        g.add_row("Input level", meter_col,
                  "Speak normally — the bars should react. If not, check Windows microphone permissions.")

        g = self.add_group("CAPTURE")
        self.noise_gate = Switch()
        self.noise_gate.toggled.connect(dirty)
        g.add_row("Noise gate", self.noise_gate,
                  "Cuts background noise below a threshold before transcription. "
                  "Setting is saved now; the audio filter lands in a future update.")
        self.sound_feedback = SegmentedControl([
            ("off", "Off"), ("subtle", "Subtle"), ("all", "All events"),
        ])
        self.sound_feedback.changed.connect(lambda _k: dirty())
        g.add_row("Sound feedback", self.sound_feedback,
                  "Quiet tones on state changes. Subtle: recording start/stop. "
                  "All events: also when text is sent or an error occurs. "
                  "Applies after you press Apply.")

        self.body.addStretch(1)
        self.shell.mic_source.levels.connect(self.meter.set_levels)

    def current_device(self) -> str:
        return str(self.device_combo.currentData() or "default")

    def set_device_key(self, key: str) -> None:
        idx = self.device_combo.findData(key)
        if idx >= 0 and idx != self.device_combo.currentIndex():
            self.device_combo.setCurrentIndex(idx)

    def _on_device_changed(self) -> None:
        self.shell.mark_dirty()
        overview = self.shell.page("overview")
        if overview is not None:
            overview.device_combo.blockSignals(True)
            idx = overview.device_combo.findData(self.device_combo.currentData())
            if idx >= 0:
                overview.device_combo.setCurrentIndex(idx)
            overview.device_combo.blockSignals(False)
        self.shell.restart_mic_meter()

    def _refresh_devices(self) -> None:
        current = self.current_device()
        _populate_device_combo(self.device_combo, current)
        self.shell.toast("Device list refreshed")

    def _toggle_meter(self) -> None:
        self.shell.set_meter_paused(self.meter.is_active())

    def sync_meter_button(self, paused: bool) -> None:
        self.meter_btn.setText("Resume" if paused else "Pause")
        self.meter.set_active(not paused)

    def load_from(self, cfg: dict) -> None:
        _populate_device_combo(self.device_combo, str(cfg.get("input_device", "default")))
        self.noise_gate.setChecked(bool(cfg.get("noise_gate_enabled", False)))
        self.sound_feedback.set_current_key(str(cfg.get("sound_feedback", "off")))

    def collect_into(self, cfg: dict) -> None:
        cfg["input_device"] = self.current_device()
        cfg["noise_gate_enabled"] = self.noise_gate.isChecked()
        cfg["sound_feedback"] = self.sound_feedback.current_key()


# --- Model & Engine -----------------------------------------------------------------

MODEL_INFO = [
    # (key, footprint text, accuracy dots 1..5)
    ("tiny", "~75 MB · fastest", 1),
    ("base", "~142 MB · fast", 2),
    ("small", "~466 MB · balanced", 3),
    ("medium", "~1.5 GB · slower", 4),
    ("large-v3", "~2.9 GB · slowest", 5),
]


class ModelPage(BasePage):
    page_id = "model"
    title = "Model & Engine"
    description = "Accuracy vs. speed, and where transcription runs."

    def _build(self) -> None:
        dirty = self.shell.mark_dirty
        self._extra_terms = ["whisper", "cuda", "gpu", "compute", "warm up",
                             "download model", "delete model", "recommended",
                             *[k for k, _s, _a in MODEL_INFO]]

        self._hw_info: Optional[dict] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[_BgWorker] = None
        self._busy = False

        g = self.add_group("WHISPER MODEL")
        grid_holder = QWidget()
        grid = QGridLayout(grid_holder)
        grid.setContentsMargins(0, 10, 0, 6)
        grid.setSpacing(12)
        self.model_cards: dict[str, ModelCard] = {}
        self._card_group = QButtonGroup(self)
        self._card_group.setExclusive(True)
        for i, (key, size_text, accuracy) in enumerate(MODEL_INFO):
            card = ModelCard(key, size_text, accuracy)
            card.toggled.connect(self._on_card_toggled)
            self._card_group.addButton(card)
            self.model_cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        for col in range(3):
            grid.setColumnStretch(col, 1)
        g.add_widget(grid_holder)

        # Local model management for the selected card.
        manage = QWidget()
        mrow = QHBoxLayout(manage)
        mrow.setContentsMargins(0, 4, 0, 4)
        mrow.setSpacing(10)
        self.model_status = hint("")
        self.model_status.setWordWrap(False)
        mrow.addWidget(self.model_status, 1)
        self.download_progress = QProgressBar()
        self.download_progress.setRange(0, 0)  # indeterminate while downloading
        self.download_progress.setMaximumWidth(160)
        self.download_progress.setVisible(False)
        mrow.addWidget(self.download_progress, 0)
        self.download_btn = QPushButton("Download model")
        self.download_btn.clicked.connect(self._download_selected)
        mrow.addWidget(self.download_btn, 0)
        self.delete_btn = QPushButton("Remove from disk")
        self.delete_btn.clicked.connect(self._delete_selected)
        mrow.addWidget(self.delete_btn, 0)
        g.add_widget(manage)
        g.add_widget(hint(
            "Models are stored once in %APPDATA%\\JasperVoice\\models and stay available "
            "offline. A model that is not installed also downloads automatically on first "
            "use (or at startup warmup)."
        ))

        g = self.add_group("EXECUTION")

        # Hardware recommendation banner (filled by a background probe).
        rec_frame, rec_box = _panel()
        rec_row = QHBoxLayout()
        rec_row.setSpacing(10)
        rec_row.addWidget(glyph_label("chip", 16, COLORS["accent"]), 0, Qt.AlignmentFlag.AlignTop)
        self.recommend_label = QLabel("Checking this PC's hardware…")
        self.recommend_label.setProperty("role", "fieldlabel")
        self.recommend_label.setWordWrap(True)
        rec_row.addWidget(self.recommend_label, 1)
        self.recheck_btn = QPushButton("Re-check")
        self.recheck_btn.setProperty("compact", True)
        self.recheck_btn.clicked.connect(self._start_hardware_probe)
        rec_row.addWidget(self.recheck_btn, 0, Qt.AlignmentFlag.AlignTop)
        rec_box.addLayout(rec_row)
        g.add_widget(rec_frame)

        self.device_seg = SegmentedControl([("auto", "Auto"), ("cpu", "CPU"), ("cuda", "GPU (CUDA)")])
        self.device_seg.changed.connect(lambda _k: dirty())
        self.device_hint = hint("Auto tries CUDA first and falls back to CPU.")
        device_col = QWidget()
        dbox = QVBoxLayout(device_col)
        dbox.setContentsMargins(0, 0, 0, 0)
        dbox.setSpacing(5)
        dbox.addWidget(self.device_seg)
        dbox.addWidget(self.device_hint)
        g.add_row("Device", device_col)

        self.compute_seg = SegmentedControl([
            ("int8", "int8"), ("int16", "int16"), ("float16", "float16"), ("float32", "float32"),
        ])
        self.compute_seg.changed.connect(lambda _k: dirty())
        self.compute_hint = hint("int8 is best on CPU. float16 on GPU for speed and accuracy.")
        compute_col = QWidget()
        cbox = QVBoxLayout(compute_col)
        cbox.setContentsMargins(0, 0, 0, 0)
        cbox.setSpacing(5)
        cbox.addWidget(self.compute_seg)
        cbox.addWidget(self.compute_hint)
        g.add_row("Compute", compute_col)

        self.warmup = Switch()
        self.warmup.toggled.connect(dirty)
        g.add_row("Warm up on launch", self.warmup,
                  "Loads the model right after startup so the first dictation is instant.")

        self.body.addStretch(1)

    # -- selection / card states --

    def _on_card_toggled(self, checked: bool) -> None:
        if checked:
            self.shell.mark_dirty()
            self._refresh_model_actions()

    def on_shown(self) -> None:
        self._refresh_card_states()
        # Auto-probe once per session. Skipped headless (offscreen = tests/CI)
        # so page navigation never spins up a QThread there; the Re-check
        # button still probes on demand.
        if (
            self._hw_info is None
            and self._thread is None
            and QApplication.platformName() != "offscreen"
        ):
            self._start_hardware_probe()

    def _refresh_card_states(self) -> None:
        active = self.shell.saved_cfg.get("model_size")
        for key, card in self.model_cards.items():
            state, _path = model_cache_state(key)
            if key == active and state == "broken":
                card.set_state_text("ACTIVE · BROKEN CACHE", emphasized=True)
            elif key == active:
                card.set_state_text("ACTIVE", emphasized=True)
            elif state == "installed":
                card.set_state_text("INSTALLED")
            elif state == "broken":
                card.set_state_text("BROKEN CACHE")
            else:
                card.set_state_text("DOWNLOADS ON FIRST USE")
        self._refresh_model_actions()

    def _refresh_model_actions(self) -> None:
        key = self.selected_model()
        state, _path = model_cache_state(key)
        if self._busy:
            return  # the busy flow owns button/label state
        self.download_btn.setEnabled(state != "installed")
        self.delete_btn.setEnabled(state in {"installed", "broken"})
        if state == "installed":
            self.model_status.setText(f"{key} is installed locally.")
        elif state == "broken":
            self.model_status.setText(
                f"{key} has an incomplete local cache — remove it or download again."
            )
        else:
            self.model_status.setText(
                f"{key} is not on disk yet — download it now or let it fetch on first use."
            )

    def selected_model(self) -> str:
        for key, card in self.model_cards.items():
            if card.isChecked():
                return key
        return "small"

    def select_model(self, key: str) -> None:
        card = self.model_cards.get(key)
        if card is not None:
            card.setChecked(True)

    # -- background work (probe / download) --

    def _start_thread(self, fn, on_done, on_error) -> None:
        self._thread = QThread()
        self._worker = _BgWorker(fn)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(on_done, Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(on_error, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """App-exit path: never abandon a running QThread (that aborts the
        process). Give it a grace period, then force-stop."""
        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(3000):
                self._thread.terminate()
                self._thread.wait(1000)
            self._thread = None
            self._worker = None

    def _start_hardware_probe(self) -> None:
        if self._thread is not None:
            return
        self.recommend_label.setText("Checking this PC's hardware…")
        self._start_thread(probe_hardware, self._on_probe_done, self._on_probe_done)

    def _on_probe_done(self, info) -> None:
        self._teardown_thread()
        if not isinstance(info, dict):
            info = {"cuda_devices": 0, "note": str(info)}
        self._apply_hardware(info)

    def _apply_hardware(self, info: dict) -> None:
        """Show the friendly recommendation derived from the probe result."""
        self._hw_info = info
        _device, _compute, message = hardware_recommendation(info)
        self.recommend_label.setText(message)
        note = info.get("note")
        if note:
            self.recommend_label.setText(f"{message}\n({note})")

    def _download_selected(self) -> None:
        if self._busy or self._thread is not None:
            return
        key = self.selected_model()
        if model_installed(key):
            self.shell.toast(f"{key} is already installed")
            return
        self._busy = True
        self.download_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        self.download_progress.setVisible(True)
        self.model_status.setText(f"Downloading {key}… the app stays usable meanwhile.")
        self._start_thread(
            lambda: download_whisper_model(key),
            lambda _path: self._on_download_done(key),
            self._on_download_error,
        )

    def _on_download_done(self, key: str) -> None:
        self._teardown_thread()
        self._busy = False
        self.download_progress.setVisible(False)
        self._refresh_card_states()
        self.shell.toast(f"Model {key} downloaded")

    def _on_download_error(self, msg: str) -> None:
        self._teardown_thread()
        self._busy = False
        self.download_progress.setVisible(False)
        self._refresh_card_states()
        QMessageBox.warning(self, "JasperVoice", f"Model download failed:\n{msg}")

    def _delete_selected(self) -> None:
        if self._busy:
            return
        key = self.selected_model()
        state, target = model_cache_state(key)
        if target is None:
            self.shell.toast(f"{key} is not installed")
            return
        active = self.shell.saved_cfg.get("model_size")
        extra = (
            "\n\nThis is the active model — it will download again on next use."
            if key == active else ""
        )
        if state == "broken":
            extra += "\n\nThis cache is incomplete and should be removed before downloading again."
        confirm = QMessageBox.question(
            self, "JasperVoice",
            f"Remove the {key} model cache from disk?\n{target}{extra}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = remove_model_cache(key)
        except OSError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not remove the model:\n{e}")
            return
        if not removed:
            self.shell.toast(f"{key} is not installed")
            return
        self._refresh_card_states()
        self.shell.toast(f"Model {key} removed from disk")

    # -- load / collect --

    def load_from(self, cfg: dict) -> None:
        self.select_model(str(cfg.get("model_size", "small")))
        self.device_seg.set_current_key(str(cfg.get("device", "auto")))
        self.compute_seg.set_current_key(str(cfg.get("compute_type", "int8")))
        self.warmup.setChecked(bool(cfg.get("warmup_on_launch", True)))
        self._refresh_card_states()

    def collect_into(self, cfg: dict) -> None:
        cfg["model_size"] = self.selected_model()
        cfg["device"] = self.device_seg.current_key()
        cfg["compute_type"] = self.compute_seg.current_key()
        cfg["warmup_on_launch"] = self.warmup.isChecked()


# --- AI Polish ------------------------------------------------------------------------

OUTPUT_MODE_ORDER = ["raw", "clean", "prompt", "commit", "docs", "command"]
OUTPUT_MODE_LABELS = {
    "raw": "Raw",
    "clean": "Clean",
    "prompt": "Prompt",
    "commit": "Commit",
    "docs": "Docs",
    "command": "Command",
}
OUTPUT_MODE_HINTS = {
    "raw": "Raw — inject exactly what was transcribed. No API call.",
    "clean": "Clean — fix punctuation and casing, keep your words. Uses the fast model.",
    "prompt": "Prompt — shape the take into an LLM prompt. Uses the fast model.",
    "commit": "Commit — shape the take into a commit message. Uses the fast model.",
    "docs": "Docs — rewrite the take as documentation prose. Uses the smart model.",
    "command": "Command — shape the take into a direct command. Uses the fast model.",
}


class PolishPage(BasePage):
    page_id = "polish"
    title = "AI Polish"
    description = ("Optional text refinement through any OpenAI-compatible API — "
                   "local or remote. Off = 100% offline.")

    def _build(self) -> None:
        dirty = self.shell.mark_dirty
        self._extra_terms = ["post-processing", "provider", "endpoint", "api key",
                             "fetch models", "output style", "timeout"]
        self._thread: Optional[QThread] = None
        self._worker: Optional[_BgWorker] = None

        g = self.add_group("PROVIDER")
        self.enabled = Switch()
        self.enabled.toggled.connect(self._on_enabled_toggled)
        g.add_row("Enable polish", self.enabled,
                  "Runs after transcription, before injection. When off, no network call is ever made.")
        self.provider_combo = QComboBox()
        self.provider_combo.setMinimumWidth(320)
        self.provider_combo.addItem("Disabled", "none")
        self.provider_combo.addItem("Custom (OpenAI-compatible)", "opencode")
        self.provider_combo.currentIndexChanged.connect(dirty)
        g.add_row("Provider", self.provider_combo,
                  "Works with any OpenAI-compatible server: Ollama, LM Studio, vLLM, "
                  "OpenRouter, OpenCode, or a cloud API.")
        self.base_url = QLineEdit()
        self.base_url.setPlaceholderText("http://localhost:11434/v1  ·  https://api.example.com/v1")
        self.base_url.setMinimumWidth(420)
        self.base_url.textChanged.connect(dirty)
        g.add_row("Endpoint", self.base_url,
                  "Base URL of the API. With or without the trailing /v1 — both work.")
        self.api_key_env = QLineEdit()
        self.api_key_env.setMinimumWidth(320)
        self.api_key_env.setPlaceholderText("OPENCODE_API_KEY")
        self.api_key_env.textChanged.connect(dirty)
        g.add_row("API key env var", self.api_key_env,
                  "Enter the environment-variable name, not the key itself (e.g. OPENCODE_API_KEY). "
                  "Set the variable outside JasperVoice and restart the app. Local servers can "
                  "leave the variable unset.")

        g = self.add_group("MODELS")
        fetch_row = QWidget()
        frow = QHBoxLayout(fetch_row)
        frow.setContentsMargins(0, 0, 0, 0)
        frow.setSpacing(10)
        self.fetch_btn = QPushButton("Fetch models")
        self.fetch_btn.setMinimumWidth(140)
        self.fetch_btn.clicked.connect(self._fetch_models)
        frow.addWidget(self.fetch_btn, 0)
        self.fetch_status = hint("Fill in the endpoint (and key, if needed), then fetch the provider's model list.")
        frow.addWidget(self.fetch_status, 1)
        g.add_widget(fetch_row)

        self.fast_model = QComboBox()
        self.fast_model.setEditable(True)
        self.fast_model.setMinimumWidth(420)
        self.fast_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.fast_model.editTextChanged.connect(lambda _t: dirty())
        g.add_row("Fast model", self.fast_model,
                  "Used for quick modes (clean, prompt, commit, command). Pick from the fetched "
                  "list or type a model id.")
        self.smart_model = QComboBox()
        self.smart_model.setEditable(True)
        self.smart_model.setMinimumWidth(420)
        self.smart_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.smart_model.editTextChanged.connect(lambda _t: dirty())
        g.add_row("Smart model", self.smart_model,
                  "Used for heavier modes (docs). Pick from the fetched list or type a model id.")
        self.timeout_spin = QSpinBox()
        self.timeout_spin.setRange(1, 120)
        self.timeout_spin.setSuffix(" s")
        self.timeout_spin.setMinimumWidth(120)
        self.timeout_spin.valueChanged.connect(dirty)
        g.add_row("Timeout", self.timeout_spin,
                  "On timeout the dictionary-corrected text is injected unchanged — dictation "
                  "never gets stuck waiting for the API.")

        g = self.add_group("OUTPUT STYLE")
        self.mode_seg = SegmentedControl(
            [(m, OUTPUT_MODE_LABELS.get(m, m)) for m in OUTPUT_MODE_ORDER if m in OUTPUT_MODES]
        )
        self.mode_seg.changed.connect(self._on_mode_changed)
        self.mode_hint = hint("")
        mode_col = QWidget()
        mbox = QVBoxLayout(mode_col)
        mbox.setContentsMargins(0, 0, 0, 0)
        mbox.setSpacing(6)
        mbox.addWidget(self.mode_seg)
        mbox.addWidget(self.mode_hint)
        g.add_row("Style", mode_col)

        self.body.addStretch(1)

    def _on_enabled_toggled(self, checked: bool) -> None:
        """Make the common path work: enabling polish should enable a real
        provider and a non-raw mode unless the user already chose otherwise."""
        if checked:
            if self.provider_combo.currentData() == "none":
                idx = self.provider_combo.findData("opencode")
                if idx >= 0:
                    self.provider_combo.setCurrentIndex(idx)
            if self.mode_seg.current_key() == "raw":
                self.mode_seg.set_current_key("clean")
        self.shell.mark_dirty()

    def _on_mode_changed(self, key: str) -> None:
        self.mode_hint.setText(OUTPUT_MODE_HINTS.get(key, ""))
        self.shell.mark_dirty()

    # -- fetch models (background) --

    def _fetch_models(self) -> None:
        if self._thread is not None:
            return
        base_url = self.base_url.text().strip()
        if not base_url:
            self.fetch_status.setText("Fill in the endpoint first.")
            return
        key_env = self.api_key_env.text().strip() or DEFAULT_CONFIG["opencode_api_key_env"]
        if not is_valid_env_var_name(key_env):
            self.fetch_status.setText(
                "API key env var must be a variable name like OPENCODE_API_KEY, not the key itself."
            )
            return
        timeout = int(self.timeout_spin.value())
        self.fetch_btn.setEnabled(False)
        self.fetch_status.setText("Fetching model list…")

        from .postprocessing import fetch_available_models

        self._thread = QThread()
        self._worker = _BgWorker(lambda: fetch_available_models(base_url, key_env, timeout))
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.done.connect(self._on_models_fetched, Qt.ConnectionType.QueuedConnection)
        self._worker.error.connect(self._on_fetch_error, Qt.ConnectionType.QueuedConnection)
        self._thread.start()

    def _teardown_thread(self) -> None:
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait(2000)
            self._thread = None
        self._worker = None

    def shutdown(self) -> None:
        """App-exit path: bounded wait, then force-stop (see ModelPage.shutdown)."""
        if self._thread is not None:
            self._thread.quit()
            if not self._thread.wait(3000):
                self._thread.terminate()
                self._thread.wait(1000)
            self._thread = None
            self._worker = None

    def _on_models_fetched(self, models) -> None:
        self._teardown_thread()
        self.fetch_btn.setEnabled(True)
        self._apply_fetched_models(list(models or []))

    def _apply_fetched_models(self, models: list) -> None:
        """Fill both model pickers, keeping whatever the user already typed."""
        if not models:
            self.fetch_status.setText("The provider returned no models.")
            return
        for combo in (self.fast_model, self.smart_model):
            current = combo.currentText()
            combo.blockSignals(True)
            combo.clear()
            combo.addItems([str(m) for m in models])
            combo.setEditText(current)
            combo.blockSignals(False)
        self.fetch_status.setText(
            f"{len(models)} models loaded — pick one for Fast and one for Smart.")
        self.shell.toast(f"Fetched {len(models)} models")

    def _on_fetch_error(self, msg: str) -> None:
        self._teardown_thread()
        self.fetch_btn.setEnabled(True)
        self.fetch_status.setText(f"Could not fetch models: {msg}")

    # -- load / collect --

    def load_from(self, cfg: dict) -> None:
        self.enabled.setChecked(bool(cfg.get("post_processing_enabled", False)))
        idx = self.provider_combo.findData(cfg.get("post_processing_provider", "none"))
        self.provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.base_url.setText(str(cfg.get("opencode_base_url", "")))
        self.api_key_env.setText(str(cfg.get("opencode_api_key_env", "OPENCODE_API_KEY")))
        self.fast_model.setEditText(str(cfg.get("opencode_fast_model", "")))
        self.smart_model.setEditText(str(cfg.get("opencode_smart_model", "")))
        self.timeout_spin.setValue(int(cfg.get("opencode_timeout_s", 20)))
        self.mode_seg.set_current_key(str(cfg.get("output_mode", "raw")))
        self.mode_hint.setText(OUTPUT_MODE_HINTS.get(self.mode_seg.current_key(), ""))

    def collect_into(self, cfg: dict) -> None:
        enabled = self.enabled.isChecked()
        provider = str(self.provider_combo.currentData() or "none")
        mode = self.mode_seg.current_key()
        if enabled and provider == "none":
            provider = "opencode"
        if enabled and mode == "raw":
            mode = "clean"
        cfg["post_processing_enabled"] = enabled
        cfg["post_processing_provider"] = provider
        cfg["opencode_base_url"] = self.base_url.text().strip()
        key_env = self.api_key_env.text().strip() or DEFAULT_CONFIG["opencode_api_key_env"]
        cfg["opencode_api_key_env"] = (
            key_env if is_valid_env_var_name(key_env) else DEFAULT_CONFIG["opencode_api_key_env"]
        )
        cfg["opencode_fast_model"] = (
            self.fast_model.currentText().strip() or DEFAULT_CONFIG["opencode_fast_model"]
        )
        cfg["opencode_smart_model"] = (
            self.smart_model.currentText().strip() or DEFAULT_CONFIG["opencode_smart_model"]
        )
        cfg["opencode_timeout_s"] = int(self.timeout_spin.value())
        cfg["output_mode"] = mode


# --- Updates ------------------------------------------------------------------------

class UpdatesPage(BasePage):
    page_id = "updates"
    title = "Updates"
    description = "Checksum-verified installers straight from GitHub Releases. Entirely optional."

    def _build(self) -> None:
        dirty = self.shell.mark_dirty
        self._extra_terms = ["version", "release", "offline install", "check now"]

        self.check_btn = self.add_action(QPushButton("Check now…"))
        self.check_btn.setProperty("primary", True)
        self.check_btn.clicked.connect(self._check_now)

        frame, box = _panel()
        vrow = QHBoxLayout()
        vrow.setSpacing(14)
        vrow.addWidget(glyph_label("download", 22, COLORS["accent"]), 0, Qt.AlignmentFlag.AlignTop)
        vcol = QVBoxLayout()
        vcol.setSpacing(4)
        self.version_label = QLabel(f"JasperVoice v{__version__}")
        self.version_label.setProperty("role", "fieldlabel")
        vcol.addWidget(self.version_label)
        vcol.addWidget(hint(
            "Updates install only from a SHA-256-verified installer. An installer whose "
            "checksum cannot be verified is never run."
        ))
        vrow.addLayout(vcol, 1)
        box.addLayout(vrow)
        self.body.addWidget(frame)

        g = self.add_group("AUTOMATIC CHECK")
        self.update_check_enabled = Switch()
        self.update_check_enabled.toggled.connect(dirty)
        g.add_row("Check on startup", self.update_check_enabled,
                  "Queries only the public release list — no account, no telemetry. "
                  "JasperVoice works fully offline when this is off or the check fails.")
        self.update_repo_edit = QLineEdit()
        self.update_repo_edit.setPlaceholderText("owner/repo")
        self.update_repo_edit.setMaximumWidth(260)
        self.update_repo_edit.textChanged.connect(dirty)
        g.add_row("Release source", self.update_repo_edit,
                  "GitHub repository checked for releases (owner/repo).")

        g = self.add_group("OFFLINE INSTALL")
        self.offline_btn = QPushButton("Install from file…")
        self.offline_btn.clicked.connect(self._install_from_file)
        g.add_row("Installer file", self.offline_btn,
                  "Runs an installer .exe you downloaded yourself (air-gapped). "
                  "Its integrity is checked before it runs.")

        self.body.addStretch(1)

    def _check_now(self) -> None:
        repo = self.update_repo_edit.text().strip() or DEFAULT_CONFIG["update_repo"]
        self.shell.open_update_dialog(repo)

    def _install_from_file(self) -> None:
        from . import updater

        path, _ = QFileDialog.getOpenFileName(
            self, "Select JasperVoice installer", "",
            "Installer (*.exe);;All files (*)",
        )
        if not path:
            return
        try:
            installer = updater.stage_local_installer(path)
        except updater.UpdateError as e:
            QMessageBox.warning(self, "JasperVoice", f"Cannot use that file:\n{e}")
            return
        confirm = QMessageBox.question(
            self, "JasperVoice",
            f"Run this installer now?\n\n{installer.name}\n\n"
            "JasperVoice will close while it updates, then relaunch.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        try:
            updater.launch_installer(installer, silent=False)
        except updater.UpdateError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not launch installer:\n{e}")
            return
        QApplication.quit()

    def load_from(self, cfg: dict) -> None:
        self.update_check_enabled.setChecked(bool(cfg.get("update_check_enabled", True)))
        self.update_repo_edit.setText(str(cfg.get("update_repo", DEFAULT_CONFIG["update_repo"])))

    def collect_into(self, cfg: dict) -> None:
        cfg["update_check_enabled"] = self.update_check_enabled.isChecked()
        cfg["update_repo"] = self.update_repo_edit.text().strip() or DEFAULT_CONFIG["update_repo"]


# --- Diagnostics --------------------------------------------------------------------

LOG_FILENAME = "jaspervoice.log"
_REPO_RE = re.compile(r"^[\w.-]+/[\w.-]+$")


class DiagnosticsPage(BasePage):
    page_id = "diagnostics"
    title = "Diagnostics"
    description = "System state, storage paths, and the live log."

    def _build(self) -> None:
        self._extra_terms = ["log", "self-test", "storage", "runtime", "report", "paths"]

        self.copy_btn = self.add_action(QPushButton("Copy report"))
        self.copy_btn.clicked.connect(self._copy_report)
        self.selftest_btn = self.add_action(QPushButton("Run self-test"))
        self.selftest_btn.clicked.connect(self._run_self_test)

        cols = QHBoxLayout()
        cols.setSpacing(12)

        run_frame, run_box = _panel()
        run_box.addWidget(_panel_header("RUNTIME", "chip"))
        self._runtime_grid = QGridLayout()
        self._runtime_grid.setHorizontalSpacing(16)
        self._runtime_grid.setVerticalSpacing(5)
        run_box.addLayout(self._runtime_grid)
        run_box.addStretch(1)
        # Ignored width: the 50/50 split comes from stretch, not size hints.
        run_frame.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cols.addWidget(run_frame, 1)

        st_frame, st_box = _panel()
        st_box.addWidget(_panel_header("STORAGE", "folder"))
        self._storage_grid = QGridLayout()
        self._storage_grid.setHorizontalSpacing(16)
        self._storage_grid.setVerticalSpacing(5)
        st_box.addLayout(self._storage_grid)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        open_folder = QPushButton("Open folder")
        open_folder.clicked.connect(lambda: _open_path(str(get_app_dir())))
        btn_row.addWidget(open_folder)
        self.open_log_btn = QPushButton("Open log")
        self.open_log_btn.clicked.connect(self._open_log)
        btn_row.addWidget(self.open_log_btn)
        btn_row.addStretch(1)
        st_box.addLayout(btn_row)
        st_box.addStretch(1)
        st_frame.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        cols.addWidget(st_frame, 1)

        self.body.addLayout(cols)

        self.selftest_label = mono("")
        self.body.addWidget(self.selftest_label)

        self.body.addWidget(_panel_header("LIVE LOG", "pulse"))
        self.log_box = QPlainTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setProperty("role", "logbox")
        self.log_box.setMinimumHeight(180)
        self.body.addWidget(self.log_box, 1)

        # Created on the UI thread (page is built on the UI thread); only
        # runs while the page is visible.
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(2000)
        self._log_timer.timeout.connect(self._refresh_log)

    # -- data collection --

    def _log_path(self):
        return get_app_dir() / LOG_FILENAME

    def _runtime_rows(self) -> list[tuple[str, str]]:
        import PySide6

        rows = [
            ("Version", f"v{__version__}" + (" (frozen)" if getattr(sys, "frozen", False) else " (dev)")),
            ("Python", f"{platform.python_version()} · {sys.platform}"),
            ("Qt", f"PySide6 {PySide6.__version__}"),
        ]
        engine_bits = []
        for dist in ("faster-whisper", "ctranslate2"):
            try:
                from importlib.metadata import version

                engine_bits.append(f"{dist} {version(dist)}")
            except Exception:
                continue
        rows.append(("Engine", " · ".join(engine_bits) or "faster-whisper (not importable)"))
        info = self.shell.runtime_info()
        resolved = info.get("resolved_device")
        loaded = info.get("model_loaded")
        if resolved:
            rows.append(("Device", f"{resolved} (model loaded)" if loaded else str(resolved)))
        else:
            rows.append(("Device", "model not loaded yet"))
        return rows

    @staticmethod
    def _compact_path(p) -> str:
        """Shorten app-dir paths for display: '…\\JasperVoice\\config.json'."""
        s = str(p)
        base = str(get_app_dir())
        if s.startswith(base):
            return "…\\JasperVoice" + s[len(base):]
        return s

    def _storage_rows(self) -> list[tuple[str, str]]:
        cfg_path = cfg_mod.get_config_path()
        models = get_models_dir()
        history = self.shell.history
        hist_path = get_app_dir() / "history.json"
        log_path = self._log_path()

        def _file_info(p) -> str:
            shown = self._compact_path(p)
            try:
                return f"{shown} · {_fmt_size(p.stat().st_size)}" if p.exists() else f"{shown} · (missing)"
            except OSError:
                return shown

        hist_desc = _file_info(hist_path)
        if history is not None:
            hist_desc = f"{history.count} entries · {hist_desc}"
        return [
            ("Config", _file_info(cfg_path)),
            ("Models", f"{self._compact_path(models)} · {_fmt_size(_dir_size(models))}"),
            ("History", hist_desc),
            ("Log", _file_info(log_path)),
        ]

    @staticmethod
    def _fill_grid(grid: QGridLayout, rows: list[tuple[str, str]]) -> None:
        while grid.count():
            item = grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.hide()
                w.deleteLater()
        for r, (key, value) in enumerate(rows):
            key_lbl = QLabel(key)
            key_lbl.setProperty("role", "hint")
            grid.addWidget(key_lbl, r, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(mono(value), r, 1)
        grid.setColumnStretch(1, 1)

    def on_shown(self) -> None:
        self._fill_grid(self._runtime_grid, self._runtime_rows())
        self._fill_grid(self._storage_grid, self._storage_rows())
        self._refresh_log()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._log_timer.start()

    def hideEvent(self, event) -> None:  # noqa: N802
        super().hideEvent(event)
        self._log_timer.stop()

    # -- live log --

    def _refresh_log(self) -> None:
        path = self._log_path()
        if not path.exists():
            self.log_box.setPlainText("(no log file yet — the windowed build writes jaspervoice.log)")
            return
        try:
            with path.open("rb") as f:
                f.seek(0, os.SEEK_END)
                size = f.tell()
                f.seek(max(0, size - 16384))
                tail = f.read().decode("utf-8", errors="replace")
        except OSError as e:
            self.log_box.setPlainText(f"(could not read log: {e})")
            return
        lines = tail.splitlines()[-100:]
        text = "\n".join(lines)
        if text != self.log_box.toPlainText():
            self.log_box.setPlainText(text)
            scrollbar = self.log_box.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def _open_log(self) -> None:
        path = self._log_path()
        if path.exists():
            _open_path(str(path))
        else:
            self.shell.toast("No log file yet")

    # -- self-test / report --

    def _self_test_results(self) -> list[tuple[str, bool, str]]:
        results: list[tuple[str, bool, str]] = []

        cfg_path = cfg_mod.get_config_path()
        try:
            readable = cfg_path.exists()
            writable = os.access(str(cfg_path.parent), os.W_OK)
            results.append(("Config file", readable and writable,
                            str(cfg_path) if readable else "missing (created on first save)"))
        except OSError as e:
            results.append(("Config file", False, str(e)))

        try:
            import sounddevice as sd

            default_in = sd.default.device[0]
            ok = default_in is not None and default_in >= 0
            results.append(("Default microphone", ok,
                            "available" if ok else "no default input device set in Windows"))
        except Exception as e:
            results.append(("Default microphone", False, str(e)))

        models = get_models_dir()
        results.append(("Models directory", models.is_dir(), str(models)))

        history = self.shell.history
        if history is not None:
            try:
                count = history.count
                results.append(("History", True, f"{count} entries readable"))
            except Exception as e:
                results.append(("History", False, str(e)))
        else:
            results.append(("History", True, "not attached (no app context)"))

        repo = str(self.shell.saved_cfg.get("update_repo", ""))
        results.append(("Updater config", bool(_REPO_RE.match(repo)),
                        repo or "empty update_repo"))

        try:
            import importlib

            importlib.import_module("jaspervoice.injection")
            results.append(("Injection module", True, "importable"))
        except Exception as e:
            results.append(("Injection module", False, str(e)))

        return results

    def _run_self_test(self) -> None:
        results = self._self_test_results()
        lines = [
            f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
            for name, ok, detail in results
        ]
        self.selftest_label.setText("\n".join(lines))
        failed = sum(1 for _n, ok, _d in results if not ok)
        self.shell.toast("Self-test passed" if failed == 0 else f"Self-test: {failed} check(s) failed")

    def _copy_report(self) -> None:
        lines = ["JasperVoice diagnostics report", "=" * 32, "", "[runtime]"]
        lines += [f"{k}: {v}" for k, v in self._runtime_rows()]
        lines += ["", "[storage]"]
        lines += [f"{k}: {v}" for k, v in self._storage_rows()]
        lines += ["", "[self-test]"]
        lines += [
            f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}"
            for name, ok, detail in self._self_test_results()
        ]
        QApplication.clipboard().setText("\n".join(lines))
        self.shell.toast("Diagnostics copied to clipboard")


PAGE_CLASSES = [
    OverviewPage,
    HistoryPage,
    DictionaryPage,
    GeneralPage,
    AudioPage,
    ModelPage,
    PolishPage,
    UpdatesPage,
    DiagnosticsPage,
]
