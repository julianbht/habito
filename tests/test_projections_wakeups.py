"""wakeup_entries: the rows ManageWakeUpsDialog lists.

Fed the standing stream, so a voided entry is already gone before this runs — the
filtering rule lives in `read_all`, tested in test_voiding.py, not repeated here. What is
this projection's own is the habit filter and the newest-first order.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from habito.actions.wakeup import build_wakeup_event
from habito.domain.events import Origin, WorkoutLogged
from habito.projections.wakeups import wakeup_entries

CEST = timezone(timedelta(hours=2))


def a_wakeup(day: int, habit: str = "sleep"):
    return build_wakeup_event(
        datetime(2026, 8, day, 7, 30, tzinfo=CEST),
        datetime(2026, 8, day - 1, 23, 15, tzinfo=CEST),
        habit=habit,
    )


def test_entries_come_back_newest_first():
    older, newer = a_wakeup(3), a_wakeup(5)

    assert wakeup_entries([older, newer], "sleep") == [newer, older]


def test_only_this_habits_wakeups_are_listed():
    mine, someone_elses = a_wakeup(4), a_wakeup(4, habit="naps")

    assert wakeup_entries([mine, someone_elses], "sleep") == [mine]


def test_events_that_are_not_wakeups_are_left_out():
    """The store is per-habit, but its stream also holds this habit's own corrections."""
    wakeup = a_wakeup(4)
    workout = WorkoutLogged(
        timestamp=datetime(2026, 8, 4, 16, 0, tzinfo=CEST),
        tz_offset_minutes=120,
        origin=Origin.backfilled,
        habit="sleep",
        workouts=["running"],
    )

    assert wakeup_entries([wakeup, workout], "sleep") == [wakeup]


def test_an_empty_log_lists_nothing():
    assert wakeup_entries([], "sleep") == []
