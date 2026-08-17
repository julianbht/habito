"""summarize_sessions: one row per real session, and nothing else.

Regression coverage for the bug this module's SessionEvent narrowing fixed: an event with
no session_id at all — TagCreated, TagDescribed, WakeUpLogged — used to fold into its own
bogus zero-length "session" here, so creating a tag while tagging a session could turn one
real session into three rows in "Manage sessions…".
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from habito.domain.events import (
    Origin,
    RoundEnded,
    SessionStarted,
    TagCreated,
    TagDescribed,
    WakeUpLogged,
)
from habito.projections.sessions import summarize_sessions

WHEN = datetime(2026, 8, 17, 9, 0, tzinfo=UTC)
SESSION = uuid4()


def _session_started() -> SessionStarted:
    return SessionStarted(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit="study",
        session_id=SESSION,
        work_minutes=25,
        break_minutes=5,
        planned_rounds=1,
    )


def _round_ended() -> RoundEnded:
    return RoundEnded(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit="study",
        session_id=SESSION,
        round_index=1,
        work_seconds=1500,
    )


def test_a_lone_session_is_one_row():
    summaries = summarize_sessions([_session_started(), _round_ended()])
    assert len(summaries) == 1
    assert summaries[0].session_id == SESSION


def test_creating_and_describing_a_tag_does_not_add_bogus_sessions():
    """Neither TagCreated nor TagDescribed has a session_id at all — they can never fold
    into their own row here, however many of them sit alongside a real session."""
    events = [
        _session_started(),
        _round_ended(),
        TagCreated(
            timestamp=WHEN, tz_offset_minutes=0, origin=Origin.live, habit="study", tag="new tag"
        ),
        TagDescribed(
            timestamp=WHEN,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit="study",
            tag="new tag",
            description="what it means",
        ),
    ]

    summaries = summarize_sessions(events)

    assert len(summaries) == 1
    assert summaries[0].session_id == SESSION
    assert summaries[0].work_seconds == 1500


def test_a_wakeup_log_does_not_add_a_bogus_session():
    """Same shape as TagCreated/TagDescribed — no session_id, so it never surfaces here,
    even though ManageSessionsDialog never actually feeds it one of these in practice."""
    wakeup = WakeUpLogged(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.backfilled,
        habit="sleep",
        bedtime=WHEN,
    )

    summaries = summarize_sessions([_session_started(), _round_ended(), wakeup])

    assert len(summaries) == 1
