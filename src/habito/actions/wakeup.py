"""Build the event for a wake-up logged after the fact, away from the moment it happened.

Mirrors ``actions/backfill.py``: the caller hands in real historical local instants, this
module turns them into an honestly-labelled event via ``stamp()``, and the caller appends
it to the store (then commits+pushed, tagged ``[backfilled]``).
"""

from __future__ import annotations

from datetime import UTC, datetime

from habito.domain.events import Origin, WakeUpLogged, stamp


def build_wakeup_event(wake: datetime, bedtime: datetime, *, habit: str) -> WakeUpLogged:
    """``wake`` and ``bedtime`` are timezone-aware local instants; ``wake`` is what
    ``stamp()`` derives ``timestamp``/``tz_offset_minutes`` from, ``bedtime`` is stored
    alongside as its own UTC instant.
    """
    if bedtime >= wake:
        raise ValueError("bedtime must be before the wake time")
    timestamp, tz_offset_minutes = stamp(wake)
    return WakeUpLogged(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.backfilled,
        habit=habit,
        bedtime=bedtime.astimezone(UTC),
    )
