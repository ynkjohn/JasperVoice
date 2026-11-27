"""JasperVoice dark palette and Qt widget styling."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from .assets import asset_path

# --- Palette (extracted from the user-provided overlay SVGs) ---

COLORS = {
    "bg": "#13161A",
    "bg_alt": "#1D2228",
    "bg_hover": "#272E36",
    "border": "#303840",
    "border_strong": "#49535E",
    "fg": "#F3F1EE",
    "fg_muted": "#B3BCC5",
    "fg_disabled": "#78818A",
    "accent": "#F4A485",
    "focus": "#97C8FF",
    "accent_hover": "#FFBEA4",
    "danger": "#FF767D",
    "warning": "#F2C373",
}

# State colors for the recording overlay (used by overlay.py too).
STATE_COLORS = {
    "idle": {
        "border": "#333340",
        "fill": "#1c1c22",
        "dot": "#555555",
        "text": "rgba(255,255,255,0.45)",
    },
    "recording": {
        "border": "#ef4444",
        "fill": "#1c1c22",
        "dot": "#ef4444",
        "text": "#ff6e6e",
        "text_label": "Listening...",
    },
    "processing": {
        "border": "#f59e0b",
        "fill": "#1c1c22",
        "dot": "#f59e0b",
        "text": "#f59e0b",
        "text_label": "Processing...",
    },
    "send": {
        "border": "#22c55e",
        "fill": "#1c1c22",
        "dot": "#22c55e",
        "text": "#4ade80",
        "text_label": "Sent!",
    },
    "error": {
        "border": "#ef4444",
        "fill": "#1c1c22",
        "dot": "#ef4444",
        "text": "#ff6e6e",
        "text_label": "Error",
    },
}

FONTS = {
    "mono": "Consolas",
    "sans": "Segoe UI",
}

STYLESHEET = f"""
QWidget {{
    color: {COLORS['fg']};
    font-family: {FONTS['sans']};
    font-size: 14px;
}}

QMainWindow, QDialog {{
    background-color: {COLORS['bg']};
    color: {COLORS['fg']};
    font-family: {FONTS['sans']};
    font-size: 13px;
}}

QLabel[role="section"] {{
    font-family: {FONTS['mono']};
    font-size: 11px;
    font-weight: bold;
    color: {COLORS['accent']};
    background: transparent;
    padding-bottom: 2px;
}}

QLabel[role="muted"] {{
    color: {COLORS['fg_muted']};
    font-size: 12px;
    background: transparent;
}}

QLabel[role="hint"] {{
    color: {COLORS['fg_muted']};
    font-size: 12px;
    background: transparent;
    padding-top: 2px;
}}

QLabel[role="title"] {{
    font-family: {FONTS['mono']};
    font-size: 15px;
    font-weight: bold;
    color: {COLORS['fg']};
    background: transparent;
    border: none;
}}

QLabel[role="subtitle"] {{
    color: {COLORS['fg_muted']};
    font-size: 12px;
    background: transparent;
    border: none;
}}

QLabel[role="mono"] {{
    font-family: {FONTS['mono']};
    font-size: 12px;
    color: {COLORS['fg_muted']};
    background: transparent;
}}

QLabel[role="fieldlabel"] {{
    color: {COLORS['fg']};
    font-size: 13px;
    background: transparent;
}}

QFrame[role="card"] {{
    background-color: {COLORS['bg_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
}}

QFrame[role="divider"] {{
    background-color: {COLORS['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}

QWidget#headerBand {{
    background-color: {COLORS['bg']};
}}

QWidget#footerBand {{
    background-color: {COLORS['bg']};
}}

QPushButton {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 6px;
    padding: 8px 18px;
    font-family: {FONTS['sans']};
    font-size: 13px;
}}
QPushButton:hover {{
    border-color: {COLORS['accent']};
    color: {COLORS['accent']};
    background-color: {COLORS['bg_hover']};
}}
QPushButton:pressed {{
    background-color: {COLORS['bg_hover']};
}}
QPushButton:focus {{
    border-color: {COLORS['accent']};
}}
QPushButton:disabled {{
    color: {COLORS['fg_disabled']};
    border-color: {COLORS['border']};
}}
QPushButton[primary="true"] {{
    background-color: {COLORS['accent']};
    color: {COLORS['bg']};
    border: 1px solid {COLORS['accent']};
    font-weight: bold;
}}
QPushButton[primary="true"]:hover {{
    background-color: {COLORS['accent_hover']};
    border-color: {COLORS['accent_hover']};
    color: {COLORS['bg']};
}}
QPushButton[primary="true"]:disabled {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg_disabled']};
    border-color: {COLORS['border']};
}}

