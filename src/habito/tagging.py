"""Synthesize the event that describes a tag.

One ``TagDescribed`` per save, stamped with the moment it was written. The caller appends
it to the store, which commits+pushes it like everything else.
"""

from __future__ import annotations

from datetime import UTC, timedelta
from datetime import datetime as _datetime

from habito.domain.events import Origin, TagDescribed, new_session_id


def build_tag_described_event(
    tag: str,
    description: str,
    *,
    habit: str,
    now: _datetime,
) -> TagDescribed:
    """Describe (or redescribe) ``tag`` as of ``now``, a timezone-aware local datetime."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    offset = now.utcoffset() or timedelta(0)
    return TagDescribed(
        timestamp=now.astimezone(UTC),
        tz_offset_minutes=int(offset.total_seconds() // 60),
        origin=Origin.live,
        habit=habit,
        session_id=new_session_id(),
        tag=tag,
        description=description,
    )
