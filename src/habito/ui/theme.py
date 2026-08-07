"""The application stylesheet: a light/dark palette plus one parameterised accent colour.

Everything that signals "this is the live app" — the primary button, the progress fill,
the focus ring — draws from one accent. Test mode swaps that accent to red, so a run that
records nothing is unmistakable at a glance rather than something you have to remember.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication
from PySide6.QtWidgets import QApplication

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
    # The stretch-goal star, drawn on top of the green "met" fill. Per-palette because one
    # amber can't carry both: the light fill is bright enough that a mid amber nearly
    # matches its luminance, so light gets a deeper one. Still a single colour per theme
    # rather than a gradient — a two-ended ramp would need this tuning three times over,
    # and shape survives colour blindness in a way hue doesn't.
    star: str


DARK = Palette(
    bg="#1e1f22",
    surface="#2b2d31",
    surface_hi="#3a3d42",
    border="#43464d",
    text="#e6e6e6",
    text_disabled="#6b6f76",
    star="#e0a53f",
)
LIGHT = Palette(
    bg="#f4f5f7",
    surface="#ffffff",
    surface_hi="#e6e8eb",
    border="#c8ccd2",
    text="#1c1e21",
    text_disabled="#a0a4ab",
    star="#9c6407",
)


# The application-wide base size, in points rather than stylesheet pixels — see the note
# on the QWidget rule in build_stylesheet.
BASE_POINT_SIZE = 10


def apply(app: QApplication, active: Theme) -> None:
    """Put a theme onto the application: base font first, then the stylesheet."""
    font = app.font()
    font.setPointSize(BASE_POINT_SIZE)
    app.setFont(font)
    app.setStyleSheet(active.stylesheet())


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
    /* No font-size here on purpose. A stylesheet size is in pixels, which leaves
       QFont::pointSize() at -1 — and Qt internals (QComboBox's, for one) read that and
       feed it straight back to setPointSize(), warning on every run. The base size is set
       as a real point size in apply() instead; rules below still override per widget. */
    QWidget {{
        background-color: {p.bg};
        color: {p.text};
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
    /* Widgets.Stepper's −/+. The size is fixed in code (it's a hit target, not a look);
       here it only loses the text padding that would squeeze the glyph off-centre. */
    QPushButton#stepper {{ padding: 0px; font-size: 17px; font-weight: bold; }}

    /* The QWidget rule above matches QMenu too, which puts it on the stylesheet paint
       path — so the highlight, border and separator the native style would have drawn
       have to be restated here or they aren't drawn at all. */
    QMenu {{
        background-color: {p.surface};
        border: 1px solid {p.border};
        border-radius: 6px;
        padding: 4px;
    }}
    QMenu::item {{
        background: transparent;
        padding: 7px 24px 7px 12px;
        border-radius: 4px;
    }}
    QMenu::item:selected {{ background-color: {accent}; color: #ffffff; }}
    QMenu::item:disabled {{ color: {p.text_disabled}; }}
    /* The page actions are an exclusive checkable group, so "checked" is the page you're
       on. Restated for :selected, where accent-on-accent would vanish. */
    QMenu::item:checked {{ font-weight: bold; color: {accent}; }}
    QMenu::item:checked:selected {{ color: #ffffff; }}
    QMenu::separator {{
        height: 1px;
        background-color: {p.border};
        margin: 5px 8px;
    }}

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

    /* The calendar. Qt's own navigation bar, themed to match. */
    QCalendarWidget QAbstractItemView {{
        background-color: {p.bg};
        outline: none;
        selection-background-color: transparent;
        selection-color: {p.text};
    }}
    QCalendarWidget QWidget#qt_calendar_navigationbar {{
        background-color: {p.surface};
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
    }}
    /* Colour only — deliberately no padding/border here. Styling QToolButton broadly is
       what stops Qt drawing the prev/next arrows, which are arrow-type tool buttons. */
    QCalendarWidget QToolButton {{
        background-color: transparent;
        color: {p.text};
        font-size: 14px;
        font-weight: bold;
    }}
    QCalendarWidget QToolButton:hover {{ background-color: {p.surface_hi}; }}
    QCalendarWidget QToolButton:pressed {{ background-color: {p.border}; }}
    /* Room to breathe, applied only to the two text buttons. */
    QCalendarWidget QToolButton#qt_calendar_monthbutton,
    QCalendarWidget QToolButton#qt_calendar_yearbutton {{
        padding: 4px 14px;
        margin: 4px 2px;
        border-radius: 5px;
    }}
    /* Qt crams this arrow into the month button's bottom-right corner, hard against the
       text. The button still opens its menu on click, so hiding it loses nothing. */
    QCalendarWidget QToolButton#qt_calendar_monthbutton::menu-indicator {{
        image: none;
        width: 0px;
    }}
    QCalendarWidget QSpinBox {{
        font-size: 14px;
        margin: 3px 2px;
    }}

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
