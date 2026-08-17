"""Projections over tags: what's known, and what each one means.

Both derived from the log rather than a separate list to maintain — whatever's been typed
or described before is what gets offered again, and nothing needs to stay in sync by hand.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from habito.domain.events import Event, SessionTagged, SessionUntagged, TagCreated, TagDescribed


def known_tags(events: Iterable[Event], habit: str) -> list[str]:
    """Every distinct tag on offer for this habit, most recently touched first.

    A tag counts as known once it's been created, described, or put on a session — so a
    tag set up ahead of time, before it's ever used, still shows up in the session-end
    picker. ``events`` is assumed chronological, the way ``read_all()`` returns it, so
    "touched last" is just "seen last" in the given order — no timestamp comparison
    needed, and a tag touched again moves back to the front rather than staying wherever
    it first appeared.
    """
    order: dict[str, None] = {}
    for e in events:
        if isinstance(e, (SessionTagged, TagCreated, TagDescribed)) and e.habit == habit:
            order.pop(e.tag, None)
            order[e.tag] = None
    return list(reversed(order))


def session_tags(events: Iterable[Event], session_id: UUID) -> set[str]:
    """Whichever tags currently stand on ``session_id`` — ``SessionTagged`` folded with
    later ``SessionUntagged`` for the same tag removing it, the same "later event wins"
    shape as :func:`tag_descriptions`. Order doesn't matter here (unlike
    :func:`known_tags`): this is only ever used to pre-check/lock rows in a picker, not to
    rank anything.
    """
    tags: set[str] = set()
    for e in events:
        if isinstance(e, SessionTagged) and e.session_id == session_id:
            tags.add(e.tag)
        elif isinstance(e, SessionUntagged) and e.session_id == session_id:
            tags.discard(e.tag)
    return tags


def tag_descriptions(events: Iterable[Event], habit: str) -> dict[str, str]:
    """Each tag's current description, folding ``TagDescribed`` the same shape as
    :func:`known_tags` folds ``SessionTagged``.

    Later entries for the same tag overwrite earlier ones — correcting a description is
    just appending a new event, not editing the old one. A tag never described is simply
    absent, not an empty string on record.
    """
    descriptions: dict[str, str] = {}
    for e in events:
        if isinstance(e, TagDescribed) and e.habit == habit:
            descriptions[e.tag] = e.description
    return descriptions