QLineEdit, QComboBox, QSpinBox, QKeySequenceEdit, QPlainTextEdit {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border_strong']};
    border-radius: 6px;
    padding: 7px 12px;
    min-height: 18px;
    font-size: 14px;
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['bg']};
}}
QSpinBox {{
    min-width: 96px;
    padding-right: 26px;
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QKeySequenceEdit:focus {{
    border-color: {COLORS['accent']};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QKeySequenceEdit:disabled {{
    color: {COLORS['fg_disabled']};
    border-color: {COLORS['border']};
}}

QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

QComboBox::down-arrow, QSpinBox::down-arrow {{
    image: url("__chevron_down__");
    width: 12px;
    height: 12px;
}}

QSpinBox::up-arrow {{
    image: url("__chevron_up__");
    width: 12px;
    height: 12px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border_strong']};
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['bg']};
    outline: none;
}}

QRadioButton, QCheckBox {{
    color: {COLORS['fg']};
    background: transparent;
    spacing: 6px;
}}
QRadioButton:disabled, QCheckBox:disabled {{
    color: {COLORS['fg_disabled']};
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLORS['border_strong']};
    border-radius: 7px;
    background-color: {COLORS['bg_alt']};
}}
QRadioButton::indicator:hover {{
    border-color: {COLORS['accent']};
}}
QRadioButton::indicator:checked {{
    background-color: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
}}
QRadioButton::indicator:checked:disabled {{
    background-color: {COLORS['fg_disabled']};
    border-color: {COLORS['fg_disabled']};
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLORS['border_strong']};
    background-color: {COLORS['bg_alt']};
}}
QCheckBox::indicator:hover {{
    border-color: {COLORS['accent']};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS['accent']};
    border: 1px solid {COLORS['accent']};
}}

QFormLayout {{
    spacing: 8px;
}}

QMenu {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border_strong']};
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 16px;
}}
QMenu::item:selected {{
    background-color: {COLORS['accent']};
    color: {COLORS['bg']};
}}
QMenu::separator {{
    height: 1px;
    background: {COLORS['border']};
    margin: 4px 8px;
}}

QToolTip {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border_strong']};
    padding: 4px 8px;
    font-family: {FONTS['sans']};
    font-size: 12px;
}}

QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border_strong']};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['fg_disabled']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QSpinBox::up-button, QSpinBox::down-button {{
    width: 20px;
    background-color: {COLORS['bg_hover']};
    border-left: 1px solid {COLORS['border']};
}}
QSpinBox::up-button:hover, QSpinBox::down-button:hover {{
    background-color: {COLORS['border']};
}}
QTableWidget {{
    background-color: {COLORS['bg_alt']};
    alternate-background-color: #191E23;
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    gridline-color: transparent;
    font-family: {FONTS['mono']};
    font-size: 12px;
}}
QTableWidget::item {{
    padding: 6px 10px;
    border-bottom: 1px solid #303840;
}}
QTableWidget::item:selected {{
    background-color: rgba(244, 164, 133, 0.22);
    color: {COLORS['fg']};
}}
QHeaderView::section {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg_muted']};
    border: none;
    border-bottom: 1px solid {COLORS['border_strong']};
    padding: 9px 12px;
    font-family: {FONTS['mono']};
    font-size: 10px;
    font-weight: bold;
}}

/* ===== Navigable settings shell ===== */

QWidget#sideBar {{
    background-color: #171B20;
    border-right: 1px solid {COLORS['border']};
}}
QWidget#sideBar QLabel {{
    background: transparent;
}}

QLabel[role="brandname"] {{
    font-size: 18px;
    font-weight: bold;
    color: {COLORS['fg']};
}}
QLabel[role="brandsub"] {{
    font-size: 11px;
    color: {COLORS['fg_muted']};
}}

QLabel[role="navgroup"] {{
    font-size: 12px;
    font-weight: bold;
    color: {COLORS['fg_muted']};
    padding: 8px 10px 3px 10px;
}}

QPushButton[nav="true"] {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: {COLORS['fg_muted']};
    text-align: left;
    padding: 5px 10px;
    font-size: 13px;
}}
QPushButton[nav="true"]:hover {{
    color: {COLORS['fg']};
    background-color: {COLORS['bg_alt']};
}}
QPushButton[nav="true"]:focus {{
    color: {COLORS['fg']};
    border-color: {COLORS['focus']};
}}
QPushButton[nav="true"][navActive="true"] {{
    color: {COLORS['fg']};
    background-color: rgba(244, 164, 133, 0.10);
    font-weight: bold;
}}

QLabel[role="pagetitle"] {{
    font-size: 31px;
    font-weight: bold;
    color: {COLORS['fg']};
    background: transparent;
}}
QLabel[role="pagedesc"] {{
    color: {COLORS['fg_muted']};
    font-size: 13px;
    background: transparent;
}}
QLabel[role="grouptitle"] {{
    font-size: 16px;
    font-weight: bold;
    color: {COLORS['fg']};
    background: transparent;
    padding: 20px 0px 8px 0px;
}}
QLabel[role="panelheader"] {{
    font-size: 16px;
    font-weight: bold;
    color: {COLORS['fg']};
    background: transparent;
    padding: 0px;
}}
QFrame[role="hairline"] {{
    background-color: {COLORS['border']};
    border: none;
}}

