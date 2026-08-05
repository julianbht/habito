"""The Pomodoro engine — a state machine that emits domain events on transitions.

UI-agnostic: it accepts commands (start/pause/resume/skip/add_time/stop) and is
driven forward by :meth:`tick` (called ~1/second). Elapsed time is derived from the
injected :class:`Clock`'s monotonic reading, so display jitter never corrupts totals.
Every transition emits an :mod:`habito.domain.events` event through the injected sink.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from habito.config.models import PomodoroConfig
from habito.domain.events import (
    BreakEnded,
    BreakStarted,
    Event,
    Origin,
    RoundEnded,
    RoundStarted,
    SessionEnded,
    SessionPaused,
    SessionResumed,
    SessionStarted,
    TimeAdjusted,
    new_session_id,
)
from habito.engine.clock import Clock, SystemClock

EventSink = Callable[[Event], None]


class State(StrEnum):
    idle = "idle"
    work = "work"
    break_ = "break"
    paused = "paused"
    awaiting = "awaiting"  # a phase finished; the next one starts when you acknowledge it
    done = "done"


@dataclass(frozen=True)
class EngineState:
    """Immutable snapshot the UI renders each tick."""

    state: State
    round_index: int
    total_rounds: int
    remaining_seconds: int
    phase_target_seconds: int
    accumulated_work_seconds: int
    session_work_seconds: int  # accumulated + the current in-progress work phase
    paused_from: State | None
    pending: State | None = None  # while awaiting: the phase acknowledgement will start


class PomodoroEngine:
    def __init__(
        self,
        config: PomodoroConfig,
        sink: EventSink,
        clock: Clock | None = None,
    ) -> None:
        self._config = config
        self._sink = sink
        self._clock = clock or SystemClock()

        self._state = State.idle
        self._session_id = None
        self._round_index = 0
        self._phase_target = 0.0
        self._elapsed_before = 0.0  # accrued elapsed before the current running segment
        self._segment_start: float | None = None  # monotonic; None while paused/stopped
        self._paused_from: State | None = None
        self._pending: tuple[State, int] | None = None
        self._accumulated_work = 0

    @property
    def clock(self) -> Clock:
        """Shared with the UI so "today" and the timezone have one owner, not two."""
        return self._clock

    # --- derived time ----------------------------------------------------
    def _phase_elapsed(self) -> float:
        if self._segment_start is None:
            return self._elapsed_before
        return self._elapsed_before + (self._clock.monotonic() - self._segment_start)

    def remaining_seconds(self) -> int:
        return max(0, round(self._phase_target - self._phase_elapsed()))

    # --- event helper ----------------------------------------------------
    def _emit(self, cls, **fields) -> None:
        self._sink(
            cls(
                timestamp=self._clock.now(),
                tz_offset_minutes=self._clock.utc_offset_minutes(),
                origin=Origin.live,
                session_id=self._session_id,
                **fields,
            )
        )

    # --- phase transitions ----------------------------------------------
    def _begin_work(self, round_index: int) -> None:
        self._state = State.work
        self._round_index = round_index
        self._phase_target = self._config.work_minutes * 60
        self._elapsed_before = 0.0
        self._segment_start = self._clock.monotonic()
        self._emit(RoundStarted, round_index=round_index)

    def _begin_break(self, round_index: int) -> None:
        self._state = State.break_
        self._phase_target = self._config.break_minutes * 60
        self._elapsed_before = 0.0
        self._segment_start = self._clock.monotonic()
        self._emit(BreakStarted, round_index=round_index)

    def _hold_for(self, phase: State, round_index: int) -> None:
        """Park between phases until :meth:`acknowledge`.

        A break that starts while you're still typing isn't a break, so the clock stops at
        the boundary and the next phase only begins when you say so. Nothing is emitted
        here — the phase that just ended has already been recorded.
        """
        self._state = State.awaiting
        self._pending = (phase, round_index)
        self._segment_start = None
        self._elapsed_before = 0.0
        self._phase_target = 0.0

    def _complete_work(self) -> None:
        work_seconds = round(self._phase_elapsed())
        self._accumulated_work += work_seconds
        self._emit(RoundEnded, round_index=self._round_index, work_seconds=work_seconds)
        if self._round_index >= self._config.rounds:
            self._end_session()
        else:
            self._hold_for(State.break_, self._round_index)

    def _complete_break(self) -> None:
        break_seconds = round(self._phase_elapsed())
        self._emit(BreakEnded, round_index=self._round_index, break_seconds=break_seconds)
        self._hold_for(State.work, self._round_index + 1)

    def _end_session(self) -> None:
        self._emit(SessionEnded, total_work_seconds=self._accumulated_work)
        self._state = State.done
        self._pending = None
        self._segment_start = None

    # --- commands --------------------------------------------------------
    def start(self) -> None:
        if self._state not in (State.idle, State.done):
            raise RuntimeError(f"cannot start from state {self._state}")
        self._session_id = new_session_id()
        self._accumulated_work = 0
        self._emit(
            SessionStarted,
            work_minutes=self._config.work_minutes,
            break_minutes=self._config.break_minutes,
            planned_rounds=self._config.rounds,
        )
        self._begin_work(1)

    def pause(self) -> None:
        if self._state not in (State.work, State.break_):
            return
        self._elapsed_before = self._phase_elapsed()
        self._segment_start = None
        self._paused_from = self._state
        self._state = State.paused
        self._emit(SessionPaused)

    def resume(self) -> None:
        if self._state is not State.paused or self._paused_from is None:
            return
        self._state = self._paused_from
        self._paused_from = None
        self._segment_start = self._clock.monotonic()
        self._emit(SessionResumed)

    def acknowledge(self) -> None:
        """Start the phase that's been waiting since the last one ended."""
        if self._state is not State.awaiting or self._pending is None:
            return
        phase, round_index = self._pending
        self._pending = None
        if phase is State.work:
            self._begin_work(round_index)
        else:
            self._begin_break(round_index)

    def skip(self) -> None:
        """Finish the current phase immediately and advance."""
        active = self._paused_from if self._state is State.paused else self._state
        if active is State.work:
            if self._state is State.paused:
                self._segment_start = None  # keep frozen elapsed
            self._complete_work()
        elif active is State.break_:
            self._complete_break()

    def add_time(self, minutes: float) -> None:
        """Extend the current phase by ``minutes`` (the +1/+3/+5/custom control)."""
        if self._state not in (State.work, State.break_, State.paused):
            return
        delta = int(round(minutes * 60))
        self._phase_target += delta
        self._emit(TimeAdjusted, round_index=self._round_index, delta_seconds=delta)

    def stop(self) -> None:
        """End the session early, finalising the in-flight phase honestly."""
        if self._state is State.awaiting:
            # Nothing is running, and the finished phase was already recorded.
            self._end_session()
            return
        active = self._paused_from if self._state is State.paused else self._state
        if active is State.work:
            work_seconds = round(self._phase_elapsed())
            self._accumulated_work += work_seconds
            self._emit(RoundEnded, round_index=self._round_index, work_seconds=work_seconds)
        elif active is State.break_:
            break_seconds = round(self._phase_elapsed())
            self._emit(BreakEnded, round_index=self._round_index, break_seconds=break_seconds)
        if active in (State.work, State.break_):
            self._end_session()

    def tick(self) -> None:
        """Advance auto-transitions when the running phase has elapsed."""
        if self._state is State.work and self.remaining_seconds() == 0:
            self._complete_work()
        elif self._state is State.break_ and self.remaining_seconds() == 0:
            self._complete_break()

    # --- introspection ---------------------------------------------------
    def snapshot(self) -> EngineState:
        in_work = self._state is State.work or (
            self._state is State.paused and self._paused_from is State.work
        )
        work_in_phase = round(self._phase_elapsed()) if in_work else 0
        return EngineState(
            state=self._state,
            round_index=self._round_index,
            total_rounds=self._config.rounds,
            remaining_seconds=self.remaining_seconds(),
            phase_target_seconds=int(self._phase_target),
            accumulated_work_seconds=self._accumulated_work,
            session_work_seconds=self._accumulated_work + work_in_phase,
            paused_from=self._paused_from,
            pending=self._pending[0] if self._pending else None,
        )

    @property
    def state(self) -> State:
        return self._state

    def update_config(self, config: PomodoroConfig) -> None:
        """Apply new Pomodoro settings. Takes effect from the next phase/session."""
        self._config = config
