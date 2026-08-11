"""A read-only window onto the event log, grouped by day.

Deliberately read-only. The log's whole value is that it's append-only, so this shows you
what's in it and nothing more — no edit, no delete. Backfilled entries are marked, so what
you see here matches the distinction the log itself makes.

This is the one view fed the raw stream, retractions included: a retracted session stays
on screen struck through, under the day it was filed on, with the retraction line beneath
it. Day totals count only what still stands, so they agree with the calendar.

Turning an event into a line of text is a pure function (:func:`describe`), kept apart from
the widget so it can be read and tested on its own.
"""

from __future__ import annotations

from collections.abc import Container, Iterable
from dataclasses import dataclass
from datetime import date
from uuid import UUID

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor, QFont
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from habito.domain.events import (
    BreakEnded,
    BreakStarted,
    Event,
    Origin,
    RoundEnded,
    RoundStarted,
    SessionEnded,
    SessionPaused,
    SessionResumed,
    SessionRetracted,
    SessionStarted,
    TimeAdjusted,
    local_datetime,
    partition_date,
    retracted_session_ids,
)
from habito.ui import theme
from habito.ui.widgets import format_duration, label

# Where a day row keeps its heading text, so the ▾/▸ prefix can be rewritten without
# having to parse it back out of the label.
_HEADING_ROLE = Qt.ItemDataRole.UserRole + 1


@dataclass(frozen=True)
class Line:
    """One event, as it reads on screen."""

    time: str
    what: str
    detail: str
    backfilled: bool
    voided: bool = False
    """Part of a session a later retraction voided — struck through, and left out of the
    day's total. Set by the view, which knows the whole stream; :func:`describe` sees one
    event and can't."""


def _local_time(event: Event) -> str:
    """Wall-clock time as it was where you were, per the recorded offset."""
    return local_datetime(event).strftime("%H:%M:%S")


def _minutes(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:.2f}".rstrip("0")


def describe(event: Event) -> Line:
    """A human-readable rendering of one event."""
    what, detail = "Event", event.type
    if isinstance(event, SessionStarted):
        what = "Session started"
        detail = (
            f"{_minutes(event.work_minutes)} + {event.break_minutes} min, "
            f"{event.planned_rounds} rounds"
        )
    elif isinstance(event, RoundStarted):
        what, detail = "Round started", f"round {event.round_index}"
    elif isinstance(event, RoundEnded):
        what = "Round ended"
        detail = f"round {event.round_index} · {format_duration(event.work_seconds)} of work"
    elif isinstance(event, BreakStarted):
        what, detail = "Break started", f"after round {event.round_index}"
    elif isinstance(event, BreakEnded):
        what = "Break ended"
        detail = f"after round {event.round_index} · {format_duration(event.break_seconds)}"
    elif isinstance(event, SessionPaused):
        what, detail = "Paused", ""
    elif isinstance(event, SessionResumed):
        what, detail = "Resumed", ""
    elif isinstance(event, TimeAdjusted):
        sign = "+" if event.delta_seconds >= 0 else "−"
        what = "Time adjusted"
        detail = f"{sign}{format_duration(abs(event.delta_seconds))} on round {event.round_index}"
    elif isinstance(event, SessionEnded):
        what = "Session ended"
        detail = f"{format_duration(event.total_work_seconds)} total"
    else:
        what = "Session retracted"
        # Says when the correction was made, since the row sits under the day it corrects
        # and its time column would otherwise read as that day's.
        made = local_datetime(event).strftime("%Y-%m-%d")
        detail = f"{event.reason} · retracted {made}" if event.reason else f"retracted {made}"

    return Line(
        time=_local_time(event),
        what=what,
        detail=detail,
        backfilled=event.origin is Origin.backfilled,
    )


def group_by_day(events: Iterable[Event], rollover_hour: int = 0) -> dict[date, list[Event]]:
    """Events bucketed by the habit-day they belong to, newest day first.

    Uses the same rollover as the calendar, so a session running past midnight reads as
    one evening in both places rather than being split in one and not the other.
    """
    days: dict[date, list[Event]] = {}
    for event in events:
        days.setdefault(partition_date(event, rollover_hour), []).append(event)
    for entries in days.values():
        entries.sort(key=lambda e: e.timestamp)
    return dict(sorted(days.items(), key=lambda item: item[0], reverse=True))


