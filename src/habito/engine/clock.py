"""Clock abstraction so the engine's timing is deterministic under test.

``monotonic()`` drives elapsed-time math (immune to wall-clock changes);
``now()`` / ``utc_offset_minutes()`` stamp events with an unambiguous instant.
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from typing import Protocol


class Clock(Protocol):
    def monotonic(self) -> float: ...
    def now(self) -> datetime: ...  # timezone-aware, UTC
    def utc_offset_minutes(self) -> int: ...  # local wall-clock offset from UTC


class SystemClock:
    def monotonic(self) -> float:
        return time.monotonic()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def utc_offset_minutes(self) -> int:
        offset = datetime.now().astimezone().utcoffset() or timedelta(0)
        return int(offset.total_seconds() // 60)


class FakeClock:
    """Manually-advanced clock for tests."""

    def __init__(self, start: datetime | None = None, offset_minutes: int = 0) -> None:
        self._mono = 0.0
        self._now = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
        self._offset = offset_minutes

    def advance(self, seconds: float) -> None:
        self._mono += seconds
        self._now = self._now + timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self._mono

    def now(self) -> datetime:
        return self._now

    def utc_offset_minutes(self) -> int:
        return self._offset
