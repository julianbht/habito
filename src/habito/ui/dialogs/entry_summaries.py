"""One-line renderings of the standalone log entries a manager dialog lists.

The counterpart to ``retract_confirm_dialog.describe_session``, kept apart from the widgets
so a row's text is a pure function that reads on its own — the same split ``log_view.
describe`` makes.
"""

from __future__ import annotations

from datetime import timedelta

from habito.domain.events import WakeUpLogged, WorkoutLogged, local_datetime
from habito.ui.widgets.controls import format_duration


def describe_wakeup(event: WakeUpLogged) -> str:
    """``2026-08-19 07:15 · bedtime 23:30 · 7h 45m asleep``."""
    woke = local_datetime(event)
    # `bedtime` shares `timestamp`'s offset (see WakeUpLogged), so the arithmetic
    # `local_datetime` does for `timestamp` applies to it by hand.
    bed = event.bedtime + timedelta(minutes=event.tz_offset_minutes)
    asleep = format_duration(int((event.timestamp - event.bedtime).total_seconds()))
    return f"{woke:%Y-%m-%d %H:%M} · bedtime {bed:%H:%M} · {asleep} asleep"


def describe_workout_log(event: WorkoutLogged) -> str:
    """``2026-08-19 18:00 · Running, Pull-ups``."""
    return f"{local_datetime(event):%Y-%m-%d %H:%M} · {', '.join(event.workouts)}"
