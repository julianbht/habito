"""Synthesize the event sequence for a session that happened away from the app.

Backfilled events carry real historical timestamps and ``origin=backfilled`` so they are
honestly distinguishable from live evidence. The caller appends them to the store, which
commits+pushes each one (tagged ``[backfilled]`` in the commit message).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from habito.domain.events import (
    BreakEnded,
    BreakStarted,
    Event,
    Origin,
    RoundEnded,
    RoundStarted,
    SessionEnded,
    SessionStarted,
    new_session_id,
)


def build_backfill_events(
    start: datetime,
    work_minutes: int,
    break_minutes: int,
    rounds: int,
    *,
    habit: str,
) -> list[Event]:
    """Walk forward from ``start`` (a timezone-aware local datetime) building events.

    Mirrors the live flow: work → break → work … with no trailing break after the
    final round.
    """
    if start.tzinfo is None:
        raise ValueError("start must be timezone-aware")
    if rounds <= 0 or work_minutes <= 0 or break_minutes <= 0:
        raise ValueError("rounds, work_minutes and break_minutes must be positive")

    offset = start.utcoffset() or timedelta(0)
    tz_offset_minutes = int(offset.total_seconds() // 60)
    session_id = new_session_id()
    events: list[Event] = []
    cursor = start

    def emit(cls, **fields) -> None:
        events.append(
            cls(
                timestamp=cursor.astimezone(UTC),
                tz_offset_minutes=tz_offset_minutes,
                origin=Origin.backfilled,
                habit=habit,
                session_id=session_id,
                **fields,
            )
        )

    emit(
        SessionStarted,
        work_minutes=work_minutes,
        break_minutes=break_minutes,
        planned_rounds=rounds,
    )

    total_work = 0
    for r in range(1, rounds + 1):
        emit(RoundStarted, round_index=r)
        cursor = cursor + timedelta(minutes=work_minutes)
        emit(RoundEnded, round_index=r, work_seconds=work_minutes * 60)
        total_work += work_minutes * 60
        if r < rounds:
            emit(BreakStarted, round_index=r)
            cursor = cursor + timedelta(minutes=break_minutes)
            emit(BreakEnded, round_index=r, break_seconds=break_minutes * 60)

    emit(SessionEnded, total_work_seconds=total_work)
    return events
