"""The read-only log view.

Turning an event into a line is a pure function, so most of this is plain assertions on
text. The widget tests check the grouping and — importantly — that nothing here can change
the log.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
from PySide6.QtCore import Qt

from habito.domain.events import (
    BreakEnded,
    Origin,
    RoundEnded,
    SessionEnded,
    SessionPaused,
    SessionRetracted,
    SessionStarted,
    SessionTagged,
    TagDescribed,
    TimeAdjusted,
)
from habito.ui import theme
from habito.ui.log_view import LogView, day_heading, describe, group_by_day

DARK = theme.Theme(accent=theme.ACCENT_LIVE, palette=theme.DARK)
SESSION = uuid4()
NOON = datetime(2026, 8, 4, 12, 0, tzinfo=UTC)


def at(hour: int, minute: int = 0, *, offset: int = 0, origin: Origin = Origin.live, **fields):
    """Build an event of the given type at a wall-clock time."""
    cls = fields.pop("cls")
    return cls(
        timestamp=datetime(2026, 8, 4, hour, minute, tzinfo=UTC),
        tz_offset_minutes=offset,
        habit="study",
        origin=origin,
        session_id=SESSION,
        **fields,
    )


@pytest.fixture
def view(qtbot):
    widget = LogView(DARK)
    qtbot.addWidget(widget)
    widget.resize(420, 400)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


# --- one event, one line --------------------------------------------------
def test_a_session_start_shows_its_format():
    line = describe(at(9, cls=SessionStarted, work_minutes=25, break_minutes=5, planned_rounds=4))
    assert line.what == "Session started"
    assert line.detail == "25 + 5 min, 4 rounds"


def test_a_sub_minute_round_length_is_not_rounded_to_nothing():
    """A 0:10 test round should read as something, not as '0 + 5 min'."""
    line = describe(
        at(9, cls=SessionStarted, work_minutes=10 / 60, break_minutes=5, planned_rounds=4)
    )
    assert not line.detail.startswith("0 +")


def test_a_finished_round_reports_the_work_done():
    line = describe(at(9, 25, cls=RoundEnded, round_index=2, work_seconds=1500))
    assert line.what == "Round ended"
    assert "round 2" in line.detail
    assert "25m" in line.detail


def test_an_adjustment_shows_its_direction():
    added = describe(at(9, cls=TimeAdjusted, round_index=1, delta_seconds=300))
    removed = describe(at(9, cls=TimeAdjusted, round_index=1, delta_seconds=-300))

    assert added.detail.startswith("+")
    assert removed.detail.startswith("−")
    assert "5m" in added.detail and "5m" in removed.detail


def test_the_session_end_reports_the_total():
    line = describe(at(11, cls=SessionEnded, total_work_seconds=6000))
    assert line.what == "Session ended"
    assert "1h 40m" in line.detail


def test_a_tagged_session_shows_its_tag():
    line = describe(at(11, cls=SessionTagged, tag="linear algebra"))
    assert line.what == "Tagged"
    assert line.detail == "linear algebra"


def test_a_tagged_session_shows_its_description_when_known():
    line = describe(
        at(11, cls=SessionTagged, tag="LinAlg-S"),
        tag_description="Strang — Linear Algebra and Its Applications",
    )
    assert line.detail == "LinAlg-S — Strang — Linear Algebra and Its Applications"


def test_a_tag_described_event_shows_what_it_means():
    line = describe(at(11, cls=TagDescribed, tag="LinAlg-S", description="Strang's book"))
    assert line.what == "Tag described"
    assert line.detail == "LinAlg-S — Strang's book"


def test_a_tag_described_event_without_text_still_reads():
    line = describe(at(11, cls=TagDescribed, tag="LinAlg-S", description=""))
    assert line.detail == "LinAlg-S"


def test_events_without_detail_still_read_cleanly():
    assert describe(at(9, cls=SessionPaused)).what == "Paused"
    assert describe(at(9, cls=SessionPaused)).detail == ""


def test_the_time_shown_is_local_not_utc():
    """Events carry their offset so the wall-clock time can be rebuilt exactly."""
    line = describe(at(12, cls=SessionPaused, offset=120))  # UTC+2
    assert line.time == "14:00:00"


def test_backfilled_events_are_flagged():
    live = describe(at(9, cls=SessionPaused))
    added = describe(at(9, cls=SessionPaused, origin=Origin.backfilled))

    assert live.backfilled is False
    assert added.backfilled is True


# --- grouping -------------------------------------------------------------
def make_day(day_offset: int, hour: int) -> RoundEnded:
    return RoundEnded(
        timestamp=NOON + timedelta(days=day_offset, hours=hour),
        tz_offset_minutes=0,
        origin=Origin.live,
        habit="study",
        session_id=SESSION,
        round_index=1,
        work_seconds=1500,
    )


def test_events_are_grouped_by_local_day_newest_first():
    events = [make_day(0, 0), make_day(-2, 0), make_day(-1, 0)]
    days = list(group_by_day(events))

    assert days == sorted(days, reverse=True)
    assert len(days) == 3


def test_events_within_a_day_stay_in_order():
    later, earlier = make_day(0, 3), make_day(0, 1)
    grouped = group_by_day([later, earlier])
    ((_, entries),) = grouped.items()

    assert entries == [earlier, later]


def test_a_day_heading_totals_the_rounds():
    events = [
        at(9, 25, cls=RoundEnded, round_index=1, work_seconds=1500),
        at(9, 30, cls=BreakEnded, round_index=1, break_seconds=300),
        at(9, 55, cls=RoundEnded, round_index=2, work_seconds=1500),
    ]
    heading = day_heading(events[0].timestamp.date(), events)

    assert "50m" in heading  # only work counts, not the break
    assert "2 rounds" in heading


def test_a_day_with_a_single_round_is_not_pluralised():
    events = [at(9, 25, cls=RoundEnded, round_index=1, work_seconds=1500)]
    assert "1 round" in day_heading(events[0].timestamp.date(), events)
    assert "1 rounds" not in day_heading(events[0].timestamp.date(), events)


# --- the widget -----------------------------------------------------------
def test_each_day_becomes_a_group_with_its_events_beneath(view):
    view.set_events([make_day(0, 0), make_day(0, 1), make_day(-1, 0)])

    assert view.tree.topLevelItemCount() == 2
    assert view.tree.topLevelItem(0).childCount() == 2  # today, both events
    assert view.tree.topLevelItem(1).childCount() == 1


def test_the_newest_day_starts_expanded(view):
    view.set_events([make_day(0, 0), make_day(-1, 0)])

    assert view.tree.topLevelItem(0).isExpanded()
    assert not view.tree.topLevelItem(1).isExpanded()


def test_the_summary_counts_events_and_days(view):
    view.set_events([make_day(0, 0), make_day(0, 1), make_day(-1, 0)])
    assert "3 events across 2 days" in view._summary_lbl.text()


def test_an_empty_log_renders_without_complaint(view):
    view.set_events([])

    assert view.tree.topLevelItemCount() == 0
    assert "0 events across 0 days" in view._summary_lbl.text()


def test_reloading_replaces_rather_than_appends(view):
    view.set_events([make_day(0, 0), make_day(-1, 0)])
    view.set_events([make_day(0, 0)])

    assert view.tree.topLevelItemCount() == 1


def test_backfilled_rows_are_marked_in_the_tree(view):
    added = RoundEnded(
        timestamp=NOON,
        tz_offset_minutes=0,
        habit="study",
        origin=Origin.backfilled,
        session_id=SESSION,
        round_index=1,
        work_seconds=1500,
    )
    view.set_events([added])
    row = view.tree.topLevelItem(0).child(0)

    assert "backfilled" in row.text(2)


def test_the_view_shows_a_tags_description_alongside_its_tag(view):
    tagged = at(9, cls=SessionTagged, tag="LinAlg-S")
    described = TagDescribed(
        timestamp=datetime(2026, 8, 5, 9, 0, tzinfo=UTC),
        tz_offset_minutes=0,
        origin=Origin.live,
        habit="study",
        session_id=uuid4(),
        tag="LinAlg-S",
        description="Strang's book",
    )
    view.set_events([tagged, described])
    day = view.tree.topLevelItem(0)
    assert "Strang's book" in day.child(0).text(2)


def test_the_view_cannot_edit_the_log(view):
    """It's a window onto an append-only log; there is nothing here that writes."""
    view.set_events([make_day(0, 0)])
    row = view.tree.topLevelItem(0).child(0)

    assert not (row.flags() & Qt.ItemFlag.ItemIsEditable)
    assert view.tree.editTriggers() == view.tree.EditTrigger.NoEditTriggers


