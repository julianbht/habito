"""Projections: fold the event log into per-day summaries.

Current state is always derived from events (event sourcing), never stored separately.
Verified (live) and backfilled study time are reported separately so retroactively-added
sessions never masquerade as in-the-moment evidence.

Fed the store's default stream, which has already dropped retracted sessions.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta

from habito.domain.events import Event, Origin, RoundEnded, SessionStarted, partition_date


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


def summarize_by_day(events: Iterable[Event], rollover_hour: int = 0) -> dict[date, DailySummary]:
    """Fold events into per-day totals.

    ``rollover_hour`` decides where a day ends — the app passes the configured value so a
    session running past midnight counts toward the evening it started. The default of 0
    is plain calendar midnight, for callers that have no opinion.
    """
    summaries: dict[date, DailySummary] = {}

    def bucket(day: date) -> DailySummary:
        if day not in summaries:
            summaries[day] = DailySummary(day=day)
        return summaries[day]

    for event in events:
        day = partition_date(event, rollover_hour)
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


def longest_run(days: Iterable[date]) -> int:
    """The longest stretch of consecutive dates in ``days`` (0 when there are none).

    Kept here rather than in the view because it's a fold over days like everything else in
    this module, and it's worth testing without standing up Qt.
    """
    ordered = sorted(set(days))
    if not ordered:
        return 0
    best = run = 1
    for previous, day in zip(ordered, ordered[1:], strict=False):
        run = run + 1 if day - previous == timedelta(days=1) else 1
        best = max(best, run)
    return best


def summary_for(events: Iterable[Event], day: date, rollover_hour: int = 0) -> DailySummary:
    """Convenience: the summary for a single day (empty if none)."""
    return summarize_by_day(events, rollover_hour).get(day, DailySummary(day=day))
