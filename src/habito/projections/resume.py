"""Projection: is the most recent session for a habit resumable?

Only ever reads what's already in the log. Closing the window mid-round now finalises
the phase in flight honestly (see ``HabitoApp.closeEvent``) — a partial ``RoundEnded`` or
``BreakEnded`` carries the exact elapsed seconds, so there's nothing to estimate. A crash
never reaches ``closeEvent`` at all, so it leaves no such marker and is correctly not
resumable here: "it is what it is" for that case, by design.

Retracting the interrupted session is how you decline resume for good — ``read_all()``
already drops retracted sessions, so a retracted one simply won't be found here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from habito.domain.events import (
    BreakEnded,
    BreakStarted,
    Event,
    Origin,
    RoundEnded,
    RoundStarted,
    SessionEnded,
    SessionStarted,
    TimeAdjusted,
)


class ResumePhase(StrEnum):
    """Which kind of phase to resume into. Kept separate from ``engine.pomodoro.State``
    so this module doesn't have to import the engine — they're sibling packages."""

    work = "work"
    break_ = "break"


@dataclass(frozen=True)
class ResumableSession:
    session_id: UUID  # the interrupted session, for reference only — resuming starts a new one
    round_index: int
    planned_rounds: int
    phase: ResumePhase
    remaining_seconds: int
    interrupted_at: datetime  # the cut-short session's SessionEnded timestamp


def _with_adjustments(
    own: list[Event], round_index: int, start: Event, end: Event, base_seconds: int
) -> int:
    """``base_seconds`` plus every ``TimeAdjusted`` delta emitted for this phase — between
    its own ``start`` and ``end`` events — so a phase that finished exactly on a
    deliberately nudged (e.g. Ctrl+down) target doesn't read as cut short against the
    original, unadjusted length ``SessionStarted`` still carries.
    """
    delta = sum(
        e.delta_seconds
        for e in own
        if isinstance(e, TimeAdjusted)
        and e.round_index == round_index
        and start.timestamp <= e.timestamp <= end.timestamp
    )
    return base_seconds + delta


def find_resumable(events: list[Event], habit: str, current_rounds: int) -> ResumableSession | None:
    """The habit's most recent session, if it was cut short before finishing.

    ``None`` when there's no session, the latest one ran to completion, it wasn't a live
    session (a backfilled entry is never "interrupted"), or ``current_rounds`` — the
    *live* ``rounds`` setting, which may have changed since — no longer has room for the
    round it was interrupted on. That last case declines rather than resuming into a
    round_index the current settings can't describe (say, rounds lowered from 4 to 2 after
    an interruption mid-round-3): silence here, not a session that contradicts itself.
    """
    started = [
        e
        for e in events
        if isinstance(e, SessionStarted) and e.habit == habit and e.origin is Origin.live
    ]
    if not started:
        return None
    last_started = max(started, key=lambda e: e.timestamp)
    session_id = last_started.session_id

    own = sorted((e for e in events if e.session_id == session_id), key=lambda e: e.timestamp)
    if not any(isinstance(e, SessionEnded) for e in own):
        # No graceful close ever finalised this one — a crash, or it's still running
        # right now. Neither case has a trustworthy stopping point to resume from.
        return None
    phase_events = [e for e in own if isinstance(e, (RoundEnded, BreakEnded))]
    if not phase_events:
        return None  # ended before any phase completed — nothing to pick back up

    work_target = round(last_started.work_minutes * 60)
    break_target = last_started.break_minutes * 60
    planned_rounds = last_started.planned_rounds
    last = phase_events[-1]
    interrupted_at = own[-1].timestamp

    if isinstance(last, RoundEnded):
        round_start = next(
            e for e in own if isinstance(e, RoundStarted) and e.round_index == last.round_index
        )
        adjusted_work_target = _with_adjustments(
            own, last.round_index, round_start, last, work_target
        )
        if last.work_seconds < adjusted_work_target:
            round_index = last.round_index
            phase = ResumePhase.work
            remaining_seconds = adjusted_work_target - last.work_seconds
        elif last.round_index >= planned_rounds:
            return None  # the final round ran its full length — nothing left to resume
        else:
            round_index = last.round_index
            phase = ResumePhase.break_
            remaining_seconds = break_target
    else:  # last is a BreakEnded
        break_start = next(
            e for e in own if isinstance(e, BreakStarted) and e.round_index == last.round_index
        )
        adjusted_break_target = _with_adjustments(
            own, last.round_index, break_start, last, break_target
        )
        if last.break_seconds < adjusted_break_target:
            round_index = last.round_index
            phase = ResumePhase.break_
            remaining_seconds = adjusted_break_target - last.break_seconds
        else:
            round_index = last.round_index + 1
            phase = ResumePhase.work
            remaining_seconds = work_target

    if round_index > current_rounds:
        return None

    return ResumableSession(
        session_id, round_index, planned_rounds, phase, remaining_seconds, interrupted_at
    )
