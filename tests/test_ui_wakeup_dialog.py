"""The WakeUp dialog's own choices: defaults, stepper-wrapping, and the day-rollback logic
for a bedtime that's really the evening before.

What a `Stepper` does is proved once in test_widgets.py; the timezone-localizing behaviour
this dialog shares with Backfill is proved once in test_timezone.py. What's left here is
this dialog's own wiring.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from PySide6.QtCore import QTime

from habito.actions.wakeup import build_wakeup_event
from habito.config.models import TimeConfig
from habito.domain.events import Event, WakeUpLogged
from habito.ui.dialogs.wakeup_dialog import WakeUpDialog
from habito.ui.widgets.controls import Stepper

CEST = timezone(timedelta(hours=2))


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


# --- editing an entry -----------------------------------------------------
# `replacing` only seeds the fields and renames the window; the void that makes it a
# correction is the manager's to add (see EntryManagerDialog), so what this dialog
# *writes* is the same single honest event either way.
def logged_wakeup(wake_hour=7, wake_minute=30, bed_hour=23, bed_minute=15):
    """A wake-up on 2026-08-04 in CEST, as it would come back out of the log."""
    return build_wakeup_event(
        datetime(2026, 8, 4, wake_hour, wake_minute, tzinfo=CEST),
        datetime(2026, 8, 3, bed_hour, bed_minute, tzinfo=CEST),
        habit="sleep",
    )


def editing(qtbot, replacing, captured=None):
    widget = WakeUpDialog(
        on_submit=(captured if captured is not None else []).append,
        default_wake_time=time(7, 0),
        default_bedtime=time(23, 0),
        habit="sleep",
        time_config=TimeConfig(timezone="Europe/Berlin"),
        today=date(2026, 8, 17),
        replacing=replacing,
    )
    qtbot.addWidget(widget)
    return widget


def test_editing_seeds_every_field_from_the_entry(qtbot):
    dialog = editing(qtbot, logged_wakeup())

    assert dialog._picked_date() == date(2026, 8, 4)
    assert (dialog._wake_time.time().hour(), dialog._wake_time.time().minute()) == (7, 30)
    assert (dialog._bedtime.time().hour(), dialog._bedtime.time().minute()) == (23, 15)


def test_editing_reads_the_entrys_own_offset_not_the_machines(qtbot):
    """History keeps the zone it was written in — same rule as everywhere else."""
    tokyo = timezone(timedelta(hours=9))
    dialog = editing(
        qtbot,
        build_wakeup_event(
            datetime(2026, 8, 4, 7, 30, tzinfo=tokyo),
            datetime(2026, 8, 3, 23, 15, tzinfo=tokyo),
            habit="sleep",
        ),
    )

    assert dialog._picked_date() == date(2026, 8, 4)
    assert dialog._wake_time.time().hour() == 7


def test_editing_renames_the_window_and_its_button(qtbot):
    dialog = editing(qtbot, logged_wakeup())

    assert dialog.windowTitle() == "Edit wake-up"
    assert dialog.ok_button.text() == "Save && commit"


def test_logging_afresh_keeps_the_log_wording(qtbot):
    dialog = editing(qtbot, None)

    assert dialog.windowTitle() == "Log wake-up"
    assert dialog.ok_button.text() == "Log && commit"


def test_editing_still_submits_one_plain_wakeup(qtbot):
    """The void is added by whoever asked for the edit; this dialog stays a form that
    produces exactly one honest event."""
    captured: list[list[Event]] = []
    dialog = editing(qtbot, logged_wakeup(), captured=captured)

    dialog._submit()

    (batch,) = captured
    assert [type(e) for e in batch] == [WakeUpLogged]