def day_heading(day: date, events: list[Event], voided: Container[UUID] = frozenset()) -> str:
    """``Mon 4 Aug · 1h 40m over 4 rounds`` — what the day amounted to.

    Counts only rounds that still stand, so the heading matches the calendar cell.
    """
    rounds = [e for e in events if isinstance(e, RoundEnded) and e.session_id not in voided]
    worked = sum(e.work_seconds for e in rounds)
    parts = [day.strftime("%a %d %b %Y"), format_duration(worked)]
    if rounds:
        parts.append(f"{len(rounds)} round{'s' if len(rounds) != 1 else ''}")
    return " · ".join(parts)


class LogView(QWidget):
    def __init__(
        self,
        ui_theme: theme.Theme,
        rollover_hour: int = 0,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = ui_theme
        self._rollover_hour = rollover_hour
        self._events: list[Event] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 6, 12, 10)
        root.setSpacing(6)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Time", "Event", "Detail"])
        # No indentation and no branch decoration, so a child row's first column lines up
        # with the "Time" header instead of being pushed right under its day. The day rows
        # carry their own ▾/▸ in the text (see _mark_expanded) to say they can be folded.
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setUniformRowHeights(True)
        # Read-only by construction, not just by omission: no item carries the editable
        # flag, and the view refuses the gestures that would start an edit anyway.
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.tree.itemExpanded.connect(self._mark_expanded)
        self.tree.itemCollapsed.connect(self._mark_expanded)
        root.addWidget(self.tree, 1)

        self._summary_lbl = label("", "muted")
        self._summary_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._summary_lbl)

        self._hint_lbl = label("Read-only — the log is append-only", "muted")
        self._hint_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._hint_lbl)

    def set_rollover_hour(self, hour: int) -> None:
        """Apply a rollover changed in Settings, regrouping without needing a restart."""
        self._rollover_hour = hour
        self.set_events(self._events)

    def set_events(self, events: Iterable[Event]) -> None:
        entries = list(events)
        self._events = entries
        voided = retracted_session_ids(entries)
        days = group_by_day(entries, self._rollover_hour)

        self.tree.clear()
        for day, day_events in days.items():
            parent = QTreeWidgetItem(self.tree, [""])
            parent.setData(0, _HEADING_ROLE, day_heading(day, day_events, voided))
            parent.setFirstColumnSpanned(True)
            bold = QFont(parent.font(0))
            bold.setBold(True)
            parent.setFont(0, bold)
            for event in day_events:
                # The retraction itself is the standing statement, so it isn't struck out.
                struck = event.session_id in voided and not isinstance(event, SessionRetracted)
                self._add_line(parent, describe(event), voided=struck)
            self._mark_expanded(parent)

        # Today is the one you'd look at first; everything older stays folded away.
        first = self.tree.topLevelItem(0)
        if first is not None:
            first.setExpanded(True)
        for column in (0, 1):
            self.tree.resizeColumnToContents(column)

        self._summary_lbl.setText(
            f"{len(entries)} events across {len(days)} day{'s' if len(days) != 1 else ''}"
        )

    @staticmethod
    def _mark_expanded(item: QTreeWidgetItem) -> None:
        """Keep the day row's ▾/▸ in step with whether it's open."""
        if item.parent() is not None:
            return
        arrow = "▾" if item.isExpanded() else "▸"
        item.setText(0, f"{arrow}  {item.data(0, _HEADING_ROLE)}")

    def _add_line(self, parent: QTreeWidgetItem, line: Line, voided: bool = False) -> None:
        detail = f"{line.detail} (backfilled)" if line.backfilled else line.detail
        item = QTreeWidgetItem(parent, [line.time, line.what, detail])
        item.setForeground(0, QBrush(QColor(theme.MUTED)))
        item.setForeground(2, QBrush(QColor(theme.MUTED)))
        if line.backfilled:
            # Same signal the calendar uses: added later, not in-the-moment evidence.
            item.setForeground(1, QBrush(QColor(theme.WARN)))
        if voided:
            # Struck through and muted across every column: still on the record, no longer
            # counting. Strike-through as well as colour, so it survives colour blindness.
            struck = QFont(item.font(1))
            struck.setStrikeOut(True)
            for column in range(3):
                item.setFont(column, struck)
                item.setForeground(column, QBrush(QColor(theme.MUTED)))
