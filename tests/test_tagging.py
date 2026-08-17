"""build_tag_described_event / build_session_tagged_event / build_session_untagged_event:
the events written by the tag manager and by tagging or untagging a session after the fact.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import pytest

from habito.actions.tagging import (
    build_session_tagged_event,
    build_session_untagged_event,
    build_tag_described_event,
)
from habito.domain.events import Origin

CEST = timezone(timedelta(hours=2))
WHEN = datetime(2026, 8, 4, 14, 0, tzinfo=CEST)


def test_fields_carry_through():
    event = build_tag_described_event("linear algebra", "Strang's book", habit="study", now=WHEN)
    assert event.tag == "linear algebra"
    assert event.description == "Strang's book"
    assert event.habit == "study"
    assert event.origin is Origin.live


def test_the_timestamp_is_converted_to_utc_with_its_offset_recorded():
    event = build_tag_described_event("x", "", habit="study", now=WHEN)
    assert event.timestamp == WHEN.astimezone(UTC)
    assert event.tz_offset_minutes == 120


def test_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_tag_described_event("x", "", habit="study", now=datetime(2026, 8, 4, 14, 0))


def test_session_tagged_fields_carry_through():
    session_id = uuid4()
    event = build_session_tagged_event(session_id, "linear algebra", habit="study", now=WHEN)
    assert event.session_id == session_id
    assert event.tag == "linear algebra"
    assert event.habit == "study"
    assert event.origin is Origin.live
    assert event.timestamp == WHEN.astimezone(UTC)
    assert event.tz_offset_minutes == 120


def test_session_untagged_fields_carry_through():
    session_id = uuid4()
    event = build_session_untagged_event(session_id, "linear algebra", habit="study", now=WHEN)
    assert event.session_id == session_id
    assert event.tag == "linear algebra"
    assert event.habit == "study"
    assert event.origin is Origin.live
    assert event.timestamp == WHEN.astimezone(UTC)
    assert event.tz_offset_minutes == 120


def test_session_tagged_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_session_tagged_event(uuid4(), "x", habit="study", now=datetime(2026, 8, 4, 14, 0))


def test_session_untagged_needs_an_aware_now():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_session_untagged_event(uuid4(), "x", habit="study", now=datetime(2026, 8, 4, 14, 0))
