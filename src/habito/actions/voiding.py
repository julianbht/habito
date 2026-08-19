"""Synthesize the event that voids one standalone log entry.

The counterpart to ``actions/retraction.py``, which voids a whole Pomodoro session by
``session_id``. This one targets a single event by its ``event_id`` — a wake-up or a
workout log — and files under the day that event was filed on.

Correcting an entry is this event plus a fresh one for the replacement, submitted together
so both land in the same batch; the caller appends whatever it gets to the store, which
commits+pushes each one.
"""

from __future__ import annotations

from datetime import datetime as _datetime

from habito.domain.events import (
    Event,
    EventVoided,
    Origin,
    SessionEvent,
    partition_date,
    stamp,
)


def build_void_event(
    target: Event,
    *,
    rollover_hour: int,
    now: _datetime,
    reason: str = "",
) -> EventVoided:
    """Void ``target``, as of ``now``, a timezone-aware local datetime.

    Takes the event itself rather than its id so ``habit`` and ``target_date`` are read off
    what's being voided instead of recomputed by each caller — a void written under the
    wrong habit lands in a store that never reads it, and one under the wrong day files
    away from what it corrects.
    """
    if isinstance(target, SessionEvent):
        raise ValueError("a session is retracted by session id, not voided event by event")
    if isinstance(target, EventVoided):
        raise ValueError("a void cannot itself be voided")
    timestamp, tz_offset_minutes = stamp(now)
    return EventVoided(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=target.habit,
        target_event_id=target.event_id,
        target_date=partition_date(target, rollover_hour),
        reason=reason.strip(),
    )
