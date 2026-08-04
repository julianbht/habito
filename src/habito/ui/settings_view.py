"""The Settings dialog: edit the Pomodoro format and add past sessions.

Kept off the main timer window so the timer stays uncluttered. Saving validates through the
controller (which persists to settings.toml and applies to the engine) and reports back a
short confirmation or error.
"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from habito.config.models import PomodoroConfig
from habito.ui import theme


class Controller(Protocol):
    def on_save_settings(self, brk: int, rounds: int) -> str | None: ...
    def on_open_backfill(self) -> None: ...


class SettingsDialog(QDialog):
    def __init__(
        self,
        controller: Controller,
        pomodoro: PomodoroConfig,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._c = controller
        self.setWindowTitle("Settings")
        self.setMinimumWidth(300)
        self._build(pomodoro)

    def _build(self, pomodoro: PomodoroConfig) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(8)

        root.addWidget(QLabel("Session format", objectName="heading"))
        root.addWidget(QLabel("Work length is set on the timer.", objectName="muted"))

        form = QFormLayout()
        form.setSpacing(8)
        self._break_spin = self._spin(pomodoro.break_minutes, maximum=120)
        self._rounds_spin = self._spin(pomodoro.rounds, maximum=24)
        form.addRow("Break minutes", self._break_spin)
        form.addRow("Rounds", self._rounds_spin)
        root.addLayout(form)

        self._save_btn = QPushButton("Save")
        self._save_btn.setDefault(True)  # Enter saves
        self._save_btn.clicked.connect(self._save)
        root.addWidget(self._save_btn)

        self._status = QLabel("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status)

        rule = QFrame()
        rule.setFrameShape(QFrame.Shape.HLine)
        rule.setStyleSheet("color: #43464d;")
        root.addWidget(rule)

        root.addWidget(QLabel("Missed a session?", objectName="muted"))
        self._backfill_btn = QPushButton("Add past session")
        self._backfill_btn.clicked.connect(self._c.on_open_backfill)
        root.addWidget(self._backfill_btn)

        for earlier, later in (
            (self._break_spin, self._rounds_spin),
            (self._rounds_spin, self._save_btn),
            (self._save_btn, self._backfill_btn),
        ):
            self.setTabOrder(earlier, later)

    @staticmethod
    def _spin(value: int, *, maximum: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(1, maximum)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return spin

    def _save(self) -> None:
        error = self._c.on_save_settings(self._break_spin.value(), self._rounds_spin.value())
        if error:
            self._status.setText(error)
            self._status.setStyleSheet(f"color: {theme.ERROR};")
        else:
            self._status.setText("Saved ✓ — applies to your next session")
            self._status.setStyleSheet(f"color: {theme.OK};")