def test_the_store_is_never_written_to(qtbot, tmp_path):
    """Opening the Log page reads the log and leaves it byte-for-byte alone."""
    from habito.app import _build_engine_and_store
    from habito.config.models import Config
    from habito.ui.app import _LOG_PAGE, HabitoApp

    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    store.append(
        SessionStarted(
            timestamp=NOON,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit="study",
            session_id=SESSION,
            work_minutes=25,
            break_minutes=5,
            planned_rounds=4,
        )
    )
    before = {p: p.read_bytes() for p in store.files()}
    assert before, "expected the append to have written a day file"

    app = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(app)
    app.show_page(_LOG_PAGE)

    assert app._log_view().tree.topLevelItemCount() == 1
    assert {p: p.read_bytes() for p in store.files()} == before


def test_day_rows_span_the_columns_and_children_do_not_indent(view):
    """Column 0 of an event must line up with the "Time" header, not sit under its day."""
    view.set_events([make_day(0, 0)])
    day_row = view.tree.topLevelItem(0)

    assert view.tree.indentation() == 0
    assert day_row.isFirstColumnSpanned()
    assert day_row.child(0).text(0) == "12:00:00"  # the event's own column 0, unindented


def test_day_rows_show_whether_they_are_folded(view):
    view.set_events([make_day(0, 0), make_day(-1, 0)])
    today, older = view.tree.topLevelItem(0), view.tree.topLevelItem(1)

    assert today.text(0).startswith("▾")  # expanded
    assert older.text(0).startswith("▸")  # folded

    older.setExpanded(True)
    assert older.text(0).startswith("▾")
    older.setExpanded(False)
    assert older.text(0).startswith("▸")


def test_the_day_heading_survives_being_folded_and_unfolded(view):
    view.set_events([make_day(0, 0)])
    row = view.tree.topLevelItem(0)
    heading = row.text(0).lstrip("▾▸ ")

    row.setExpanded(False)
    row.setExpanded(True)
    assert row.text(0).lstrip("▾▸ ") == heading  # not re-parsed out of its own label


# --- retractions ----------------------------------------------------------
def _retraction(target=date(2026, 8, 4), reason="", session=SESSION):
    """A retraction written on the 7th, voiding a session filed on ``target``."""
    return SessionRetracted(
        timestamp=datetime(2026, 8, 7, 12, 23, tzinfo=UTC),
        tz_offset_minutes=0,
        origin=Origin.live,
        habit="study",
        session_id=session,
        target_date=target,
        reason=reason,
    )


def test_a_retraction_says_when_it_was_made():
    """Its row sits under the day it corrects, so the time column alone would mislead."""
    line = describe(_retraction(reason="wrong date"))
    assert line.what == "Session retracted"
    assert "2026-08-07" in line.detail
    assert "wrong date" in line.detail


def test_a_retraction_without_a_reason_still_reads():
    assert describe(_retraction()).detail == "retracted 2026-08-07"


def test_a_retraction_groups_under_the_day_it_corrects():
    """Written on the 7th, it belongs with the 4th — where the events it voids are."""
    days = group_by_day([at(9, cls=SessionPaused), _retraction()])
    assert list(days) == [date(2026, 8, 4)]
    assert len(days[date(2026, 8, 4)]) == 2


def test_a_retracted_day_heading_stops_counting_the_work():
    events = [at(9, 25, cls=RoundEnded, round_index=1, work_seconds=1500), _retraction()]
    heading = day_heading(date(2026, 8, 4), events, {SESSION})
    assert "25m" not in heading
    assert "round" not in heading


def test_a_heading_still_counts_a_session_that_was_not_retracted():
    other = uuid4()
    events = [at(9, 25, cls=RoundEnded, round_index=1, work_seconds=1500)]
    assert "25m" in day_heading(date(2026, 8, 4), events, {other})


def test_retracted_rows_are_struck_through(view):
    view.set_events([at(9, cls=SessionPaused), _retraction()])
    day = view.tree.topLevelItem(0)
    voided, retraction = day.child(0), day.child(1)

    assert voided.font(1).strikeOut()
    # The retraction is the statement that still stands, so it isn't struck out itself.
    assert not retraction.font(1).strikeOut()


def test_rows_of_other_sessions_are_not_struck_through(view):
    other = uuid4()
    view.set_events([at(9, cls=SessionPaused), _retraction(session=other)])
    day = view.tree.topLevelItem(0)
    assert not day.child(0).font(1).strikeOut()
