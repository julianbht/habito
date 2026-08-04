"""The Settings dialog, driven by keyboard.

Dialogs get Enter handling from Qt's ``autoDefault`` mechanism rather than our
:class:`~habito.ui.widgets.Button`, so it's worth proving the focused button is the one
that fires — not whichever button happens to be the dialog's default.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from habito.config.models import PomodoroConfig
from habito.ui.settings_view import SettingsDialog


class FakeController:
    def __init__(self) -> None:
        self.saved: list[tuple[int, int, str]] = []
        self.previewed: list[str] = []
        self.backfills = 0
        self.error: str | None = None

    def on_save_settings(self, brk: int, rounds: int, sound: str) -> str | None:
        self.saved.append((brk, rounds, sound))
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
    qtbot.mouseClick(widget._save_btn, Qt.MouseButton.LeftButton)

    assert controller.saved == [(12, 6, "notification")]
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

    assert controller.saved == [(5, 4, "notification")]


def test_tab_reaches_every_control(dialog, qtbot):
    widget, _ = dialog
    widget._break_spin.setFocus()

    seen = []
    for _ in range(5):
        qtbot.keyClick(widget.focusWidget(), Qt.Key.Key_Tab)
        seen.append(widget.focusWidget())

    assert seen == [
        widget._rounds_spin,
        widget._sound_box,
        widget._preview_btn,
        widget._save_btn,
        widget._backfill_btn,
    ]
