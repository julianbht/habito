"""Retracting a session — the log's one correction.

Covers the three things that have to hold: the retraction files under the day it corrects
(not the day it was written), the default replay stops counting the voided session, and a
session spanning the rollover is voided in both of its day files.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from habito.backfill import build_backfill_events
from habito.domain.events import (
    RoundEnded,
    SessionRetracted,
    SessionStarted,
    drop_retracted,
    partition_date,
)
from habito.projections.daily import summarize_by_day
from habito.projections.sessions import summarize_sessions
from habito.retraction import build_retraction_events
from habito.storage.event_store import EventStore

CEST = timezone(timedelta(hours=2))
# The correction is made days after the session it voids, which is the whole point.
LATER = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def _store(root, **kwargs):
    return EventStore(root, "study", **kwargs)


def _backfilled(store, day, hour=6, rounds=2):
    """Put a backfilled session in the log and return its (session_id, days)."""
    events = build_backfill_events(
        datetime(day.year, day.month, day.day, hour, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=rounds,
        habit="study",
    )
    for event in events:
        store.append(event)
    session = summarize_sessions(store.read_all(include_retracted=True))[0]
    return session


def test_retraction_files_under_the_day_it_corrects(tmp_path):
    store = _store(tmp_path)
    session = _backfilled(store, datetime(2026, 8, 4).date())

    for event in build_retraction_events(
        session.session_id, session.days, habit="study", now=LATER, reason="wrong date"
    ):
        store.append(event)

    # Written on the 7th, filed on the 4th — beside the events it voids, not off in a
    # later file you'd have to know to look for.
    day_file = tmp_path / "study" / "2026" / "08" / "2026-08-04.jsonl"
    assert "session_retracted" in day_file.read_text(encoding="utf-8")
    assert not (tmp_path / "study" / "2026" / "08" / "2026-08-07.jsonl").exists()


def test_retraction_keeps_its_own_timestamp(tmp_path):
    store = _store(tmp_path)
    session = _backfilled(store, datetime(2026, 8, 4).date())
    for event in build_retraction_events(
        session.session_id, session.days, habit="study", now=LATER
    ):
        store.append(event)

    retraction = next(
        e for e in store.read_all(include_retracted=True) if isinstance(e, SessionRetracted)
    )
    # When the correction was made stays truthful even though it files under another day.
    assert retraction.timestamp == LATER.astimezone(UTC)
    assert retraction.target_date == datetime(2026, 8, 4).date()
    assert partition_date(retraction) == datetime(2026, 8, 4).date()


def test_read_all_drops_the_retracted_session(tmp_path):
    store = _store(tmp_path)
    session = _backfilled(store, datetime(2026, 8, 4).date())
    assert len(store.read_all()) > 0

    for event in build_retraction_events(
        session.session_id, session.days, habit="study", now=LATER
    ):
        store.append(event)

    assert store.read_all() == []  # the retraction line goes too
    assert len(store.read_all(include_retracted=True)) > 0


def test_retraction_leaves_other_sessions_alone(tmp_path):
    store = _store(tmp_path)
    kept = _backfilled(store, datetime(2026, 8, 3).date())
    voided = _backfilled(store, datetime(2026, 8, 4).date())

    for event in build_retraction_events(voided.session_id, voided.days, habit="study", now=LATER):
        store.append(event)

    remaining = {e.session_id for e in store.read_all()}
    assert remaining == {kept.session_id}


def test_calendar_stops_counting_a_retracted_day(tmp_path):
    store = _store(tmp_path)
    session = _backfilled(store, datetime(2026, 8, 4).date())
    day = datetime(2026, 8, 4).date()
    assert summarize_by_day(store.read_all())[day].total_work_seconds == 6000

    for event in build_retraction_events(
        session.session_id, session.days, habit="study", now=LATER
    ):
        store.append(event)

    assert day not in summarize_by_day(store.read_all())


def test_session_spanning_the_rollover_is_retracted_in_both_files(tmp_path):
    store = _store(tmp_path, rollover_hour=3)
    # Starts at 23:00 and runs past 03:00, so its events straddle two habit-days.
    session = _backfilled(store, datetime(2026, 8, 4).date(), hour=23, rounds=5)
    assert len(session.days) == 2

    events = build_retraction_events(session.session_id, session.days, habit="study", now=LATER)
    assert len(events) == 2
    for event in events:
        store.append(event)

    # Neither day file is left asserting time the log as a whole no longer claims.
    for day in session.days:
        text = (tmp_path / "study" / f"{day:%Y}" / f"{day:%m}" / f"{day:%Y-%m-%d}.jsonl").read_text(
            encoding="utf-8"
        )
        assert "session_retracted" in text
    assert store.read_all() == []


def test_drop_retracted_ignores_stream_order():
    """The retraction can precede its target, since it files under the earlier day."""
    sid = uuid4()
    retraction = SessionRetracted(
        timestamp=LATER.astimezone(UTC),
        tz_offset_minutes=120,
        habit="study",
        session_id=sid,
        target_date=datetime(2026, 8, 4).date(),
    )
    started = SessionStarted(
        timestamp=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        tz_offset_minutes=120,
        habit="study",
        session_id=sid,
        work_minutes=25,
        break_minutes=5,
        planned_rounds=4,
    )
    assert drop_retracted([retraction, started]) == []


def test_retraction_needs_a_target_day():
    with pytest.raises(ValueError, match="at least one target day"):
        build_retraction_events(uuid4(), [], habit="study", now=LATER)


def test_retraction_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_retraction_events(
            uuid4(), [datetime(2026, 8, 4).date()], habit="study", now=datetime(2026, 8, 7, 14, 0)
        )


def test_summarize_sessions_marks_the_retracted_one(tmp_path):
    store = _store(tmp_path)
    session = _backfilled(store, datetime(2026, 8, 4).date())
    for event in build_retraction_events(
        session.session_id, session.days, habit="study", now=LATER
    ):
        store.append(event)

    sessions = summarize_sessions(store.read_all(include_retracted=True))
    assert [s.retracted for s in sessions] == [True]
    assert sessions[0].work_seconds == 6000  # what it claimed, still readable


def test_rounds_survive_a_retraction_of_a_different_session(tmp_path):
    """A retraction keyed on one session must not touch rows that merely share a day."""
    store = _store(tmp_path)
    day = datetime(2026, 8, 4).date()
    morning = _backfilled(store, day, hour=6)
    evening = _backfilled(store, day, hour=18)

    for event in build_retraction_events(
        morning.session_id, morning.days, habit="study", now=LATER
    ):
        store.append(event)

    remaining = store.read_all()
    assert {e.session_id for e in remaining} == {evening.session_id}
    assert sum(e.work_seconds for e in remaining if isinstance(e, RoundEnded)) == 6000
