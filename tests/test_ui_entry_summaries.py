"""describe_wakeup / describe_workout_log — the one line a manager row shows.

Pure functions, kept apart from the widgets, so this is plain assertions on text. The
counterpart for sessions is `describe_session`, covered in test_ui_retract_confirm_dialog.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from habito.actions.wakeup import build_wakeup_event
from habito.actions.workout import build_workout_logged_event
from habito.ui.dialogs.entry_summaries import describe_wakeup, describe_workout_log

CEST = timezone(timedelta(hours=2))


def test_a_wakeup_reads_as_when_you_woke_when_you_went_to_bed_and_how_long():
    wakeup = build_wakeup_event(
        datetime(2026, 8, 4, 7, 30, tzinfo=CEST),
        datetime(2026, 8, 3, 23, 15, tzinfo=CEST),
        habit="sleep",
    )

    assert describe_wakeup(wakeup) == "2026-08-04 07:30 · bedtime 23:15 · 8h 15m asleep"


def test_a_wakeup_reads_off_its_own_recorded_offset_not_the_machines():
    """Same rule as everywhere else: history keeps the zone it was written in."""
    wakeup = build_wakeup_event(
        datetime(2026, 8, 4, 7, 30, tzinfo=timezone(timedelta(hours=9))),
        datetime(2026, 8, 3, 23, 15, tzinfo=timezone(timedelta(hours=9))),
        habit="sleep",
    )

    assert describe_wakeup(wakeup).startswith("2026-08-04 07:30 · bedtime 23:15")


def test_a_workout_log_reads_as_when_and_what():
    logged = build_workout_logged_event(
        datetime(2026, 8, 4, 18, 0, tzinfo=CEST), ["running"], habit="workout"
    )

    assert describe_workout_log(logged) == "2026-08-04 18:00 · running"


def test_a_workout_log_lists_every_workout_in_the_entry():
    """One entry can cover several workouts done in the same sitting — the row has to say
    which, or two entries on one evening look identical."""
    logged = build_workout_logged_event(
        datetime(2026, 8, 4, 18, 0, tzinfo=CEST), ["running", "pull-ups"], habit="workout"
    )

    assert describe_workout_log(logged) == "2026-08-04 18:00 · running, pull-ups"
