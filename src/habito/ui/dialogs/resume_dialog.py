"""Prompt offering to resume a session the last launch cut short.

Shown once, right after the main window comes up (see ``HabitoApp._offer_resume``).
Deliberately a choice, not automatic: closing the window early might have been on
purpose, so resuming has to be something you ask for, not something sprung on you.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QVBoxLayout, QWidget

from habito.projections.resume import ResumableSession, ResumePhase
from habito.ui.widgets.controls import COMPACT_DIALOG_WIDTH, format_duration, label


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

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Resume")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Not now")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)  # Esc also closes, via QDialog
        root.addWidget(buttons)
