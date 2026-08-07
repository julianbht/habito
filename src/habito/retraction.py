"""Synthesize the events that void an earlier session.

One :class:`SessionRetracted` per habit-day the session's events landed on, each stamped
with the moment the correction was made and filed under the day it corrects. The caller
appends them to the store, which commits+pushes each one.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, timedelta
from datetime import datetime as _datetime
from uuid import UUID

from habito.domain.events import Origin, SessionRetracted


def build_retraction_events(
    session_id: UUID,
    days: Iterable[date],
    *,
    habit: str,
    now: _datetime,
    reason: str = "",
) -> list[SessionRetracted]:
    """Void ``session_id`` across every day in ``days``.

    ``now`` is a timezone-aware local datetime — when the correction is being made, which
    is what the retraction records as its own timestamp.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    targets = sorted(set(days))
    if not targets:
        raise ValueError("a retraction needs at least one target day")

    offset = now.utcoffset() or timedelta(0)
    return [
        SessionRetracted(
            timestamp=now.astimezone(UTC),
            tz_offset_minutes=int(offset.total_seconds() // 60),
            origin=Origin.live,
            habit=habit,
            session_id=session_id,
            target_date=day,
            reason=reason.strip(),
        )
        for day in targets
    ]
