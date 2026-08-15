"""The Backfill dialog's own choices about its fields.

What a `Stepper` does is proved once in test_widgets.py; what is left here is that this
dialog wrapped every steppable field — the clock included — chose step sizes that match
how each value is picked, and still builds the same events from them.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import QTime

from habito.domain.events import Event, SessionStarted
from habito.ui.dialogs.backfill_dialog import BackfillDialog
from habito.ui.widgets import Stepper


@pytest.fixture
def dialog(qtbot):
    widget = BackfillDialog(
        on_submit=lambda events: None,
        default_work=25,
        default_break=5,
        default_rounds=4,
        habit="study",
        today=date(2026, 8, 5),
    )
    qtbot.addWidget(widget)
    return widget


def test_every_stepped_field_is_wrapped_including_the_clock(dialog):
    """The cramped arrows come from `QAbstractSpinBox`, so a `QTimeEdit` has exactly the
    same pair as a spin box counting minutes and needs the same wrapping. The date field
    is exempt: `setCalendarPopup` already replaces its arrows with one dropdown button.
    """
    fields = (dialog._time, dialog._work, dialog._break, dialog._rounds)
    assert all(isinstance(field.parent(), Stepper) for field in fields)


def test_the_step_size_follows_how_the_value_is_used(dialog):
    """A round length is remembered in fives — 25, 50 — where a break and a round count are
    picked exactly. Same rule as Settings."""
    assert dialog._work.singleStep() == 5
    assert dialog._break.singleStep() == 1
    assert dialog._rounds.singleStep() == 1


def test_the_fields_still_reach_the_events(dialog):
    """Wrapping a field must not change what the dialog builds from it."""
    captured: list[list[Event]] = []
    dialog._on_submit = captured.append
    dialog._time.setTime(QTime(9, 30))
    dialog._work.setValue(50)
    dialog._break.setValue(10)
    dialog._rounds.setValue(2)

    dialog._submit()

    started = captured[0][0]
    assert isinstance(started, SessionStarted)
    assert (started.work_minutes, started.break_minutes, started.planned_rounds) == (50, 10, 2)
    assert (dialog._start().hour, dialog._start().minute) == (9, 30)
