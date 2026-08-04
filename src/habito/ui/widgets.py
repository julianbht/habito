"""Small presentation helpers and shared widgets."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QValidator
from PySide6.QtWidgets import QLabel, QPushButton, QSpinBox, QWidget

_MINUTES_RE = re.compile(r"\d{0,3}(:\d{0,2})?")


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


def parse_minutes(text: str) -> int | None:
    """Parse ``"30"`` or ``"30:00"`` / ``"29:40"`` into whole minutes (rounded)."""
    text = text.strip()
    if not text:
        return None
    try:
        if ":" in text:
            mm, _, ss = text.partition(":")
            total = int(mm) * 60 + (int(ss) if ss else 0)
            return round(total / 60)
        return round(float(text))
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


class MinutesSpinBox(QSpinBox):
    """Minute input that reads back as ``MM:SS`` but accepts ``30`` or ``30:00``.

    ``QSpinBox`` already supplies the up/down arrows, keyboard stepping (Up/Down,
    PageUp/PageDown) and range clamping; we only teach it the ``MM:SS`` presentation.

    Keyboard tracking is off so typing ``3`` on the way to ``30`` doesn't emit an
    intermediate ``valueChanged`` — the value commits on Enter or focus-out.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        minimum: int = 1,
        maximum: int = 600,
        object_name: str = "",
    ) -> None:
        super().__init__(parent)
        self.setObjectName(object_name)
        self.setRange(minimum, maximum)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setKeyboardTracking(False)
        self.setAccelerated(True)

    def textFromValue(self, value: int) -> str:  # noqa: N802 (Qt override)
        return f"{value:02d}:00"

    def valueFromText(self, text: str) -> int:  # noqa: N802 (Qt override)
        minutes = parse_minutes(text)
        return self.minimum() if minutes is None else minutes

    def validate(self, text: str, pos: int):
        """Let partial input stand while typing; only reject impossible text outright."""
        stripped = text.strip()
        if not stripped:
            return (QValidator.State.Intermediate, text, pos)
        if not _MINUTES_RE.fullmatch(stripped):
            return (QValidator.State.Invalid, text, pos)
        minutes = parse_minutes(stripped)
        if minutes is None or not (self.minimum() <= minutes <= self.maximum()):
            return (QValidator.State.Intermediate, text, pos)
        return (QValidator.State.Acceptable, text, pos)
