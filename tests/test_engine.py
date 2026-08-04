from __future__ import annotations

from conftest import make_config
from habito.domain.events import (
    BreakStarted,
    RoundEnded,
    RoundStarted,
    SessionEnded,
    SessionStarted,
    TimeAdjusted,
)
from habito.engine.clock import FakeClock
from habito.engine.pomodoro import PomodoroEngine, State


def build(work=25, brk=5, rounds=2):
    events = []
    clock = FakeClock()
    engine = PomodoroEngine(make_config(work, brk, rounds), sink=events.append, clock=clock)
    return engine, clock, events


def types(events):
    return [e.type for e in events]


def test_start_emits_session_and_first_round():
    engine, clock, events = build()
    engine.start()
    assert isinstance(events[0], SessionStarted)
    assert isinstance(events[1], RoundStarted)
    assert engine.state is State.work
    assert engine.snapshot().round_index == 1


def test_full_two_round_session_auto_advances():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()

    clock.advance(25 * 60)
    engine.tick()  # work 1 -> break 1
    assert isinstance(events[-1], BreakStarted)

    clock.advance(5 * 60)
    engine.tick()  # break 1 -> work 2
    assert isinstance(events[-1], RoundStarted)
    assert engine.snapshot().round_index == 2

    clock.advance(25 * 60)
    engine.tick()  # work 2 (last) -> session ends, no trailing break
    assert isinstance(events[-1], SessionEnded)
    assert events[-1].total_work_seconds == 2 * 25 * 60
    assert engine.state is State.done


def test_no_trailing_break_after_last_round():
    _, _, events = _run_full(rounds=3)
    assert not isinstance(events[-2], BreakStarted)
    assert isinstance(events[-1], SessionEnded)
    assert sum(isinstance(e, BreakStarted) for e in events) == 2  # rounds-1 breaks


def _run_full(work=25, brk=5, rounds=3):
    engine, clock, events = build(work, brk, rounds)
    engine.start()
    for r in range(1, rounds + 1):
        clock.advance(work * 60)
        engine.tick()
        if r < rounds:
            clock.advance(brk * 60)
            engine.tick()
    return engine, clock, events


def test_pause_freezes_remaining():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(60)
    engine.pause()
    remaining = engine.remaining_seconds()
    clock.advance(300)  # time passes while paused
    assert engine.remaining_seconds() == remaining
    assert engine.state is State.paused
    engine.resume()
    clock.advance(60)
    assert engine.remaining_seconds() == remaining - 60


def test_add_time_extends_phase_and_logs():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    before = engine.remaining_seconds()
    engine.add_time(3)
    assert engine.remaining_seconds() == before + 3 * 60
    adj = [e for e in events if isinstance(e, TimeAdjusted)]
    assert adj and adj[0].delta_seconds == 180


def test_added_time_counts_toward_work():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    engine.add_time(5)
    clock.advance(30 * 60)  # 25 + 5 extended
    engine.tick()
    ended = [e for e in events if isinstance(e, RoundEnded)][0]
    assert ended.work_seconds == 30 * 60


def test_skip_work_advances_to_break():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(120)
    engine.skip()
    assert isinstance(events[-2], RoundEnded)
    assert events[-2].work_seconds == 120  # only elapsed time counted
    assert isinstance(events[-1], BreakStarted)


def test_stop_finalizes_and_ends_session():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(600)
    engine.stop()
    assert isinstance(events[-2], RoundEnded)
    assert isinstance(events[-1], SessionEnded)
    assert events[-1].total_work_seconds == 600
    assert engine.state is State.done


def test_session_work_seconds_tracks_live():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(300)
    assert engine.snapshot().session_work_seconds == 300
    clock.advance(25 * 60 - 300)
    engine.tick()  # complete round 1
    clock.advance(5 * 60)
    engine.tick()  # complete break, start round 2
    clock.advance(100)
    assert engine.snapshot().session_work_seconds == 25 * 60 + 100
