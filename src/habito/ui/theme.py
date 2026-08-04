"""The application stylesheet: a light/dark palette plus one parameterised accent colour.

Everything that signals "this is the live app" — the primary button, the progress bar, the
focus ring — draws from one accent. Test mode swaps that accent to red, so a run that
records nothing is unmistakable at a glance rather than something you have to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication

ACCENT_LIVE = "#3b8ed0"
ACCENT_TEST = "#d9534f"

# Semantic colours that don't vary with the accent or the palette.
OK = "#2fa572"
WARN = "#d9863b"
ERROR = "#d9534f"
BREAK = "#3b8ed0"
MUTED = "#9aa0a6"


@dataclass(frozen=True)
class Palette:
    bg: str
    surface: str
    surface_hi: str
    border: str
    text: str
    text_disabled: str


DARK = Palette(
    bg="#1e1f22",
    surface="#2b2d31",
    surface_hi="#3a3d42",
    border="#43464d",
    text="#e6e6e6",
    text_disabled="#6b6f76",
)
LIGHT = Palette(
    bg="#f4f5f7",
    surface="#ffffff",
    surface_hi="#e6e8eb",
    border="#c8ccd2",
    text="#1c1e21",
    text_disabled="#a0a4ab",
)


def accent_for(test_mode: bool) -> str:
    return ACCENT_TEST if test_mode else ACCENT_LIVE


def palette_for(theme: str) -> Palette:
    """Resolve the configured ``dark`` / ``light`` / ``system`` setting to a palette."""
    if theme == "light":
        return LIGHT
    if theme == "dark":
        return DARK
    hints = QGuiApplication.styleHints()  # "system": ask the OS, defaulting to dark
    if hints is not None and hints.colorScheme() == Qt.ColorScheme.Light:
        return LIGHT
    return DARK


def build_stylesheet(accent: str, palette: Palette = DARK) -> str:
    """Qt stylesheet for the whole app, themed around ``accent`` and ``palette``."""
    p = palette
    return f"""
    QWidget {{
        background-color: {p.bg};
        color: {p.text};
        font-size: 13px;
    }}
    QDialog {{ background-color: {p.bg}; }}

    QLabel {{ background: transparent; }}
    QLabel#muted {{ color: {MUTED}; font-size: 11px; }}
    QLabel#round {{ font-size: 14px; }}
    QLabel#state {{ font-size: 15px; font-weight: bold; }}
    QLabel#time {{ font-size: 52px; font-weight: bold; }}
    QLabel#today {{ font-size: 13px; }}
    QLabel#heading {{ font-size: 15px; font-weight: bold; }}
    QLabel#banner {{
        background-color: {ACCENT_TEST};
        color: #ffffff;
        font-weight: bold;
        padding: 5px;
    }}

    QPushButton {{
        background-color: {p.surface_hi};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 7px 14px;
    }}
    QPushButton:hover {{ background-color: {p.border}; }}
    QPushButton:pressed {{ background-color: {p.surface}; }}
    QPushButton:disabled {{ color: {p.text_disabled}; background-color: {p.surface}; }}
    QPushButton#primary {{
        background-color: {accent};
        border-color: {accent};
        color: #ffffff;
        font-size: 19px;
    }}
    QPushButton#primary:hover {{ background-color: {accent}; border-color: {p.text}; }}
    QPushButton#transport {{ font-size: 19px; }}
    QPushButton#nudge {{ padding: 0px; font-size: 13px; border-radius: 5px; }}
    QPushButton#gear {{ font-size: 15px; padding: 2px 7px; }}

    QSpinBox, QDateEdit, QTimeEdit, QLineEdit, QComboBox {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 3px 6px;
        selection-background-color: {accent};
    }}
    QSpinBox#time {{
        font-size: 52px;
        font-weight: bold;
        border-width: 2px;
        padding: 2px 4px;
    }}
    QComboBox::drop-down {{ border: none; width: 16px; }}
    QComboBox QAbstractItemView {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        selection-background-color: {accent};
    }}

    /* The focus ring — the whole point of the keyboard work; must be obvious. */
    QPushButton:focus, QSpinBox:focus, QComboBox:focus,
    QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus {{
        border: 2px solid {accent};
    }}

    QProgressBar {{
        background-color: {p.surface};
        border: none;
        border-radius: 4px;
        height: 8px;
        text-align: center;
    }}
    QProgressBar::chunk {{ background-color: {accent}; border-radius: 4px; }}
    """
