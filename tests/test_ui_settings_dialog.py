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


class FakeController:
    def __init__(self) -> None:
        self.saved: list[SettingsValues] = []
        self.previewed: list[str] = []
        self.backfills = 0
        self.error: str | None = None

    def on_save_settings(self, values: SettingsValues) -> str | None:
        self.saved.append(values)
        return self.error

    def on_open_backfill(self) -> None:
        self.backfills += 1

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
    widget._backfill_btn.setFocus()
    qtbot.keyClick(widget._backfill_btn, Qt.Key.Key_Return)

    assert controller.backfills == 1
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
    for _ in range(7):
        qtbot.keyClick(widget.focusWidget(), Qt.Key.Key_Tab)
        seen.append(widget.focusWidget())

    assert seen == [
        widget._rounds_spin,
        widget._goal_spin,
        widget._buffer_spin,
        widget._sound_box,
        widget._preview_btn,
        widget._save_btn,
        widget._backfill_btn,
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


def test_the_goal_is_spelled_out_in_hours(dialog):
    """"95 minutes" is not how anyone thinks about a study target."""
    widget, _ = dialog
    widget._goal_spin.setValue(100)
    widget._buffer_spin.setValue(5)

    assert "1h 40m a day" in widget._goal_lbl.text()
    assert "green from 1h 35m" in widget._goal_lbl.text()


def test_the_readout_follows_the_allowance(dialog):
    widget, _ = dialog
    widget._goal_spin.setValue(100)

    widget._buffer_spin.setValue(0)
    assert "green from 1h 40m" in widget._goal_lbl.text()

    widget._buffer_spin.setValue(20)
    assert "green from 1h 20m" in widget._goal_lbl.text()


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
