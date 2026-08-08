"""The Backfill dialog's number and time fields.

Every field that can be stepped is wrapped in a :class:`~habito.ui.widgets.Stepper`, for
the same reason the Settings dialog is: Qt's native arrows are two 14x13px targets stacked
in one corner, so the pointer that just pressed one is resting inside it and a nudge toward
the other lands on the first again.
"""

from __future__ import annotations

from datetime import date

import pytest
from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import QAbstractSpinBox

from habito.ui.backfill_view import BackfillDialog
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
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def _stepper(field) -> Stepper:
    """The :class:`Stepper` wrapping a field — its parent, by construction."""
    parent = field.parent()
    assert isinstance(parent, Stepper)
    return parent


def test_every_stepped_field_carries_its_own_buttons(dialog):
    """Including the clock: the cramped arrows come from ``QAbstractSpinBox``, so a
    ``QTimeEdit`` has exactly the same pair as a spin box counting minutes."""
    for field in (dialog._time, dialog._work, dialog._break, dialog._rounds):
        assert field.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
        assert _stepper(field)


def test_the_step_buttons_are_worth_aiming_at_and_side_by_side(dialog):
    stepper = _stepper(dialog._work)

    assert stepper._up.width() >= 24 and stepper._up.height() >= 24
    assert stepper._up.x() >= stepper._down.x() + stepper._down.width()
    assert stepper._up.y() == stepper._down.y()


def test_up_still_works_after_down(dialog, qtbot):
    stepper = _stepper(dialog._work)
    dialog._work.setValue(30)

    qtbot.mouseClick(stepper._down, Qt.MouseButton.LeftButton)
    assert dialog._work.value() == 25
    qtbot.mouseClick(stepper._up, Qt.MouseButton.LeftButton)
    assert dialog._work.value() == 30


def test_the_work_length_steps_by_five_and_snaps_onto_the_grid(dialog, qtbot):
    """A round length is remembered in fives; 47 + 5 would strand it off the grid."""
    dialog._work.setValue(47)

    qtbot.mouseClick(_stepper(dialog._work)._up, Qt.MouseButton.LeftButton)

    assert dialog._work.value() == 50


def test_the_break_and_rounds_step_by_one(dialog, qtbot):
    for field in (dialog._break, dialog._rounds):
        before = field.value()
        qtbot.mouseClick(_stepper(field)._up, Qt.MouseButton.LeftButton)
        assert field.value() == before + 1


def test_the_clock_steps_the_hour(dialog, qtbot):
    dialog._time.setTime(QTime(6, 0))

    qtbot.mouseClick(_stepper(dialog._time)._up, Qt.MouseButton.LeftButton)

    assert dialog._time.time() == QTime(7, 0)


def test_a_direction_greys_out_at_its_limit(dialog):
    rounds = _stepper(dialog._rounds)

    dialog._rounds.setValue(1)  # the minimum
    assert not rounds._down.isEnabled()
    assert rounds._up.isEnabled()

    dialog._rounds.setValue(24)  # the maximum
    assert rounds._down.isEnabled()
    assert not rounds._up.isEnabled()


def test_the_clock_greys_out_at_midnight(dialog):
    """``stepEnabled`` answers for a time edit too — 00:00 is the bottom of its range."""
    stepper = _stepper(dialog._time)

    dialog._time.setTime(QTime(0, 0))
    assert not stepper._down.isEnabled()
    assert stepper._up.isEnabled()

    dialog._time.setTime(QTime(12, 0))
    assert stepper._down.isEnabled()


def test_the_step_buttons_stay_out_of_the_tab_order(dialog):
    stepper = _stepper(dialog._work)

    assert stepper._up.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert stepper._down.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_the_fields_still_reach_the_events(dialog, qtbot):
    """Wrapping a field must not change what the dialog builds from it."""
    captured: list[list[object]] = []
    dialog._on_submit = captured.append
    dialog._time.setTime(QTime(9, 30))
    dialog._work.setValue(50)
    dialog._break.setValue(10)
    dialog._rounds.setValue(2)

    dialog._submit()

    started = captured[0][0]
    assert (started.work_minutes, started.break_minutes, started.planned_rounds) == (50, 10, 2)
    assert dialog._start().hour == 9 and dialog._start().minute == 30
