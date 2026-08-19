"""Manage one stream of standalone log entries — sleep or workouts.

The list of what's been logged, an "add" button that opens that stream's own logging
dialog, and a right-click menu per row to correct or void an entry. One class for both
streams: a wake-up and a workout log differ in what a row says and which form adds one,
never in the shape of managing them, so those two come in as data (``reload``,
``open_form``) rather than as a second dialog.

Editing is a void plus a fresh entry, appended together in one submit — the log is never
rewritten, so "I logged the wrong time" is the old entry withdrawn and the corrected one
added. That's why ``open_form`` is told which entry is being replaced: the same logging
dialog serves both, pre-filled when it's an edit.

Sessions keep their own manager (`ManageSessionsDialog`): a session is many events voided
as one by ``session_id``, and its row menu offers tagging rather than editing. The two
share the list widget (`EntryList`), which is the part that is genuinely the same.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from habito.actions.voiding import build_void_event
from habito.domain.events import Event
from habito.ui.dialogs.void_confirm_dialog import VoidConfirmDialog
from habito.ui.svg_icons import icon
from habito.ui.widgets.controls import (
    BROWSE_DIALOG_HEIGHT,
    BROWSE_DIALOG_WIDTH,
    button,
    primary_button,
)
from habito.ui.widgets.entry_list import EntryList

SubmitCallback = Callable[[Iterable[Event]], None]


@dataclass(frozen=True)
class ManagedEntry:
    """One row: the event, and the line of text standing for it.

    Rendered by the caller (``entry_summaries``) rather than by a callback in here, so this
    dialog never has to know which concrete event type it is showing."""

    summary: str
    event: Event


FormOpener = Callable[[QWidget, SubmitCallback, Event | None], None]
"""Open this stream's logging dialog, parented to the manager, submitting through the given
callback. The third argument is the entry being replaced, or ``None`` for a fresh one."""

ExtraAction = tuple[str, Callable[[QWidget], None]]
"""A second, plain button beside "add" — the workout catalog, which sleep has no equivalent
of."""


class EntryManagerDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        hint: str,
        empty_text: str,
        add_text: str,
        reload: Callable[[], Sequence[ManagedEntry]],
        open_form: FormOpener,
        on_submit: SubmitCallback,
        rollover_hour: int,
        now: Callable[[], datetime],
        extra: ExtraAction | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reload = reload
        self._open_form = open_form
        self._on_submit = on_submit
        self._rollover_hour = rollover_hour
        # Read afresh per correction rather than fixed at construction: a manager can sit
        # open for a long time, and a void records when it was made.
        self._now = now
        self._entries: list[ManagedEntry] = []
        self.setWindowTitle(title)
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build(hint, empty_text, add_text, extra)
        self._refresh()

    def _build(self, hint: str, empty_text: str, add_text: str, extra: ExtraAction | None) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        self.list = EntryList(hint, empty_text)
        self.list.row_menu_requested.connect(self._on_row_menu)
        root.addWidget(self.list, 1)

        actions = QHBoxLayout()
        self.add_button = primary_button(add_text)
        self.add_button.clicked.connect(self._add)
        actions.addWidget(self.add_button)
        if extra is not None:
            text, open_extra = extra
            extra_btn = button(text)
            extra_btn.clicked.connect(lambda: self._open_extra(open_extra))
            actions.addWidget(extra_btn)
        actions.addStretch(1)
        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        root.addLayout(actions)

    def _refresh(self) -> None:
        self._entries = list(self._reload())
        self.list.set_rows([e.summary for e in self._entries])

    def _submit(self, events: Iterable[Event]) -> None:
        self._on_submit(events)
        self._refresh()

    def _add(self) -> None:
        self._open_form(self, self._submit, None)

    def _open_extra(self, open_extra: Callable[[QWidget], None]) -> None:
        # The catalog writes its own events as they're made, so there is nothing to submit
        # here — but a workout added or renamed there changes what a row can say.
        open_extra(self)
        self._refresh()

    def _on_row_menu(self, row: int, pos: QPoint) -> None:
        if not 0 <= row < len(self._entries):
            return
        entry = self._entries[row]
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self._edit(entry))
        menu.addAction(icon("undo"), "Void…", lambda: self._void(entry))
        menu.exec(pos)

    def _edit(self, entry: ManagedEntry) -> None:
        """Replace ``entry``: the void and its replacement go in as one submit, so the log
        never holds the correction without what it corrects, or the other way round."""

        def submit(events: Iterable[Event]) -> None:
            void = build_void_event(entry.event, rollover_hour=self._rollover_hour, now=self._now())
            self._submit([void, *events])

        self._open_form(self, submit, entry.event)

    def _void(self, entry: ManagedEntry) -> None:
        VoidConfirmDialog(
            entry.event,
            entry.summary,
            self._submit,
            self._rollover_hour,
            self._now(),
            parent=self,
        ).exec()
