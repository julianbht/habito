"""The Settings dialog: Pomodoro format, daily goal, notification sound.

Kept off the main timer window so the timer stays uncluttered. Saving validates through the
controller (which persists to settings.json and applies to the engine) and reports back a
short confirmation or error.

The most sections of any dialog in the app, so it's the one sized to `LARGE_DIALOG_WIDTH`/
`_HEIGHT` (see `ui.widgets`) rather than growing past the window that opened it — the form
scrolls inside that fixed size, with Save pinned below the scroll area rather than
somewhere you might have to scroll to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from habito.config.models import SYSTEM_TZ, GoalsConfig, PomodoroConfig, TimeConfig
from habito.ui import sounds, theme
from habito.ui.svg_icons import icon
from habito.ui.widgets import (
    LARGE_DIALOG_HEIGHT,
    LARGE_DIALOG_WIDTH,
    Stepper,
    StepSpinBox,
    button,
    label,
)


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
    stretch_minutes: int = 0  # 0 means "no stretch goal", matching the spin's "Off"
    stretch_buffer_minutes: int = 10
    break_reminder_minutes: int = 3
    resume_window_minutes: int = 10
    timezone: str = SYSTEM_TZ
    rollover_hour: int = 3


class Controller(Protocol):
    def on_save_settings(self, values: SettingsValues) -> str | None: ...
    def on_preview_sound(self, sound: str) -> None: ...


# Sentinel entries in the sound combo: one opens a file picker, the other marks the row
# holding whatever file was picked.
_BROWSE = "__browse__"
_CUSTOM_SLOT = "__custom__"

_SYSTEM_LABEL = "System"


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
        break_reminder_minutes: int = 3,
        time_config: TimeConfig | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._c = controller
        self._last_sound = sound
        self._time = time_config or TimeConfig()
        self._last_timezone = self._time.timezone
        self.setWindowTitle("Settings")
        self.setMinimumWidth(LARGE_DIALOG_WIDTH)
        self.setMinimumHeight(LARGE_DIALOG_HEIGHT)
        self._build(pomodoro, goals or GoalsConfig(), sound, break_reminder_minutes)

    def _build(
        self, pomodoro: PomodoroConfig, goals: GoalsConfig, sound: str, break_reminder_minutes: int
    ) -> None:
        # Save stays outside the scroll area, pinned at the bottom — the thing the dialog
        # exists to do shouldn't need scrolling down to find, however long the form above
        # it grows.
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll, 1)

        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(20, 18, 20, 12)
        root.setSpacing(8)

        root.addWidget(label("Session format", "heading"))

        form = QFormLayout()
        form.setSpacing(8)
        self._break_spin = self._spin(pomodoro.break_minutes, maximum=120, suffix=" min")
        self._rounds_spin = self._spin(pomodoro.rounds, maximum=24)
        self._resume_window_spin = self._spin(
            pomodoro.resume_window_minutes, maximum=180, suffix=" min"
        )
        self._resume_window_spin.setToolTip(
            "Closing the app mid-round still offers to resume it, but only if you're back "
            "within this long"
        )
        form.addRow("Break length", Stepper(self._break_spin))
        form.addRow("Rounds", Stepper(self._rounds_spin))
        form.addRow("Resume window", Stepper(self._resume_window_spin))
        root.addLayout(form)

        root.addWidget(_rule())
        root.addWidget(label("Daily goal", "heading"))
        root.addLayout(self._build_goal_form(goals))

        root.addWidget(_rule())
        root.addWidget(label("Notifications", "heading"))
        root.addLayout(self._build_sound_row(sound))
        root.addLayout(self._build_reminder_form(break_reminder_minutes))

        root.addWidget(_rule())
        root.addWidget(label("Timezone", "heading"))
        root.addLayout(self._build_timezone_form())

        scroll.setWidget(content)

        footer = QVBoxLayout()
        footer.setContentsMargins(20, 8, 20, 14)
        footer.setSpacing(8)
        footer.addWidget(_rule())
        self._save_btn = button("Save", "primary")
        self._save_btn.setDefault(True)  # Enter saves
        self._save_btn.clicked.connect(self._save)
        footer.addWidget(self._save_btn)

        self._status = label("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.addWidget(self._status)
        outer.addLayout(footer)

        chain = [
            self._break_spin,
            self._rounds_spin,
            self._resume_window_spin,
            self._goal_spin,
            self._buffer_spin,
            self._stretch_spin,
            self._stretch_buffer_spin,
            self._sound_box,
            self._preview_btn,
            self._reminder_spin,
            self._tz_box,
            self._rollover_spin,
            self._save_btn,
        ]
        for earlier, later in zip(chain, chain[1:], strict=False):
            self.setTabOrder(earlier, later)

    def _build_goal_form(self, goals: GoalsConfig) -> QFormLayout:
        """How much study time earns a green day on the calendar."""
        form = QFormLayout()
        form.setSpacing(8)
        self._goal_spin = self._spin(goals.daily_minutes, maximum=24 * 60, suffix=" min", step=5)
        self._goal_spin.setToolTip("Study time that makes a day count")

        self._buffer_spin = self._spin(goals.buffer_minutes, minimum=0, maximum=60, suffix=" min")
        self._buffer_spin.setToolTip("Falling this far short still counts")

        # 0 is "no stretch goal" rather than a real value, so the spin shows Off there
        # instead of an absurd "0 min" the validator would then have to reject.
        self._stretch_spin = self._spin(
            goals.stretch_minutes or 0,
            minimum=0,
            maximum=24 * 60,
            suffix=" min",
            step=5,
        )
        self._stretch_spin.setSpecialValueText("Off")
        self._stretch_spin.setToolTip("A great day — earns a ★ on the calendar")

        # Its own allowance rather than reusing buffer_minutes: a great day is a bigger
        # ask, so it reasonably gets more slack for the same reason the daily goal has a
        # buffer at all.
        self._stretch_buffer_spin = self._spin(
            goals.stretch_buffer_minutes, minimum=0, maximum=60, suffix=" min"
        )
        self._stretch_buffer_spin.setToolTip("Falling this far short of the great day still counts")

        form.addRow("Goal", Stepper(self._goal_spin))
        form.addRow("Allowance", Stepper(self._buffer_spin))
        form.addRow("Great day", Stepper(self._stretch_spin))
        form.addRow("Great-day allowance", Stepper(self._stretch_buffer_spin))
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

        self._preview_btn = button("Test")
        self._preview_btn.setIcon(icon("volume_up"))
        self._preview_btn.setIconSize(QSize(16, 16))
        self._preview_btn.setToolTip("Hear the selected sound")
        self._preview_btn.clicked.connect(self._preview)
        row.addWidget(self._preview_btn)
        return row

    def _build_reminder_form(self, break_reminder_minutes: int) -> QFormLayout:
        form = QFormLayout()
        form.setSpacing(8)
        self._reminder_spin = self._spin(
            break_reminder_minutes, minimum=1, maximum=60, suffix=" min"
        )
        self._reminder_spin.setToolTip(
            "A second nudge this long after “Break over”, if it's still unacknowledged"
        )
        form.addRow("Reminder", Stepper(self._reminder_spin))
        return form

    def _build_timezone_form(self) -> QFormLayout:
        """Which wall clock a day is measured against, and where that day breaks."""
        form = QFormLayout()
        form.setSpacing(8)

        self._rollover_spin = self._spin(
            self._time.rollover_hour, minimum=0, maximum=23, suffix=":00"
        )
        self._rollover_spin.setToolTip(
            "Studying past this hour still counts toward the day before — so a session "
            "running past midnight isn't split in two"
        )

        self._tz_box = QComboBox()
        self._tz_box.addItem(_SYSTEM_LABEL, SYSTEM_TZ)
        self._tz_box.insertSeparator(self._tz_box.count())
        for name in self._time.choices():
            self._tz_box.addItem(name, name)
        self._tz_box.setCurrentIndex(max(0, self._tz_box.findData(self._last_timezone)))
        self._tz_box.setToolTip(
            "The wall clock your log and calendar use — set this if the computer's zone "
            "isn't where you are"
        )

        form.addRow("Zone", self._tz_box)
        form.addRow("New day starts", Stepper(self._rollover_spin))
        return form

    def selected_timezone(self) -> str:
        """The picked zone. A separator carries no data, so fall back rather than save it."""
        return self._tz_box.currentData() or self._last_timezone

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
    def _spin(
        value: int, *, maximum: int, minimum: int = 1, suffix: str = "", step: int = 1
    ) -> StepSpinBox:
        spin = StepSpinBox()
        spin.setRange(minimum, maximum)
        spin.setSingleStep(step)
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
            resume_window_minutes=self._resume_window_spin.value(),
            daily_minutes=self._goal_spin.value(),
            buffer_minutes=self._buffer_spin.value(),
            stretch_minutes=self._stretch_spin.value(),
            stretch_buffer_minutes=self._stretch_buffer_spin.value(),
            break_reminder_minutes=self._reminder_spin.value(),
            sound=self.selected_sound(),
            timezone=self.selected_timezone(),
            rollover_hour=self._rollover_spin.value(),
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
            self._status.setText("Saved — applies to your next session")
            self._status.setStyleSheet(f"color: {theme.OK};")
