from __future__ import annotations

from datetime import UTC, date, datetime

from habito.backfill import build_backfill_events
from habito.domain.events import (
    BreakStarted,
    Origin,
    RoundEnded,
    SessionEnded,
    SessionStarted,
)
from habito.projections.daily import summarize_by_day, summary_for


def _start(hour=6):
    # 06:00 at UTC+2 local
    tz = UTC
    naive = datetime(2026, 8, 4, hour, 0)
    return naive.replace(tzinfo=tz)


def test_backfill_builds_expected_sequence():
    events = build_backfill_events(
        _start(), work_minutes=25, break_minutes=5, rounds=4, habit="study"
    )
    assert isinstance(events[0], SessionStarted)
    assert isinstance(events[-1], SessionEnded)
    assert all(e.origin is Origin.backfilled for e in events)
    # 4 rounds -> 3 breaks (no trailing break)
    assert sum(isinstance(e, BreakStarted) for e in events) == 3
    assert events[-1].total_work_seconds == 4 * 25 * 60


def test_every_backfilled_event_carries_one_id_and_a_backfilled_origin():
    """Each construction names the stamp itself, so nothing structural keeps them agreeing.

    ``origin`` matters most here: a backfilled event that claimed to be live would be
    counted as verified evidence, which is the one thing backfill must never produce.
    """
    events = build_backfill_events(_start(), 25, 5, 3, habit="study")

    assert len({e.session_id for e in events}) == 1
    assert all(e.origin is Origin.backfilled for e in events)
    assert all(e.habit == "study" for e in events)


def test_backfill_timestamps_advance_monotonically():
    events = build_backfill_events(_start(), 25, 5, 2, habit="study")
    stamps = [e.timestamp for e in events]
    assert stamps == sorted(stamps)


def test_backfill_marked_backfilled_in_projection():
    events = build_backfill_events(_start(), 25, 5, 4, habit="study")
    summary = summary_for(events, date(2026, 8, 4))
    assert summary.backfilled_work_seconds == 4 * 25 * 60
    assert summary.verified_work_seconds == 0
    assert summary.total_work_seconds == 4 * 25 * 60
    assert summary.sessions == 1


def test_projection_splits_verified_and_backfilled():
    day = date(2026, 8, 4)
    verified = RoundEnded(
        timestamp=datetime(2026, 8, 4, 4, 25, tzinfo=UTC),
        tz_offset_minutes=120,
        habit="study",
        session_id=__import__("uuid").uuid4(),
        round_index=1,
        work_seconds=1500,
        origin=Origin.live,
    )
    backfilled = build_backfill_events(_start(), 25, 5, 1, habit="study")
    summary = summary_for([verified, *backfilled], day)
    assert summary.verified_work_seconds == 1500
    assert summary.backfilled_work_seconds == 1500
    assert summary.total_work_seconds == 3000


def test_local_date_uses_offset():
    # 23:30 UTC on Aug 4 at +2h local -> local date Aug 5
    ev = SessionStarted(
        timestamp=datetime(2026, 8, 4, 23, 30, tzinfo=UTC),
        tz_offset_minutes=120,
        origin=Origin.live,
        habit="study",
        session_id=__import__("uuid").uuid4(),
        work_minutes=25,
        break_minutes=5,
        planned_rounds=4,
    )
    summaries = summarize_by_day([ev])
    assert date(2026, 8, 5) in summaries
