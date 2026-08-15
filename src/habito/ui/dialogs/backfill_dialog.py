"""Dialog to retroactively add a study session you did away from the app.

Produces backfilled events (``origin=backfilled``) via
:func:`habito.actions.backfill.build_backfill_events`
and hands them to the ``on_submit`` callback, which appends them to the store (each is then
committed+pushed, tagged ``[backfilled]``).

Qt's date/time editors replace the old free-text fields, so there is nothing left to
mis-type and no format to explain.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from habito.actions.backfill import build_backfill_events
from habito.config.models import TimeConfig
from habito.domain.events import Event
from habito.ui import theme
from habito.ui.widgets.controls import COMPACT_DIALOG_WIDTH, Stepper, StepSpinBox

SubmitCallback = Callable[[list[Event]], None]


class BackfillDialog(QDialog):
    def __init__(
        self,
        on_submit: SubmitCallback,
        default_work: int,
        default_break: int,
        default_rounds: int,
        habit: str,
        time_config: TimeConfig | None = None,
        today: date | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._tz = time_config or TimeConfig()
        self._today = today or date.today()
        self.setWindowTitle("Backfill")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build(default_work, default_break, default_rounds)

    def _build(self, work: int, brk: int, rounds: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # "Today" is the configured timezone's, which on a machine set to another zone
        # is not the same day the computer thinks it is.
        today = QDate(self._today.year, self._today.month, self._today.day)
        self._date = QDateEdit(today)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setMaximumDate(today)  # you can't backfill the future
        form.addRow("Date", self._date)

        self._time = QTimeEdit(QTime(6, 0))
        self._time.setDisplayFormat("HH:mm")
        form.addRow("Start time", Stepper(self._time))

        # A round length is remembered in fives — 25, 50 — where a break is tuned against
        # how long it actually felt, so they don't step alike. Same rule as Settings.
        self._work = self._spin(work, maximum=600, step=5)
        self._break = self._spin(brk, maximum=120)
        self._rounds = self._spin(rounds, maximum=24)
        form.addRow("Work minutes", Stepper(self._work))
        form.addRow("Break minutes", Stepper(self._break))
        form.addRow("Rounds", Stepper(self._rounds))
        root.addLayout(form)

        self._error = QLabel("")
        self._error.setWordWrap(True)
        self._error.setStyleSheet(f"color: {theme.ERROR};")
        root.addWidget(self._error)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText("Add && commit")
        ok.setObjectName("primary")
        ok.setDefault(True)
        buttons.accepted.connect(self._submit)
        buttons.rejected.connect(self.reject)  # Esc also closes, via QDialog
        root.addWidget(buttons)

    @staticmethod
    def _spin(value: int, *, maximum: int, step: int = 1) -> StepSpinBox:
        spin = StepSpinBox()
        spin.setRange(1, maximum)
        spin.setSingleStep(step)
        spin.setValue(value)
        spin.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return spin

    def _submit(self) -> None:
        try:
            events = build_backfill_events(
                self._start(),
                self._work.value(),
                self._break.value(),
                self._rounds.value(),
                habit=self._habit,
            )
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit(events)
        self.accept()

    def _start(self) -> datetime:
        qd, qt = self._date.date(), self._time.time()
        naive = datetime.combine(
            date(qd.year(), qd.month(), qd.day()), time(qt.hour(), qt.minute())
        )
        # What was typed is a wall-clock time in the configured zone, so it's stamped
        # with that zone's offset — not converted from the machine's.
        return self._tz.localize(naive)
