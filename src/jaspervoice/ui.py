"""Settings window for JasperVoice (dark theme, non-modal, live-apply)."""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import sys
from copy import deepcopy
from typing import Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QKeySequenceEdit,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCore import QThread

from . import __version__
from . import config as cfg_mod
from .config import (
    DEFAULT_CONFIG,
    VALID_COMPUTE_TYPES,
    VALID_DEVICES,
    VALID_MODEL_SIZES,
    get_app_dir,
    get_models_dir,
)

log = logging.getLogger(__name__)


# --- Hotkey format conversion (Qt <-> keyboard-lib) ---

# Tokens that don't title-case cleanly. Map them explicitly; anything else
# passes through .title() (handles single letters, f1-f24, digits).
_TOKEN_TITLE = {
    "ctrl": "Ctrl",
    "shift": "Shift",
    "alt": "Alt",
    "altgr": "AltGr",
    "meta": "Meta",
    "super": "Super",
    "space": "Space",
    "tab": "Tab",
    "enter": "Enter",
    "return": "Return",
    "esc": "Esc",
    "escape": "Escape",
    "backspace": "Backspace",
    "delete": "Delete",
    "del": "Delete",
    "insert": "Insert",
    "home": "Home",
    "end": "End",
    "pgup": "PgUp",
    "pageup": "PgUp",
    "pgdown": "PgDown",
    "pagedown": "PgDown",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "capslock": "CapsLock",
    "numlock": "NumLock",
    "scrolllock": "ScrollLock",
    "printscreen": "PrintScreen",
    "menu": "Menu",
}


def keyboard_to_qt(s: str) -> QKeySequence:
    """Convert keyboard-lib format ('ctrl+shift+r') to QKeySequence."""
    parts = [p.strip() for p in s.lower().split("+") if p.strip()]
    qt_parts = [_TOKEN_TITLE.get(p, p.title()) for p in parts]
    return QKeySequence("+".join(qt_parts))


def qt_to_keyboard(seq: QKeySequence) -> str:
    """Convert QKeySequence to keyboard-lib format. Returns empty string if no keys set."""
    s = seq.toString()
    if not s:
        return ""
    # Qt's toString() returns tokens already separated by '+'. We need the
    # reverse of _TOKEN_TITLE, but .lower() works for every entry because
    # the canonical Qt names are the same words as the keyboard-lib tokens.
    return s.lower()


# --- Languages ---

LANGUAGES = [
    ("pt", "Português"),
    ("en", "English"),
    ("es", "Español"),
    ("auto", "Auto-detect"),
]


# Ordered + human-friendly labels for the radio groups. Anything not listed
# here still renders (falls back to the raw key) so new config values won't
# silently disappear from the UI.
MODEL_ORDER = ["tiny", "base", "small", "medium", "large-v3"]
MODEL_HINTS = {
    "tiny": "Fastest, lowest accuracy",
    "base": "Fast, basic accuracy",
    "small": "Balanced — recommended",
    "medium": "Slower, higher accuracy",
    "large-v3": "Slowest, best accuracy",
}

DEVICE_ORDER = ["auto", "cpu", "cuda"]
DEVICE_LABELS = {
    "auto": "Auto",
    "cpu": "CPU",
    "cuda": "GPU (CUDA)",
}

COMPUTE_ORDER = ["int8", "int16", "float16", "float32"]
COMPUTE_LABELS = {
    "int8": "int8",
    "int16": "int16",
    "float16": "float16",
    "float32": "float32",
}


def _ordered_keys(valid: set[str], order: list[str]) -> list[str]:
    """Return keys from `valid` in `order`, appending any extras at the end."""
    ordered = [k for k in order if k in valid]
    ordered += [k for k in valid if k not in order]
    return ordered


# --- Label helpers ---

def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "section")
    return lbl


def _muted_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "muted")
    lbl.setWordWrap(True)
    return lbl


def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "fieldlabel")
    return lbl


