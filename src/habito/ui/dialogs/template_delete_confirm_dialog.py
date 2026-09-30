"""Confirm deleting one session template — the "Delete…" action in the templates manager.

The config counterpart to `VoidConfirmDialog`: the same Compact shape, with the primary
named for the action. Nothing to reinstate afterwards and no reason to record, since a
template is a setting rather than a log entry — which is also why deleting one needs asking.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    button,
    button_row,
    label,
    primary_button,
)


class TemplateDeleteConfirmDialog(QDialog):
    def __init__(self, summary: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Delete template")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)
        root.addWidget(label(summary, "muted"))
        question = label("Delete this template? Sessions already logged with it are unaffected.")
        question.setWordWrap(True)
        root.addWidget(question)

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.ok_button = primary_button("Delete")
        self.ok_button.clicked.connect(self.accept)
        root.addLayout(button_row(self, primary=self.ok_button, dismiss=cancel_btn))
