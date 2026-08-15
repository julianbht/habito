"""The prompt that gates the next phase.

The point of it is that the break does *not* start on its own — so most of these check
that nothing moved until the button was pressed.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.engine.pomodoro import State
from habito.ui.app import HabitoApp
from habito.ui.dialogs.phase_dialog import PhaseDialog


@pytest.fixture
def app(qtbot, tmp_path):
    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    # store built with test_mode=False so the log lives under tmp_path; the *window*
    # still runs in test mode. Otherwise every test shares one scratch file.
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def finish_the_round(app):
    app.on_start()
    app._engine.skip()
    app._repaint()


def make_dialog(pressed: list) -> PhaseDialog:
    return PhaseDialog("Round complete", "Take a break.", "Start break", lambda: pressed.append(1))


# --- the dialog on its own ------------------------------------------------
def test_the_button_reports_and_closes(qtbot):
    pressed = []
    dialog = make_dialog(pressed)
    qtbot.addWidget(dialog)
    dialog.present()

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert pressed == [1]
    assert not dialog.isVisible()


def test_it_arrives_on_top_but_drops_back_when_focus_leaves(qtbot):
    """Topmost is for arriving in front, not for staying there."""
    dialog = make_dialog([])
    qtbot.addWidget(dialog)
    dialog.present()
    assert dialog.is_always_on_top()

    QApplication.sendEvent(dialog, QEvent(QEvent.Type.WindowDeactivate))

    assert not dialog.is_always_on_top()
    assert dialog.isVisible()  # dropping the hint must not take the window down


def test_escape_does_not_dismiss_it(qtbot):
    """Closing it without answering would leave the session parked forever."""
    pressed = []
    dialog = make_dialog(pressed)
    qtbot.addWidget(dialog)
    dialog.present()

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert dialog.isVisible()
    assert pressed == []


def test_the_action_button_is_focused_so_enter_works(qtbot):
    pressed = []
    dialog = make_dialog(pressed)
    qtbot.addWidget(dialog)
    dialog.present()

    qtbot.keyClick(dialog.focusWidget(), Qt.Key.Key_Return)
    assert pressed == [1]
    assert not dialog.isVisible()


# --- how the window uses it -----------------------------------------------
def test_the_break_does_not_start_until_the_prompt_is_answered(app):
    finish_the_round(app)

    assert app._engine.state is State.awaiting
    assert app._phase_dialog is not None
    assert app._phase_dialog.isVisible()
    assert app._phase_dialog.action_button.text() == "Start break"


def test_no_break_time_accrues_while_the_prompt_waits(app, qtbot):
    finish_the_round(app)
    qtbot.wait(60)
    app._tick()

    assert app._engine.state is State.awaiting  # the clock isn't running


def test_pressing_the_button_starts_the_break(app, qtbot):
    finish_the_round(app)
    qtbot.mouseClick(app._phase_dialog.action_button, Qt.MouseButton.LeftButton)

    assert app._engine.state is State.break_
    assert app._phase_dialog is None
    assert app._engine.remaining_seconds() == app._config.pomodoro.break_minutes * 60


def test_answering_the_prompt_brings_the_timer_back_to_the_front(app, qtbot):
    finish_the_round(app)
    qtbot.mouseClick(app._phase_dialog.action_button, Qt.MouseButton.LeftButton)

    assert app.isVisible()
    assert not app.isMinimized()
    assert app.focusWidget() is not None  # focus landed back in the timer


def test_the_prompt_offers_the_next_round_after_a_break(app, qtbot):
    finish_the_round(app)
    qtbot.mouseClick(app._phase_dialog.action_button, Qt.MouseButton.LeftButton)

    app._engine.skip()  # finish the break
    app._repaint()

    assert app._engine.state is State.awaiting
    assert app._phase_dialog.action_button.text() == "Start round 2"


def test_stopping_instead_takes_the_prompt_down(app):
    """The prompt isn't modal, so stopping the session is still an option."""
    finish_the_round(app)
    assert app._phase_dialog is not None

    app.on_stop()
    assert app._engine.state is State.done
    assert app._phase_dialog is None


def test_the_primary_button_also_starts_the_waiting_phase(app, qtbot):
    finish_the_round(app)
    qtbot.mouseClick(app._view._primary_btn, Qt.MouseButton.LeftButton)

    assert app._engine.state is State.break_
    assert app._phase_dialog is None


def test_the_session_end_prompt_does_not_gate_anything(app):
    config = app._config.pomodoro
    app.on_start()
    for _ in range(config.rounds * 2 - 1):
        app._engine.skip()
        app._repaint()
        app._engine.acknowledge()
        app._repaint()

    assert app._engine.state is State.done
    assert app._phase_dialog is not None
    assert app._phase_dialog.gates_phase is False
    assert app._phase_dialog.action_button.text() == "Done"
