from __future__ import annotations

from uuid import uuid4

import pytest

from conftest import make_config
from habito.domain.events import (
    BreakStarted,
    Origin,
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
    engine = PomodoroEngine(
        make_config(work, brk, rounds), sink=events.append, clock=clock, habit="study"
    )
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


def test_a_finished_phase_waits_to_be_acknowledged():
    """The break shouldn't start while you're still finishing a thought."""
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()

    clock.advance(25 * 60)
    engine.tick()
    assert engine.state is State.awaiting
    assert engine.snapshot().pending is State.break_
    assert isinstance(events[-1], RoundEnded)  # the round is recorded...

    clock.advance(10 * 60)  # ...and no break time accrues while we wait
    engine.tick()
    assert engine.state is State.awaiting

    engine.acknowledge()
    assert engine.state is State.break_
    assert isinstance(events[-1], BreakStarted)
    assert engine.remaining_seconds() == 5 * 60  # a full break, not a shortened one


def test_full_two_round_session_advances_when_acknowledged():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()

    clock.advance(25 * 60)
    engine.tick()  # work 1 -> waiting
    engine.acknowledge()  # -> break 1
    assert isinstance(events[-1], BreakStarted)

    clock.advance(5 * 60)
    engine.tick()  # break 1 -> waiting
    engine.acknowledge()  # -> work 2
    assert isinstance(events[-1], RoundStarted)
    assert engine.snapshot().round_index == 2

    clock.advance(25 * 60)
    engine.tick()  # work 2 (last) -> session ends, no trailing break
    assert isinstance(events[-1], SessionEnded)
    assert events[-1].total_work_seconds == 2 * 25 * 60
    assert engine.state is State.done


def test_the_last_round_ends_the_session_without_waiting():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()

    assert engine.state is State.done  # nothing queued, so nothing to acknowledge
    assert engine.snapshot().pending is None


def test_acknowledge_does_nothing_when_no_phase_is_waiting():
    engine, clock, events = build()
    engine.acknowledge()
    assert engine.state is State.idle

    engine.start()
    before = list(events)
    engine.acknowledge()
    assert engine.state is State.work
    assert events == before


def test_stopping_while_waiting_ends_the_session():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()
    assert engine.state is State.awaiting

    engine.stop()
    assert engine.state is State.done
    assert isinstance(events[-1], SessionEnded)
    # The finished round was already recorded; stopping must not record it twice.
    assert sum(isinstance(e, RoundEnded) for e in events) == 1


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
            engine.acknowledge()  # start the break
            clock.advance(brk * 60)
            engine.tick()
            engine.acknowledge()  # start the next round
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
    assert isinstance(events[-1], RoundEnded)
    assert events[-1].work_seconds == 120  # only elapsed time counted
    assert engine.state is State.awaiting  # skipping still waits for you

    engine.acknowledge()
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


def test_resume_session_starts_new_session_with_shortened_work_target():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.resume_session(2, State.work, remaining_seconds=180, resumed_from=uuid4())

    assert isinstance(events[0], SessionStarted)
    assert isinstance(events[1], RoundStarted)
    assert events[1].round_index == 2
    assert engine.state is State.work
    assert engine.snapshot().round_index == 2
    assert engine.remaining_seconds() == 180  # not the configured 25 minutes


def test_resume_session_starts_new_session_with_shortened_break_target():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.resume_session(1, State.break_, remaining_seconds=90, resumed_from=uuid4())

    assert isinstance(events[1], BreakStarted)
    assert events[1].round_index == 1
    assert engine.state is State.break_
    assert engine.remaining_seconds() == 90  # not the configured 5 minutes


def test_resume_session_completes_normally_from_there():
    """A resumed round still ends (and can finish the session) like any other."""
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.resume_session(1, State.work, remaining_seconds=120, resumed_from=uuid4())

    clock.advance(120)
    engine.tick()
    assert isinstance(events[-1], SessionEnded)
    assert events[-1].total_work_seconds == 120


def test_resume_session_links_back_to_the_interrupted_session():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(60)
    engine.stop()
    first_id = events[0].session_id

    engine.resume_session(2, State.work, remaining_seconds=180, resumed_from=first_id)
    resumed = events[len(events) - 2 :]  # SessionStarted, RoundStarted just emitted
    assert resumed[0].session_id != first_id
    assert resumed[0].resumed_from == first_id
    assert all(e.session_id == resumed[0].session_id for e in resumed)
    assert all(e.origin is Origin.live for e in resumed)


def test_resume_session_rejects_a_running_engine():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    with pytest.raises(RuntimeError):
        engine.resume_session(1, State.work, remaining_seconds=60, resumed_from=uuid4())


def test_session_id_is_none_before_the_first_start():
    engine, clock, events = build()
    assert engine.session_id is None


def test_session_id_survives_completion_for_the_session_complete_prompt():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    started_id = events[0].session_id

    clock.advance(25 * 60)
    engine.tick()

    assert engine.state is State.done
    assert engine.session_id == started_id


def test_update_config_takes_effect_next_session():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.update_config(make_config(work=50, brk=10, rounds=1))
    engine.start()
    assert engine.remaining_seconds() == 50 * 60


def test_session_work_seconds_tracks_live():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(300)
    assert engine.snapshot().session_work_seconds == 300
    clock.advance(25 * 60 - 300)
    engine.tick()  # complete round 1
    engine.acknowledge()
    clock.advance(5 * 60)
    engine.tick()  # complete break
    engine.acknowledge()  # start round 2
    clock.advance(100)
    assert engine.snapshot().session_work_seconds == 25 * 60 + 100


def test_every_event_of_a_session_carries_one_id_and_a_live_origin():
    """The stamp each emit site spells out by hand, checked once across all of them.

    Every transition names ``session_id`` and ``origin`` itself, so nothing structural
    stops one site from disagreeing with the rest — this is what would notice.
    """
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    engine.pause()
    engine.resume()
    engine.add_time(1)
    clock.advance(26 * 60)
    engine.tick()  # round 1 -> waiting
    engine.acknowledge()  # -> break 1
    clock.advance(5 * 60)
    engine.tick()  # break 1 -> waiting
    engine.acknowledge()  # -> round 2
    clock.advance(25 * 60)
    engine.tick()  # last round -> session ends

    # Every emit site the engine has, minus the two `stop()` reaches; see below.
    assert set(types(events)) == {
        "session_started",
        "round_started",
        "session_paused",
        "session_resumed",
        "time_adjusted",
        "round_ended",
        "break_started",
        "break_ended",
        "session_ended",
    }
    assert len({e.session_id for e in events}) == 1
    assert all(e.origin is Origin.live for e in events)
    assert all(e.habit == "study" for e in events)


def test_a_session_ended_by_stop_carries_the_same_stamp():
    """`stop()` has emit sites of its own, which the run to completion never reaches."""
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(10 * 60)
    engine.stop()

    assert types(events)[-2:] == ["round_ended", "session_ended"]
    assert len({e.session_id for e in events}) == 1
    assert all(e.origin is Origin.live for e in events)


def test_a_second_session_gets_its_own_id():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    first = events[0].session_id
    engine.stop()
    engine.start()

    assert events[-1].session_id != first
