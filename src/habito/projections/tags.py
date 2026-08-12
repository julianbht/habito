"""Projection: which tags have been used before, for the session-end picker.

Derived from the log rather than a separate list to maintain — whatever's been typed
before is what gets offered again, and nothing needs to stay in sync by hand.
"""

from __future__ import annotations

from collections.abc import Iterable

from habito.domain.events import Event, SessionTagged


def known_tags(events: Iterable[Event], habit: str) -> list[str]:
    """Every distinct tag used for this habit, alphabetically."""
    return sorted({e.tag for e in events if isinstance(e, SessionTagged) and e.habit == habit})
