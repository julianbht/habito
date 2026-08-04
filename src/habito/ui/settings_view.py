"""The Settings dialog: Pomodoro format, daily goal, notification sound, past sessions.

Kept off the main timer window so the timer stays uncluttered. Saving validates through the
controller (which persists to settings.toml and applies to the engine) and reports back a
short confirmation or error.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from habito.config.models import GoalsConfig, PomodoroConfig
from habito.ui import sounds, theme
from habito.ui.widgets import button, label


@dataclass(frozen=True)
class SettingsValues:
    """Everything the dialog can change, handed over in one piece.

    A single value object rather than a growing positional argument list — the dialog has
    picked up a section per feature and would otherwise be passing five loose ints.
    """

    break_minutes: int
    rounds: int
    daily_minutes: int
    buffer_minutes: int
    sound: str


class Controller(Protocol):
    def on_save_settings(self, values: SettingsValues) -> str | None: ...
    def on_open_backfill(self) -> None: ...
    def on_preview_sound(self, sound: str) -> None: ...


# Sentinel entries in the sound combo: one opens a file picker, the other marks the row
# holding whatever file was picked.
_BROWSE = "__browse__"
_CUSTOM_SLOT = "__custom__"


def _rule() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #43464d;")
    return line


class SettingsDialog(QDialog):
    def __init__(
        self,
        controller: Controller,
        pomodoro: PomodoroConfig,
        goals: GoalsConfig | None = None,
        sound: str = sounds.DEFAULT,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._c = controller
        self._last_sound = sound
        self.setWindowTitle("Settings")
        self.setMinimumWidth(340)
        self._build(pomodoro, goals or GoalsConfig(), sound)

    def _build(self, pomodoro: PomodoroConfig, goals: GoalsConfig, sound: str) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(8)

        root.addWidget(label("Session format", "heading"))

        form = QFormLayout()
        form.setSpacing(8)
        self._break_spin = self._spin(pomodoro.break_minutes, maximum=120, suffix=" min")
        self._rounds_spin = self._spin(pomodoro.rounds, maximum=24)
        form.addRow("Break length", self._break_spin)
        form.addRow("Rounds", self._rounds_spin)
        root.addLayout(form)

        root.addWidget(_rule())
        root.addWidget(label("Daily goal", "heading"))
        root.addLayout(self._build_goal_form(goals))

        root.addWidget(_rule())
        root.addWidget(label("Notification sound", "heading"))
        root.addLayout(self._build_sound_row(sound))

        root.addWidget(_rule())
        self._save_btn = button("Save")
        self._save_btn.setDefault(True)  # Enter saves
        self._save_btn.clicked.connect(self._save)
        root.addWidget(self._save_btn)

        self._status = label("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status)

        root.addWidget(_rule())
        root.addWidget(label("Missed a session?", "muted"))
        self._backfill_btn = button("Add past session")
        self._backfill_btn.clicked.connect(self._c.on_open_backfill)
        root.addWidget(self._backfill_btn)

        chain = [
            self._break_spin,
            self._rounds_spin,
            self._goal_spin,
            self._buffer_spin,
            self._sound_box,
            self._preview_btn,
            self._save_btn,
            self._backfill_btn,
        ]
        for earlier, later in zip(chain, chain[1:], strict=False):
            self.setTabOrder(earlier, later)

    def _build_goal_form(self, goals: GoalsConfig) -> QFormLayout:
        """How much study time earns a green day on the calendar."""
        form = QFormLayout()
        form.setSpacing(8)
        self._goal_spin = self._spin(goals.daily_minutes, maximum=24 * 60, suffix=" min")
        self._goal_spin.setSingleStep(5)
        self._goal_spin.setToolTip("Study time that makes a day count")

        self._buffer_spin = self._spin(
            goals.buffer_minutes, minimum=0, maximum=60, suffix=" min"
        )
        self._buffer_spin.setToolTip("Falling this far short still counts")

        form.addRow("Goal", self._goal_spin)
        form.addRow("Allowance", self._buffer_spin)
        return form

    def _build_sound_row(self, sound: str) -> QHBoxLayout:
        """The picker, plus a button to hear the choice before committing to it."""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._sound_box = QComboBox()
        for entry in sounds.CATALOGUE:
            self._sound_box.addItem(entry.label, entry.key)
        self._sound_box.insertSeparator(self._sound_box.count())
        self._sound_box.addItem("Choose a file…", _BROWSE)
        if sounds.is_custom(sound):
            self._add_custom(sound)
        self._sound_box.setCurrentIndex(max(0, self._sound_box.findData(sound)))
        self._sound_box.setToolTip("Played when a round or break ends")
        self._sound_box.activated.connect(self._on_sound_chosen)
        row.addWidget(self._sound_box, 1)

        self._preview_btn = button("▶ Test")
        self._preview_btn.setToolTip("Hear the selected sound")
        self._preview_btn.clicked.connect(self._preview)
        row.addWidget(self._preview_btn)
        return row

    def _add_custom(self, path: str) -> None:
        """Show a chosen file as its own entry, replacing any previous one."""
        existing = self._sound_box.findData(_CUSTOM_SLOT, Qt.ItemDataRole.UserRole + 1)
        if existing >= 0:
            self._sound_box.removeItem(existing)
        self._sound_box.insertItem(0, sounds.label_for(path), path)
        self._sound_box.setItemData(0, _CUSTOM_SLOT, Qt.ItemDataRole.UserRole + 1)
        self._sound_box.setItemData(0, path, Qt.ItemDataRole.ToolTipRole)
        self._sound_box.setCurrentIndex(0)

    def _on_sound_chosen(self, index: int) -> None:
        if self._sound_box.itemData(index) != _BROWSE:
            self._preview()
            return

        chosen, _ = QFileDialog.getOpenFileName(
            self, "Choose a notification sound", "", sounds.FILE_FILTER
        )
        if chosen:
            self._add_custom(chosen)
            self._preview()
        else:
            # Never leave "Choose a file…" showing as though it were the selection.
            self._sound_box.setCurrentIndex(max(0, self._sound_box.findData(self._last_sound)))

    @staticmethod
    def _spin(value: int, *, maximum: int, minimum: int = 1, suffix: str = "") -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return spin

    def selected_sound(self) -> str:
        chosen = self._sound_box.currentData()
        return self._last_sound if chosen in (None, _BROWSE) else chosen

    def values(self) -> SettingsValues:
        return SettingsValues(
            break_minutes=self._break_spin.value(),
            rounds=self._rounds_spin.value(),
            daily_minutes=self._goal_spin.value(),
            buffer_minutes=self._buffer_spin.value(),
            sound=self.selected_sound(),
        )

    def _preview(self) -> None:
        self._last_sound = self.selected_sound()
        self._c.on_preview_sound(self._last_sound)

    def _save(self) -> None:
        error = self._c.on_save_settings(self.values())
        if error:
            self._status.setText(error)
            self._status.setStyleSheet(f"color: {theme.ERROR};")
        else:
            self._status.setText("Saved ✓ — applies to your next session")
            self._status.setStyleSheet(f"color: {theme.OK};")
