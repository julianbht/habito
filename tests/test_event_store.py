from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from habito.domain.events import Origin, RoundEnded, SessionStarted
from habito.storage.event_store import EventStore


def _session_started(session_id, when=datetime(2026, 8, 4, 4, 0, tzinfo=UTC), habit="study"):
    return SessionStarted(
        timestamp=when,
        tz_offset_minutes=120,
        habit=habit,
        session_id=session_id,
        work_minutes=25,
        break_minutes=5,
        planned_rounds=4,
    )


def _store(root, **kwargs):
    """A store rooted at the data repo, scoped to the 'study' habit."""
    return EventStore(root, "study", **kwargs)


def test_append_and_replay_roundtrip(tmp_path):
    store = _store(tmp_path)
    sid = uuid4()
    store.append(_session_started(sid))
    store.append(
        RoundEnded(
            timestamp=datetime(2026, 8, 4, 4, 25, tzinfo=UTC),
            tz_offset_minutes=120,
            habit="study",
            session_id=sid,
            round_index=1,
            work_seconds=1500,
        )
    )

    events = store.read_all()
    assert len(events) == 2
    assert isinstance(events[0], SessionStarted)
    assert isinstance(events[1], RoundEnded)
    assert events[1].work_seconds == 1500
    assert events[0].origin is Origin.live


def test_subscribers_notified_on_append(tmp_path):
    store = _store(tmp_path)
    seen = []
    store.subscribe(seen.append)
    store.append(_session_started(uuid4()))
    assert len(seen) == 1


def test_read_all_missing_dir_is_empty(tmp_path):
    store = _store(tmp_path / "nope")
    assert store.read_all() == []


def test_append_is_one_line_per_event(tmp_path):
    store = _store(tmp_path)
    for _ in range(3):
        store.append(_session_started(uuid4()))

    files = store.files()
    assert len(files) == 1  # same day, so one file
    assert len(files[0].read_text(encoding="utf-8").strip().splitlines()) == 3


# --- the day partition ----------------------------------------------------
def test_events_are_filed_under_habit_year_month_and_iso_date(tmp_path):
    store = _store(tmp_path)
    store.append(_session_started(uuid4()))

    written = store.files()[0]
    # 06:00 local on Aug 4 (UTC+2)
    assert written.relative_to(tmp_path).as_posix() == "study/2026/08/2026-08-04.jsonl"


def test_the_month_directory_is_zero_padded_so_it_sorts_as_text(tmp_path):
    store = _store(tmp_path)
    for month in (8, 10):
        store.append(_session_started(uuid4(), datetime(2026, month, 4, 8, 0, tzinfo=UTC)))

    assert [p.parent.name for p in store.files()] == ["08", "10"]


def test_separate_days_go_to_separate_files(tmp_path):
    store = _store(tmp_path)
    store.append(_session_started(uuid4(), datetime(2026, 8, 4, 8, 0, tzinfo=UTC)))
    store.append(_session_started(uuid4(), datetime(2026, 8, 5, 8, 0, tzinfo=UTC)))

    assert [p.name for p in store.files()] == ["2026-08-04.jsonl", "2026-08-05.jsonl"]


def test_replay_is_ordered_across_files_and_years(tmp_path):
    """ISO names sort as text exactly as they sort by date, including over a year end."""
    store = _store(tmp_path)
    for when in (
        datetime(2027, 1, 1, 8, 0, tzinfo=UTC),
        datetime(2026, 8, 4, 8, 0, tzinfo=UTC),
        datetime(2026, 12, 31, 8, 0, tzinfo=UTC),
    ):
        store.append(_session_started(uuid4(), when))

    stamps = [e.timestamp for e in store.read_all()]
    assert stamps == sorted(stamps)
    assert [p.parent.parent.name for p in store.files()] == ["2026", "2026", "2027"]


def test_the_rollover_hour_keeps_a_late_session_in_one_file(tmp_path):
    """23:50 and 00:30 are one evening, so they belong in one day's file."""
    store = _store(tmp_path, rollover_hour=3)
    evening = datetime(2026, 8, 4, 21, 50, tzinfo=UTC)  # 23:50 local
    after_midnight = datetime(2026, 8, 4, 22, 30, tzinfo=UTC)  # 00:30 local, next day
    store.append(_session_started(uuid4(), evening))
    store.append(_session_started(uuid4(), after_midnight))

    assert [p.name for p in store.files()] == ["2026-08-04.jsonl"]


def test_without_a_rollover_the_same_session_would_split(tmp_path):
    """The contrast case — plain midnight puts one evening in two files."""
    store = _store(tmp_path, rollover_hour=0)
    store.append(_session_started(uuid4(), datetime(2026, 8, 4, 21, 50, tzinfo=UTC)))
    store.append(_session_started(uuid4(), datetime(2026, 8, 4, 22, 30, tzinfo=UTC)))

    assert [p.name for p in store.files()] == ["2026-08-04.jsonl", "2026-08-05.jsonl"]


def test_a_split_session_still_replays_as_one_ordered_stream(tmp_path):
    """Two files, one stream — session identity travels in session_id, not the path."""
    store = _store(tmp_path, rollover_hour=0)
    sid = uuid4()
    store.append(_session_started(sid, datetime(2026, 8, 4, 21, 50, tzinfo=UTC)))
    store.append(
        RoundEnded(
            timestamp=datetime(2026, 8, 4, 22, 30, tzinfo=UTC),
            tz_offset_minutes=120,
            habit="study",
            session_id=sid,
            round_index=1,
            work_seconds=1500,
        )
    )

    events = store.read_all()
    assert len(store.files()) == 2
    assert [e.session_id for e in events] == [sid, sid]
    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)


# --- the habit partition --------------------------------------------------
def test_the_path_follows_the_event_not_the_store(tmp_path):
    """A path can never disagree with the line inside it."""
    store = _store(tmp_path)
    written = store.path_for(_session_started(uuid4(), habit="reading"))

    assert written.relative_to(tmp_path).as_posix() == "reading/2026/08/2026-08-04.jsonl"


def test_a_second_habit_does_not_leak_into_this_ones_replay(tmp_path):
    study = EventStore(tmp_path, "study")
    reading = EventStore(tmp_path, "reading")
    study.append(_session_started(uuid4(), habit="study"))
    reading.append(_session_started(uuid4(), habit="reading"))
    reading.append(_session_started(uuid4(), habit="reading"))

    assert [e.habit for e in study.read_all()] == ["study"]
    assert [e.habit for e in reading.read_all()] == ["reading", "reading"]


def test_a_habit_name_cannot_escape_the_data_repo(tmp_path):
    for bad in ("../escape", "two words", "Study", "sub/dir", ""):
        with pytest.raises(ValidationError):
            _session_started(uuid4(), habit=bad)
