"""Projections: fold the event log into per-day summaries.

Current state is always derived from events (event sourcing), never stored separately.
Verified (live) and backfilled study time are reported separately so retroactively-added
sessions never masquerade as in-the-moment evidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from habito.domain.events import Event, Origin, RoundEnded, SessionStarted


def local_date(event: Event) -> date:
    """The wall-clock date on which the event occurred, per its recorded tz offset."""
    return (event.timestamp + timedelta(minutes=event.tz_offset_minutes)).date()


@dataclass
class DailySummary:
    day: date
    verified_work_seconds: int = 0
    backfilled_work_seconds: int = 0
    sessions: int = 0
    session_ids: set = field(default_factory=set)

    @property
    def total_work_seconds(self) -> int:
        return self.verified_work_seconds + self.backfilled_work_seconds


def summarize_by_day(events: Iterable[Event]) -> dict[date, DailySummary]:
    summaries: dict[date, DailySummary] = {}

    def bucket(day: date) -> DailySummary:
        if day not in summaries:
            summaries[day] = DailySummary(day=day)
        return summaries[day]

    for event in events:
        day = local_date(event)
        if isinstance(event, RoundEnded):
            s = bucket(day)
            if event.origin is Origin.backfilled:
                s.backfilled_work_seconds += event.work_seconds
            else:
                s.verified_work_seconds += event.work_seconds
        elif isinstance(event, SessionStarted):
            s = bucket(day)
            if event.session_id not in s.session_ids:
                s.session_ids.add(event.session_id)
                s.sessions += 1

    return summaries


def summary_for(events: Iterable[Event], day: date) -> DailySummary:
    """Convenience: the summary for a single day (empty if none)."""
    return summarize_by_day(events).get(day, DailySummary(day=day))
