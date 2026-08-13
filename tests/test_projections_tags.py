"""known_tags/tag_descriptions: what the session-end picker offers and what each tag
means, both derived from the log itself."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from habito.domain.events import Origin, SessionTagged, TagDescribed
from habito.projections.tags import known_tags, tag_descriptions

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


def described(tag: str, description: str, habit: str = "study") -> TagDescribed:
    return TagDescribed(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit=habit,
        session_id=uuid4(),
        tag=tag,
        description=description,
    )


def test_no_tags_yet():
    assert known_tags([], "study") == []


def test_tags_come_back_sorted_and_deduplicated():
    events = [tagged("linear algebra"), tagged("topology"), tagged("linear algebra")]
    assert known_tags(events, "study") == ["linear algebra", "topology"]


def test_a_different_habits_tags_are_not_offered():
    events = [tagged("linear algebra", habit="study"), tagged("running", habit="exercise")]
    assert known_tags(events, "study") == ["linear algebra"]


def test_a_tag_only_ever_described_is_still_known():
    """Defined ahead of time in the tag manager, before any session used it."""
    events = [described("linear algebra", "Strang's book")]
    assert known_tags(events, "study") == ["linear algebra"]


def test_no_descriptions_yet():
    assert tag_descriptions([], "study") == {}


def test_a_tag_never_described_is_simply_absent():
    events = [tagged("topology")]
    assert tag_descriptions(events, "study") == {}


def test_the_latest_description_wins():
    events = [described("linear algebra", "first draft"), described("linear algebra", "Strang")]
    assert tag_descriptions(events, "study") == {"linear algebra": "Strang"}


def test_descriptions_are_scoped_to_their_habit():
    events = [described("running shoes", "Nike", habit="exercise")]
    assert tag_descriptions(events, "study") == {}
