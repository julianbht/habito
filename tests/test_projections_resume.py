"""find_resumable: what counts as a session worth offering to resume.

Event streams here are produced by the real engine (a graceful close finalises the
in-flight phase via ``stop()``, same as ``HabitoApp.closeEvent``) rather than
hand-built, so a fixture can't silently drift from what the engine actually emits.
"""

from __future__ import annotations

from conftest import make_config
from habito.engine.clock import FakeClock
from habito.engine.pomodoro import PomodoroEngine
from habito.projections.resume import ResumePhase, find_resumable


def build(work=25, brk=5, rounds=4):
    events = []
    clock = FakeClock()
    engine = PomodoroEngine(
        make_config(work, brk, rounds), sink=events.append, clock=clock, habit="study"
    )
    return engine, clock, events


def test_no_sessions_means_nothing_resumable():
    assert find_resumable([], "study", current_rounds=4) is None


def test_a_completed_session_is_not_resumable():
    engine, clock, events = build(work=25, brk=5, rounds=1)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()  # rounds=1: this ends the session outright
    assert find_resumable(events, "study", current_rounds=1) is None


def test_closed_mid_round_resumes_the_same_round_with_the_gap():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(15 * 60)  # 15 of 25 minutes in
    engine.stop()  # what HabitoApp.closeEvent now does on quit

    resumable = find_resumable(events, "study", current_rounds=4)
    assert resumable is not None
    assert resumable.round_index == 1
    assert resumable.planned_rounds == 4
    assert resumable.phase is ResumePhase.work
    assert resumable.remaining_seconds == 10 * 60


def test_closed_mid_break_resumes_the_break_with_the_gap():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()
    engine.acknowledge()  # -> break 1
    clock.advance(2 * 60)  # 2 of 5 minutes into the break
    engine.stop()

    resumable = find_resumable(events, "study", current_rounds=4)
    assert resumable is not None
    assert resumable.round_index == 1
    assert resumable.phase is ResumePhase.break_
    assert resumable.remaining_seconds == 3 * 60


def test_closed_right_after_a_full_round_offers_the_break():
    """Round finished in full, but the app closed before the break prompt was answered."""
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()  # round 1 -> awaiting (full length, nothing cut short)
    engine.stop()  # closeEvent's on_stop() while awaiting

    resumable = find_resumable(events, "study", current_rounds=4)
    assert resumable is not None
    assert resumable.round_index == 1
    assert resumable.phase is ResumePhase.break_
    assert resumable.remaining_seconds == 5 * 60  # a full break — none of it logged yet


def test_closed_right_after_a_full_break_offers_the_next_round():
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()
    engine.acknowledge()  # -> break 1
    clock.advance(5 * 60)
    engine.tick()  # break 1 -> awaiting round 2
    engine.stop()

    resumable = find_resumable(events, "study", current_rounds=4)
    assert resumable is not None
    assert resumable.round_index == 2
    assert resumable.phase is ResumePhase.work
    assert resumable.remaining_seconds == 25 * 60


def test_closed_mid_final_round_is_still_resumable():
    engine, clock, events = build(work=25, brk=5, rounds=2)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()
    engine.acknowledge()  # -> break 1
    clock.advance(5 * 60)
    engine.tick()
    engine.acknowledge()  # -> round 2 (the last one)
    clock.advance(10 * 60)
    engine.stop()

    resumable = find_resumable(events, "study", current_rounds=2)
    assert resumable is not None
    assert resumable.round_index == 2
    assert resumable.phase is ResumePhase.work
    assert resumable.remaining_seconds == 15 * 60


def test_closing_while_idle_leaves_nothing_to_resume():
    engine, clock, events = build()
    engine.stop()  # what closeEvent calls unconditionally; a no-op while idle
    assert find_resumable(events, "study", current_rounds=4) is None


def test_a_different_habit_is_not_resumable_here():
    engine, clock, events = build()
    engine.start()
    clock.advance(60)
    engine.stop()
    assert find_resumable(events, "reading", current_rounds=4) is None


def test_a_still_running_session_is_not_resumable():
    """No SessionEnded yet — either it's genuinely still running, or it crashed. Either
    way there's no honest stopping point to offer, by design (see module docstring)."""
    engine, clock, events = build()
    engine.start()
    clock.advance(60)  # no stop() — nothing finalises it

    assert find_resumable(events, "study", current_rounds=4) is None


def test_rounds_lowered_below_the_interrupted_round_is_not_resumable():
    """Settings changed since the interruption: resuming round 3 would contradict a
    ``rounds`` setting that no longer has a round 3."""
    engine, clock, events = build(work=25, brk=5, rounds=4)
    engine.start()
    clock.advance(25 * 60)
    engine.tick()
    engine.acknowledge()  # -> break 1
    clock.advance(5 * 60)
    engine.tick()
    engine.acknowledge()  # -> round 2
    clock.advance(10 * 60)
    engine.stop()  # interrupted mid round 2, planned_rounds was 4

    assert find_resumable(events, "study", current_rounds=4) is not None  # unchanged: fine
    assert find_resumable(events, "study", current_rounds=1) is None  # rounds now < 2
