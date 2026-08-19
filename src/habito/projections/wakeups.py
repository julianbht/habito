"""Projection: the wake-ups that still stand, newest first.

What `ManageWakeUpsDialog` lists. Fed the standing stream (``read_all()``), so a voided
entry is already gone by the time it gets here — unlike sessions, there is no
"retracted, shown struck through" row to render.
"""

from __future__ import annotations

from collections.abc import Iterable

from habito.domain.events import Event, WakeUpLogged


def wakeup_entries(events: Iterable[Event], habit: str) -> list[WakeUpLogged]:
    """Every standing wake-up for this habit, most recent first."""
    entries = [e for e in events if isinstance(e, WakeUpLogged) and e.habit == habit]
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries
