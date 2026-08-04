"""Append-only JSONL event store (the Repository over the evidence log).

Each :meth:`append` writes exactly one JSON line and ``fsync``s it to disk before
notifying subscribers. Subscribers (e.g. the evidence recorder) are how the git
commit+push is triggered — kept decoupled from the domain via the Observer pattern.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from habito.domain.events import Event, EventAdapter

Listener = Callable[[Event], None]


class EventStore:
    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Listener] = []

    @property
    def path(self) -> Path:
        return self._path

    def subscribe(self, listener: Listener) -> None:
        """Register an observer notified after each durable append."""
        self._listeners.append(listener)

    def append(self, event: Event) -> None:
        line = event.model_dump_json()
        with self._path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        for listener in self._listeners:
            listener(event)

    def read_all(self) -> list[Event]:
        """Replay the full log, parsing each line into its concrete event type."""
        if not self._path.exists():
            return []
        events: list[Event] = []
        with self._path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                events.append(EventAdapter.validate_json(raw))
        return events
