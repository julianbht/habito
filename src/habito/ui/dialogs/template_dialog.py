"""Add a session template, or edit one — the form behind the templates manager.

Same shape as ``WakeUpDialog``: Compact, one form, an error line above a Cancel / primary
row, and a ``replacing`` argument that only seeds the fields and renames the window and its
button. Unlike the log forms it produces a config value, not an event, so ``on_submit``
answers back: the list-wide rules (no two templates with the same label) are the manager's
to check, and a refusal keeps the form open with the reason shown.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QFormLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from habito.config.models import SessionTemplate
from habito.ui import theme
from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    Stepper,
    StepSpinBox,
    button,
    button_row,
    primary_button,
)

SubmitCallback = Callable[[SessionTemplate], str | None]
"""Hand over the finished template; ``None`` when it was accepted, else why not."""


class TemplateDialog(QDialog):
    def __init__(
        self,
        on_submit: SubmitCallback,
        replacing: SessionTemplate | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._editing = replacing is not None
        self.setWindowTitle("Edit template" if self._editing else "New template")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build(replacing or SessionTemplate())

    def _build(self, seed: SessionTemplate) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self.name_edit = QLineEdit(seed.name or "")
        self.name_edit.setPlaceholderText("Optional, e.g. Deep work")
        self.name_edit.setMaxLength(40)
        form.addRow("Name", self.name_edit)

        # Whole minutes: a sub-minute round is a testing convenience set from the timer's
        # own duration field, not something a template form needs to offer.
        self.work_spin = _spin(max(1, round(seed.work_minutes)), maximum=180, step=5)
        self.break_spin = _spin(seed.break_minutes, maximum=120, step=1)
        self.rounds_spin = _spin(seed.rounds, maximum=24, step=1, suffix="")
        form.addRow("Work", Stepper(self.work_spin))
        form.addRow("Break", Stepper(self.break_spin))
        form.addRow("Rounds", Stepper(self.rounds_spin))
        root.addLayout(form)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)  # Esc also closes, via QDialog
        self.ok_button = primary_button("Save" if self._editing else "Add")
        self.ok_button.clicked.connect(self._submit)
        root.addLayout(button_row(self, primary=self.ok_button, dismiss=cancel_btn))

    def template(self) -> SessionTemplate:
        return SessionTemplate(
            name=self.name_edit.text(),
            work_minutes=self.work_spin.value(),
            break_minutes=self.break_spin.value(),
            rounds=self.rounds_spin.value(),
        )

    def _submit(self) -> None:
        try:
            template = self.template()
        except ValidationError as exc:
            self._error.setText(exc.errors()[0]["msg"])
            return
        error = self._on_submit(template)
        if error is not None:
            self._error.setText(error)
            return
        self.accept()


def _spin(value: int, *, maximum: int, step: int, suffix: str = " min") -> StepSpinBox:
    spin = StepSpinBox()
    spin.setRange(1, maximum)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setSuffix(suffix)
    spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
    return spin
