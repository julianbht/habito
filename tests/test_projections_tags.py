"""known_tags: what the session-end picker offers, derived from the log itself."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from habito.domain.events import Origin, SessionTagged
from habito.projections.tags import known_tags

WHEN = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def tagged(tag: str, habit: str = "study", origin: Origin = Origin.live) -> SessionTagged:
    return SessionTagged(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=origin,
        habit=habit,
        session_id=uuid4(),
        tag=tag,
    )


def test_no_tags_yet():
    assert known_tags([], "study") == []


def test_tags_come_back_sorted_and_deduplicated():
    events = [tagged("linear algebra"), tagged("topology"), tagged("linear algebra")]
    assert known_tags(events, "study") == ["linear algebra", "topology"]


def test_a_different_habits_tags_are_not_offered():
    events = [tagged("linear algebra", habit="study"), tagged("running", habit="exercise")]
    assert known_tags(events, "study") == ["linear algebra"]
