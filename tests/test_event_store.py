from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from habito.domain.events import Origin, RoundEnded, SessionStarted
from habito.storage.event_store import EventStore


def _session_started(session_id):
    return SessionStarted(
        timestamp=datetime(2026, 8, 4, 4, 0, tzinfo=UTC),
        tz_offset_minutes=120,
        session_id=session_id,
        work_minutes=25,
        break_minutes=5,
        planned_rounds=4,
    )


def test_append_and_replay_roundtrip(tmp_path):
    store = EventStore(tmp_path / "events.jsonl")
    sid = uuid4()
    store.append(_session_started(sid))
    store.append(
        RoundEnded(
            timestamp=datetime(2026, 8, 4, 4, 25, tzinfo=UTC),
            tz_offset_minutes=120,
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
    store = EventStore(tmp_path / "events.jsonl")
    seen = []
    store.subscribe(seen.append)
    store.append(_session_started(uuid4()))
    assert len(seen) == 1


def test_read_all_missing_file_is_empty(tmp_path):
    store = EventStore(tmp_path / "nope" / "events.jsonl")
    assert store.read_all() == []


def test_append_is_one_line_per_event(tmp_path):
    path = tmp_path / "events.jsonl"
    store = EventStore(path)
    for _ in range(3):
        store.append(_session_started(uuid4()))
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
