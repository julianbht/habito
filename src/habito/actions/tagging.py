"""Synthesize the events that create and describe a tag.

One event per save, stamped with the moment it was written. The caller appends it to the
store, which commits+pushes it like everything else.
"""

from __future__ import annotations

from datetime import datetime as _datetime
from uuid import UUID

from habito.domain.events import (
    Origin,
    SessionTagged,
    SessionUntagged,
    TagCreated,
    TagDescribed,
    stamp,
)


def build_tag_created_event(tag: str, *, habit: str, now: _datetime) -> TagCreated:
    """Mark that ``tag`` exists, as of ``now``, a timezone-aware local datetime."""
    timestamp, tz_offset_minutes = stamp(now)
    return TagCreated(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        tag=tag,
    )


def build_session_tagged_event(
    session_id: UUID, tag: str, *, habit: str, now: _datetime
) -> SessionTagged:
    """Attach ``tag`` to ``session_id`` retroactively, as of ``now``.

    The session-end prompt builds its own ``SessionTagged`` inline (it already has the
    live clock's ``timestamp``/``tz_offset_minutes`` in hand, with no local instant to
    convert) — this is for tagging after the fact, from a dialog that only has a local
    ``now`` to stamp, the same shape as `build_retraction_events`.
    """
    timestamp, tz_offset_minutes = stamp(now)
    return SessionTagged(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        session_id=session_id,
        tag=tag,
    )


def build_session_untagged_event(
    session_id: UUID, tag: str, *, habit: str, now: _datetime
) -> SessionUntagged:
    """Remove ``tag`` from ``session_id``, as of ``now`` — the mirror of
    `build_session_tagged_event`."""
    timestamp, tz_offset_minutes = stamp(now)
    return SessionUntagged(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        session_id=session_id,
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
        tag=tag,
        description=description,
    )
