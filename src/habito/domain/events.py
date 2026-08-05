"""Immutable domain events — the append-only log is a sequence of these.

Every event is timestamped in UTC and carries the local ``tz_offset_minutes`` so the
exact wall-clock time can be reconstructed unambiguously. ``origin`` distinguishes
live (committed-in-the-moment, evidentially strong) events from backfilled ones.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, TypeAdapter


class Origin(StrEnum):
    live = "live"
    backfilled = "backfilled"


class BaseEvent(BaseModel):
    model_config = {"frozen": True}

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime  # timezone-aware, UTC
    tz_offset_minutes: int  # local wall-clock offset from UTC, in minutes
    origin: Origin = Origin.live
    session_id: UUID


class SessionStarted(BaseEvent):
    type: Literal["session_started"] = "session_started"
    work_minutes: float  # fractional so a round can be shorter than a minute
    break_minutes: int
    planned_rounds: int


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


Event = Annotated[
    SessionStarted
    | RoundStarted
    | RoundEnded
    | BreakStarted
    | BreakEnded
    | SessionPaused
    | SessionResumed
    | TimeAdjusted
    | SessionEnded,
    Field(discriminator="type"),
]
"""Discriminated union over the ``type`` field — validates each line into its subtype."""

EventAdapter: TypeAdapter = TypeAdapter(Event)


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
