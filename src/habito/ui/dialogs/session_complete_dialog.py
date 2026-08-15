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
(:class:`~habito.ui.dialogs.phase_dialog.PhaseDialog`'s width, from `PromptDialog`) until
that click, and only then grows to the tag manager's own
:data:`~habito.ui.widgets.tag_picker.DIALOG_MIN_WIDTH` / `DIALOG_MIN_HEIGHT` — the common
case is skipping the prompt, and a dialog pre-widened for a tree it isn't showing would
read as a different, bigger kind of prompt than "Round complete" or "Break over" for no
reason.

Only ``selected_tags()`` (which tags end up attached) is this dialog's own concern —
everything about what tags exist and what they're named is `TagPicker`'s, tested once
there.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from habito.ui.dialogs.prompt_dialog import PromptDialog
from habito.ui.dialogs.tag_edit_dialog import SubmitCallback
from habito.ui.widgets import button, primary_button
from habito.ui.widgets.tag_picker import DIALOG_MIN_HEIGHT, DIALOG_MIN_WIDTH, TagPicker


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
        self.tag_picker = TagPicker(
            known_tags, descriptions, on_describe_tag, habit, now, checkable=True
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
        self.tag_picker.new_tag_button.setVisible(False)
        self.action_button = primary_button(action)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self._attach_tag_link)
        bottom_row.addWidget(self.tag_picker.new_tag_button)
        bottom_row.addStretch(1)
        bottom_row.addWidget(self.action_button)
        self._root.addSpacing(4)
        self._root.addLayout(bottom_row)

    def _reveal_tag_picker(self) -> None:
        self._attach_tag_link.setVisible(False)
        self.tag_picker.new_tag_button.setVisible(True)
        self._tag_section.setVisible(True)
        self.setMinimumWidth(DIALOG_MIN_WIDTH)
        self.setMinimumHeight(DIALOG_MIN_HEIGHT)

    def selected_tags(self) -> list[str]:
        return self.tag_picker.selected_tags()

    def _accept(self) -> None:
        tags = self.selected_tags()
        self.accept()
        self._on_accept(tags)

    def reject(self) -> None:
        """Esc or the close button — same as attaching no tags and pressing the button."""
        tags = self.selected_tags()
        super().reject()
        self._on_accept(tags)
