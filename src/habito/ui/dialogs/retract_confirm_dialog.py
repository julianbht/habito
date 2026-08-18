"""Confirm voiding one session — the "Retract session…" action in a `ManageSessionsDialog`
row's right-click menu.

A Compact dialog like `CatalogEditDialog`/`BackfillDialog` (one ask plus a short optional
field), not a `PromptDialog` — this isn't an always-on-top interruption, it's an ordinary
modal opened on purpose. The primary button stays named for the action ("Retract &
commit"), the same convention every other primary button in the app follows, rather than a
literal "Yes" — the button *is* the confirmation.

Produces :class:`~habito.domain.events.SessionRetracted` events via
:func:`habito.actions.retraction.build_retraction_events` and hands them to ``on_submit``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from habito.actions.retraction import build_retraction_events
from habito.domain.events import Event, Origin
from habito.projections.sessions import SessionSummary
from habito.ui import theme
from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    button,
    format_duration,
    label,
    primary_button,
)

SubmitCallback = Callable[[list[Event]], None]


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


class RetractConfirmDialog(QDialog):
    def __init__(
        self,
        session: SessionSummary,
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._session = session
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self.setWindowTitle("Retract session")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        root.addWidget(label(describe_session(self._session), "muted"))

        question = label("Permanently retract this session? It stays in the log, struck through.")
        question.setWordWrap(True)
        root.addWidget(question)

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (optional) — e.g. entered under the wrong date")
        self.reason.setMaxLength(200)
        root.addWidget(self.reason)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(cancel_btn)
        self._ok_btn = primary_button("Retract && commit")
        self._ok_btn.clicked.connect(self._submit)
        row.addWidget(self._ok_btn)
        root.addLayout(row)

    def _submit(self) -> None:
        try:
            events = build_retraction_events(
                self._session.session_id,
                self._session.days,
                habit=self._habit,
                now=self._now,
                reason=self.reason.text(),
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit(list(events))
        self.accept()
