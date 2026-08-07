"""Projection: fold the event log into one row per session.

What the retract dialog picks from, and the level a correction is made at — a mistake is
made in whole sessions, so this is the unit the UI offers.

Fed the raw stream (``read_all(include_retracted=True)``), so an already-retracted session
still appears and is marked as such.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from uuid import UUID

from habito.domain.events import (
    Event,
    Origin,
    RoundEnded,
    SessionRetracted,
    local_datetime,
    partition_date,
    retracted_session_ids,
)


@dataclass(frozen=True)
class SessionSummary:
    session_id: UUID
    started: datetime  # local wall clock, off the event's own recorded offset
    work_seconds: int
    origin: Origin
    days: tuple[date, ...]
    """Every habit-day the session's events fall on, earliest first — more than one when it
    ran past the rollover. A retraction is written per day, so this is what drives that."""
    retracted: bool

    @property
    def day(self) -> date:
        """The day the session started, which is the one it reads as."""
        return self.days[0]


def summarize_sessions(events: Iterable[Event], rollover_hour: int = 0) -> list[SessionSummary]:
    """One row per session, newest first."""
    entries = list(events)
    retracted = retracted_session_ids(entries)

    starts: dict[UUID, datetime] = {}
    seconds: dict[UUID, int] = {}
    origins: dict[UUID, Origin] = {}
    days: dict[UUID, set[date]] = {}

    for event in entries:
        if isinstance(event, SessionRetracted):
            continue
        sid = event.session_id
        local = local_datetime(event)
        if sid not in starts or local < starts[sid]:
            starts[sid] = local
            origins[sid] = event.origin
        seconds.setdefault(sid, 0)
        days.setdefault(sid, set()).add(partition_date(event, rollover_hour))
        if isinstance(event, RoundEnded):
            seconds[sid] += event.work_seconds

    summaries = [
        SessionSummary(
            session_id=sid,
            started=starts[sid],
            work_seconds=seconds[sid],
            origin=origins[sid],
            days=tuple(sorted(days[sid])),
            retracted=sid in retracted,
        )
        for sid in starts
    ]
    summaries.sort(key=lambda s: s.started, reverse=True)
    return summaries
