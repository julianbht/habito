"""The one place a tag's name and description get set — reused by both `TagPicker`
call sites (the tag manager, and the session-end picker's "+ New tag"), so there is only
ever one form for this, not two dialogs that happen to agree.

Its "Save" always means the same thing regardless of who opened it: persist the tag's name
and/or description and close. It never attaches anything to a session — that stays entirely
`TagPicker`'s (checkbox) and its caller's (the commit button) job, so the two "save"-shaped
actions in the app are never the same button wearing two meanings.

**Creating** always writes a ``TagCreated`` — it's the only event that will ever make a
name-only tag real, so pressing Save is a deliberate "this tag exists now" regardless of
whether a description came with it — plus a ``TagDescribed`` too, but only if a description
was actually typed: an empty one is a valid answer to an optional field, not something that
belongs on the log as if it were real content. **Editing** only ever writes a
``TagDescribed``, and only if the description actually changed, so reopening a tag and
closing it again via Save is a no-op rather than a redundant entry.

The description is a multi-line ``QPlainTextEdit``, not a one-line field — a tag's meaning
can run longer than fits a line. ``setTabChangesFocus(True)`` is what keeps Tab moving to
Save/Cancel instead of typing a tab character, the one thing a plain text edit doesn't do
by default that every other field here does.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtGui import QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.domain.events import Event
from habito.ui.widgets import COMPACT_DIALOG_WIDTH, button, primary_button

SubmitCallback = Callable[[Event], None]

_NAME_MAX_LENGTH = 200
_DESCRIPTION_HEIGHT = 90


class TagEditDialog(QDialog):
    def __init__(
        self,
        tag: str | None,
        description: str,
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self._original_tag = tag
        self._original_description = description
        # Set on accept, so the caller learns the (possibly new) name and its saved
        # description without re-reading the store.
        self.tag_name = ""
        self.description = ""
        self.setWindowTitle("New tag" if tag is None else "Edit tag")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self._build(tag, description)

    def _build(self, tag: str | None, description: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        self._name = QLineEdit(tag or "")
        self._name.setMaxLength(_NAME_MAX_LENGTH)
        if tag is not None:
            # Read-only, not disabled: still legible and selectable, just not changeable —
            # renaming a tag would silently orphan every event already filed under the old
            # name, which nothing in this app is built to reconcile.
            self._name.setReadOnly(True)
        else:
            self._name.textChanged.connect(self._sync_save_enabled)
        form.addRow("Name", self._name)

        self._description = QPlainTextEdit(description)
        self._description.setPlaceholderText("Optional")
        self._description.setFixedHeight(_DESCRIPTION_HEIGHT)
        self._description.setTabChangesFocus(True)
        form.addRow("Description", self._description)
        root.addLayout(form)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)
        self.save_btn = primary_button("Save")
        self.save_btn.setEnabled(bool((tag or "").strip()))
        self.save_btn.clicked.connect(self._on_save)
        row.addWidget(self.save_btn)
        root.addLayout(row)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        """Set initial focus here, not in ``_build`` — Qt assigns its own default focus
        once the window activates, silently overriding a ``setFocus()`` called any
        earlier (see ``PromptDialog.present`` for the same ordering requirement)."""
        super().showEvent(event)
        (self._description if self._original_tag is not None else self._name).setFocus()

    def _sync_save_enabled(self) -> None:
        self.save_btn.setEnabled(bool(self._name.text().strip()))

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        description = self._description.toPlainText().strip()
        if self._original_tag is None:
            self._on_submit(build_tag_created_event(name, habit=self._habit, now=self._now))
            if description:
                self._on_submit(
                    build_tag_described_event(name, description, habit=self._habit, now=self._now)
                )
        elif description != self._original_description:
            self._on_submit(
                build_tag_described_event(name, description, habit=self._habit, now=self._now)
            )
        self.tag_name = name
        self.description = description
        self.accept()
