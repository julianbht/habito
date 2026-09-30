"""A month at a glance: how long you studied each day, and whether it was enough.

Days that reach the low goal are filled green, with a star for the middle goal and a second
for the high one; days that didn't are left as they are, so the run of green reads as the
streak and nothing competes with it. Nothing else is encoded
here on purpose — how the time was recorded, and which day is today, are questions the log
and the timer already answer, and a second mark per cell costs more than it tells you.
"""

from __future__ import annotations

import math
from datetime import date

from PySide6.QtCore import QDate, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPolygonF
from PySide6.QtWidgets import QCalendarWidget, QVBoxLayout, QWidget

from habito.projections.daily import DailySummary, longest_run
from habito.ui import theme
from habito.ui.widgets.controls import format_duration, label

_MET_FILL = 0.30  # how strongly a met day is tinted toward green
_STAR_RADIUS = 4.5  # small: it shares the cell with the day number and the duration
_STAR_INSET = 6  # from the cell's top-right corner, the only free space there is
_STAR_GAP = 10  # centre to centre, when a second star sits left of the first


def _star(center: QPointF, radius: float) -> QPolygonF:
    """A five-pointed star, first point straight up."""
    inner = radius * 0.45
    return QPolygonF(
        [
            QPointF(
                center.x() + (radius if i % 2 == 0 else inner) * math.cos(a),
                center.y() + (radius if i % 2 == 0 else inner) * math.sin(a),
            )
            for i, a in enumerate(-math.pi / 2 + i * math.pi / 5 for i in range(10))
        ]
    )


def _to_date(qdate: QDate) -> date:
    return date(qdate.year(), qdate.month(), qdate.day())


class StudyCalendar(QCalendarWidget):
    """A month grid that paints each day from its :class:`DailySummary`."""

    def __init__(
        self,
        ui_theme: theme.Theme,
        low_seconds: int,
        middle_seconds: int | None = None,
        high_seconds: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = ui_theme
        self._low = low_seconds
        self._middle = middle_seconds
        self._high = high_seconds
        self._summaries: dict[date, DailySummary] = {}

        self.setGridVisible(False)
        self.setVerticalHeaderFormat(QCalendarWidget.VerticalHeaderFormat.NoVerticalHeader)
        self.setHorizontalHeaderFormat(QCalendarWidget.HorizontalHeaderFormat.SingleLetterDayNames)
        self.setSelectionMode(QCalendarWidget.SelectionMode.NoSelection)
        self.setNavigationBarVisible(True)

    def set_summaries(self, summaries: dict[date, DailySummary]) -> None:
        self._summaries = summaries
        self.updateCells()

    def goal_seconds(self) -> tuple[int, int | None, int | None]:
        return self._low, self._middle, self._high

    def set_goals(
        self, low_seconds: int, middle_seconds: int | None = None, high_seconds: int | None = None
    ) -> None:
        self._low = low_seconds
        self._middle = middle_seconds
        self._high = high_seconds
        self.updateCells()

    def meets_goal(self, summary: DailySummary) -> bool:
        return summary.total_work_seconds >= self._low

    def stars(self, summary: DailySummary) -> int:
        """0, 1 for the middle goal, 2 for the high one. An unset goal is never reached."""
        worked = summary.total_work_seconds
        return sum(1 for goal in (self._middle, self._high) if goal is not None and worked >= goal)

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate) -> None:  # noqa: N802
        day = _to_date(qdate)
        summary = self._summaries.get(day)
        in_month = qdate.month() == self.monthShown() and qdate.year() == self.yearShown()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = rect.adjusted(2, 2, -2, -2)

        if summary is not None and in_month and self.meets_goal(summary):
            self._paint_met(painter, box)
            self._paint_stars(painter, box, self.stars(summary))

        self._paint_text(painter, box, day, summary, in_month)
        painter.restore()

    def _paint_stars(self, painter: QPainter, box: QRect, count: int) -> None:
        """Middle/high marks, tucked into the corner the text doesn't use."""
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._theme.palette.star))
        for i in range(count):
            center = QPointF(box.right() - _STAR_INSET - i * _STAR_GAP, box.top() + _STAR_INSET)
            painter.drawPolygon(_star(center, _STAR_RADIUS))

    def _paint_met(self, painter: QPainter, box: QRect) -> None:
        """A met day is filled, however the time was recorded.

        The verified/backfilled split is kept by the log and the projection, which is where
        it can be read properly — at one cell per day the calendar only has room to answer
        "did this day count", and a second encoding there was more noise than signal.
        """
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
        low_seconds: int,
        middle_seconds: int | None = None,
        high_seconds: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summaries: dict[date, DailySummary] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(6)

        self.calendar = StudyCalendar(ui_theme, low_seconds, middle_seconds, high_seconds)
        self.calendar.currentPageChanged.connect(self._on_page_changed)
        root.addWidget(self.calendar, 1)

        self._total_lbl = label("", "today")
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._total_lbl)

        self._render_page()

    # --- navigation ------------------------------------------------------
    def shown_month(self) -> tuple[int, int]:
        return self.calendar.yearShown(), self.calendar.monthShown()

    def show_month(self, year: int, month: int) -> None:
        self.calendar.setCurrentPage(year, month)

    # --- contents --------------------------------------------------------
    def set_goals(
        self, low_seconds: int, middle_seconds: int | None = None, high_seconds: int | None = None
    ) -> None:
        """Apply goals changed in Settings without needing a restart."""
        self.calendar.set_goals(low_seconds, middle_seconds, high_seconds)
        self._render_page()

    def set_summaries(self, summaries: dict[date, DailySummary]) -> None:
        self._summaries = summaries
        self.calendar.set_summaries(summaries)
        self._render_page()

    def month_summaries(self) -> list[DailySummary]:
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        return [s for day, s in self._summaries.items() if day.year == year and day.month == month]

    def _on_page_changed(self, *_: int) -> None:
        """``currentPageChanged`` passes (year, month); the render reads both off the
        widget itself, so they're accepted and discarded."""
        self._render_page()

    def _render_page(self) -> None:
        """The month in one line: time put in, and the longest unbroken run of green.

        A run rather than a count of green days — the count is just the grid read back to
        you, whereas tracing the longest consecutive stretch across a month is the one
        thing the picture doesn't hand you. Scoped to the month shown, like the total
        beside it, so paging back doesn't mix a month figure with an all-time one.
        """
        days = self.month_summaries()
        studied = sum(s.total_work_seconds for s in days)
        text = f"{format_duration(studied)} this month"

        run = longest_run(s.day for s in days if self.calendar.meets_goal(s))
        if run:
            text += f" · best run {run} day{'s' if run != 1 else ''}"
        stars = [self.calendar.stars(s) for s in days]
        for count in (1, 2):
            if days_with := stars.count(count):
                text += f" · {days_with} {'★' * count}"
        self._total_lbl.setText(text)
