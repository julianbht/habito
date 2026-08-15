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
from habito.ui.widgets import button
from habito.ui.widgets.tag_picker import TagPicker


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
        self._build(known_tags, descriptions or {}, on_describe_tag, habit, now)
        self._add_action_row(action)
        self.action_button.clicked.connect(self._accept)

    def _build(
        self,
        known_tags: list[str],
        descriptions: dict[str, str],
        on_describe_tag: SubmitCallback,
        habit: str,
        now: datetime,
    ) -> None:
        # Shrink-wrapped and centred, like the action button below — not stretched to the
        # dialog's full width, which left its text pinned to the left edge under a centred
        # heading and message.
        link_row = QHBoxLayout()
        link_row.addStretch(1)
        self._attach_tag_link = button("+ Attach tag", "link")
        self._attach_tag_link.setToolTip("Optional — attach a tag for what you were working on")
        self._attach_tag_link.clicked.connect(self._reveal_tag_picker)
        link_row.addWidget(self._attach_tag_link)
        link_row.addStretch(1)
        self._root.addLayout(link_row)

        self.tag_picker = TagPicker(
            known_tags, descriptions, on_describe_tag, habit, now, checkable=True
        )
        new_tag_row = QHBoxLayout()
        new_tag_row.addWidget(self.tag_picker.new_tag_button)
        new_tag_row.addStretch(1)

        # One container so the tree and its "+ New tag" row show/hide together — the
        # picker itself doesn't lay the button out (see its module docstring), so without
        # this the button would stay put while the link hid only the tree.
        self._tag_section = QWidget()
        section = QVBoxLayout(self._tag_section)
        section.setContentsMargins(0, 0, 0, 0)
        section.setSpacing(8)
        section.addWidget(self.tag_picker)
        section.addLayout(new_tag_row)
        self._tag_section.setVisible(False)
        self._root.addWidget(self._tag_section)

    def _reveal_tag_picker(self) -> None:
        self._attach_tag_link.setVisible(False)
        self._tag_section.setVisible(True)

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
