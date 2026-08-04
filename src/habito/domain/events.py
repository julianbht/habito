"""Immutable domain events — the append-only log is a sequence of these.

Every event is timestamped in UTC and carries the local ``tz_offset_minutes`` so the
exact wall-clock time can be reconstructed unambiguously. ``origin`` distinguishes
live (committed-in-the-moment, evidentially strong) events from backfilled ones.
"""

from __future__ import annotations

from datetime import datetime
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
    work_minutes: int
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
