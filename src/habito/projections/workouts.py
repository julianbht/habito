"""Projections over workouts: the catalog (what's known, what each one means) and the log
entries themselves.

The catalog pair is derived from the log rather than a separate list to maintain — the same
shape as ``projections.tags``. There is no ``session_workouts`` equivalent: unlike a tag, a
workout is never attached to a Pomodoro session (see ``WorkoutLogged``'s docstring), so
nothing needs to ask "which workouts does this session currently have."

:func:`workout_entries` is the other half — one row per logged entry, for
``ManageWorkoutsDialog``, mirroring ``projections.wakeups.wakeup_entries``.
"""

from __future__ import annotations

from collections.abc import Iterable

from habito.domain.events import Event, WorkoutCreated, WorkoutDescribed, WorkoutLogged


def known_workouts(events: Iterable[Event], habit: str) -> list[str]:
    """Every distinct workout on offer for this habit, most recently touched first.

    A workout counts as known once it's been created, described, or logged — so one set up
    ahead of time, before it's ever logged, still shows up in the picker. ``events`` is
    assumed chronological, the way ``read_all()`` returns it, the same "touched last comes
    first" shape as :func:`habito.projections.tags.known_tags`.
    """
    order: dict[str, None] = {}
    for e in events:
        if e.habit != habit:
            continue
        if isinstance(e, (WorkoutCreated, WorkoutDescribed)):
            order.pop(e.workout, None)
            order[e.workout] = None
        elif isinstance(e, WorkoutLogged):
            for workout in e.workouts:
                order.pop(workout, None)
                order[workout] = None
    return list(reversed(order))


def workout_descriptions(events: Iterable[Event], habit: str) -> dict[str, str]:
    """Each workout's current description, folding ``WorkoutDescribed`` the same shape as
    :func:`habito.projections.tags.tag_descriptions` folds ``TagDescribed``."""
    descriptions: dict[str, str] = {}
    for e in events:
        if isinstance(e, WorkoutDescribed) and e.habit == habit:
            descriptions[e.workout] = e.description
    return descriptions


def workout_entries(events: Iterable[Event], habit: str) -> list[WorkoutLogged]:
    """Every standing workout log entry for this habit, most recent first.

    Fed the standing stream (``read_all()``), so a voided entry is already gone.
    """
    entries = [e for e in events if isinstance(e, WorkoutLogged) and e.habit == habit]
    entries.sort(key=lambda e: e.timestamp, reverse=True)
    return entries
