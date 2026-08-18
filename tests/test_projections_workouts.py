"""known_workouts/workout_descriptions: what the workout picker offers, and what each one
means — all derived from the log itself, mirroring test_projections_tags.py. There is no
session_workouts equivalent to test: a workout is never attached to a Pomodoro session (see
WorkoutLogged's own docstring)."""

from __future__ import annotations

from datetime import UTC, datetime

from habito.domain.events import Origin, WorkoutCreated, WorkoutDescribed, WorkoutLogged
from habito.projections.workouts import known_workouts, workout_descriptions

WHEN = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def created(workout: str, habit: str = "workout") -> WorkoutCreated:
    return WorkoutCreated(
        timestamp=WHEN, tz_offset_minutes=0, origin=Origin.live, habit=habit, workout=workout
    )


def described(workout: str, description: str, habit: str = "workout") -> WorkoutDescribed:
    return WorkoutDescribed(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit=habit,
        workout=workout,
        description=description,
    )


def logged(workouts: list[str], habit: str = "workout") -> WorkoutLogged:
    return WorkoutLogged(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.backfilled,
        habit=habit,
        workouts=workouts,
    )


def test_no_workouts_yet():
    assert known_workouts([], "workout") == []


def test_the_most_recently_touched_workout_comes_first():
    events = [created("running"), created("yoga")]
    assert known_workouts(events, "workout") == ["yoga", "running"]


def test_a_workout_touched_again_moves_back_to_the_front():
    events = [created("running"), created("yoga"), created("running")]
    assert known_workouts(events, "workout") == ["running", "yoga"]


def test_workouts_are_deduplicated():
    events = [created("running"), created("running")]
    assert known_workouts(events, "workout") == ["running"]


def test_a_different_habits_workouts_are_not_offered():
    events = [created("running", habit="workout"), created("linear algebra", habit="study")]
    assert known_workouts(events, "workout") == ["running"]


def test_a_workout_only_ever_described_is_still_known():
    events = [described("running", "5k loop")]
    assert known_workouts(events, "workout") == ["running"]


def test_a_workout_only_ever_logged_is_still_known():
    """Never explicitly created — used straight from a log entry's "+ New workout"."""
    events = [logged(["running"])]
    assert known_workouts(events, "workout") == ["running"]


def test_every_workout_in_a_multi_workout_log_entry_is_known():
    events = [logged(["running", "yoga"])]
    assert known_workouts(events, "workout") == ["yoga", "running"]


def test_a_workout_logged_again_moves_back_to_the_front():
    events = [created("yoga"), created("running"), logged(["yoga"])]
    assert known_workouts(events, "workout") == ["yoga", "running"]


def test_no_descriptions_yet():
    assert workout_descriptions([], "workout") == {}


def test_a_workout_never_described_is_simply_absent():
    events = [created("running")]
    assert workout_descriptions(events, "workout") == {}


def test_the_latest_description_wins():
    events = [described("running", "first draft"), described("running", "5k loop")]
    assert workout_descriptions(events, "workout") == {"running": "5k loop"}


def test_descriptions_are_scoped_to_their_habit():
    events = [described("linear algebra", "Strang", habit="study")]
    assert workout_descriptions(events, "workout") == {}
