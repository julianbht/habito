"""build_tag_described_event: the one TagDescribed the tag manager writes per save."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from habito.actions.tagging import build_tag_described_event
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
