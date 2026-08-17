"""known_tags/tag_descriptions/session_tags: what the session-end picker offers, what
each tag means, and which tags currently stand on a given session — all derived from the
log itself."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from habito.domain.events import Origin, SessionTagged, SessionUntagged, TagDescribed
from habito.projections.tags import known_tags, session_tags, tag_descriptions

WHEN = datetime(2026, 8, 4, 9, 0, tzinfo=UTC)


def tagged(
    tag: str, habit: str = "study", origin: Origin = Origin.live, session_id: UUID | None = None
) -> SessionTagged:
    return SessionTagged(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=origin,
        habit=habit,
        session_id=session_id or uuid4(),
        tag=tag,
    )


def untagged(tag: str, session_id: UUID, habit: str = "study") -> SessionUntagged:
    return SessionUntagged(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit=habit,
        session_id=session_id,
        tag=tag,
    )


def described(tag: str, description: str, habit: str = "study") -> TagDescribed:
    return TagDescribed(
        timestamp=WHEN,
        tz_offset_minutes=0,
        origin=Origin.live,
        habit=habit,
        tag=tag,
        description=description,
    )


def test_no_tags_yet():
    assert known_tags([], "study") == []


def test_the_most_recently_touched_tag_comes_first():
    events = [tagged("topology"), tagged("linear algebra")]
    assert known_tags(events, "study") == ["linear algebra", "topology"]


def test_a_tag_touched_again_moves_back_to_the_front():
    events = [tagged("topology"), tagged("linear algebra"), tagged("topology")]
    assert known_tags(events, "study") == ["topology", "linear algebra"]


def test_tags_are_deduplicated():
    events = [tagged("linear algebra"), tagged("linear algebra")]
    assert known_tags(events, "study") == ["linear algebra"]


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


def test_a_session_with_no_tags_has_none():
    assert session_tags([], uuid4()) == set()


def test_a_tagged_session_shows_its_tags():
    session_id = uuid4()
    events = [
        tagged("topology", session_id=session_id),
        tagged("linear algebra", session_id=session_id),
    ]
    assert session_tags(events, session_id) == {"topology", "linear algebra"}


def test_untagging_removes_it():
    session_id = uuid4()
    events = [tagged("topology", session_id=session_id), untagged("topology", session_id)]
    assert session_tags(events, session_id) == set()


def test_untagging_then_retagging_leaves_it_standing():
    session_id = uuid4()
    events = [
        tagged("topology", session_id=session_id),
        untagged("topology", session_id),
        tagged("topology", session_id=session_id),
    ]
    assert session_tags(events, session_id) == {"topology"}


def test_only_the_named_sessions_tags_count():
    session_id, other = uuid4(), uuid4()
    events = [tagged("topology", session_id=session_id), tagged("linear algebra", session_id=other)]
    assert session_tags(events, session_id) == {"topology"}