def _hint_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setProperty("role", "hint")
    lbl.setWordWrap(True)
    return lbl


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    """Build a titled card container; returns (frame, content_layout)."""
    frame = QFrame()
    frame.setProperty("role", "card")
    box = QVBoxLayout(frame)
    box.setContentsMargins(18, 14, 18, 16)
    box.setSpacing(10)

    header = QLabel(title)
    header.setProperty("role", "section")
    box.addWidget(header)
    return frame, box


# --- Settings window ---

class SettingsWindow(QMainWindow):
    """JasperVoice settings dialog. Non-modal, X hides, Apply/Cancel footer."""

    configChanged = Signal(dict)

    def __init__(self, cfg: dict, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.setWindowTitle("JasperVoice — Settings")
        self.setMinimumSize(640, 520)
        self.resize(800, 560)

        # Working copy of config; updated on Apply.
        self._cfg = deepcopy(cfg)
        # Slight extensions for v1 UI fields. Falls back to sensible defaults
        # if older config.json doesn't have them.
        self._cfg.setdefault("paste_delay_ms", 15)
        self._cfg.setdefault("min_recording_ms", 200)

        self._dirty = False

        self._build_ui()
        self._load_values_into_ui()
        self.apply_btn.setEnabled(False)

    # --- Construction ---

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Header band ---
        header_band = QWidget()
        header_band.setObjectName("headerBand")
        hb = QVBoxLayout(header_band)
        hb.setContentsMargins(28, 22, 28, 18)
        hb.setSpacing(2)
        title = QLabel("JASPERVOICE")
        title.setProperty("role", "title")
        hb.addWidget(title)
        subtitle = QLabel("Push-to-talk voice dictation")
        subtitle.setProperty("role", "subtitle")
        hb.addWidget(subtitle)
        root.addWidget(header_band)

        divider = QFrame()
        divider.setProperty("role", "divider")
        root.addWidget(divider)

        # --- Scrollable body (cards) ---
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        # Outer layout centers a fixed-width column so maximizing the window
        # doesn't stretch the cards across the whole screen.
        outer = QHBoxLayout(body)
        outer.setContentsMargins(24, 20, 24, 20)
        outer.setSpacing(0)
        outer.addStretch(1)

        column = QWidget()
        column.setMaximumWidth(720)
        column.setStyleSheet("background: transparent;")
        content = QVBoxLayout(column)
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(16)

        content.addWidget(self._build_general_card())
        content.addWidget(self._build_whisper_card())
        content.addWidget(self._build_behavior_card())
        content.addWidget(self._build_updates_card())
        content.addWidget(self._build_diagnostics_card())
        content.addStretch(1)

        outer.addWidget(column, 0)
        outer.addStretch(1)

        root.addWidget(scroll, 1)

        # --- Footer band ---
        footer_band = QWidget()
        footer_band.setObjectName("footerBand")
        fb = QHBoxLayout(footer_band)
        fb.setContentsMargins(24, 14, 24, 16)
        fb.setSpacing(10)
        self.status_hint = QLabel("")
        self.status_hint.setProperty("role", "hint")
        fb.addWidget(self.status_hint)
        fb.addStretch(1)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.clicked.connect(self._on_cancel)
        self.apply_btn = QPushButton("Apply")
        self.apply_btn.setProperty("primary", True)
        self.apply_btn.setDefault(True)
        self.apply_btn.clicked.connect(self._on_apply)
        fb.addWidget(self.cancel_btn)
        fb.addWidget(self.apply_btn)

        top_divider = QFrame()
        top_divider.setProperty("role", "divider")
        root.addWidget(top_divider)
        root.addWidget(footer_band)

    # --- Card builders ---

    def _build_general_card(self) -> QFrame:
        frame, box = _card("General")
        grid = self._field_grid()

        self.hotkey_edit = QKeySequenceEdit()
        self.hotkey_edit.setMaximumWidth(240)
        self.hotkey_edit.editingFinished.connect(self._mark_dirty)
        self._add_field(
            grid, 0, "Hotkey", self.hotkey_edit,
            "Hold to record, release to transcribe.",
        )

        self.hotkey_mode_combo = QComboBox()
        self.hotkey_mode_combo.setMaximumWidth(240)
        self.hotkey_mode_combo.addItem("Push to talk", "push_to_talk")
        self.hotkey_mode_combo.addItem("Toggle (press to start/stop)", "toggle")
        self.hotkey_mode_combo.currentIndexChanged.connect(self._mark_dirty)
        self._add_field(
            grid, 1, "Mode", self.hotkey_mode_combo,
            "Push to talk: hold to record. Toggle: press once to start, again to stop.",
        )

        self.lang_combo = QComboBox()
        self.lang_combo.setMaximumWidth(240)
        for code, label in LANGUAGES:
            self.lang_combo.addItem(label, code)
        self.lang_combo.currentIndexChanged.connect(self._mark_dirty)
        self._add_field(
            grid, 2, "Language", self.lang_combo,
            "Spoken language. Auto-detect picks per recording.",
        )

        box.addLayout(grid)
        return frame

    def _build_whisper_card(self) -> QFrame:
        frame, box = _card("Whisper Model")

        self._model_group = QButtonGroup(self)
        self._model_radios = {}
        for size in _ordered_keys(VALID_MODEL_SIZES, MODEL_ORDER):
            rb = QRadioButton(size)
            rb.setToolTip(MODEL_HINTS.get(size, ""))
            rb.toggled.connect(self._mark_dirty)
            self._model_group.addButton(rb)
            self._model_radios[size] = rb
        box.addLayout(self._radio_row("Model", self._model_radios))
        box.addWidget(_hint_label(
            "Larger models are more accurate but slower. "
            "small is the balanced default for dictation."
        ))

        self._device_group = QButtonGroup(self)
        self._device_radios = {}
        for dev in _ordered_keys(VALID_DEVICES, DEVICE_ORDER):
            rb = QRadioButton(DEVICE_LABELS.get(dev, dev))
            rb.toggled.connect(self._mark_dirty)
            self._device_group.addButton(rb)
            self._device_radios[dev] = rb
        box.addLayout(self._radio_row("Device", self._device_radios))

        self._compute_group = QButtonGroup(self)
        self._compute_radios = {}
        for ct in _ordered_keys(VALID_COMPUTE_TYPES, COMPUTE_ORDER):
            rb = QRadioButton(COMPUTE_LABELS.get(ct, ct))
            rb.toggled.connect(self._mark_dirty)
            self._compute_group.addButton(rb)
            self._compute_radios[ct] = rb
        box.addLayout(self._radio_row("Compute", self._compute_radios))
        box.addWidget(_hint_label(
            "int8 is best on CPU. Use float16 on GPU for speed and accuracy."
        ))
        return frame

    def _build_behavior_card(self) -> QFrame:
        frame, box = _card("Behavior")
        grid = self._field_grid()

        self.paste_delay = QSpinBox()
        self.paste_delay.setRange(0, 200)
        self.paste_delay.setSuffix(" ms")
        self.paste_delay.setSingleStep(5)
        self.paste_delay.setMaximumWidth(120)
        self.paste_delay.valueChanged.connect(self._mark_dirty)
        self._add_field(
            grid, 0, "Paste delay", self.paste_delay,
            "Pause before pasting. Raise if text arrives truncated.",
        )

        self.min_duration = QSpinBox()
        self.min_duration.setRange(50, 2000)
        self.min_duration.setSuffix(" ms")
        self.min_duration.setSingleStep(50)
        self.min_duration.setMaximumWidth(120)
        self.min_duration.valueChanged.connect(self._mark_dirty)
        self._add_field(
            grid, 1, "Min recording", self.min_duration,
            "Recordings shorter than this are ignored.",
        )

        box.addLayout(grid)
        return frame

    def _build_updates_card(self) -> QFrame:
        frame, box = _card("Updates")

        self.update_check_enabled = QCheckBox(
            "Check GitHub for updates when JasperVoice starts"
        )
        self.update_check_enabled.toggled.connect(self._mark_dirty)
        box.addWidget(self.update_check_enabled)
        box.addWidget(_hint_label(
            "Only the public release list is queried — no account, no telemetry, "
            "and no source code is downloaded. Updates install from a signed, "
            "checksum-verified installer. JasperVoice works fully offline if this "
            "is off or the check fails."
        ))

        grid = self._field_grid()
        self.update_repo_edit = QLineEdit()
        self.update_repo_edit.setMaximumWidth(280)
        self.update_repo_edit.setPlaceholderText("owner/repo")
        self.update_repo_edit.textChanged.connect(self._mark_dirty)
        self._add_field(
            grid, 0, "Release source", self.update_repo_edit,
            "GitHub repository to check for releases (owner/repo).",
        )
        box.addLayout(grid)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)
        check_btn = QPushButton("Check now...")
        check_btn.setMaximumWidth(160)
        check_btn.clicked.connect(self._open_update_dialog)
        btn_row.addWidget(check_btn)
        offline_btn = QPushButton("Install from file...")
        offline_btn.setMaximumWidth(180)
        offline_btn.clicked.connect(self._install_from_file)
        btn_row.addWidget(offline_btn)
        btn_row.addStretch(1)
        box.addLayout(btn_row)
        box.addWidget(_hint_label(
            "\"Install from file\" runs an installer .exe you downloaded yourself "
            "(offline / air-gapped). It is checked for integrity before running."
        ))
        return frame

    def _build_diagnostics_card(self) -> QFrame:
        frame, box = _card("Diagnostics")
        grid = QGridLayout()
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(6)

        self.config_path_label = QLabel(str(cfg_mod.get_config_path()))
        self.config_path_label.setProperty("role", "mono")
        self.config_path_label.setWordWrap(True)
        self.config_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(_field_label("Config"), 0, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.config_path_label, 0, 1)

        self.models_path_label = QLabel(str(get_models_dir()))
        self.models_path_label.setProperty("role", "mono")
        self.models_path_label.setWordWrap(True)
        self.models_path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        grid.addWidget(_field_label("Models"), 1, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(self.models_path_label, 1, 1)

        self.version_label = QLabel(
            f"v{__version__}  •  Python {platform.python_version()}  •  {sys.platform}"
        )
        self.version_label.setProperty("role", "muted")
        grid.addWidget(_field_label("Version"), 2, 0)
        grid.addWidget(self.version_label, 2, 1)

        box.addLayout(grid)

        open_btn = QPushButton("Open config folder")
        open_btn.setMaximumWidth(180)
        open_btn.clicked.connect(self._open_config_folder)
        box.addWidget(open_btn)
        return frame

    # --- Layout helpers ---

    @staticmethod
    def _field_grid() -> QGridLayout:
        grid = QGridLayout()
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)
        return grid

    def _add_field(
        self, grid: QGridLayout, row: int, label: str, widget: QWidget, hint: str
    ) -> None:
        grid.addWidget(_field_label(label), row, 0, Qt.AlignmentFlag.AlignTop)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(2)
        col.addWidget(widget, 0, Qt.AlignmentFlag.AlignLeft)
        if hint:
            col.addWidget(_hint_label(hint))
        wrapper = QWidget()
        wrapper.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        wrapper.setStyleSheet("background: transparent;")
        wrapper.setLayout(col)
        grid.addWidget(wrapper, row, 1)

    def _radio_row(self, label: str, radios: dict) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        lbl = _field_label(label)
        lbl.setMinimumWidth(110)
        lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        row.addWidget(lbl, 0, Qt.AlignmentFlag.AlignTop)
        radios_box = QHBoxLayout()
        radios_box.setContentsMargins(0, 0, 0, 0)
        radios_box.setSpacing(16)
        for rb in radios.values():
            radios_box.addWidget(rb)
        radios_box.addStretch(1)
        row.addLayout(radios_box, 1)
        return row

    # --- Load / collect ---

    def _load_values_into_ui(self) -> None:
        """Populate the form from self._cfg, blocking signals so this does
        not mark the form dirty."""
        widgets = self._all_input_widgets()
        for w in widgets:
            w.blockSignals(True)
        try:
            try:
                self.hotkey_edit.setKeySequence(keyboard_to_qt(self._cfg["hotkey"]))
            except Exception:
                self.hotkey_edit.setKeySequence(QKeySequence(DEFAULT_CONFIG["hotkey"]))
            self._set_combo_by_data(self.lang_combo, self._cfg["language"])
            self._set_combo_by_data(self.hotkey_mode_combo, self._cfg.get("hotkey_mode", "push_to_talk"))
            self._check_radio(self._model_radios, self._cfg["model_size"], "small")
            self._check_radio(self._device_radios, self._cfg["device"], "auto")
            self._check_radio(self._compute_radios, self._cfg["compute_type"], "int8")
            self.paste_delay.setValue(int(self._cfg.get("paste_delay_ms", 15)))
            self.min_duration.setValue(int(self._cfg.get("min_recording_ms", 200)))
            self.update_check_enabled.setChecked(bool(self._cfg.get("update_check_enabled", True)))
            self.update_repo_edit.setText(str(self._cfg.get("update_repo", DEFAULT_CONFIG["update_repo"])))
        finally:
            for w in widgets:
                w.blockSignals(False)
        self._dirty = False
        self.apply_btn.setEnabled(False)
        if hasattr(self, "status_hint"):
            self.status_hint.setText("")

    def _all_input_widgets(self) -> list[QWidget]:
        return [
            self.hotkey_edit,
            self.lang_combo,
            self.hotkey_mode_combo,
            self.paste_delay,
            self.min_duration,
            self.update_check_enabled,
            self.update_repo_edit,
            *self._model_radios.values(),
            *self._device_radios.values(),
            *self._compute_radios.values(),
        ]

    @staticmethod
    def _set_combo_by_data(combo: QComboBox, data: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == data:
                combo.setCurrentIndex(i)
                return
        combo.setCurrentIndex(0)

    @staticmethod
    def _check_radio(radios: dict[str, QRadioButton], key: str, fallback: str) -> None:
        if key in radios:
            radios[key].setChecked(True)
        elif fallback in radios:
            radios[fallback].setChecked(True)

    def _collect_values(self) -> dict:
        hotkey = qt_to_keyboard(self.hotkey_edit.keySequence())
        if not hotkey:
            hotkey = DEFAULT_CONFIG["hotkey"]
        language = self.lang_combo.currentData() or DEFAULT_CONFIG["language"]
        return {
            **self._cfg,
            "hotkey": hotkey,
            "hotkey_mode": str(self.hotkey_mode_combo.currentData() or "push_to_talk"),
            "language": str(language),
            "model_size": self._checked_key(self._model_radios, "small"),
            "device": self._checked_key(self._device_radios, "auto"),
            "compute_type": self._checked_key(self._compute_radios, "int8"),
            "paste_delay_ms": int(self.paste_delay.value()),
            "min_recording_ms": int(self.min_duration.value()),
            "update_check_enabled": bool(self.update_check_enabled.isChecked()),
            "update_repo": self.update_repo_edit.text().strip() or DEFAULT_CONFIG["update_repo"],
        }

    @staticmethod
    def _checked_key(radios: dict[str, QRadioButton], fallback: str) -> str:
        for key, rb in radios.items():
            if rb.isChecked():
                return key
        return fallback

    # --- Apply / cancel ---

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True
            self.apply_btn.setEnabled(True)
            self.status_hint.setText("Unsaved changes")

    def _on_apply(self) -> None:
        new_cfg = self._collect_values()
        self._cfg = new_cfg
        cfg_mod.save_config(new_cfg)
        self.configChanged.emit(new_cfg)
        self._dirty = False
        self.apply_btn.setEnabled(False)
        self.status_hint.setText("Saved")

    def _on_cancel(self) -> None:
        self._load_values_into_ui()

    # --- Other actions ---

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

    def closeEvent(self, event) -> None:  # noqa: ARG002
        # Hide instead of closing. App keeps running.
        self.hide()

    def update_config(self, cfg: dict) -> None:
        self._cfg = deepcopy(cfg)
        self._load_values_into_ui()

    # --- Update actions ---

    def _open_update_dialog(self) -> None:
        repo = self.update_repo_edit.text().strip() or DEFAULT_CONFIG["update_repo"]
        dlg = UpdateDialog(repo=repo, parent=self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        self._update_dialog = dlg  # keep a reference

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
            QMessageBox.Yes | QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        try:
            updater.launch_installer(installer, silent=False)
        except updater.UpdateError as e:
            QMessageBox.warning(self, "JasperVoice", f"Could not launch installer:\n{e}")
            return
        # Quit so the installer can replace locked files.
        from PySide6.QtWidgets import QApplication
        QApplication.quit()


class StatsWindow(QMainWindow):
    """Usage statistics: total words, average WPM, total audio time, history."""

    def __init__(self, history, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._history = history
        self.setWindowTitle("JasperVoice — Statistics")
        self.setMinimumSize(560, 420)
        self.resize(600, 480)
        self._build_ui()

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # --- Summary card ---
        frame, box = _card("Summary")
        self._total_label = QLabel("0 transcriptions")
        self._total_label.setProperty("role", "fieldlabel")
        box.addWidget(self._total_label)
        self._words_label = QLabel("0 words")
        self._words_label.setProperty("role", "fieldlabel")
        box.addWidget(self._words_label)
        self._duration_label = QLabel("0.0s total audio")
        self._duration_label.setProperty("role", "fieldlabel")
        box.addWidget(self._duration_label)
        self._wpm_label = QLabel("0.0 avg WPM")
        self._wpm_label.setProperty("role", "fieldlabel")
        box.addWidget(self._wpm_label)
        root.addWidget(frame)

        # --- History card ---
        hist_frame, hist_box = _card("Recent Transcriptions")
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Time", "Words", "Mode", "Text"])
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setAlternatingRowColors(True)
        hist_box.addWidget(self._table)

        clear_btn = QPushButton("Clear history")
        clear_btn.setMaximumWidth(140)
        clear_btn.clicked.connect(self._clear_history)
        hist_box.addWidget(clear_btn)

        root.addWidget(hist_frame, 1)

    def refresh(self) -> None:
        entries = self._history.entries()
        total_words = self._history.total_words
        total_dur = self._history.total_duration_s
        count = self._history.count
        avg_wpm = (total_words / (total_dur / 60.0)) if total_dur > 0 else 0.0

        self._total_label.setText(f"{count} transcriptions")
        self._words_label.setText(f"{total_words} words")
        self._duration_label.setText(f"{total_dur:.1f}s total audio")
        self._wpm_label.setText(f"{avg_wpm:.1f} avg WPM")

        recent = list(reversed(entries[-50:]))
        self._table.setRowCount(len(recent))
        for i, e in enumerate(recent):
            ts = e.timestamp[11:16] if len(e.timestamp) >= 16 else e.timestamp
            self._table.setItem(i, 0, QTableWidgetItem(ts))
            self._table.setItem(i, 1, QTableWidgetItem(str(e.word_count)))
            self._table.setItem(i, 2, QTableWidgetItem(e.mode))
            self._table.setItem(i, 3, QTableWidgetItem(e.text[:120]))

    def _clear_history(self) -> None:
        self._history.clear()
        self.refresh()

    def closeEvent(self, event) -> None:  # noqa: ARG002
        self.hide()


# --- Update dialog + background workers ---

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

        frame, box = _card("Software Update")
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
        self._action_btn.setText("Download && Install")
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
            "Downloaded and verified. Click Install to update — JasperVoice will "
            "close, update, and relaunch."
        )
        self._action_btn.setText("Install")
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
        from PySide6.QtWidgets import QApplication

        try:
            updater.launch_installer(self._installer_path, silent=False)
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

    def closeEvent(self, event) -> None:  # noqa: ARG002
        self._teardown_thread()
        super().closeEvent(event)
