"""Dialog to void a session that shouldn't stand — the wrong date, or time the timer
recorded that wasn't real.

Produces :class:`~habito.domain.events.SessionRetracted` events via
:func:`habito.actions.retraction.build_retraction_events` and hands them to ``on_submit``, which
appends them to the store (each is then committed+pushed).

Sits in the ☰ menu beside Backfill, the other correction made by hand. The log view stays
read-only: this appends to the log like everything else does.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from habito.actions.retraction import build_retraction_events
from habito.domain.events import Event, Origin
from habito.projections.sessions import SessionSummary
from habito.ui import theme
from habito.ui.widgets import BROWSE_DIALOG_HEIGHT, BROWSE_DIALOG_WIDTH, format_duration, label

SubmitCallback = Callable[[list[Event]], None]

_SESSION_ROLE = Qt.ItemDataRole.UserRole + 1


def describe_session(session: SessionSummary) -> str:
    """``2026-08-04 06:00 · 1h 40m · backfilled`` — enough to tell two sessions apart."""
    parts = [
        session.started.strftime("%Y-%m-%d %H:%M"),
        format_duration(session.work_seconds),
    ]
    if session.origin is Origin.backfilled:
        parts.append("backfilled")
    if len(session.days) > 1:
        parts.append(f"spans {len(session.days)} days")
    return " · ".join(parts)


class RetractDialog(QDialog):
    def __init__(
        self,
        sessions: Sequence[SessionSummary],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        # Already-retracted sessions are left out: there is nothing left to void, and a
        # second retraction would say nothing the first doesn't.
        self._sessions = [s for s in sessions if not s.retracted]
        self.setWindowTitle("Retract session")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        hint = "Pick the session to void. It stays in the log, struck through."
        root.addWidget(label(hint, "muted"))

        # A one-column QTreeWidget rather than QListWidget — same widget every other list
        # in the app uses (log view, tag pickers, shortcuts), so it picks up the theme's
        # tree styling (row height, font size, accent-coloured selection) for free instead
        # of falling back to whatever the native list style draws. A plain non-editable
        # list either way: large editable combo boxes have aborted the Qt suite.
        self.list = QTreeWidget()
        self.list.setHeaderHidden(True)
        self.list.setIndentation(0)
        self.list.setRootIsDecorated(False)
        self.list.setAlternatingRowColors(True)
        self.list.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.list.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        for session in self._sessions:
            item = QTreeWidgetItem(self.list, [describe_session(session)])
            item.setData(0, _SESSION_ROLE, session.session_id)
        if self._sessions:
            # Newest first, the one a fresh mistake will be.
            first = self.list.topLevelItem(0)
            assert first is not None  # just populated above, from a non-empty _sessions
            self.list.setCurrentItem(first)
        root.addWidget(self.list, 1)

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (optional) — e.g. entered under the wrong date")
        self.reason.setMaxLength(200)
        root.addWidget(self.reason)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = self._buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Retract && commit")
        ok.setObjectName("primary")
        ok.setDefault(True)
        ok.setEnabled(bool(self._sessions))
        if not self._sessions:
            self._error.setText("Nothing to retract — the log has no standing sessions.")
        self._buttons.accepted.connect(self._submit)
        self._buttons.rejected.connect(self.reject)  # Esc also closes, via QDialog
        root.addWidget(self._buttons)

    def _selected(self) -> SessionSummary | None:
        item = self.list.currentItem()
        # Stubbed as always returning QTreeWidgetItem; nothing selected returns None.
        if item is None:  # pyright: ignore[reportUnnecessaryComparison]
            return None
        row = self.list.indexOfTopLevelItem(item)
        if 0 <= row < len(self._sessions):
            return self._sessions[row]
        return None

    def _submit(self) -> None:
        session = self._selected()
        if session is None:
            self._error.setText("Pick a session first.")
            return
        try:
            events = build_retraction_events(
                session.session_id,
                session.days,
                habit=self._habit,
                now=self._now,
                reason=self.reason.text(),
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit(list(events))
        self.accept()
