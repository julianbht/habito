"""HabitoApp._maybe_remind: the "still on break?" nudge, timed against a real clock.

Uses a FakeClock-backed engine (bypassing _build_engine_and_store, which always wires a
real SystemClock) so the reminder delay can be fast-forwarded instead of waited out.
"""

from __future__ import annotations

from habito.config.models import Config
from habito.engine.clock import FakeClock
from habito.engine.pomodoro import PomodoroEngine, State
from habito.storage.event_store import EventStore
from habito.ui.app import HabitoApp
from habito.ui.notifier import Notification


class RecordingSink:
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, note: Notification) -> None:
        self.sent.append(note)

    def set_sound(self, sound: str) -> None:
        pass


def build(qtbot, tmp_path, *, break_reminder_minutes: int = 3, rounds: int = 4):
    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "pomodoro": {"rounds": rounds},
            "ui": {"break_reminder_minutes": break_reminder_minutes},
        }
    )
    store = EventStore(config.data_repo_path(), config.habit, config.time.rollover_hour)
    clock = FakeClock()
    engine = PomodoroEngine(config.pomodoro, sink=store.append, clock=clock, habit=config.habit)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    sink = RecordingSink()
    window._notifier = sink
    return window, clock, sink


def _reach_awaiting_next_round(window):
    """Work round 1 -> awaiting break -> break -> awaiting round 2, all instantly."""
    window.on_start()
    window._engine.skip()  # round 1 done -> awaiting break
    window._repaint()
    window._engine.acknowledge()  # -> break
    window._engine.skip()  # break done -> awaiting round 2
    window._repaint()


def test_no_reminder_before_the_delay(qtbot, tmp_path):
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    _reach_awaiting_next_round(window)
    sink.sent.clear()  # drop the original "Break over" notification

    clock.advance(179)  # just under 3 minutes
    window._repaint()

    assert sink.sent == []


def test_a_reminder_fires_once_the_delay_passes(qtbot, tmp_path):
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    _reach_awaiting_next_round(window)
    sink.sent.clear()

    clock.advance(180)
    window._repaint()

    assert [n.title for n in sink.sent] == ["Still on break?"]


def test_the_reminder_fires_only_once(qtbot, tmp_path):
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    _reach_awaiting_next_round(window)
    sink.sent.clear()

    clock.advance(180)
    window._repaint()
    clock.advance(600)  # long past the delay again
    window._repaint()

    assert [n.title for n in sink.sent] == ["Still on break?"]


def test_acknowledging_before_the_delay_prevents_the_reminder(qtbot, tmp_path):
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    _reach_awaiting_next_round(window)
    sink.sent.clear()

    clock.advance(60)
    window._repaint()
    window._engine.acknowledge()  # round 2 starts
    window._repaint()
    clock.advance(300)  # long past the delay, but no longer waiting
    window._repaint()

    assert sink.sent == []
    assert window._awaiting_break_over_since is None


def test_no_reminder_while_awaiting_a_break(qtbot, tmp_path):
    """Break-only scope: a round finished, awaiting the break, must never nag."""
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    window.on_start()
    window._engine.skip()  # round 1 done -> awaiting break
    window._repaint()
    sink.sent.clear()

    clock.advance(600)
    window._repaint()

    assert sink.sent == []
    assert window._engine.state is State.awaiting


def test_a_later_break_gets_its_own_reminder(qtbot, tmp_path):
    """One wait's reminder having fired must not silence the next one."""
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=3)
    _reach_awaiting_next_round(window)
    clock.advance(180)
    window._repaint()  # first reminder fires
    sink.sent.clear()

    window._engine.acknowledge()  # -> round 2
    window._engine.skip()  # round 2 done -> awaiting break
    window._repaint()
    window._engine.acknowledge()  # -> break
    window._engine.skip()  # break done -> awaiting round 3
    window._repaint()
    sink.sent.clear()

    clock.advance(180)
    window._repaint()

    assert [n.title for n in sink.sent] == ["Still on break?"]


def test_the_delay_is_configurable(qtbot, tmp_path):
    window, clock, sink = build(qtbot, tmp_path, break_reminder_minutes=1)
    _reach_awaiting_next_round(window)
    sink.sent.clear()

    clock.advance(60)
    window._repaint()

    assert [n.title for n in sink.sent] == ["Still on break?"]
