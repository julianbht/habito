"""Small presentation helpers and shared widgets."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QValidator
from PySide6.QtWidgets import QLabel, QPushButton, QSpinBox, QWidget

_DURATION_RE = re.compile(r"\d{0,3}(:\d{0,2})?")


def format_timer(seconds: int) -> str:
    """``MM:SS`` (or ``H:MM:SS`` past an hour) for the big countdown."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration(seconds: int) -> str:
    """Human total like ``1h 23m`` / ``45m`` / ``0m`` for the daily readout."""
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes = rem // 60
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m"


def parse_seconds(text: str) -> int | None:
    """Parse a typed duration into seconds.

    A bare number is minutes — ``30`` is half an hour, which is what you mean when you
    type it into a Pomodoro timer. Anything with a colon is read literally, so ``0:10``
    is ten seconds and ``1:30`` is ninety.
    """
    text = text.strip()
    if not text:
        return None
    try:
        if ":" in text:
            mm, _, ss = text.partition(":")
            return int(mm or 0) * 60 + int(ss or 0)
        return round(float(text) * 60)
    except ValueError:
        return None


def label(text: str = "", object_name: str = "") -> QLabel:
    """A ``QLabel`` tagged for the stylesheet.

    Qt accepts ``objectName`` as a constructor keyword at runtime, but its type stubs
    don't model that — so set it explicitly and keep the call sites type-clean.
    """
    widget = QLabel(text)
    widget.setObjectName(object_name)
    return widget


class Button(QPushButton):
    """A push button that Enter activates, not just Space.

    Qt reserves Return/Enter for a *dialog's* default button, so in a plain window a
    focused button ignores it — which is surprising once you've tabbed onto it and are
    expecting the same key that works everywhere else to press it.
    """

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        enter = (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if event.key() in enter and not event.isAutoRepeat() and self.isEnabled():
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


def button(text: str = "", object_name: str = "") -> Button:
    """A :class:`Button` tagged for the stylesheet. See :func:`label`."""
    widget = Button(text)
    widget.setObjectName(object_name)
    return widget


class DurationSpinBox(QSpinBox):
    """Duration input measured in **seconds**, displayed as ``MM:SS``.

    Counting seconds rather than minutes is what lets you type ``0:10`` — handy for
    trying a notification without waiting out a real round, and for anyone who wants a
    ninety-second round. A bare ``30`` still means thirty minutes; see
    :func:`parse_seconds`.

    ``QSpinBox`` already supplies keyboard stepping (Up/Down, PageUp/PageDown) and range
    clamping; we only teach it the ``MM:SS`` presentation.

    Keyboard tracking is off so typing ``3`` on the way to ``30`` doesn't emit an
    intermediate ``valueChanged`` — the value commits on Enter or focus-out.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        minimum: int = 5,
        maximum: int = 180 * 60,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setRange(minimum, maximum)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setKeyboardTracking(False)
        self.setAccelerated(True)

    def textFromValue(self, value: int) -> str:  # noqa: N802 (Qt override)
        return format_timer(value)

    def valueFromText(self, text: str) -> int:  # noqa: N802 (Qt override)
        seconds = parse_seconds(text)
        return self.minimum() if seconds is None else seconds

    def validate(self, text: str, pos: int):
        """Let partial input stand while typing; only reject impossible text outright."""
        stripped = text.strip()
        if not stripped:
            return (QValidator.State.Intermediate, text, pos)
        if not _DURATION_RE.fullmatch(stripped):
            return (QValidator.State.Invalid, text, pos)
        seconds = parse_seconds(stripped)
        if seconds is None or not (self.minimum() <= seconds <= self.maximum()):
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Acceptable, text, pos)
