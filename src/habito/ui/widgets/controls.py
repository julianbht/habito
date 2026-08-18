"""Small presentation helpers and shared widgets."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QValidator, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDateTimeEdit,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QSpinBox,
    QWidget,
)

_DURATION_RE = re.compile(r"\d{0,3}(:\d{0,2})?")

# The app's three standard sizes, so a dialog (or page — HabitoApp's own _PAGE_SIZES reuses
# LARGE_DIALOG_WIDTH/_HEIGHT for the calendar and log) picks whichever shape matches its job
# rather than choosing its own numbers:
# - COMPACT: a single ask or a short form — PhaseDialog, SessionCompleteDialog (collapsed),
#   CatalogEditDialog, BackfillDialog, WakeUpDialog, ResumePromptDialog, RetractConfirmDialog.
#   Width only; height follows content. A list here scrolls rather than growing the dialog
#   to fit it — that's what a scrollbar is for — so a size tier is about a dialog's *job*,
#   not how much content it could hold.
# - BROWSE: pick one thing from a list, or manage a small growing one — ManageSessionsDialog,
#   ShortcutsDialog, CatalogManagerDialog, SessionTagDialog, WorkoutLogDialog,
#   SessionCompleteDialog once its tag picker is showing.
# - LARGE: everything at once — currently only SettingsDialog, scrolled internally rather
#   than left to grow taller than the window that opened it.
COMPACT_DIALOG_WIDTH = 320
BROWSE_DIALOG_WIDTH = 440
BROWSE_DIALOG_HEIGHT = 360
LARGE_DIALOG_WIDTH = 460
LARGE_DIALOG_HEIGHT = 580


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


def prompt_new_tag(parent: QWidget) -> str | None:
    """The one-line "New tag" prompt — shared by the session-end picker and the tag
    manager's "+ New tag", so it's the same window rather than two that merely match."""
    text, ok = QInputDialog.getText(parent, "New tag", "Tag:")
    text = text.strip()
    return text if ok and text else None


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


def primary_button(text: str) -> Button:
    """The dialog's one affirmative action: accent-coloured, and the button Enter
    activates. Same size as every other button — see CLAUDE.md § Controls."""
    widget = button(text, "primary")
    widget.setDefault(True)
    return widget


class _NoWheelMixin:
    """Mouse wheel never changes the value.

    A field like this always sits next to a :class:`Stepper` (or, for a combo box, is
    reachable by click), so wheel-scroll was never the only way to change it — but it *is*
    the only widget in a scrollable form that steals a scroll gesture passing over it
    instead of letting the page scroll. Ignoring the event here (rather than overriding it
    with a no-op) is what lets Qt's normal propagation hand it up to the parent — the
    ``QScrollArea`` it's sitting in, most of the time.
    """

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802 (Qt override)
        event.ignore()


class StepSpinBox(_NoWheelMixin, QSpinBox):
    """A spin box whose stepping snaps onto multiples of the step size.

    ``QSpinBox`` adds the step to whatever is already there, so a value that is off the
    grid stays off it forever — 47 minutes with a 5-minute step goes 47, 52, 57, and you
    can never reach a round number by pressing a button. Snapping spends the first press
    rounding onto the grid, in the direction you were already heading so a press never
    moves the value backwards, and every press after that lands on a number you'd have
    picked deliberately.
    """

    def stepBy(self, steps: int) -> None:  # noqa: N802 (Qt override)
        step = self.singleStep()
        remainder = self.value() % step
        if steps and step > 1 and remainder:
            self.setValue(self.value() + (step - remainder if steps > 0 else -remainder))
            steps -= 1 if steps > 0 else -1
        if steps:
            super().stepBy(steps)


# Big enough to hit without aiming. Qt's own spin arrows are 14x13px each; these are ~4x
# the area, and side by side rather than stacked.
STEP_BUTTON_SIZE = (30, 28)


class Stepper(QWidget):
    """Any spin box with press-and-hold ``−`` / ``+`` buttons at its right-hand end.

    Qt stacks its two spin arrows in one corner, touching, at 14x13px each. The pointer
    that just pressed one is therefore sitting *inside* it, and a small nudge toward the
    other still lands on the first — so the control reads as "the up button stopped
    working" when it is only being missed. These sit side by side instead: the pointer
    travels along the axis they're separated on, across targets twice as wide as they are
    tall, so overshooting one lands on nothing rather than silently repeating it.

    They stay grouped at the right, where the native arrows were, rather than flanking the
    field — one cluster to look at per row instead of two.

    The buttons take no focus, so the spin box stays the single tab stop and Up/Down keep
    working from the keyboard — this wraps a control without becoming one.

    It wraps ``QAbstractSpinBox`` rather than ``QSpinBox`` because the cramped arrows are
    drawn by the base class: a ``QTimeEdit`` has exactly the same pair in the same corner,
    and there is no reason for the fix to stop at the spin boxes that count minutes.
    """

    def __init__(self, spin: QAbstractSpinBox, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.spin = spin
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)

        self._down = self._arrow("−", -1, "Less")
        self._up = self._arrow("+", 1, "More")

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(spin, 1)
        row.addWidget(self._down)
        row.addWidget(self._up)

        self._watch(spin)
        self._sync()

    def _watch(self, spin: QAbstractSpinBox) -> None:
        """Re-sync however the value moved — typed, keyed, or stepped.

        ``QAbstractSpinBox`` declares no value-changed signal of its own; each concrete
        spin box names its own, so the kinds this app wraps are wired by hand.
        """
        if isinstance(spin, QSpinBox):
            spin.valueChanged.connect(self._sync)
        elif isinstance(spin, QDateTimeEdit):
            spin.dateTimeChanged.connect(self._sync)

    def _arrow(self, text: str, direction: int, tip: str) -> Button:
        btn = button(text, "stepper")
        btn.setFixedSize(*STEP_BUTTON_SIZE)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setAutoRepeat(True)  # holding runs the value up rather than needing N clicks
        btn.setAutoRepeatDelay(400)
        btn.setAutoRepeatInterval(70)
        btn.setToolTip(tip)
        btn.clicked.connect(lambda: self.spin.stepBy(direction))
        return btn

    def _sync(self) -> None:
        """Grey out a direction at its limit — silence would read as the earlier bug.

        ``stepEnabled`` is the spin box's own answer to "can I still move that way", so a
        minute count at its minimum and a clock at midnight are settled by the same line.
        """
        step = QAbstractSpinBox.StepEnabledFlag
        enabled = self.spin.stepEnabled()
        self._down.setEnabled(bool(enabled & step.StepDownEnabled))
        self._up.setEnabled(bool(enabled & step.StepUpEnabled))


class DurationSpinBox(_NoWheelMixin, QSpinBox):
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
        minimum: int = 1,
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


class NoWheelComboBox(_NoWheelMixin, QComboBox):
    """A combo box that only changes on a deliberate click — see :class:`_NoWheelMixin`.
    Worse than a spin box left un-wrapped: scrolling past it can silently swap your
    timezone or notification sound rather than just nudge a number."""
