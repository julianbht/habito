"""Synthesize the events for the workout catalog and for a workout logged after the fact.

Mirrors ``actions/tagging.py`` (catalog: create/describe) and ``actions/wakeup.py`` (a
backfilled entry, always written after the thing it describes already happened). The caller
appends whatever's returned to the workout store, which commits+pushes it like everything
else.
"""

from __future__ import annotations

from datetime import datetime as _datetime

from habito.domain.events import Origin, WorkoutCreated, WorkoutDescribed, WorkoutLogged, stamp


def build_workout_created_event(workout: str, *, habit: str, now: _datetime) -> WorkoutCreated:
    """Mark that ``workout`` exists, as of ``now``, a timezone-aware local datetime."""
    timestamp, tz_offset_minutes = stamp(now)
    return WorkoutCreated(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        workout=workout,
    )


def build_workout_described_event(
    workout: str,
    description: str,
    *,
    habit: str,
    now: _datetime,
) -> WorkoutDescribed:
    """Describe (or redescribe) ``workout`` as of ``now``, a timezone-aware local datetime."""
    timestamp, tz_offset_minutes = stamp(now)
    return WorkoutDescribed(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.live,
        habit=habit,
        workout=workout,
        description=description,
    )


def build_workout_logged_event(
    when: _datetime, workouts: list[str], *, habit: str
) -> WorkoutLogged:
    """``when`` is the timezone-aware local instant the workout(s) happened — ``stamp()``
    derives ``timestamp``/``tz_offset_minutes`` from it, same as a backfilled session."""
    if not workouts:
        raise ValueError("pick at least one workout")
    timestamp, tz_offset_minutes = stamp(when)
    return WorkoutLogged(
        timestamp=timestamp,
        tz_offset_minutes=tz_offset_minutes,
        origin=Origin.backfilled,
        habit=habit,
        workouts=workouts,
    )
