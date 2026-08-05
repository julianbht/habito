"""A month at a glance: how long you studied each day, and whether it was enough.

Days that reach the goal are filled green; days that didn't are left as they are, so the
run of green reads as the streak and nothing competes with it. Nothing else is encoded
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
from habito.ui.widgets import format_duration, label

_MET_FILL = 0.30  # how strongly a met day is tinted toward green
_STAR_RADIUS = 4.5  # small: it shares the cell with the day number and the duration
_STAR_INSET = 6  # from the cell's top-right corner, the only free space there is


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
        threshold_seconds: int,
        stretch_seconds: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = ui_theme
        self._threshold = threshold_seconds
        self._stretch = stretch_seconds
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

    def stretch_seconds(self) -> int | None:
        return self._stretch

    def set_goals(self, threshold_seconds: int, stretch_seconds: int | None = None) -> None:
        self._threshold = threshold_seconds
        self._stretch = stretch_seconds
        self.updateCells()

    def meets_goal(self, summary: DailySummary) -> bool:
        return summary.total_work_seconds >= self._threshold

    def meets_stretch(self, summary: DailySummary) -> bool:
        """A great day. Always False when no stretch goal is set, so no star is drawn."""
        return self._stretch is not None and summary.total_work_seconds >= self._stretch

    def paintCell(self, painter: QPainter, rect: QRect, qdate: QDate) -> None:  # noqa: N802
        day = _to_date(qdate)
        summary = self._summaries.get(day)
        in_month = qdate.month() == self.monthShown() and qdate.year() == self.yearShown()

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        box = rect.adjusted(2, 2, -2, -2)

        if summary is not None and in_month and self.meets_goal(summary):
            self._paint_met(painter, box)
            if self.meets_stretch(summary):
                self._paint_star(painter, box)

        self._paint_text(painter, box, day, summary, in_month)
        painter.restore()

    def _paint_star(self, painter: QPainter, box: QRect) -> None:
        """The great-day mark, tucked into the corner the text doesn't use."""
        center = QPointF(box.right() - _STAR_INSET, box.top() + _STAR_INSET)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(self._theme.palette.star))
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
        threshold_seconds: int,
        stretch_seconds: int | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._summaries: dict[date, DailySummary] = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(6)

        self.calendar = StudyCalendar(ui_theme, threshold_seconds, stretch_seconds)
        self.calendar.currentPageChanged.connect(lambda *_: self._render_page())
        root.addWidget(self.calendar, 1)

        self._total_lbl = label("", "today")
        self._total_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._total_lbl)

        self._hint_lbl = label("", "muted")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._hint_lbl)

        self._render_hint()
        self._render_page()

    def _render_hint(self) -> None:
        """Name both goals, so the green and the star each say what earned them."""
        text = f"Green once a day reaches {format_duration(self.calendar.threshold_seconds())}"
        stretch = self.calendar.stretch_seconds()
        if stretch is not None:
            text += f" · ★ at {format_duration(stretch)}"
        self._hint_lbl.setText(text)

    # --- navigation ------------------------------------------------------
    def shown_month(self) -> tuple[int, int]:
        return self.calendar.yearShown(), self.calendar.monthShown()

    def show_month(self, year: int, month: int) -> None:
        self.calendar.setCurrentPage(year, month)

    # --- contents --------------------------------------------------------
    def set_goals(self, threshold_seconds: int, stretch_seconds: int | None = None) -> None:
        """Apply goals changed in Settings without needing a restart."""
        self.calendar.set_goals(threshold_seconds, stretch_seconds)
        self._render_hint()
        self._render_page()

    def set_summaries(self, summaries: dict[date, DailySummary]) -> None:
        self._summaries = summaries
        self.calendar.set_summaries(summaries)
        self._render_page()

    def month_summaries(self) -> list[DailySummary]:
        year, month = self.calendar.yearShown(), self.calendar.monthShown()
        return [
            s for day, s in self._summaries.items() if day.year == year and day.month == month
        ]

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
        starred = sum(1 for s in days if self.calendar.meets_stretch(s))
        if starred:
            text += f" · {starred} ★"
        self._total_lbl.setText(text)
