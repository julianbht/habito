"""The prompt shown when a session finishes: an optional tag or two, then dismiss.

Unlike :class:`~habito.ui.dialogs.phase_dialog.PhaseDialog`, nothing here "gates" a phase — the
session already ended, nothing is waiting on this dialog — so Esc or the close button
dismissing it plainly (same as attaching no tags and pressing the action button) is the
right default, not something to swallow.

Tags start hidden behind a "+ Attach tag" link, not an always-visible picker: the common
case is skipping the prompt entirely, and a control that's never used shouldn't be the
first thing on screen every time a session ends. "Attach", not "add" — this dialog only
ever links an existing or freshly-typed tag to *this session* (``SessionTagged``); it never
defines what a tag itself means, that's `TagPicker`'s "+ New tag" / double-click, which
this dialog embeds the same as the tag manager does — see CLAUDE.md § Tags.

The bottom row is one control on the left, the action button on the right — the same shape
as the tag manager's "+ New tag" / "Close", not a row of its own: the left slot holds
"+ Attach tag" until it's clicked, then swaps to "+ New tag" once the tree is showing,
rather than stacking a second row underneath. Sized like every other press-OK prompt
(:data:`~habito.ui.widgets.controls.COMPACT_DIALOG_WIDTH`, same as `PhaseDialog`) until that
click, and only then grows to the "browse a list" size the tag manager uses
(:data:`~habito.ui.widgets.controls.BROWSE_DIALOG_WIDTH` / `BROWSE_DIALOG_HEIGHT`) — the common case
is skipping the prompt, and a dialog pre-widened for a tree it isn't showing would read as
a different, bigger kind of prompt than "Round complete" or "Break over" for no reason.

Only ``selected_tags()`` (which tags end up attached) is this dialog's own concern —
everything about what tags exist and what they're named is `TagPicker`'s, tested once
there.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.ui.dialogs.catalog_edit_dialog import SubmitCallback
from habito.ui.dialogs.prompt_dialog import PromptDialog
from habito.ui.widgets.catalog_picker import CatalogPicker
from habito.ui.widgets.controls import (
    BROWSE_DIALOG_HEIGHT,
    BROWSE_DIALOG_WIDTH,
    button,
    primary_button,
)


class SessionCompleteDialog(PromptDialog):
    # Never gates a phase — see the module docstring. HabitoApp checks this the same way
    # it checks PhaseDialog.gates_phase, so the two dialogs share one call site.
    gates_phase = False

    def __init__(
        self,
        title: str,
        body: str,
        action: str,
        known_tags: list[str],
        on_accept: Callable[[list[str]], None],
        on_describe_tag: SubmitCallback,
        habit: str,
        now: datetime,
        descriptions: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, body, parent)
        self._on_accept = on_accept
        self._build(known_tags, descriptions or {}, on_describe_tag, habit, now, action)
        self.action_button.clicked.connect(self._accept)

    def _build(
        self,
        known_tags: list[str],
        descriptions: dict[str, str],
        on_describe_tag: SubmitCallback,
        habit: str,
        now: datetime,
        action: str,
    ) -> None:
        self.tag_picker = CatalogPicker(
            known_tags,
            descriptions,
            on_describe_tag,
            lambda tag: build_tag_created_event(tag, habit=habit, now=now),
            lambda tag, description: build_tag_described_event(
                tag, description, habit=habit, now=now
            ),
            "tag",
            checkable=True,
        )
        self._tag_section = QWidget()
        section = QVBoxLayout(self._tag_section)
        section.setContentsMargins(0, 0, 0, 0)
        section.addWidget(self.tag_picker)
        self._tag_section.setVisible(False)
        self._root.addWidget(self._tag_section, 1)

        self._attach_tag_link = button("+ Attach tag", "link")
        self._attach_tag_link.setToolTip("Optional — attach a tag for what you were working on")
        self._attach_tag_link.clicked.connect(self._reveal_tag_picker)
        self.tag_picker.new_button.setVisible(False)
        self.action_button = primary_button(action)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._attach_tag_link)
        bottom_row.addWidget(self.tag_picker.new_button)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.action_button)
        self._root.addSpacing(4)
        self._root.addLayout(bottom_row)

    def _reveal_tag_picker(self) -> None:
        self._attach_tag_link.setVisible(False)
        self.tag_picker.new_button.setVisible(True)
        self._tag_section.setVisible(True)
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)

    def selected_tags(self) -> list[str]:
        return self.tag_picker.selected()

    def _accept(self) -> None:
        tags = self.selected_tags()
        self.accept()
        self._on_accept(tags)

    def reject(self) -> None:
        """Esc or the close button — same as attaching no tags and pressing the button."""
        tags = self.selected_tags()
        super().reject()
        self._on_accept(tags)
