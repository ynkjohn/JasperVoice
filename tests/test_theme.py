"""Tests for the dark theme module."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from jaspervoice import theme


def test_required_palette_keys_present():
    for key in ("bg", "bg_alt", "border", "fg", "fg_muted", "accent"):
        assert key in theme.COLORS
        assert theme.COLORS[key].startswith("#")
        assert len(theme.COLORS[key]) == 7


def test_state_colors_have_all_states():
    for state in ("idle", "recording", "processing", "error"):
        assert state in theme.STATE_COLORS
        assert "border" in theme.STATE_COLORS[state]
        assert "fill" in theme.STATE_COLORS[state]


def test_fonts_have_mono_and_sans():
    assert "mono" in theme.FONTS
    assert "sans" in theme.FONTS


def test_stylesheet_is_nonempty_and_contains_key_selectors():
    css = theme.STYLESHEET
    assert len(css) > 100
    for selector in (
        "QMainWindow",
        "QPushButton",
        "QPushButton[primary",
        "QLineEdit",
        "QComboBox",
        "QSpinBox",
        "QKeySequenceEdit",
        "QRadioButton::indicator:checked",
        "QCheckBox::indicator:checked",
        "QLabel[role=\"section\"]",
    ):
        assert selector in css, f"missing selector: {selector}"


def test_apply_theme_sets_stylesheet_and_dark_palette(qapp):
    theme.apply_theme(qapp)
    assert "background-color" in qapp.styleSheet()
    pal = qapp.palette()
    from PySide6.QtGui import QPalette
    # Qt normalizes hex to lowercase; compare case-insensitively.
    assert pal.color(QPalette.Window).name().lower() == theme.COLORS["bg"].lower()
    assert pal.color(QPalette.Highlight).name().lower() == theme.COLORS["accent"].lower()
