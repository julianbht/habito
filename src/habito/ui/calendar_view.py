"""A month at a glance: how long you studied each day, and whether it was enough.

Days that reach the goal are filled green; days that didn't are left as they are, so the
run of green reads as the streak and nothing competes with it. Time that came from a
backfilled session is drawn as an outline rather than a solid fill — the same distinction
the log makes, carried into the view rather than quietly averaged away.
"""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import QDate, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QCalendarWidget, QVBoxLayout, QWidget

from habito.projections.daily import DailySummary
from habito.ui import theme
from habito.ui.widgets import format_duration, label

_MET_FILL = 0.30  # how strongly a met day is tinted toward green
_TODAY_RING = 0.55


def _to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


class StudyCalendar(QCalendarWidget):
    """A month grid that paints each day from its :class:`DailySummary`."""

    def __init__(
        self,
        ui_theme: theme.Theme,
        threshold_seconds: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = ui_theme
        self._threshold = threshold_seconds
        self._summaries: dict[date, DailySummary] = {}

        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(
            QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames
        )
        self.setSelectionMode(QCalendarWidget.SelectionMode.NoSelection)
        self.setNavigationBarVisible(True)

    def set_summaries(self, summaries: dict[date, DailySummary]) -> None:
        self._summaries = summaries
        self.updateCells()

    def threshold_seconds(self) -> int:
        return self._threshold

    def meets_goal(self, summary: DailySummary) -> bool:
        return summary.total_work_seconds >= self._threshold

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate) -> None:  # noqa: N802
        day = _to_date(qdate)
        summary = self._summaries.get(day)
        in_month = qdate.month() == self.monthShown() and qdate.year() == self.yearShown()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = rect.adjusted(2, 2, -2, -2)

        if summary is not None and self.meets_goal(summary) and in_month:
            self._paint_met(painter, box, summary)
        if day == date.today():
            painter.setPen(QPen(theme.mix(self._theme.palette.bg, theme.OK, _TODAY_RING), 1))
            painter.drawRoundedRect(box, 5, 5)

        self._paint_text(painter, box, day, summary, in_month)
        painter.restore()

    def _paint_met(self, painter: QPainter, box: QRect, summary: DailySummary) -> None:
        green = QColor(theme.OK)
        if summary.backfilled_work_seconds:
            # Added after the fact: outlined, not filled, so it never reads as verified.
            painter.setPen(QPen(green, 1))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box, 5, 5)
            return
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(theme.mix(self._theme.palette.bg, theme.OK, _MET_FILL))
        painter.drawRoundedRect(box, 5, 5)

    def _paint_text(
        self,
        painter: QPainter,
        box: QRect,
        day: date,
        summary: DailySummary | None,
        in_month: bool,
    ) -> None:
        text_color = QColor(self._theme.palette.text if in_month else theme.MUTED)
        if not in_month:
            text_color.setAlpha(110)

        number = QFont(painter.font())
        number.setPointSize(max(7, number.pointSize()))
        painter.setFont(number)
        painter.setPen(text_color)
        painter.drawText(
            box.adjusted(0, 1, 0, 0),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            str(day.day),
        )

        if summary is None or not summary.total_work_seconds or not in_month:
            return
        small = QFont(painter.font())
        small.setPointSize(max(6, small.pointSize() - 2))
        painter.setFont(small)
        painter.setPen(QColor(theme.MUTED))
        painter.drawText(
            box.adjusted(0, 0, 0, -1),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom,
            format_duration(summary.total_work_seconds),
        )


class CalendarView(QWidget):
    """The calendar plus a one-line readout of the month it's showing."""

    def __init__(
        self,
        ui_theme: theme.Theme,
        threshold_seconds: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summaries: dict[date, DailySummary] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(6)

        self.calendar = StudyCalendar(ui_theme, threshold_seconds)
        self.calendar.currentPageChanged.connect(lambda *_: self._render_total())
        root.addWidget(self.calendar, 1)

        self._total_lbl = label("", "today")
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._total_lbl)

        goal = format_duration(threshold_seconds)
        self._hint_lbl = label(f"Green once a day reaches {goal}", "muted")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._hint_lbl)

        self._render_total()

    def set_summaries(self, summaries: dict[date, DailySummary]) -> None:
        self._summaries = summaries
        self.calendar.set_summaries(summaries)
        self._render_total()

    def month_summaries(self) -> list[DailySummary]:
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        return [
            s for day, s in self._summaries.items() if day.year == year and day.month == month
        ]

    def _render_total(self) -> None:
        days = self.month_summaries()
        studied = sum(s.total_work_seconds for s in days)
        met = sum(1 for s in days if self.calendar.meets_goal(s))
        self._total_lbl.setText(f"{format_duration(studied)} this month · {met} days green")
