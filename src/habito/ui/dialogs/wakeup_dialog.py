"""Dialog to log when you woke up, entered later at the PC — and to correct one already
logged.

Modeled on ``BackfillDialog`` for a consistent feel: same compact size, same date/time
field pattern, same error-label-then-primary-button shape. Produces a backfilled
``WakeUpLogged`` via :func:`habito.actions.wakeup.build_wakeup_event` and hands it to the
``on_submit`` callback, which appends it to the wake-up store (then committed+pushed,
tagged ``[backfilled]``).

``replacing`` seeds the fields from an existing entry and renames the dialog and its
button. It changes nothing about what this dialog *writes* — the correction is the caller's
to make, by voiding the old entry alongside the new one this submits (see
``EntryManagerDialog``), so a form that only ever produces one honest wake-up event stays
that way.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (
    QDateEdit,
    QDialog,
    QFormLayout,
    QLabel,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from habito.actions.wakeup import build_wakeup_event
from habito.config.models import TimeConfig
from habito.domain.events import Event, WakeUpLogged, local_datetime
from habito.ui import theme
from habito.ui.widgets.controls import (
    COMPACT_DIALOG_WIDTH,
    Stepper,
    button,
    button_row,
    primary_button,
)

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
        replacing: WakeUpLogged | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._tz = time_config or TimeConfig()
        self._today = today or date.today()
        self._editing = replacing is not None
        self.setWindowTitle("Edit wake-up" if self._editing else "Log wake-up")
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)
        self.setModal(True)
        self._build(*self._seed(replacing, default_wake_time, default_bedtime))

    def _seed(
        self, replacing: WakeUpLogged | None, default_wake_time: time, default_bedtime: time
    ) -> tuple[date, time, time]:
        """The date and two clock values the fields start on — the configured defaults for a
        fresh entry, the existing one's own wall-clock values when correcting it."""
        if replacing is None:
            return self._today, default_wake_time, default_bedtime
        woke = local_datetime(replacing)
        # `bedtime` shares `timestamp`'s offset (see WakeUpLogged), so the same arithmetic
        # `local_datetime` does for `timestamp` applies to it by hand.
        bed = replacing.bedtime + timedelta(minutes=replacing.tz_offset_minutes)
        return woke.date(), woke.time(), bed.time()

    def _build(self, seed_date: date, default_wake_time: time, default_bedtime: time) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        # "Today" is the configured timezone's, which on a machine set to another zone
        # is not the same day the computer thinks it is — same reasoning as Backfill.
        today = QDate(self._today.year, self._today.month, self._today.day)
        self._date = QDateEdit(QDate(seed_date.year, seed_date.month, seed_date.day))
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

        cancel_btn = button("Cancel")
        cancel_btn.clicked.connect(self.reject)  # Esc also closes, via QDialog
        self.ok_button = primary_button("Save && commit" if self._editing else "Log && commit")
        self.ok_button.clicked.connect(self._submit)
        root.addLayout(button_row(self, primary=self.ok_button, dismiss=cancel_btn))

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
