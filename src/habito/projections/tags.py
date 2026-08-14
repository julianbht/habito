"""Projections over tags: what's known, and what each one means.

Both derived from the log rather than a separate list to maintain — whatever's been typed
or described before is what gets offered again, and nothing needs to stay in sync by hand.
"""

from __future__ import annotations

from collections.abc import Iterable

from habito.domain.events import Event, SessionTagged, TagCreated, TagDescribed


def known_tags(events: Iterable[Event], habit: str) -> list[str]:
    """Every distinct tag on offer for this habit, alphabetically.

    A tag counts as known once it's been created, described, or put on a session — so a
    tag set up ahead of time, before it's ever used, still shows up in the session-end
    picker.
    """
    tags = {
        e.tag
        for e in events
        if isinstance(e, (SessionTagged, TagCreated, TagDescribed)) and e.habit == habit
    }
    return sorted(tags)


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
