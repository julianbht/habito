"""The shared widgets in :mod:`habito.ui.widgets.controls`, tested once and only here.

Everything a `Stepper` or a `StepSpinBox` does is a property of the widget, not of the
dialog that happens to hold one — so it is proved here against a bare instance. A dialog's
own tests assert only that it wrapped its fields and picked sensible step sizes; see the
testing section of CLAUDE.md.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt, QTime
from PySide6.QtWidgets import QAbstractSpinBox, QTimeEdit

from habito.ui.widgets.controls import Stepper, StepSpinBox


@pytest.fixture
def stepped(qtbot):
    """A 5-stepping spin box in its stepper, shown so geometry is real."""
    spin = StepSpinBox()
    spin.setRange(0, 100)
    spin.setSingleStep(5)
    spin.setValue(50)
    stepper = Stepper(spin)
    qtbot.addWidget(stepper)
    stepper.show()
    qtbot.waitExposed(stepper)
    return stepper


@pytest.fixture
def clock(qtbot):
    """A time edit in its stepper — the same widget over a `QDateTimeEdit`."""
    edit = QTimeEdit(QTime(6, 0))
    edit.setDisplayFormat("HH:mm")
    stepper = Stepper(edit)
    qtbot.addWidget(stepper)
    stepper.show()
    qtbot.waitExposed(stepper)
    return stepper


# --- the stepper ----------------------------------------------------------
def test_the_native_arrows_are_replaced_not_supplemented(stepped, clock):
    for stepper in (stepped, clock):
        assert stepper.spin.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons


def test_the_buttons_are_worth_aiming_at_and_side_by_side(stepped):
    """The original bug: Qt's two 14x13px arrows are stacked and touching, so a miss on one
    lands on the other and looks like a dead button. Side by side, the pointer travels along
    the axis they're separated on, and they don't overlap on it at all.
    """
    assert stepped._up.width() >= 24 and stepped._up.height() >= 24
    assert stepped._up.x() >= stepped._down.x() + stepped._down.width()
    assert stepped._up.y() == stepped._down.y()


def test_up_still_works_after_down(stepped, qtbot):
    qtbot.mouseClick(stepped._down, Qt.MouseButton.LeftButton)
    assert stepped.spin.value() == 45
    qtbot.mouseClick(stepped._up, Qt.MouseButton.LeftButton)
    assert stepped.spin.value() == 50


def test_a_direction_greys_out_at_its_limit(stepped):
    stepped.spin.setValue(0)
    assert not stepped._down.isEnabled()
    assert stepped._up.isEnabled()

    stepped.spin.setValue(100)
    assert stepped._down.isEnabled()
    assert not stepped._up.isEnabled()


def test_the_buttons_stay_out_of_the_tab_order(stepped):
    """Tab still walks field to field; the buttons are for the mouse."""
    assert stepped._up.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert stepped._down.focusPolicy() == Qt.FocusPolicy.NoFocus


# --- the stepper over a clock ---------------------------------------------
def test_a_time_edit_steps_and_greys_out_like_any_other_spin(clock, qtbot):
    """`Stepper` wraps `QAbstractSpinBox`, so a `QTimeEdit` — which draws the identical
    cramped arrows — gets the identical treatment. Midnight is the bottom of its range,
    which `stepEnabled` reports just as a spin box reports its minimum.
    """
    qtbot.mouseClick(clock._up, Qt.MouseButton.LeftButton)
    assert clock.spin.time() == QTime(7, 0)

    clock.spin.setTime(QTime(0, 0))
    assert not clock._down.isEnabled()
    assert clock._up.isEnabled()


# --- snapping -------------------------------------------------------------
def test_stepping_snaps_an_off_grid_value_onto_the_grid(stepped, qtbot):
    """47 + 5 would be 52, and nothing you press afterwards ever reaches a round number."""
    stepped.spin.setValue(47)
    qtbot.mouseClick(stepped._up, Qt.MouseButton.LeftButton)
    assert stepped.spin.value() == 50

    stepped.spin.setValue(47)
    qtbot.mouseClick(stepped._down, Qt.MouseButton.LeftButton)
    assert stepped.spin.value() == 45


def test_a_step_of_one_needs_no_snapping(qtbot):
    spin = StepSpinBox()
    spin.setRange(0, 100)
    spin.setValue(7)
    qtbot.addWidget(spin)

    spin.stepBy(1)

    assert spin.value() == 8
