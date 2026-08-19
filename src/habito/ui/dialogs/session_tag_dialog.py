"""Tag or untag one session after the fact — the ☰ "Manage sessions" dialog's per-row
"Manage tags…" action, for the case a session finished without being tagged (or was tagged
wrong) and the session-end prompt is long gone.

Reuses the exact same `CatalogPicker` the session-end prompt and the log-workout dialog
embed (see CLAUDE.md § Tags) — seeded with the session's current tags via
`checked=` so unchecking one reads as "take this back off" rather than "I never touched
this." Nothing is written per click, unlike `CatalogEditDialog`'s Save: checking and
unchecking here is free until "Apply Tags", which diffs the tree's final state against what
the session had when this dialog opened and writes exactly the difference — a
`SessionTagged` per newly-checked tag, a `SessionUntagged` per newly-unchecked one. The
muted line above the buttons tracks that same diff live ("No changes" / "N tags changed"),
off the tree's own `itemChanged` signal. Cancelling (Esc, the close button) discards that
diff the same way any other dialog's Cancel does; a tag created or described via "+ New
tag"/double-click along the way still stands, since that write already landed the moment it
was saved.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime
from uuid import UUID

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from habito.actions.tagging import (
    build_session_tagged_event,
    build_session_untagged_event,
    build_tag_created_event,
    build_tag_described_event,
)
from habito.domain.events import Event
from habito.ui.widgets.catalog_picker import CatalogPicker
from habito.ui.widgets.controls import (
    BROWSE_DIALOG_HEIGHT,
    BROWSE_DIALOG_WIDTH,
    button,
    button_row,
    label,
    primary_button,
)

SubmitCallback = Callable[[Iterable[Event]], None]


class SessionTagDialog(QDialog):
    def __init__(
        self,
        session_id: UUID,
        current_tags: set[str],
        known_tags: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session_id = session_id
        self._current_tags = current_tags
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self.setWindowTitle("Manage tags")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self._build(known_tags, descriptions)

    def _build(self, known_tags: list[str], descriptions: dict[str, str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        self.tag_picker = CatalogPicker(
            known_tags,
            descriptions,
            lambda event: self._on_submit([event]),
            lambda tag: build_tag_created_event(tag, habit=self._habit, now=self._now),
            lambda tag, description: build_tag_described_event(
                tag, description, habit=self._habit, now=self._now
            ),
            "tag",
            hint="Check a tag to attach it, uncheck to remove it.",
            checked=self._current_tags,
        )
        root.addWidget(self.tag_picker, 1)

        # Checking/unchecking writes nothing until "Apply Tags" (see the module
        # docstring), so this is the only feedback that anything changed at all before
        # then — updated off the tree's own itemChanged rather than tracked by hand.
        self._status = label("", "muted")
        self._update_status()
        self.tag_picker.tree.itemChanged.connect(self._update_status)
        root.addWidget(self._status)

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._done_btn = primary_button("Apply Tags")
        self._done_btn.clicked.connect(self._accept)
        root.addLayout(
            button_row(
                self,
                primary=self._done_btn,
                dismiss=cancel_btn,
                auxiliary=(self.tag_picker.new_button,),
            )
        )

    def _diff(self) -> tuple[set[str], set[str]]:
        final = set(self.tag_picker.selected())
        return final - self._current_tags, self._current_tags - final

    def _update_status(self) -> None:
        added, removed = self._diff()
        changed = len(added) + len(removed)
        if changed == 0:
            self._status.setText("No changes")
        elif changed == 1:
            self._status.setText("1 tag changed")
        else:
            self._status.setText(f"{changed} tags changed")

    def _accept(self) -> None:
        added, removed = self._diff()
        events: list[Event] = [
            build_session_tagged_event(self._session_id, tag, habit=self._habit, now=self._now)
            for tag in sorted(added)
        ]
        events += [
            build_session_untagged_event(self._session_id, tag, habit=self._habit, now=self._now)
            for tag in sorted(removed)
        ]
        if events:
            self._on_submit(events)
        self.accept()
