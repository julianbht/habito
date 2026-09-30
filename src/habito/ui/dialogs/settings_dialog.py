"""The Settings dialog: Pomodoro format, goals, notification sound.

Kept off the main timer window so the timer stays uncluttered. Saving validates through the
controller (which persists to settings.json and applies to the engine) and reports back a
short confirmation or error.

The most sections of any dialog in the app, so it's the one sized to `LARGE_DIALOG_WIDTH`/
`_HEIGHT` (see `ui.widgets.controls`) rather than growing past the window that opened it — the form
scrolls inside that fixed size, with Save pinned below the scroll area rather than
somewhere you might have to scroll to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from typing import Protocol

from PySide6.QtCore import QSize, Qt, QTime
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QScrollArea,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from habito.config.models import SYSTEM_TZ, GoalsConfig, PomodoroConfig, TimeConfig, WakeUpConfig
from habito.ui import sounds, theme
from habito.ui.svg_icons import icon
from habito.ui.widgets.controls import (
    LARGE_DIALOG_HEIGHT,
    LARGE_DIALOG_WIDTH,
    NoWheelComboBox,
    Stepper,
    StepSpinBox,
    button,
    button_row,
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
    low_minutes: int
    low_buffer_minutes: int
    sound: str
    middle_minutes: int = 0  # 0 means "no middle goal", matching the spin's "Off"
    middle_buffer_minutes: int = 10
    high_minutes: int = 0
    high_buffer_minutes: int = 15
    break_reminder_minutes: int = 3
    resume_window_minutes: int = 10
    timezone: str = SYSTEM_TZ
    rollover_hour: int = 3
    # None when the wake-up section wasn't shown (extras disabled) — leaves the config's
    # current value alone rather than asserting a value nobody had a chance to edit.
    default_wake_time: time | None = None
    default_bedtime: time | None = None


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
        wakeup: WakeUpConfig | None = None,
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
        self._build(pomodoro, goals or GoalsConfig(), sound, break_reminder_minutes, wakeup)

    def _build(
        self,
        pomodoro: PomodoroConfig,
        goals: GoalsConfig,
        sound: str,
        break_reminder_minutes: int,
        wakeup: WakeUpConfig | None,
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
        root.addWidget(label("Goals", "heading"))
        root.addLayout(self._build_goal_form(goals))

        root.addWidget(_rule())
        root.addWidget(label("Notifications", "heading"))
        root.addLayout(self._build_sound_row(sound))
        root.addLayout(self._build_reminder_form(break_reminder_minutes))

        root.addWidget(_rule())
        root.addWidget(label("Timezone", "heading"))
        root.addLayout(self._build_timezone_form())

        self._wake_time_edit: QTimeEdit | None = None
        self._bedtime_edit: QTimeEdit | None = None
        if wakeup is not None:
            root.addWidget(_rule())
            root.addWidget(label("Wake-up defaults", "heading"))
            root.addLayout(self._build_wakeup_form(wakeup))

        scroll.setWidget(content)

        footer = QVBoxLayout()
        footer.setContentsMargins(20, 8, 20, 14)
        footer.setSpacing(8)
        footer.addWidget(_rule())
        self._save_btn = button("Save", "primary")
        self._save_btn.setDefault(True)  # Enter saves
        self._save_btn.clicked.connect(self._save)
        # Right-aligned in a button_row like every other dialog — not centred, and not
        # (via a bare addWidget into a QVBoxLayout) stretched to the full width.
        footer.addLayout(button_row(self, primary=self._save_btn))

        self._status = label("")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        footer.addWidget(self._status)
        outer.addLayout(footer)

        chain: list[QWidget] = [
            self._break_spin,
            self._rounds_spin,
            self._resume_window_spin,
            self._low_spin,
            self._low_buffer_spin,
            self._middle_spin,
            self._middle_buffer_spin,
            self._high_spin,
            self._high_buffer_spin,
            self._sound_box,
            self._preview_btn,
            self._reminder_spin,
            self._tz_box,
            self._rollover_spin,
        ]
        if self._wake_time_edit is not None and self._bedtime_edit is not None:
            chain += [self._wake_time_edit, self._bedtime_edit]
        chain.append(self._save_btn)
        for earlier, later in zip(chain, chain[1:], strict=False):
            self.setTabOrder(earlier, later)

    def _build_wakeup_form(self, wakeup: WakeUpConfig) -> QFormLayout:
        """Defaults the Log-wake-up dialog opens with, so most days are just a click."""
        form = QFormLayout()
        form.setSpacing(8)

        wake = wakeup.default_wake_time
        self._wake_time_edit = QTimeEdit(QTime(wake.hour, wake.minute))
        self._wake_time_edit.setDisplayFormat("HH:mm")

        bed = wakeup.default_bedtime
        self._bedtime_edit = QTimeEdit(QTime(bed.hour, bed.minute))
        self._bedtime_edit.setDisplayFormat("HH:mm")

        form.addRow("Wake time", Stepper(self._wake_time_edit))
        form.addRow("Bedtime", Stepper(self._bedtime_edit))
        return form

    def _build_goal_form(self, goals: GoalsConfig) -> QFormLayout:
        """How much study time earns a green day, and a star or two on top."""
        form = QFormLayout()
        form.setSpacing(8)
        self._low_spin = self._spin(goals.low_minutes, maximum=24 * 60, suffix=" min", step=5)
        self._low_spin.setToolTip("Study time that makes a day count — turns it green")
        self._low_buffer_spin = self._allowance_spin(goals.low_buffer_minutes, "the low goal")

        self._middle_spin = self._optional_goal_spin(goals.middle_minutes, "earns a ★")
        self._middle_buffer_spin = self._allowance_spin(
            goals.middle_buffer_minutes, "the middle goal"
        )
        self._high_spin = self._optional_goal_spin(goals.high_minutes, "earns ★★")
        self._high_buffer_spin = self._allowance_spin(goals.high_buffer_minutes, "the high goal")

        form.addRow("Low", Stepper(self._low_spin))
        form.addRow("Low allowance", Stepper(self._low_buffer_spin))
        form.addRow("Middle", Stepper(self._middle_spin))
        form.addRow("Middle allowance", Stepper(self._middle_buffer_spin))
        form.addRow("High", Stepper(self._high_spin))
        form.addRow("High allowance", Stepper(self._high_buffer_spin))
        return form

    def _optional_goal_spin(self, minutes: int | None, reward: str) -> StepSpinBox:
        # 0 is "no such goal" rather than a real value, so the spin shows Off there
        # instead of an absurd "0 min" the validator would then have to reject.
        spin = self._spin(minutes or 0, minimum=0, maximum=24 * 60, suffix=" min", step=5)
        spin.setSpecialValueText("Off")
        spin.setToolTip(f"Reaching it {reward} on the calendar")
        return spin

    def _allowance_spin(self, minutes: int, goal: str) -> StepSpinBox:
        spin = self._spin(minutes, minimum=0, maximum=60, suffix=" min")
        spin.setToolTip(f"Falling this far short of {goal} still counts")
        return spin

    def _build_sound_row(self, sound: str) -> QHBoxLayout:
        """The picker, plus a button to hear the choice before committing to it."""
        row = QHBoxLayout()
        row.setSpacing(8)

        self._sound_box = NoWheelComboBox()
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

        self._tz_box = NoWheelComboBox()
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
            low_minutes=self._low_spin.value(),
            low_buffer_minutes=self._low_buffer_spin.value(),
            middle_minutes=self._middle_spin.value(),
            middle_buffer_minutes=self._middle_buffer_spin.value(),
            high_minutes=self._high_spin.value(),
            high_buffer_minutes=self._high_buffer_spin.value(),
            break_reminder_minutes=self._reminder_spin.value(),
            sound=self.selected_sound(),
            timezone=self.selected_timezone(),
            rollover_hour=self._rollover_spin.value(),
            default_wake_time=self._qtime(self._wake_time_edit),
            default_bedtime=self._qtime(self._bedtime_edit),
        )

    @staticmethod
    def _qtime(edit: QTimeEdit | None) -> time | None:
        if edit is None:
            return None
        qt = edit.time()
        return time(qt.hour(), qt.minute())

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
