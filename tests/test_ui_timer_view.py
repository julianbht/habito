"""UI tests driven through Qt's real event loop.

``qtbot`` (from pytest-qt) owns the ``QApplication`` and delivers genuine mouse and key
events, so focus, tab traversal and shortcuts are actually exercised rather than faked by
calling the handler directly. Run headless with ``QT_QPA_PLATFORM=offscreen`` (conftest
sets this automatically).
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from habito.engine.pomodoro import EngineState, State
from habito.ui.timer_view import TimerView
from habito.ui.widgets import MinutesSpinBox, parse_minutes


class FakeController:
    """Records what the view asked for, so assertions read as user intent."""

    def __init__(self) -> None:
        self.started = 0
        self.paused = 0
        self.stopped = 0
        self.added: list[float] = []
        self.work_minutes: list[int] = []

    def on_start(self) -> None:
        self.started += 1

    def on_pause_resume(self) -> None:
        self.paused += 1

    def on_stop(self) -> None:
        self.stopped += 1

    def on_add_time(self, minutes: float) -> None:
        self.added.append(minutes)

    def on_set_work_minutes(self, minutes: int) -> str | None:
        self.work_minutes.append(minutes)
        return None


def snapshot(state: State, remaining: int = 0, target: int = 0, work: int = 0) -> EngineState:
    return EngineState(
        state=state,
        round_index=1,
        total_rounds=4,
        remaining_seconds=remaining,
        phase_target_seconds=target,
        accumulated_work_seconds=0,
        session_work_seconds=work,
        paused_from=None,
    )


@pytest.fixture
def view(qtbot):
    controller = FakeController()
    widget = TimerView(controller=controller, quick_add_minutes=[1, 3, 5], work_minutes=25)
    qtbot.addWidget(widget)
    widget.show()
    qtbot.waitExposed(widget)
    return widget, controller


# --- the duration control (feature 1) ------------------------------------
@pytest.mark.parametrize(
    ("text", "expected"),
    [("30", 30), ("30:00", 30), ("29:40", 30), ("29:00", 29), ("", None), ("abc", None)],
)
def test_parse_minutes(text, expected):
    assert parse_minutes(text) == expected


def test_spin_box_displays_mm_ss(qtbot):
    spin = MinutesSpinBox()
    qtbot.addWidget(spin)
    spin.setValue(25)
    assert spin.text() == "25:00"


def test_spin_box_arrows_step_by_configured_amount(view, qtbot):
    widget, controller = view
    widget._step_box.setCurrentText("5")
    widget._on_step_activated(widget._step_box.currentIndex())

    widget._spin.stepUp()
    assert widget._spin.value() == 30
    assert controller.work_minutes[-1] == 30


def test_typing_a_duration_commits_on_enter(view, qtbot):
    widget, controller = view
    widget._spin.setFocus()
    widget._spin.lineEdit().selectAll()
    qtbot.keyClicks(widget._spin, "45")
    qtbot.keyClick(widget._spin, Qt.Key.Key_Return)

    assert widget._spin.value() == 45
    assert controller.work_minutes[-1] == 45


def test_keyboard_up_arrow_changes_duration(view, qtbot):
    widget, controller = view
    widget._spin.setFocus()
    qtbot.keyClick(widget._spin, Qt.Key.Key_Up)

    assert widget._spin.value() == 26
    assert controller.work_minutes[-1] == 26


def test_nudge_buttons_adjust_the_live_round(view, qtbot):
    widget, controller = view
    widget.render_state(snapshot(State.work, remaining=900, target=1500), 0)

    qtbot.mouseClick(widget._up_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(widget._down_btn, Qt.MouseButton.LeftButton)

    assert controller.added == [1, -1]


# --- rendering ------------------------------------------------------------
def test_swaps_between_editor_and_countdown(view):
    widget, _ = view
    assert widget._stack.currentIndex() == 0  # idle: editable duration

    widget.render_state(snapshot(State.work, remaining=900, target=1500), 0)
    assert widget._stack.currentIndex() == 1  # running: live countdown
    assert widget._time_lbl.text() == "15:00"

    widget.render_state(snapshot(State.done), 0)
    assert widget._stack.currentIndex() == 0  # back to editable when finished


def test_progress_and_stop_button_track_state(view):
    widget, _ = view
    widget.render_state(snapshot(State.idle), 0)
    assert not widget._stop_btn.isEnabled()

    widget.render_state(snapshot(State.work, remaining=750, target=1500), 0)
    assert widget._stop_btn.isEnabled()
    assert widget._progress.value() == 500  # half of a 1000-step bar


def test_primary_button_toggles_between_start_and_pause(view, qtbot):
    widget, controller = view
    qtbot.mouseClick(widget._primary_btn, Qt.MouseButton.LeftButton)
    assert controller.started == 1

    widget.render_state(snapshot(State.work, remaining=900, target=1500), 0)
    qtbot.mouseClick(widget._primary_btn, Qt.MouseButton.LeftButton)
    assert controller.paused == 1
    assert controller.started == 1


def test_today_total_is_rendered(view):
    widget, _ = view
    widget.render_state(snapshot(State.idle), 3900)
    assert widget._today_lbl.text() == "Today: 1h 05m"


# --- keyboard navigation (feature 3) --------------------------------------
def tab_chain(widget, qtbot, steps: int) -> list:
    return [
        (qtbot.keyClick(widget.focusWidget(), Qt.Key.Key_Tab), widget.focusWidget())[1]
        for _ in range(steps)
    ]


@pytest.mark.parametrize(
    "state", [State.idle, State.work], ids=["idle", "running"]
)
def test_tab_walks_the_controls_in_order(view, qtbot, state):
    """The chain is the same in both modes — the ▲/▼ pair is never hidden."""
    widget, _ = view
    widget.render_state(snapshot(state, remaining=900, target=1500), 0)
    widget._spin.setFocus() if state is State.idle else widget._up_btn.setFocus()

    expected = [widget._up_btn, widget._down_btn, widget._step_box, widget._primary_btn]
    if state is State.idle:
        # Stop is disabled with no session to stop, and Qt skips disabled widgets.
        assert not widget._stop_btn.isEnabled()
    else:
        expected = expected[1:] + [widget._stop_btn]  # started on ▲; the spin box is hidden

    assert tab_chain(widget, qtbot, len(expected)) == expected


def test_focus_survives_the_switch_into_a_running_session(view):
    widget, _ = view
    widget.focus_first()
    assert widget.focusWidget() is widget._spin

    # The duration field is about to be hidden; focus must land somewhere usable.
    widget.render_state(snapshot(State.work, remaining=1500, target=1500), 0)
    assert widget.focusWidget() is widget._primary_btn


def test_nudge_buttons_keep_focus_across_a_swap(view):
    """They sit beside the stack, not inside it, so a swap can't disturb them."""
    widget, _ = view
    widget.render_state(snapshot(State.work, remaining=1500, target=1500), 0)
    widget._up_btn.setFocus()

    widget.render_state(snapshot(State.done), 0)
    assert widget.focusWidget() is widget._up_btn


def test_focus_elsewhere_is_left_alone_when_the_page_swaps(view):
    widget, _ = view
    widget._stop_btn.setFocus()
    widget.render_state(snapshot(State.work, remaining=1500, target=1500), 0)
    assert widget.focusWidget() is widget._stop_btn


def test_space_activates_the_focused_button(view, qtbot):
    widget, controller = view
    widget._primary_btn.setFocus()
    qtbot.keyClick(widget._primary_btn, Qt.Key.Key_Space)
    assert controller.started == 1


def test_nudging_while_idle_changes_the_planned_length_not_the_round(view):
    widget, controller = view
    widget.render_state(snapshot(State.idle), 0)

    widget.nudge_up()
    widget.nudge_up()
    widget.nudge_down()

    assert widget._spin.value() == 26
    assert controller.added == []  # nothing to add time to — no session is running


def test_nudging_while_running_adjusts_the_round_not_the_planned_length(view):
    widget, controller = view
    widget.render_state(snapshot(State.work, remaining=900, target=1500), 0)

    widget.nudge_up()
    widget.nudge_down()

    assert controller.added == [1, -1]
    assert widget._spin.value() == 25  # planned length untouched mid-session
