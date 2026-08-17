"""The WakeUp dialog's own choices: defaults, stepper-wrapping, and the day-rollback logic
for a bedtime that's really the evening before.

What a `Stepper` does is proved once in test_widgets.py; the timezone-localizing behaviour
this dialog shares with Backfill is proved once in test_timezone.py. What's left here is
this dialog's own wiring.
"""

from __future__ import annotations

from datetime import date, time

import pytest
from PySide6.QtCore import QTime

from habito.domain.events import Event, WakeUpLogged
from habito.ui.dialogs.wakeup_dialog import WakeUpDialog
from habito.ui.widgets.controls import Stepper


@pytest.fixture
def dialog(qtbot):
    widget = WakeUpDialog(
        on_submit=lambda events: None,
        default_wake_time=time(7, 0),
        default_bedtime=time(23, 0),
        habit="sleep",
        today=date(2026, 8, 17),
    )
    qtbot.addWidget(widget)
    return widget


def test_the_time_fields_default_from_config(dialog):
    assert (dialog._wake_time.time().hour(), dialog._wake_time.time().minute()) == (7, 0)
    assert (dialog._bedtime.time().hour(), dialog._bedtime.time().minute()) == (23, 0)


def test_the_clock_fields_are_wrapped(dialog):
    assert isinstance(dialog._wake_time.parent(), Stepper)
    assert isinstance(dialog._bedtime.parent(), Stepper)


def test_a_bedtime_before_midnight_rolls_back_to_the_evening_before(dialog):
    """The normal case: woke at 07:00, bedtime picked as 23:00 — that's last night, not a
    bedtime an hour from now."""
    dialog._wake_time.setTime(QTime(7, 0))
    dialog._bedtime.setTime(QTime(23, 0))

    bed = dialog._bed()

    assert bed.date() == date(2026, 8, 16)
    assert (bed.hour, bed.minute) == (23, 0)


def test_a_bedtime_after_midnight_stays_on_the_wake_date(dialog):
    """Asleep at 01:00, woke at 08:00 the same calendar day — no rollback needed."""
    dialog._wake_time.setTime(QTime(8, 0))
    dialog._bedtime.setTime(QTime(1, 0))

    bed = dialog._bed()

    assert bed.date() == date(2026, 8, 17)
    assert (bed.hour, bed.minute) == (1, 0)


def test_submitting_builds_a_wakeup_event(dialog):
    captured: list[list[Event]] = []
    dialog._on_submit = captured.append
    dialog._wake_time.setTime(QTime(6, 30))
    dialog._bedtime.setTime(QTime(22, 45))

    dialog._submit()

    logged = captured[0][0]
    assert isinstance(logged, WakeUpLogged)
    # The event's own `.timestamp` is UTC — check the local wall-clock time that went in,
    # same as `test_ui_backfill_dialog.py` does for `_start()`.
    assert (dialog._wake().hour, dialog._wake().minute) == (6, 30)
