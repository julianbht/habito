"""Dialog to log a workout done away from the app — the workout extra's mirror of
``WakeUpDialog``, with a checkable ``CatalogPicker`` added so more than one workout can be
picked for the same date/time in one go (see CLAUDE.md § Extras for the wake-up shape this
follows, and ``WorkoutLogged``'s own docstring for why a list, not one event per workout).

Sized at ``BROWSE_DIALOG_WIDTH``/``_HEIGHT`` from the start, unlike ``SessionCompleteDialog``,
which starts Compact and only grows once its tag picker is revealed: there, attaching a tag
is optional and skipping it is the common case, so a control nobody usually touches
shouldn't be the first thing on screen. Here, picking at least one workout *is* the point of
opening this dialog — there's no "skip this" case to keep small for — so there's no
collapsed state worth having.

Creating a workout type inline ("+ New workout") writes its ``CatalogEditDialog`` event(s)
immediately, through ``on_describe_workout`` — the same split ``SessionCompleteDialog``
makes between "describe the catalog entry" (writes now) and "log this instance" (writes on
submit, via ``build_workout_logged_event``, only once you press "Log & commit").

The only ☰ entry point for workouts, deliberately — there's no separate "Manage workouts…"
the way tags get a ``CatalogManagerDialog``. The picker embedded here (double-click to edit
a description, "+ New workout" to add one) already covers everything a standalone manager
would, since — unlike a tag's checkable picker, which only ever appears mid-session-tagging
— this dialog is already its own top-level menu entry with nothing else it needs to be
nested inside. Opening it just to fix a workout's description and pressing Cancel afterwards
is a perfectly normal use, not a workaround.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from habito.actions.workout import (
    build_workout_created_event,
    build_workout_described_event,
    build_workout_logged_event,
)
from habito.config.models import TimeConfig
from habito.domain.events import Event
from habito.ui import theme
from habito.ui.dialogs.catalog_edit_dialog import SubmitCallback as DescribeWorkoutCallback
from habito.ui.widgets.catalog_picker import CatalogPicker
from habito.ui.widgets.controls import BROWSE_DIALOG_HEIGHT, BROWSE_DIALOG_WIDTH, Stepper

SubmitCallback = Callable[[list[Event]], None]


class WorkoutLogDialog(QDialog):
    def __init__(
        self,
        on_submit: SubmitCallback,
        on_describe_workout: DescribeWorkoutCallback,
        known_workouts: list[str],
        descriptions: dict[str, str],
        habit: str,
        now: datetime,
        time_config: TimeConfig | None = None,
        today: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._tz = time_config or TimeConfig()
        self._today = today or date.today()
        self.setWindowTitle("Log workout")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build(known_workouts, descriptions, on_describe_workout, habit, now)

    def _build(
        self,
        known_workouts: list[str],
        descriptions: dict[str, str],
        on_describe_workout: DescribeWorkoutCallback,
        habit: str,
        now: datetime,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # "Today" is the configured timezone's, which on a machine set to another zone is
        # not the same day the computer thinks it is — same reasoning as Backfill/WakeUp.
        today = QDate(self._today.year, self._today.month, self._today.day)
        self._date = QDateEdit(today)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setMaximumDate(today)  # you can't log a workout in the future
        form.addRow("Date", self._date)

        # Defaults to right now — you're most often logging a workout you just finished,
        # unlike wake-up/bedtime, which have their own configured defaults instead.
        default_time = now.time()
        self._time = QTimeEdit(QTime(default_time.hour, default_time.minute))
        self._time.setDisplayFormat("HH:mm")
        form.addRow("Time", Stepper(self._time))
        root.addLayout(form)

        self.picker = CatalogPicker(
            known_workouts,
            descriptions,
            on_describe_workout,
            lambda workout: build_workout_created_event(workout, habit=habit, now=now),
            lambda workout, description: build_workout_described_event(
                workout, description, habit=habit, now=now
            ),
            "workout",
            checkable=True,
        )
        root.addWidget(self.picker, 1)

        new_row = QHBoxLayout()
        new_row.addWidget(self.picker.new_button)
        new_row.addStretch(1)
        root.addLayout(new_row)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Log && commit")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)  # Esc also closes, via QDialog
        root.addWidget(buttons)

    def _submit(self) -> None:
        try:
            event = build_workout_logged_event(
                self._when(), self.picker.selected(), habit=self._habit
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit([event])
        self.accept()

    def _when(self) -> datetime:
        qd, qt = self._date.date(), self._time.time()
        naive = datetime.combine(
            date(qd.year(), qd.month(), qd.day()), time(qt.hour(), qt.minute())
        )
        # What was typed is a wall-clock time in the configured zone, so it's stamped with
        # that zone's offset — not converted from the machine's. Same gotcha as
        # Backfill/WakeUp; see CLAUDE.md § Time.
        return self._tz.localize(naive)
