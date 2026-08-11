"""Phase changes get announced — and the ones you caused yourself don't.

Delivery (tray message, taskbar flash, beep) needs a real desktop, so the window is given a
recording sink instead. What's worth testing is *which* transitions speak and what they say.
"""

from __future__ import annotations

import pytest

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.engine.pomodoro import EngineState, State
from habito.ui.app import HabitoApp
from habito.ui.notifier import DesktopNotifier, Notification, notification_for


class RecordingSink:
    def __init__(self) -> None:
        self.sent: list[Notification] = []
        self.sound = ""

    def send(self, note: Notification) -> None:
        self.sent.append(note)

    def set_sound(self, sound: str) -> None:
        self.sound = sound


def snapshot(
    state: State,
    round_index: int = 1,
    work_seconds: int = 0,
    pending: State | None = None,
) -> EngineState:
    return EngineState(
        state=state,
        round_index=round_index,
        total_rounds=4,
        remaining_seconds=0,
        phase_target_seconds=1500,
        accumulated_work_seconds=work_seconds,
        session_work_seconds=work_seconds,
        paused_from=None,
        pending=pending,
    )


# --- what gets said -------------------------------------------------------
def test_finishing_a_round_offers_the_break():
    snap = snapshot(State.awaiting, round_index=2, pending=State.break_)
    note = notification_for(State.work, snap)
    assert note is not None
    assert note.title == "Round complete"
    assert "Round 2 of 4" in note.body
    assert note.action == "Start break"


def test_finishing_a_break_offers_the_next_round():
    snap = snapshot(State.awaiting, round_index=2, pending=State.work)
    note = notification_for(State.break_, snap)
    assert note is not None
    assert note.title == "Break over"
    assert "Round 3 of 4" in note.body  # the one about to start, not the one just done
    assert note.action == "Start round 3"


def test_finishing_the_session_reports_the_total():
    note = notification_for(State.work, snapshot(State.done, work_seconds=3900))
    assert note is not None
    assert note.title == "Session complete"
    assert "1h 05m" in note.body
    assert note.action == "Done"


@pytest.mark.parametrize(
    ("previous", "state"),
    [
        (State.work, State.work),  # still running — nothing happened
        (State.idle, State.work),  # you pressed start; you know
        (State.work, State.paused),  # you pressed pause; you know
        (State.paused, State.work),  # you pressed resume; you know
        (State.idle, State.idle),
    ],
)
def test_nothing_is_announced_for_non_events(previous, state):
    assert notification_for(previous, snapshot(state)) is None


# --- when the window sends them -------------------------------------------
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
    window._notifier = RecordingSink()
    return window


def test_starting_a_session_says_nothing(app):
    app.on_start()
    assert app._notifier.sent == []


def test_an_automatic_phase_change_is_announced(app):
    app.on_start()
    app._engine.skip()  # finish the work round the way the clock would
    app._repaint()

    assert [n.title for n in app._notifier.sent] == ["Round complete"]


def test_stopping_by_hand_is_not_announced(app):
    app.on_start()
    app.on_stop()

    assert app._notifier.sent == []


def test_the_suppression_only_applies_to_the_stop_that_set_it(app):
    """A no-op stop must not swallow the next genuine notification."""
    app.on_stop()  # idle: the engine ignores this
    app.on_start()
    app._engine.skip()
    app._repaint()

    assert [n.title for n in app._notifier.sent] == ["Round complete"]


def test_a_full_session_announces_every_phase_change(app):
    app.on_start()
    for _ in range(app._config.pomodoro.rounds * 2 - 1):
        app._engine.skip()
        app._repaint()
        app._engine.acknowledge()  # the prompt's button, pressed
        app._repaint()

    titles = [n.title for n in app._notifier.sent]
    assert titles[0] == "Round complete"
    assert titles[-1] == "Session complete"
    assert titles.count("Session complete") == 1


def test_notifications_can_be_switched_off(qtbot, tmp_path):
    config = Config.model_validate(
        {
            "ui": {"notifications": False},
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
        }
    )
    # store built with test_mode=False so the log lives under tmp_path; the *window*
    # still runs in test mode. Otherwise every test shares one scratch file.
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)

    assert isinstance(window._notifier, DesktopNotifier)
    assert window._notifier._enabled is False
