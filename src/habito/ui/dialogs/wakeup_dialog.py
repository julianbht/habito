"""Dialog to log when you woke up, entered later at the PC.

Modeled on ``BackfillDialog`` for a consistent feel: same compact size, same date/time
field pattern, same error-label-then-primary-button shape. Produces a backfilled
``WakeUpLogged`` via :func:`habito.actions.wakeup.build_wakeup_event` and hands it to the
``on_submit`` callback, which appends it to the wake-up store (then committed+pushed,
tagged ``[backfilled]``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QTime
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

from habito.actions.wakeup import build_wakeup_event
from habito.config.models import TimeConfig
from habito.domain.events import Event
from habito.ui import theme
from habito.ui.widgets.controls import COMPACT_DIALOG_WIDTH, Stepper

SubmitCallback = Callable[[list[Event]], None]


class WakeUpDialog(QDialog):
    def __init__(
        self,
        on_submit: SubmitCallback,
        default_wake_time: time,
        default_bedtime: time,
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
        self.setWindowTitle("Log wake-up")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build(default_wake_time, default_bedtime)

    def _build(self, default_wake_time: time, default_bedtime: time) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # "Today" is the configured timezone's, which on a machine set to another zone
        # is not the same day the computer thinks it is — same reasoning as Backfill.
        today = QDate(self._today.year, self._today.month, self._today.day)
        self._date = QDateEdit(today)
        self._date.setCalendarPopup(True)
        self._date.setDisplayFormat("yyyy-MM-dd")
        self._date.setMaximumDate(today)  # you can't log a wake-up in the future
        form.addRow("Date", self._date)

        self._wake_time = QTimeEdit(QTime(default_wake_time.hour, default_wake_time.minute))
        self._wake_time.setDisplayFormat("HH:mm")
        form.addRow("Wake time", Stepper(self._wake_time))

        self._bedtime = QTimeEdit(QTime(default_bedtime.hour, default_bedtime.minute))
        self._bedtime.setDisplayFormat("HH:mm")
        form.addRow("Bedtime", Stepper(self._bedtime))
        root.addLayout(form)

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
            event = build_wakeup_event(self._wake(), self._bed(), habit=self._habit)
        except ValueError as exc:
            self._error.setText(str(exc))
            return
        self._on_submit([event])
        self.accept()

    def _wake(self) -> datetime:
        return self._localize(self._picked_date(), self._wake_time.time())

    def _bed(self) -> datetime:
        """The picked bedtime, dated the evening *before* the wake time whenever the
        clock value alone would otherwise land it on or after the wake instant — the
        normal case, since you go to bed before you wake up, not the same clock reading
        forward. Only stays on the wake date itself for a bedtime after midnight, e.g.
        asleep 01:00, woke 08:00 the same calendar day.
        """
        wake = self._wake()
        picked = self._picked_date()
        bed = self._localize(picked, self._bedtime.time())
        if bed >= wake:
            bed = self._localize(picked - timedelta(days=1), self._bedtime.time())
        return bed

    def _picked_date(self) -> date:
        qd = self._date.date()
        return date(qd.year(), qd.month(), qd.day())

    def _localize(self, day: date, qt: QTime) -> datetime:
        naive = datetime.combine(day, time(qt.hour(), qt.minute()))
        # What was typed is a wall-clock time in the configured zone, so it's stamped
        # with that zone's offset — not converted from the machine's. Same gotcha as
        # Backfill; see CLAUDE.md § Time.
        return self._tz.localize(naive)
