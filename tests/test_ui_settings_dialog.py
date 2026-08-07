"""The Settings dialog, driven by keyboard.

Dialogs get Enter handling from Qt's ``autoDefault`` mechanism rather than our
:class:`~habito.ui.widgets.Button`, so it's worth proving the focused button is the one
that fires — not whichever button happens to be the dialog's default.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from habito.config.models import GoalsConfig, PomodoroConfig
from habito.ui.settings_view import SettingsDialog, SettingsValues
from habito.ui.widgets import Stepper


class FakeController:
    def __init__(self) -> None:
        self.saved: list[SettingsValues] = []
        self.previewed: list[str] = []
        self.error: str | None = None

    def on_save_settings(self, values: SettingsValues) -> str | None:
        self.saved.append(values)
        return self.error

    def on_preview_sound(self, sound: str) -> None:
        self.previewed.append(sound)


@pytest.fixture
def dialog(qtbot):
    controller = FakeController()
    widget = SettingsDialog(controller=controller, pomodoro=PomodoroConfig())
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget, controller


def test_edits_are_passed_to_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._break_spin.setValue(12)
    widget._rounds_spin.setValue(6)
    widget._goal_spin.setValue(120)
    widget._buffer_spin.setValue(10)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved == [
        SettingsValues(
            break_minutes=12,
            rounds=6,
            daily_minutes=120,
            buffer_minutes=10,
            sound="notification",
        )
    ]
    assert "Saved" in widget._status.text()


def test_a_rejected_save_is_reported(dialog, qtbot):
    widget, controller = dialog
    controller.error = "rounds: must be positive"
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert widget._status.text() == "rounds: must be positive"


def test_enter_presses_the_focused_button_not_the_default(dialog, qtbot):
    widget, controller = dialog
    widget._preview_btn.setFocus()
    qtbot.keyClick(widget._preview_btn, Qt.Key.Key_Return)

    assert controller.previewed == ["notification"]
    assert controller.saved == []  # Save is the default button, but wasn't focused


def test_enter_saves_when_the_save_button_has_focus(dialog, qtbot):
    widget, controller = dialog
    widget._save_btn.setFocus()
    qtbot.keyClick(widget._save_btn, Qt.Key.Key_Return)

    assert controller.saved[0].break_minutes == 5
    assert controller.saved[0].rounds == 4
    assert controller.saved[0].sound == "notification"


def test_tab_reaches_every_control(dialog, qtbot):
    widget, _ = dialog
    widget._break_spin.setFocus()

    seen = []
    for _ in range(9):
        qtbot.keyClick(widget.focusWidget(), Qt.Key.Key_Tab)
        seen.append(widget.focusWidget())

    assert seen == [
        widget._rounds_spin,
        widget._goal_spin,
        widget._buffer_spin,
        widget._stretch_spin,
        widget._sound_box,
        widget._preview_btn,
        widget._tz_box,
        widget._rollover_spin,
        widget._save_btn,
    ]


# --- the daily goal -------------------------------------------------------
def test_the_goal_fields_start_from_the_config(qtbot):
    controller = FakeController()
    widget = SettingsDialog(
        controller=controller,
        pomodoro=PomodoroConfig(),
        goals=GoalsConfig(daily_minutes=120, buffer_minutes=10),
    )
    qtbot.addWidget(widget)

    assert widget._goal_spin.value() == 120
    assert widget._buffer_spin.value() == 10


def test_the_allowance_may_be_zero_but_the_goal_may_not(dialog):
    widget, _ = dialog
    assert widget._buffer_spin.minimum() == 0
    assert widget._goal_spin.minimum() == 1


def test_goal_edits_reach_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._goal_spin.setValue(150)
    widget._buffer_spin.setValue(15)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved[0].daily_minutes == 150
    assert controller.saved[0].buffer_minutes == 15


# --- stepping ------------------------------------------------------------
def _stepper(spin) -> Stepper:
    """The :class:`Stepper` wrapping a spin box — its parent, by construction."""
    parent = spin.parent()
    assert isinstance(parent, Stepper)
    return parent


def test_the_step_buttons_are_worth_aiming_at_and_side_by_side(dialog):
    """The original bug: Qt's two 14x13px arrows are stacked and touching, so a miss on one
    lands on the other and looks like a dead button. Side by side, the pointer travels along
    the axis they're separated on, and they don't overlap on it at all.
    """
    widget, _ = dialog
    stepper = _stepper(widget._goal_spin)

    assert stepper._up.width() >= 24 and stepper._up.height() >= 24
    assert stepper._up.x() >= stepper._down.x() + stepper._down.width()
    assert stepper._up.y() == stepper._down.y()


def test_up_still_works_after_down(dialog, qtbot):
    widget, _ = dialog
    stepper = _stepper(widget._goal_spin)
    widget._goal_spin.setValue(60)

    qtbot.mouseClick(stepper._down, Qt.MouseButton.LeftButton)
    assert widget._goal_spin.value() == 55
    qtbot.mouseClick(stepper._up, Qt.MouseButton.LeftButton)
    assert widget._goal_spin.value() == 60


def test_stepping_snaps_an_off_grid_value_onto_the_grid(dialog, qtbot):
    """47 + 5 would be 52, and nothing you press afterwards ever reaches a round number."""
    widget, _ = dialog
    stepper = _stepper(widget._goal_spin)
    widget._goal_spin.setValue(47)

    qtbot.mouseClick(stepper._up, Qt.MouseButton.LeftButton)
    assert widget._goal_spin.value() == 50

    widget._goal_spin.setValue(47)
    qtbot.mouseClick(stepper._down, Qt.MouseButton.LeftButton)
    assert widget._goal_spin.value() == 45


def test_the_break_steps_by_one(dialog, qtbot):
    """A break is tuned a minute at a time; only the goal is coarse enough to want 5."""
    widget, _ = dialog
    stepper = _stepper(widget._break_spin)
    widget._break_spin.setValue(5)

    qtbot.mouseClick(stepper._up, Qt.MouseButton.LeftButton)

    assert widget._break_spin.value() == 6


def test_a_direction_greys_out_at_its_limit(dialog):
    widget, _ = dialog
    stepper = _stepper(widget._buffer_spin)

    widget._buffer_spin.setValue(0)  # the minimum
    assert not stepper._down.isEnabled()
    assert stepper._up.isEnabled()

    widget._buffer_spin.setValue(60)  # the maximum
    assert stepper._down.isEnabled()
    assert not stepper._up.isEnabled()


def test_the_step_buttons_stay_out_of_the_tab_order(dialog):
    """Tab still walks field to field; the buttons are for the mouse."""
    widget, _ = dialog
    stepper = _stepper(widget._goal_spin)

    assert stepper._up.focusPolicy() == Qt.FocusPolicy.NoFocus
    assert stepper._down.focusPolicy() == Qt.FocusPolicy.NoFocus


def test_backfill_is_not_offered_here(qtbot, dialog):
    """It lives in the ☰ menu; having it in both places was just a duplicate."""
    widget, _ = dialog
    labels = [b.text() for b in widget.findChildren(type(widget._save_btn))]

    assert not any(word in text.lower() for text in labels for word in ("past session", "backfill"))
