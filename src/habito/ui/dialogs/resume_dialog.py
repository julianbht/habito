"""Prompt offering to resume a session the last launch cut short.

Shown once, right after the main window comes up (see ``HabitoApp._offer_resume``).
Deliberately a choice, not automatic: closing the window early might have been on
purpose, so resuming has to be something you ask for, not something sprung on you.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from habito.projections.resume import ResumableSession, ResumePhase
from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    button,
    button_row,
    format_duration,
    label,
    primary_button,
)


def describe_resumable(resumable: ResumableSession) -> str:
    phase = "work" if resumable.phase is ResumePhase.work else "break"
    return (
        f"Round {resumable.round_index} of {resumable.planned_rounds} was cut short. "
        f"{format_duration(resumable.remaining_seconds)} left on the {phase} — resume it?"
    )


class ResumePromptDialog(QDialog):
    def __init__(self, resumable: ResumableSession, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Resume last session?")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build(resumable)

    def _build(self, resumable: ResumableSession) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        message = label(describe_resumable(resumable))
        message.setWordWrap(True)
        root.addWidget(message)

        dismiss_btn = button("Not now")
        dismiss_btn.clicked.connect(self.reject)  # Esc also closes, via QDialog
        self.resume_button = primary_button("Resume")
        self.resume_button.clicked.connect(self.accept)
        root.addLayout(button_row(self, primary=self.resume_button, dismiss=dismiss_btn))
