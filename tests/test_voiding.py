"""Voiding one standalone log entry — the correction for a wake-up or a workout log.

The session-level counterpart is `test_retraction.py`; this covers what is different here:
the target is one ``event_id`` rather than a whole session, the builder reads ``habit`` and
``target_date`` off the event instead of trusting a caller to supply them, and it refuses
targets that belong to the other mechanism.

Correcting an entry is a void plus a fresh entry appended together — the pair, and the fact
that only the replacement is left standing, is covered at the end.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from habito.actions.backfill import build_backfill_events
from habito.actions.voiding import build_void_event
from habito.actions.wakeup import build_wakeup_event
from habito.actions.workout import build_workout_logged_event
from habito.domain.events import EventVoided, Origin, drop_corrected, partition_date
from habito.storage.event_store import EventStore

CEST = timezone(timedelta(hours=2))
# The correction is made days after the entry it voids, which is the whole point.
LATER = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def a_wakeup(day=4, hour=7):
    return build_wakeup_event(
        datetime(2026, 8, day, hour, 30, tzinfo=CEST),
        datetime(2026, 8, day - 1, 23, 15, tzinfo=CEST),
        habit="sleep",
    )


def a_workout(day=4, hour=18):
    return build_workout_logged_event(
        datetime(2026, 8, day, hour, 0, tzinfo=CEST), ["running"], habit="workout"
    )


def test_a_void_names_the_event_it_withdraws():
    wakeup = a_wakeup()

    void = build_void_event(wakeup, rollover_hour=3, now=LATER)

    assert void.target_event_id == wakeup.event_id
    assert void.type == "event_voided"


def test_a_void_is_recorded_live_even_though_its_target_was_backfilled():
    """Withdrawing something is an act that happens the instant you do it, whatever the
    age of what it withdraws — see CLAUDE.md § Origin."""
    wakeup = a_wakeup()
    assert wakeup.origin is Origin.backfilled

    void = build_void_event(wakeup, rollover_hour=3, now=LATER)

    assert void.origin is Origin.live
    assert void.timestamp == LATER.astimezone(UTC)


def test_a_void_takes_its_habit_from_the_event_it_voids():
    """A void written under the wrong habit lands in a store that never reads it, so the
    builder reads it off the target rather than taking it from the caller."""
    assert build_void_event(a_wakeup(), rollover_hour=3, now=LATER).habit == "sleep"
    assert build_void_event(a_workout(), rollover_hour=3, now=LATER).habit == "workout"


def test_a_void_files_under_the_day_it_corrects_not_the_day_it_was_written():
    workout = a_workout(day=4)

    void = build_void_event(workout, rollover_hour=3, now=LATER)

    assert void.target_date == datetime(2026, 8, 4).date()
    assert partition_date(void, rollover_hour=3) == datetime(2026, 8, 4).date()


def test_the_stored_target_date_survives_a_later_rollover_change():
    """`target_date` is copied in at write time, so re-reading the log under a different
    rollover can't move a void away from what it corrects."""
    workout = a_workout(day=4, hour=1)  # before a rollover_hour=3, so it counts as the 3rd
    void = build_void_event(workout, rollover_hour=3, now=LATER)
    assert void.target_date == datetime(2026, 8, 3).date()

    assert partition_date(void, rollover_hour=0) == datetime(2026, 8, 3).date()


def test_a_reason_is_optional_and_trimmed():
    assert build_void_event(a_wakeup(), rollover_hour=3, now=LATER).reason == ""
    voided = build_void_event(a_wakeup(), rollover_hour=3, now=LATER, reason="  wrong day  ")
    assert voided.reason == "wrong day"


def test_a_session_event_cannot_be_voided_one_event_at_a_time():
    """A session is withdrawn as a whole by SessionRetracted; two overlapping undo
    mechanisms aimed at the same events would be two systems fighting over one job."""
    started = build_backfill_events(
        datetime(2026, 8, 4, 6, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=1,
        habit="study",
    )[0]

    with pytest.raises(ValueError, match="retracted by session id"):
        build_void_event(started, rollover_hour=3, now=LATER)


def test_a_void_cannot_itself_be_voided():
    void = build_void_event(a_wakeup(), rollover_hour=3, now=LATER)

    with pytest.raises(ValueError, match="cannot itself be voided"):
        build_void_event(void, rollover_hour=3, now=LATER)


def test_voiding_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_void_event(a_wakeup(), rollover_hour=3, now=datetime(2026, 8, 7, 14, 0))


def test_drop_corrected_removes_the_voided_entry_and_keeps_the_void():
    wakeup = a_wakeup()
    void = build_void_event(wakeup, rollover_hour=3, now=LATER)

    assert drop_corrected([wakeup, void]) == [void]


def test_drop_corrected_ignores_stream_order():
    """The void files under the day it corrects, so it can precede its target in the
    concatenated stream — both sets are collected before anything is dropped."""
    wakeup = a_wakeup()
    void = build_void_event(wakeup, rollover_hour=3, now=LATER)

    assert drop_corrected([void, wakeup]) == [void]


def test_a_void_only_touches_the_entry_it_names():
    kept = a_wakeup(day=5)
    dropped = a_wakeup(day=4)
    void = build_void_event(dropped, rollover_hour=3, now=LATER)

    assert drop_corrected([dropped, kept, void]) == [kept, void]


def test_read_all_hides_a_voided_entry_and_raw_still_shows_it(tmp_path):
    store = EventStore(tmp_path, "sleep", 3)
    wakeup = a_wakeup()
    store.append(wakeup)
    store.append(build_void_event(wakeup, rollover_hour=3, now=LATER))

    assert [e.type for e in store.read_all()] == ["event_voided"]
    assert [e.type for e in store.read_all(raw=True)] == ["wake_up_logged", "event_voided"]


def test_the_void_lands_in_its_targets_own_day_file(tmp_path):
    """Not the file for the day the correction was made — opening the day the mistake
    landed on shows the correction beside it."""
    store = EventStore(tmp_path, "sleep", 3)
    wakeup = a_wakeup(day=4)
    store.append(wakeup)
    store.append(build_void_event(wakeup, rollover_hour=3, now=LATER))

    day_file = tmp_path / "sleep" / "2026" / "08" / "2026-08-04.jsonl"
    assert "event_voided" in day_file.read_text(encoding="utf-8")
    assert store.files() == [day_file]


def test_editing_an_entry_is_a_void_plus_its_replacement(tmp_path):
    """What the manager's "Edit…" submits: the log keeps both, and only the corrected
    entry still stands."""
    store = EventStore(tmp_path, "sleep", 3)
    wrong = a_wakeup(hour=7)
    store.append(wrong)

    right = a_wakeup(hour=8)
    for event in (build_void_event(wrong, rollover_hour=3, now=LATER), right):
        store.append(event)

    standing = store.read_all()
    assert [e.event_id for e in standing if isinstance(e, type(right))] == [right.event_id]
    assert sum(isinstance(e, EventVoided) for e in standing) == 1
    assert len(store.read_all(raw=True)) == 3
