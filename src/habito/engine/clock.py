"""Clock abstraction so the engine's timing is deterministic under test.

``monotonic()`` drives elapsed-time math (immune to wall-clock changes);
``now()`` / ``utc_offset_minutes()`` stamp events with an unambiguous instant.

The clock also owns the configured timezone, so "what day is it" has exactly one
answer across the engine, the calendar and the backfill dialog. ``set_zone`` exists
because Settings can change that zone mid-run.
"""

from __future__ import annotations

import time
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def now(self) -> datetime: ...  # timezone-aware, UTC
    def utc_offset_minutes(self) -> int: ...  # local wall-clock offset from UTC
    def today(self) -> date: ...  # local wall-clock date
    def set_zone(self, zone: tzinfo | None) -> None: ...  # None follows the machine


class SystemClock:
    def __init__(self, zone: tzinfo | None = None) -> None:
        self._zone = zone

    def set_zone(self, zone: tzinfo | None) -> None:
        self._zone = zone

    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(UTC)

    def local_now(self) -> datetime:
        # astimezone(None) means "the machine's zone", so no branch is needed here.
        return self.now().astimezone(self._zone)

    def utc_offset_minutes(self) -> int:
        # Resolved at the current instant, so DST is handled rather than assumed.
        offset = self.local_now().utcoffset() or timedelta(0)
        return int(offset.total_seconds() // 60)

    def today(self) -> date:
        return self.local_now().date()


class FakeClock:
    """Manually-advanced clock for tests."""

    def __init__(self, start: datetime | None = None, offset_minutes: int = 0) -> None:
        self._mono = 0.0
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)
        self._offset = offset_minutes
        self._zone: tzinfo | None = None

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._now = self._now + timedelta(seconds=seconds)

    def set_zone(self, zone: tzinfo | None) -> None:
        """A zone, once set, wins over ``offset_minutes`` — same as the real clock."""
        self._zone = zone

    def monotonic(self) -> float:
        return self._mono

    def now(self) -> datetime:
        return self._now

    def utc_offset_minutes(self) -> int:
        if self._zone is None:
            return self._offset
        offset = self._now.astimezone(self._zone).utcoffset() or timedelta(0)
        return int(offset.total_seconds() // 60)

    def today(self) -> date:
        return (self._now + timedelta(minutes=self.utc_offset_minutes())).date()
