"""Dialog to act on a past session: retract it, or tag/untag it after the fact.

Right-click a row for its menu (Manage tags…, Retract session…) rather than a single
selection-driven button — there are two different actions now, one destructive and one
not, and a context menu keeps that distinction visible instead of one button whose meaning
depends on what else you've clicked. Retracting opens `RetractConfirmDialog`, tagging opens
`SessionTagDialog` — both scoped to whichever row was clicked, this dialog stays a shell
around the list and the two sub-dialogs, same shape as `TagManagerDialog` around
`TagPicker`.

Sits in the ☰ menu where "Retract session…" used to, since it now covers strictly more —
this is the one place all of a habit's past sessions are listed to pick one from. The log
view stays read-only: this appends to the log like everything else does.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime
from uuid import UUID

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import (
    QDialog,
    QMenu,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from habito.domain.events import Event
from habito.projections.sessions import SessionSummary
from habito.ui.dialogs.retract_confirm_dialog import RetractConfirmDialog, describe_session
from habito.ui.dialogs.session_tag_dialog import SessionTagDialog
from habito.ui.svg_icons import icon
from habito.ui.widgets.controls import BROWSE_DIALOG_HEIGHT, BROWSE_DIALOG_WIDTH, button, label

SubmitCallback = Callable[[Iterable[Event]], None]

_SESSION_ROLE = Qt.ItemDataRole.UserRole + 1


class ManageSessionsDialog(QDialog):
    def __init__(
        self,
        sessions: Sequence[SessionSummary],
        session_tags_by_id: dict[UUID, set[str]],
        known_tags: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self._session_tags_by_id = dict(session_tags_by_id)
        self._known_tags = known_tags
        self._descriptions = descriptions
        # Already-retracted sessions are left out: there is nothing left to retract or
        # tag on one that no longer stands.
        self._sessions = [s for s in sessions if not s.retracted]
        self.setWindowTitle("Manage sessions")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        hint = "Right-click a session to retract it or manage its tags."
        root.addWidget(label(hint, "muted"))

        # A one-column QTreeWidget rather than QListWidget — same widget every other list
        # in the app uses (log view, tag pickers, shortcuts), so it picks up the theme's
        # tree styling for free instead of falling back to the native list style. A plain
        # non-editable list either way: large editable combo boxes have aborted the suite.
        self.list = QTreeWidget()
        self.list.setHeaderHidden(True)
        self.list.setIndentation(0)
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.list.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_context_menu)
        self._populate()
        root.addWidget(self.list, 1)

        self._empty_lbl = label("", "muted")
        if not self._sessions:
            self._empty_lbl.setText("Nothing to manage — the log has no standing sessions.")
        root.addWidget(self._empty_lbl)

        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn)

    def _populate(self) -> None:
        self.list.clear()
        for session in self._sessions:
            item = QTreeWidgetItem(self.list, [describe_session(session)])
            item.setData(0, _SESSION_ROLE, session.session_id)

    def _row_at(self, pos: QPoint) -> SessionSummary | None:
        item = self.list.itemAt(pos)
        if item is None:
            return None
        row = self.list.indexOfTopLevelItem(item)
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    def _on_context_menu(self, pos: QPoint) -> None:
        session = self._row_at(pos)
        if session is None:
            return
        menu = QMenu(self)
        menu.addAction(icon("sell"), "Manage tags…", lambda: self._open_tag_dialog(session))
        menu.addAction(icon("undo"), "Retract session…", lambda: self._open_retract_dialog(session))
        menu.exec(self.list.viewport().mapToGlobal(pos))

    def _open_tag_dialog(self, session: SessionSummary) -> None:
        current = self._session_tags_by_id.get(session.session_id, set())
        dialog = SessionTagDialog(
            session.session_id,
            current,
            self._known_tags,
            self._descriptions,
            self._on_submit,
            self._habit,
            self._now,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._session_tags_by_id[session.session_id] = set(dialog.tag_picker.selected_tags())

    def _open_retract_dialog(self, session: SessionSummary) -> None:
        dialog = RetractConfirmDialog(session, self._on_submit, self._habit, self._now, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._sessions = [s for s in self._sessions if s.session_id != session.session_id]
            self._populate()
            if not self._sessions:
                self._empty_lbl.setText("Nothing to manage — the log has no standing sessions.")
