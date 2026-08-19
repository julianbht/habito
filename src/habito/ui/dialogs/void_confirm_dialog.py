"""Confirm voiding one log entry — the "Void…" action in a manager row's right-click menu.

The standalone-entry counterpart to `RetractConfirmDialog`, and the same shape: a Compact
dialog with an optional reason and a primary button named for the action rather than a
literal "Yes". Produces one :class:`~habito.domain.events.EventVoided` via
:func:`habito.actions.voiding.build_void_event` and hands it to ``on_submit``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QVBoxLayout, QWidget

from habito.actions.voiding import build_void_event
from habito.domain.events import Event
from habito.ui import theme
from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    button,
    button_row,
    label,
    primary_button,
)

SubmitCallback = Callable[[list[Event]], None]


class VoidConfirmDialog(QDialog):
    def __init__(
        self,
        target: Event,
        summary: str,
        on_submit: SubmitCallback,
        rollover_hour: int,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._target = target
        self._summary = summary
        self._on_submit = on_submit
        self._rollover_hour = rollover_hour
        self._now = now
        self.setWindowTitle("Void entry")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        root.addWidget(label(self._summary, "muted"))

        question = label("Permanently void this entry? It stays in the log, struck through.")
        question.setWordWrap(True)
        root.addWidget(question)

        self.reason = QLineEdit()
        self.reason.setPlaceholderText("Reason (optional) — e.g. logged the wrong day")
        self.reason.setMaxLength(200)
        root.addWidget(self.reason)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self._ok_btn = primary_button("Void && commit")
        self._ok_btn.clicked.connect(self._submit)
        root.addLayout(button_row(self, primary=self._ok_btn, dismiss=cancel_btn))

    def _submit(self) -> None:
        try:
            event = build_void_event(
                self._target,
                rollover_hour=self._rollover_hour,
                now=self._now,
                reason=self.reason.text(),
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit([event])
        self.accept()
