"""Synthesize the events that create and describe a tag.

One event per save, stamped with the moment it was written. The caller appends it to the
store, which commits+pushes it like everything else.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from datetime import datetime as _datetime

from habito.domain.events import Origin, TagCreated, TagDescribed, new_session_id


def _offset_minutes(now: _datetime) -> int:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    return int((now.utcoffset() or timedelta(0)).total_seconds() // 60)


def build_tag_created_event(tag: str, *, habit: str, now: _datetime) -> TagCreated:
    """Mark that ``tag`` exists, as of ``now``, a timezone-aware local datetime."""
    return TagCreated(
        timestamp=now.astimezone(UTC),
        tz_offset_minutes=_offset_minutes(now),
        origin=Origin.live,
        habit=habit,
        session_id=new_session_id(),
        tag=tag,
    )


def build_tag_described_event(
    tag: str,
    description: str,
    *,
    habit: str,
    now: _datetime,
) -> TagDescribed:
    """Describe (or redescribe) ``tag`` as of ``now``, a timezone-aware local datetime."""
    return TagDescribed(
        timestamp=now.astimezone(UTC),
        tz_offset_minutes=_offset_minutes(now),
        origin=Origin.live,
        habit=habit,
        session_id=new_session_id(),
        tag=tag,
        description=description,
    )
