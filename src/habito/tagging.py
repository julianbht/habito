"""Synthesize the events that create and describe a tag.

One event per save, stamped with the moment it was written. The caller appends it to the
store, which commits+pushes it like everything else.
"""

from __future__ import annotations

from datetime import datetime as _datetime

from habito.domain.events import Origin, TagCreated, TagDescribed, new_session_id, stamp


def build_tag_created_event(tag: str, *, habit: str, now: _datetime) -> TagCreated:
    """Mark that ``tag`` exists, as of ``now``, a timezone-aware local datetime."""
    timestamp, tz_offset_minutes = stamp(now)
    return TagCreated(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
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
    timestamp, tz_offset_minutes = stamp(now)
    return TagDescribed(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        session_id=new_session_id(),
        tag=tag,
        description=description,
    )
