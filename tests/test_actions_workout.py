"""build_workout_created_event / build_workout_described_event / build_workout_logged_event:
the events written by the workout catalog and by logging a workout after the fact — the
workout extra's mirror of test_tagging.py (catalog) and test_actions_wakeup.py (a logged
entry).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from habito.actions.workout import (
    build_workout_created_event,
    build_workout_described_event,
    build_workout_logged_event,
)
from habito.domain.events import Origin

CEST = timezone(timedelta(hours=2))
WHEN = datetime(2026, 8, 4, 14, 0, tzinfo=CEST)


def test_created_fields_carry_through():
    event = build_workout_created_event("running", habit="workout", now=WHEN)
    assert event.workout == "running"
    assert event.habit == "workout"
    assert event.origin is Origin.live
    assert event.timestamp == WHEN.astimezone(UTC)
    assert event.tz_offset_minutes == 120


def test_created_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_workout_created_event("running", habit="workout", now=datetime(2026, 8, 4, 14, 0))


def test_described_fields_carry_through():
    event = build_workout_described_event(
        "running", "5k around the park", habit="workout", now=WHEN
    )
    assert event.workout == "running"
    assert event.description == "5k around the park"
    assert event.habit == "workout"
    assert event.origin is Origin.live


def test_described_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_workout_described_event(
            "running", "", habit="workout", now=datetime(2026, 8, 4, 14, 0)
        )


def test_logged_is_always_backfilled():
    event = build_workout_logged_event(WHEN, ["running"], habit="workout")
    assert event.origin is Origin.backfilled


def test_logged_carries_the_workouts_list_in_order():
    event = build_workout_logged_event(WHEN, ["running", "push-ups", "yoga"], habit="workout")
    assert event.workouts == ["running", "push-ups", "yoga"]
    assert event.habit == "workout"


def test_logged_timestamp_and_offset_come_from_when():
    event = build_workout_logged_event(WHEN, ["running"], habit="workout")
    assert event.timestamp == WHEN.astimezone(UTC)
    assert event.tz_offset_minutes == 120


def test_logged_needs_an_aware_when():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_workout_logged_event(datetime(2026, 8, 4, 14, 0), ["running"], habit="workout")


def test_logged_rejects_an_empty_workout_list():
    with pytest.raises(ValueError, match="at least one workout"):
        build_workout_logged_event(WHEN, [], habit="workout")
