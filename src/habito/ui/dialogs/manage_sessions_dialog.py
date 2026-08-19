"""Manage the study habit's past sessions: back one, retract one, or tag it after the fact.

The one place a session is acted on. "Backfill…" is its primary button, so adding a session
and correcting one live in the same window rather than two menu entries you have to know
are related. Row actions are a right-click menu (Manage tags…, Retract session…): two
actions, one destructive and one not, kept visibly distinct instead of one button whose
meaning depends on what else is selected. The tag catalog is reached through "Manage
tags…" as well — its picker is the catalog manager (see `CatalogPicker`), so there is no
separate button for it.

A session is voided as a whole by ``session_id`` (`RetractConfirmDialog`), not entry by
entry — which is why sleep and workouts use `EntryManagerDialog` instead of this. The list
widget itself (`EntryList`) is shared with them.

`reload` is called after anything that writes, so a session backfilled from inside this
dialog appears in the list behind it — the snapshot is never patched by hand.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QHBoxLayout, QMenu, QVBoxLayout, QWidget

from habito.domain.events import Event
from habito.projections.sessions import SessionSummary
from habito.ui.dialogs.retract_confirm_dialog import RetractConfirmDialog, describe_session
from habito.ui.dialogs.session_tag_dialog import SessionTagDialog
from habito.ui.svg_icons import icon
from habito.ui.widgets.controls import (
    BROWSE_DIALOG_HEIGHT,
    BROWSE_DIALOG_WIDTH,
    button,
    primary_button,
)
from habito.ui.widgets.entry_list import EntryList

SubmitCallback = Callable[[Iterable[Event]], None]

_HINT = "Right-click a session to retract it or manage its tags."
_EMPTY = "Nothing to manage — the log has no standing sessions."


@dataclass(frozen=True)
class SessionsSnapshot:
    """Everything the dialog shows, folded from the log in one go so the four parts can
    never disagree about which sessions and tags currently stand."""

    sessions: Sequence[SessionSummary]
    tags_by_session: Mapping[UUID, set[str]]
    known_tags: list[str]
    descriptions: Mapping[str, str]


class ManageSessionsDialog(QDialog):
    def __init__(
        self,
        *,
        reload: Callable[[], SessionsSnapshot],
        on_submit: SubmitCallback,
        habit: str,
        now: Callable[[], datetime],
        open_backfill: Callable[[QWidget], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reload = reload
        self._on_submit = on_submit
        self._habit = habit
        # Read afresh per correction, not fixed at construction — a retraction records
        # when it was made, and this dialog can sit open for a long time.
        self._now = now
        self._open_backfill = open_backfill
        self._sessions: list[SessionSummary] = []
        self._snapshot = SessionsSnapshot((), {}, [], {})
        self.setWindowTitle("Manage sessions")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build()
        self._refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        self.list = EntryList(_HINT, _EMPTY)
        self.list.row_menu_requested.connect(self._on_row_menu)
        root.addWidget(self.list, 1)

        actions = QHBoxLayout()
        self.backfill_button = primary_button("Backfill…")
        self.backfill_button.clicked.connect(self._backfill)
        actions.addWidget(self.backfill_button)
        actions.addStretch(1)
        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        root.addLayout(actions)

    def _refresh(self) -> None:
        self._snapshot = self._reload()
        # Already-retracted sessions are left out: there is nothing left to retract or tag
        # on one that no longer stands.
        self._sessions = [s for s in self._snapshot.sessions if not s.retracted]
        self.list.set_rows([describe_session(s) for s in self._sessions])

    def _submit(self, events: Iterable[Event]) -> None:
        self._on_submit(events)
        self._refresh()

    def _backfill(self) -> None:
        self._open_backfill(self)
        self._refresh()

    def _on_row_menu(self, row: int, pos: QPoint) -> None:
        if not 0 <= row < len(self._sessions):
            return
        session = self._sessions[row]
        menu = QMenu(self)
        menu.addAction(icon("sell"), "Manage tags…", lambda: self._open_tag_dialog(session))
        menu.addAction(icon("undo"), "Retract session…", lambda: self._open_retract_dialog(session))
        menu.exec(pos)

    def _open_tag_dialog(self, session: SessionSummary) -> None:
        SessionTagDialog(
            session.session_id,
            self._snapshot.tags_by_session.get(session.session_id, set()),
            self._snapshot.known_tags,
            dict(self._snapshot.descriptions),
            self._submit,
            self._habit,
            self._now(),
            parent=self,
        ).exec()

    def _open_retract_dialog(self, session: SessionSummary) -> None:
        RetractConfirmDialog(
            session,
            self._submit,
            self._habit,
            self._now(),
            parent=self,
        ).exec()
