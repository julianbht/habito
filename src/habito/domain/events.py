"""Immutable domain events — the append-only log is a sequence of these.

Every event is timestamped in UTC and carries the local ``tz_offset_minutes`` so the
exact wall-clock time can be reconstructed unambiguously. ``origin`` distinguishes
live (committed-in-the-moment, evidentially strong) events from backfilled ones, and
``habit`` says which habit the event is evidence of.

A mistake is corrected by appending :class:`SessionRetracted`, so the record shows both
what was claimed and that it was withdrawn.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, TypeAdapter

HABIT_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
"""A habit name becomes a directory, so it must be a safe path segment. Lowercase because
Windows filesystems are case-insensitive: ``Study`` and ``study`` would be one directory."""


class Origin(StrEnum):
    live = "live"
    backfilled = "backfilled"


class BaseEvent(BaseModel):
    model_config = {"frozen": True}

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime  # timezone-aware, UTC
    tz_offset_minutes: int  # local wall-clock offset from UTC, in minutes
    # No default: `Origin.live` as one would make an omission indistinguishable from a
    # claim, and a backfilled event that forgot to say so would pass itself off as live.
    origin: Origin
    # Required, never defaulted — see CLAUDE.md § Habits.
    habit: str = Field(pattern=HABIT_PATTERN)
    session_id: UUID


class SessionStarted(BaseEvent):
    type: Literal["session_started"] = "session_started"
    work_minutes: float  # fractional so a round can be shorter than a minute
    break_minutes: int
    planned_rounds: int
    # Set only when this session continues one closed mid-round rather than starting
    # fresh at round 1 (see habito.projections.resume) — the interrupted session's id, so
    # the log itself shows the link instead of a round sequence that looks like a gap.
    resumed_from: UUID | None = None


class RoundStarted(BaseEvent):
    type: Literal["round_started"] = "round_started"
    round_index: int


class RoundEnded(BaseEvent):
    type: Literal["round_ended"] = "round_ended"
    round_index: int
    work_seconds: int


class BreakStarted(BaseEvent):
    type: Literal["break_started"] = "break_started"
    round_index: int


class BreakEnded(BaseEvent):
    type: Literal["break_ended"] = "break_ended"
    round_index: int
    break_seconds: int


class SessionPaused(BaseEvent):
    type: Literal["session_paused"] = "session_paused"


class SessionResumed(BaseEvent):
    type: Literal["session_resumed"] = "session_resumed"


class TimeAdjusted(BaseEvent):
    """Records a manual +N-minute adjustment to the current phase, transparently."""

    type: Literal["time_adjusted"] = "time_adjusted"
    round_index: int
    delta_seconds: int


class SessionEnded(BaseEvent):
    type: Literal["session_ended"] = "session_ended"
    total_work_seconds: int


class SessionRetracted(BaseEvent):
    """Voids an earlier session, by appending rather than editing.

    The target is the inherited ``session_id``: one retraction voids that whole session,
    live or backfilled, and every event carrying the id stops counting.

    ``target_date`` is the habit-day the voided events were filed under, copied in at write
    time. It files this event beside what it corrects (see :func:`partition_date`), and
    being stored rather than derived keeps it there across a ``rollover_hour`` change. A
    session spanning the rollover takes one retraction per day it touched.

    To reinstate a retracted session, backfill it again.
    """

    type: Literal["session_retracted"] = "session_retracted"
    target_date: date
    reason: str = ""


class SessionTagged(BaseEvent):
    """A free-form label put on a session after the fact — the ☰ prompt on session end.

    Its own event rather than a field on ``SessionStarted``: the tag is only known once
    the session is over, and ``SessionStarted`` is long since written and committed by
    then — nothing is ever rewritten to add it. Optional and rare by design: skipping the
    prompt (the common case) means no event at all, not an empty tag. Filed under today
    like anything else — ``target_date`` doesn't apply, since this describes the session
    rather than correcting an earlier day.
    """

    type: Literal["session_tagged"] = "session_tagged"
    tag: str


Event = Annotated[
    SessionStarted
    | RoundStarted
    | RoundEnded
    | BreakStarted
    | BreakEnded
    | SessionPaused
    | SessionResumed
    | TimeAdjusted
    | SessionEnded
    | SessionRetracted
    | SessionTagged,
    Field(discriminator="type"),
]
"""Discriminated union over the ``type`` field — validates each line into its subtype."""

EventAdapter: TypeAdapter[Event] = TypeAdapter(Event)


def new_session_id() -> UUID:
    return uuid4()


def local_datetime(event: Event) -> datetime:
    """The wall clock the event happened on, per the offset recorded *with* the event.

    Read off the event rather than from config, so changing the timezone setting never
    retroactively moves history.
    """
    return event.timestamp + timedelta(minutes=event.tz_offset_minutes)


def logical_day(local: datetime, rollover_hour: int = 0) -> date:
    """Which habit-day a local wall-clock time falls in.

    Days roll over at ``rollover_hour`` rather than midnight, so time spent past 12am
    counts toward the day you'd say you studied on instead of splitting in two. ``0`` is
    plain calendar midnight.
    """
    return (local - timedelta(hours=rollover_hour)).date()


def logical_date(event: Event, rollover_hour: int = 0) -> date:
    """Which habit-day an event belongs to.

    A pure function of the event alone — no session lookup, no clock — which is what lets
    the store use it to pick a file without keeping any state of its own.
    """
    return logical_day(local_datetime(event), rollover_hour)


def partition_date(event: Event, rollover_hour: int = 0) -> date:
    """Which habit-day an event is *filed under* — its day file, and the day it reads in.

    For anything that happened, that is the day it happened on. A retraction is a statement
    about another day, so it files under ``target_date``: the day it corrects. Opening that
    day then shows the correction alongside what it corrects.

    Still a pure function of the event, reading ``target_date`` off it as the rest reads
    ``habit``. The store, the calendar and the log all go through here, so a file holds
    exactly the events those views attribute to its day.
    """
    if isinstance(event, SessionRetracted):
        return event.target_date
    return logical_date(event, rollover_hour)


def retracted_session_ids(events: Iterable[Event]) -> set[UUID]:
    """The sessions voided by a retraction somewhere in ``events``."""
    return {e.session_id for e in events if isinstance(e, SessionRetracted)}


def drop_retracted(events: Iterable[Event]) -> list[Event]:
    """``events`` with every retracted session removed, retraction lines included.

    Collects the set in a first pass so the result holds whatever the stream order is: a
    retraction files under the target's day, so retracting a session that spanned a
    rollover puts the line in the earlier day's file, ahead of events it voids in the later.
    """
    entries = list(events)
    retracted = retracted_session_ids(entries)
    if not retracted:
        return entries
    return [e for e in entries if e.session_id not in retracted]
