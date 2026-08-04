"""The application stylesheet: a light/dark palette plus one parameterised accent colour.

Everything that signals "this is the live app" — the primary button, the progress fill,
the focus ring — draws from one accent. Test mode swaps that accent to red, so a run that
records nothing is unmistakable at a glance rather than something you have to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication

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


def mix(base: str, tint: str, amount: float) -> QColor:
    """Blend ``amount`` of ``tint`` into ``base`` (0.0 → base, 1.0 → tint)."""
    a, b = QColor(base), QColor(tint)
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(a.red() + (b.red() - a.red()) * amount),
        round(a.green() + (b.green() - a.green()) * amount),
        round(a.blue() + (b.blue() - a.blue()) * amount),
    )


# How much of the phase colour bleeds into the background as a session fills it. Enough to
# read as progress across the whole window, not enough to compete with the text on top.
PROGRESS_TINT = 0.16


@dataclass(frozen=True)
class Theme:
    """The resolved look for one run: which accent, which palette."""

    accent: str
    palette: Palette

    @classmethod
    def resolve(cls, ui_theme: str, test_mode: bool) -> Theme:
        return cls(accent=accent_for(test_mode), palette=palette_for(ui_theme))

    def stylesheet(self) -> str:
        return build_stylesheet(self.accent, self.palette)

    def background(self) -> QColor:
        return QColor(self.palette.bg)

    def progress_fill(self, phase_color: str) -> QColor:
        """The background colour for the elapsed portion of the window."""
        return mix(self.palette.bg, phase_color, PROGRESS_TINT)


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

    QSpinBox, QDateEdit, QTimeEdit, QLineEdit {{
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
    /* The focus ring — the whole point of the keyboard work; must be obvious. */
    QPushButton:focus, QSpinBox:focus,
    QDateEdit:focus, QTimeEdit:focus, QLineEdit:focus {{
        border: 2px solid {accent};
    }}

    /* Painted in ProgressBackground.paintEvent — it *is* the progress indicator. */
    QWidget#progressBackground {{ background: transparent; }}

    /* The log is a dense table; it gets a size of its own and room to breathe. */
    QTreeView {{
        background-color: {p.surface};
        alternate-background-color: {p.bg};  /* a faint stripe helps a dense table scan */
        border: 1px solid {p.border};
        border-radius: 6px;
        font-size: 14px;
    }}
    QTreeView::item {{ padding: 5px 4px; border: none; }}
    QTreeView::item:selected {{ background-color: {accent}; color: #ffffff; }}
    QTreeView::branch {{ background: transparent; }}
    QHeaderView::section {{
        background-color: {p.surface_hi};
        color: {p.text};
        border: none;
        border-bottom: 1px solid {p.border};
        padding: 6px 6px;
        font-size: 13px;
        font-weight: bold;
    }}
    """