QFrame[role="panel"] {{
    background-color: {COLORS['bg_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}
QFrame[role="panel"] QLabel {{
    background: transparent;
}}

QFrame[role="stattile"] {{
    background-color: {COLORS['bg_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}
QFrame[role="stattile"] QLabel {{
    background: transparent;
}}
QLabel[role="statvalue"] {{
    font-size: 26px;
    font-weight: bold;
    color: {COLORS['fg']};
}}
QLabel[role="statcaption"] {{
    font-size: 12px;
    color: {COLORS['fg_muted']};
}}

QPushButton[seg="true"] {{
    background-color: {COLORS['bg_alt']};
    color: {COLORS['fg_muted']};
    border: 1px solid {COLORS['border_strong']};
    border-left: none;
    border-radius: 0px;
    padding: 8px 16px;
    font-size: 12px;
}}
QPushButton[seg="true"][segfirst="true"] {{
    border-left: 1px solid {COLORS['border_strong']};
    border-top-left-radius: 6px;
    border-bottom-left-radius: 6px;
}}
QPushButton[seg="true"][seglast="true"] {{
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QPushButton[seg="true"]:hover {{
    color: {COLORS['fg']};
    background-color: {COLORS['bg_hover']};
}}
QPushButton[seg="true"]:checked {{
    background-color: {COLORS['accent']};
    color: {COLORS['bg']};
    border-color: {COLORS['accent']};
}}

QPushButton[compact="true"] {{
    padding: 4px 12px;
    font-size: 11px;
    border-radius: 5px;
}}

QPushButton[modelcard="true"] {{
    background-color: {COLORS['bg_alt']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
    padding: 0px;
    text-align: left;
    min-height: 124px;
}}
QPushButton[modelcard="true"]:hover {{
    border-color: {COLORS['border_strong']};
    background-color: {COLORS['bg_hover']};
}}
QPushButton[modelcard="true"]:checked {{
    border: 1px solid {COLORS['accent']};
    background-color: rgba(244, 164, 133, 0.08);
}}
QLabel[role="cardname"] {{
    font-size: 15px;
    font-weight: bold;
    color: {COLORS['fg']};
    background: transparent;
}}
QLabel[role="cardstate"] {{
    font-size: 12px;
    color: {COLORS['fg_muted']};
    background: transparent;
}}
QLabel[role="cardstate"][emph="true"] {{
    color: {COLORS['accent']};
}}

QWidget#statusBar {{
    background-color: #171B20;
    border-top: 1px solid {COLORS['border']};
}}
QWidget#statusBar QLabel {{
    background: transparent;
    font-size: 12px;
    color: {COLORS['fg_muted']};
}}
QLabel[role="statelamp"] {{
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}}
QLabel[role="dirtyhint"] {{
    color: {COLORS['accent']};
}}

QLabel[role="toast"] {{
    background-color: {COLORS['bg_hover']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['accent']};
    padding: 8px 16px;
    font-size: 12px;
}}

QPushButton:focus, QPushButton[primary="true"]:focus,
QPushButton[nav="true"]:focus, QPushButton[seg="true"]:focus,
QPushButton[modelcard="true"]:focus,
QLineEdit:focus, QComboBox:focus, QSpinBox:focus,
QKeySequenceEdit:focus, QPlainTextEdit:focus, QTableWidget:focus {{
    border-color: {COLORS['focus']};
}}

QCheckBox:focus::indicator, QRadioButton:focus::indicator {{
    border-color: {COLORS['focus']};
}}

QPlainTextEdit[role="logbox"] {{
    background-color: #171B20;
    color: {COLORS['fg_muted']};
    border: 1px solid {COLORS['border']};
    font-family: {FONTS['mono']};
    font-size: 11px;
    selection-background-color: {COLORS['accent']};
    selection-color: {COLORS['bg']};
}}
"""


def apply_theme(app: QApplication) -> None:
    """Install the stylesheet and force a dark palette on the QApplication."""
    stylesheet = STYLESHEET
    for direction in ("down", "up"):
        chevron = asset_path(f"chevron-{direction}.svg")
        stylesheet = stylesheet.replace(f"__chevron_{direction}__", chevron.as_posix() if chevron else "")
    app.setStyleSheet(stylesheet)
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(COLORS["bg"]))
    pal.setColor(QPalette.WindowText, QColor(COLORS["fg"]))
    pal.setColor(QPalette.Base, QColor(COLORS["bg_alt"]))
    pal.setColor(QPalette.AlternateBase, QColor(COLORS["bg_hover"]))
    pal.setColor(QPalette.ToolTipBase, QColor(COLORS["bg_alt"]))
    pal.setColor(QPalette.ToolTipText, QColor(COLORS["fg"]))
    pal.setColor(QPalette.Text, QColor(COLORS["fg"]))
    pal.setColor(QPalette.Button, QColor(COLORS["bg_alt"]))
    pal.setColor(QPalette.ButtonText, QColor(COLORS["fg"]))
    pal.setColor(QPalette.BrightText, QColor(COLORS["accent"]))
    pal.setColor(QPalette.Highlight, QColor(COLORS["accent"]))
    pal.setColor(QPalette.HighlightedText, QColor(COLORS["bg"]))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(COLORS["fg_disabled"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(COLORS["fg_disabled"]))
    app.setPalette(pal)
