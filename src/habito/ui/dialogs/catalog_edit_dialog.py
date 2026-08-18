"""The one place a catalog entry's name and description get set — shared by every
``CatalogPicker`` call site (tags: the tag manager and the session-end "+ New tag";
workouts: the workout manager and the log-workout dialog's "+ New workout"), so there is
only ever one form for this shape, not near-duplicate dialogs that happen to agree.

Generalized from what was ``TagEditDialog``: tags and workouts are two unrelated domains
(one about study sessions, one its own extra) that happen to want the identical
name-plus-description editor. ``noun`` ("tag" / "workout") is what makes the window title
and button text read right either way; ``build_created``/``build_described`` are the two
event-builders (``habito.actions.tagging`` or `habito.actions.workout`) already bound to
their ``habit``/``now`` via ``functools.partial`` by the caller — this dialog knows nothing
about either.

Its "Save" always means the same thing regardless of who opened it: persist the entry's
name and/or description and close. It never attaches anything to a session or a log entry —
that stays entirely ``CatalogPicker``'s (checkbox) and its caller's (the commit button)
job, so the two "save"-shaped actions in the app are never the same button wearing two
meanings.

**Creating** always writes the "created" event — it's the only event that will ever make a
name-only entry real, so pressing Save is a deliberate "this exists now" regardless of
whether a description came with it — plus a "described" event too, but only if a
description was actually typed: an empty one is a valid answer to an optional field, not
something that belongs on the log as if it were real content. **Editing** only ever writes
a "described" event, and only if the description actually changed, so reopening an entry
and closing it again via Save is a no-op rather than a redundant entry.

The description is a multi-line ``QPlainTextEdit``, not a one-line field — a description
can run longer than fits a line. ``setTabChangesFocus(True)`` is what keeps Tab moving to
Save/Cancel instead of typing a tab character, the one thing a plain text edit doesn't do
by default that every other field here does.
"""

from __future__ import annotations

from collections.abc import Callable

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

from habito.domain.events import Event
from habito.ui.widgets.controls import COMPACT_DIALOG_WIDTH, button, primary_button

SubmitCallback = Callable[[Event], None]
CreatedBuilder = Callable[[str], Event]
DescribedBuilder = Callable[[str, str], Event]

_NAME_MAX_LENGTH = 200
_DESCRIPTION_HEIGHT = 90


class CatalogEditDialog(QDialog):
    def __init__(
        self,
        noun: str,
        name: str | None,
        description: str,
        on_submit: SubmitCallback,
        build_created: CreatedBuilder,
        build_described: DescribedBuilder,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._noun = noun
        self._on_submit = on_submit
        self._build_created = build_created
        self._build_described = build_described
        self._original_name = name
        self._original_description = description
        # Set on accept, so the caller learns the (possibly new) name and its saved
        # description without re-reading the store.
        self.name = ""
        self.description = ""
        self.setWindowTitle(f"New {noun}" if name is None else f"Edit {noun}")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self._build(name, description)

    def _build(self, name: str | None, description: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)
        self._name = QLineEdit(name or "")
        self._name.setMaxLength(_NAME_MAX_LENGTH)
        if name is not None:
            # Read-only, not disabled: still legible and selectable, just not changeable —
            # renaming would silently orphan every event already filed under the old name,
            # which nothing in this app is built to reconcile.
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
        self.save_btn.setEnabled(bool((name or "").strip()))
        self.save_btn.clicked.connect(self._on_save)
        row.addWidget(self.save_btn)
        root.addLayout(row)

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt override)
        """Set initial focus here, not in ``_build`` — Qt assigns its own default focus
        once the window activates, silently overriding a ``setFocus()`` called any
        earlier (see ``PromptDialog.present`` for the same ordering requirement)."""
        super().showEvent(event)
        (self._description if self._original_name is not None else self._name).setFocus()

    def _sync_save_enabled(self) -> None:
        self.save_btn.setEnabled(bool(self._name.text().strip()))

    def _on_save(self) -> None:
        name = self._name.text().strip()
        if not name:
            return
        description = self._description.toPlainText().strip()
        if self._original_name is None:
            self._on_submit(self._build_created(name))
            if description:
                self._on_submit(self._build_described(name, description))
        elif description != self._original_description:
            self._on_submit(self._build_described(name, description))
        self.name = name
        self.description = description
        self.accept()
