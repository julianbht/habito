from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from habito.actions.wakeup import build_wakeup_event
from habito.domain.events import Origin, WakeUpLogged


def _wake(hour=7):
    return datetime(2026, 8, 17, hour, 0, tzinfo=UTC)


def test_build_wakeup_event_records_the_wake_instant_and_bedtime():
    wake = _wake()
    bed = wake - timedelta(hours=8)

    event = build_wakeup_event(wake, bed, habit="sleep")

    assert isinstance(event, WakeUpLogged)
    assert event.timestamp == wake
    assert event.bedtime == bed
    assert event.origin is Origin.backfilled
    assert event.habit == "sleep"


def test_a_bedtime_on_or_after_the_wake_time_is_rejected():
    wake = _wake()

    with pytest.raises(ValueError, match="bedtime must be before"):
        build_wakeup_event(wake, wake, habit="sleep")

    with pytest.raises(ValueError, match="bedtime must be before"):
        build_wakeup_event(wake, wake + timedelta(minutes=1), habit="sleep")


def test_each_wakeup_event_mints_its_own_session_id():
    """Not part of any session, so nothing should tie two logged wake-ups together."""
    wake = _wake()
    bed = wake - timedelta(hours=8)

    first = build_wakeup_event(wake, bed, habit="sleep")
    second = build_wakeup_event(wake, bed, habit="sleep")

    assert first.session_id != second.session_id
