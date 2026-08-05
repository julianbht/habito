"""Append-only JSONL event store, partitioned into one file per day.

Each :meth:`append` writes exactly one JSON line and ``fsync``s it to disk before
notifying subscribers. Subscribers (e.g. the evidence recorder) are how the git
commit+push is triggered — kept decoupled from the domain via the Observer pattern.

Files are laid out as ``<root>/2026/2026-08-05.jsonl``. One file per day rather than one
growing log, because every event is committed and pushed the moment it happens: git
rewrites the whole file as a new blob each time, so a single log would make every commit
cost more than the last one, forever. A day file stops growing when the day ends, which
keeps that cost flat no matter how many years accumulate. It also means an old day's file
is never touched again, so a change to one stands out in the history.

Which file an event lands in is decided by :func:`logical_date` — a pure function of the
event, so the store needs no memory of the session in progress. A session running past the
rollover hour is simply split across two files; nothing downstream can tell, because
:meth:`read_all` concatenates them back into one ordered stream and session identity
travels in ``session_id``, not in the file name.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from habito.domain.events import Event, EventAdapter, logical_date

Listener = Callable[[Event], None]


class EventStore:
    def __init__(self, root: Path, rollover_hour: int = 0) -> None:
        self._root = Path(root)
        self._rollover_hour = rollover_hour
        self._root.mkdir(parents=True, exist_ok=True)
        self._listeners: list[Listener] = []

    @property
    def root(self) -> Path:
        return self._root

    def set_rollover_hour(self, hour: int) -> None:
        """Change where days break. Only affects where *new* events are filed — files
        already written keep their contents, since nothing is ever rewritten."""
        self._rollover_hour = hour

    def path_for(self, event: Event) -> Path:
        """The file an event belongs in. Derived from the event, never from the clock."""
        day = logical_date(event, self._rollover_hour)
        return self._root / f"{day:%Y}" / f"{day:%Y-%m-%d}.jsonl"

    def subscribe(self, listener: Listener) -> None:
        """Register an observer notified after each durable append."""
        self._listeners.append(listener)

    def append(self, event: Event) -> None:
        line = event.model_dump_json()
        path = self.path_for(event)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())
        for listener in self._listeners:
            listener(event)

    def files(self) -> list[Path]:
        """Every day file, oldest first.

        ISO names mean sorting the paths as text *is* sorting them by date, so no parsing
        is needed here — and nothing downstream ever reads a date out of a file name.
        """
        if not self._root.exists():
            return []
        return sorted(self._root.glob("*/*.jsonl"))

    def read_all(self) -> list[Event]:
        """Replay the full log, parsing each line into its concrete event type."""
        events: list[Event] = []
        for path in self.files():
            with path.open("r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    events.append(EventAdapter.validate_json(raw))
        return events
