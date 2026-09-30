"""The Settings dialog, driven by keyboard.

Dialogs get Enter handling from Qt's ``autoDefault`` mechanism rather than our
:class:`~habito.ui.widgets.controls.Button`, so it's worth proving the focused button is the one
that fires — not whichever button happens to be the dialog's default.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from habito.config.models import GoalsConfig, PomodoroConfig
from habito.ui.dialogs.settings_dialog import SettingsDialog, SettingsValues
from habito.ui.widgets.controls import Stepper


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
    widget._low_spin.setValue(120)
    widget._low_buffer_spin.setValue(10)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved == [
        SettingsValues(
            break_minutes=12,
            rounds=6,
            low_minutes=120,
            low_buffer_minutes=10,
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
    for _ in range(14):
        qtbot.keyClick(widget.focusWidget(), Qt.Key.Key_Tab)
        seen.append(widget.focusWidget())

    assert seen == [
        widget._rounds_spin,
        widget._resume_window_spin,
        widget._low_spin,
        widget._low_buffer_spin,
        widget._middle_spin,
        widget._middle_buffer_spin,
        widget._high_spin,
        widget._high_buffer_spin,
        widget._sound_box,
        widget._preview_btn,
        widget._reminder_spin,
        widget._tz_box,
        widget._rollover_spin,
        widget._save_btn,
    ]


# --- the goals -----------------------------------------------------------
def test_the_goal_fields_start_from_the_config(qtbot):
    controller = FakeController()
    widget = SettingsDialog(
        controller=controller,
        pomodoro=PomodoroConfig(),
        goals=GoalsConfig(low_minutes=120, low_buffer_minutes=10, middle_buffer_minutes=20),
    )
    qtbot.addWidget(widget)

    assert widget._low_spin.value() == 120
    assert widget._low_buffer_spin.value() == 10
    assert widget._middle_buffer_spin.value() == 20


def test_the_allowance_may_be_zero_but_the_goal_may_not(dialog):
    widget, _ = dialog
    assert widget._low_buffer_spin.minimum() == 0
    assert widget._low_spin.minimum() == 1


def test_goal_edits_reach_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._low_spin.setValue(150)
    widget._low_buffer_spin.setValue(15)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved[0].low_minutes == 150
    assert controller.saved[0].low_buffer_minutes == 15


def test_middle_buffer_edits_reach_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._middle_buffer_spin.setValue(20)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved[0].middle_buffer_minutes == 20


def test_reminder_delay_starts_from_the_config(qtbot):
    controller = FakeController()
    widget = SettingsDialog(
        controller=controller, pomodoro=PomodoroConfig(), break_reminder_minutes=7
    )
    qtbot.addWidget(widget)

    assert widget._reminder_spin.value() == 7


def test_reminder_delay_edits_reach_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._reminder_spin.setValue(10)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved[0].break_reminder_minutes == 10


def test_resume_window_starts_from_the_config(qtbot):
    controller = FakeController()
    widget = SettingsDialog(
        controller=controller, pomodoro=PomodoroConfig(resume_window_minutes=15)
    )
    qtbot.addWidget(widget)

    assert widget._resume_window_spin.value() == 15


def test_resume_window_edits_reach_the_controller(dialog, qtbot):
    widget, controller = dialog
    widget._resume_window_spin.setValue(20)
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved[0].resume_window_minutes == 20


# --- stepping ------------------------------------------------------------
# What a Stepper *does* is proved once in test_widgets.py. All that is left here is what
# this dialog chose: that every number field got one, and how coarsely each one moves.
def test_every_number_field_is_wrapped_in_a_stepper(dialog):
    widget, _ = dialog
    fields = (
        widget._break_spin,
        widget._rounds_spin,
        widget._resume_window_spin,
        widget._low_spin,
        widget._low_buffer_spin,
        widget._middle_spin,
        widget._middle_buffer_spin,
        widget._high_spin,
        widget._high_buffer_spin,
        widget._reminder_spin,
        widget._rollover_spin,
    )
    assert all(isinstance(spin.parent(), Stepper) for spin in fields)


def test_the_step_size_follows_how_the_value_is_used(dialog):
    """A goal is picked roughly, so it moves in 5s; a break is tuned against how long it
    actually feels, so it moves in 1s. Same widget, different `singleStep`."""
    widget, _ = dialog

    assert widget._low_spin.singleStep() == 5
    assert widget._middle_spin.singleStep() == 5
    assert widget._high_spin.singleStep() == 5
    assert widget._break_spin.singleStep() == 1
    assert widget._rounds_spin.singleStep() == 1
    assert widget._low_buffer_spin.singleStep() == 1
    assert widget._middle_buffer_spin.singleStep() == 1
    assert widget._high_buffer_spin.singleStep() == 1
    assert widget._reminder_spin.singleStep() == 1
    assert widget._resume_window_spin.singleStep() == 1


def test_backfill_is_not_offered_here(qtbot, dialog):
    """It lives in the ☰ menu; having it in both places was just a duplicate."""
    widget, _ = dialog
    labels = [b.text() for b in widget.findChildren(type(widget._save_btn))]

    assert not any(word in text.lower() for text in labels for word in ("past session", "backfill"))
