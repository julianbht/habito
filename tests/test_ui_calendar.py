"""The calendar view: per-day study time, green once the day's goal is met.

The colouring is painted rather than set on a widget, so the "is it green" checks read the
pixels back out of the cell.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from pydantic import ValidationError
from PySide6.QtCore import QDate, QRect
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QSpinBox, QToolButton, QWidget

from habito.config.models import GoalsConfig
from habito.projections.daily import DailySummary, longest_run
from habito.ui import theme
from habito.ui.calendar_view import CalendarView, StudyCalendar

DARK = theme.Theme(accent=theme.ACCENT_LIVE, palette=theme.DARK)
GOAL = GoalsConfig()
THRESHOLD = GOAL.threshold_seconds()

TODAY = date.today()
# A day mid-month, so "is it in the month shown" never depends on today's date.
ANCHOR = TODAY.replace(day=15)


def summary(day: date, verified: int = 0, backfilled: int = 0) -> DailySummary:
    return DailySummary(day=day, verified_work_seconds=verified, backfilled_work_seconds=backfilled)


@pytest.fixture
def view(qtbot):
    widget = CalendarView(DARK, THRESHOLD)
    qtbot.addWidget(widget)
    widget.resize(360, 400)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def cell_pixels(calendar: StudyCalendar, day: date) -> list[tuple[int, int, int]]:
    """Paint one cell onto a blank tile and return every pixel in it."""
    image = QImage(40, 34, QImage.Format.Format_ARGB32)
    image.fill(theme.DARK.bg)
    painter = QPainter(image)
    calendar.paintCell(painter, QRect(0, 0, 40, 34), QDate(day.year, day.month, day.day))
    painter.end()
    return [
        image.pixelColor(x, y).getRgb()[:3]
        for x in range(image.width())
        for y in range(image.height())
    ]


def green_pixels(calendar: StudyCalendar, day: date) -> int:
    """How much of the cell reads as green. Antialiasing means exact matches won't do."""
    return sum(1 for r, g, b in cell_pixels(calendar, day) if g > r + 8 and g > b + 8)


# --- the goal -------------------------------------------------------------
def test_the_goal_allows_a_buffer():
    """Four 25-minute rounds is 100 minutes; missing it by a couple still counts."""
    assert GoalsConfig(daily_minutes=100, buffer_minutes=5).threshold_seconds() == 95 * 60


def test_the_buffer_can_be_removed():
    assert GoalsConfig(daily_minutes=100, buffer_minutes=0).threshold_seconds() == 100 * 60


@pytest.mark.parametrize(
    ("minutes", "met"),
    [
        (0, False),
        (60, False),
        (94, False),  # just short, even with the buffer
        (95, True),  # exactly on the buffered threshold
        (100, True),  # the goal itself
        (180, True),
    ],
)
def test_days_are_judged_against_the_buffered_goal(view, minutes, met):
    assert view.calendar.meets_goal(summary(ANCHOR, verified=minutes * 60)) is met


def test_backfilled_time_counts_toward_the_goal(view):
    day = summary(ANCHOR, verified=60 * 60, backfilled=40 * 60)
    assert view.calendar.meets_goal(day) is True


# --- what gets painted ----------------------------------------------------
FILL = theme.mix(theme.DARK.bg, theme.OK, 0.30).getRgb()[:3]


def test_a_day_that_missed_the_goal_gets_no_colour(view):
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=60 * 60)})
    assert FILL not in cell_pixels(view.calendar, ANCHOR)


def test_a_day_that_met_the_goal_is_filled_green(view):
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=100 * 60)})
    assert FILL in cell_pixels(view.calendar, ANCHOR)


def test_a_day_with_no_entry_at_all_is_plain(view):
    view.set_summaries({})
    assert FILL not in cell_pixels(view.calendar, ANCHOR)


# --- the stretch goal -----------------------------------------------------
STAR = QColor(theme.DARK.star).getRgb()[:3]


@pytest.fixture
def stretch_view(qtbot):
    """A calendar with both goals set: green at 95m (buffered), star at 175m."""
    widget = CalendarView(DARK, THRESHOLD, GoalsConfig(stretch_minutes=180).stretch_seconds())
    qtbot.addWidget(widget)
    widget.resize(360, 400)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def test_the_stretch_goal_is_buffered_like_the_daily_one():
    goals = GoalsConfig(daily_minutes=100, buffer_minutes=5, stretch_minutes=180)
    assert goals.threshold_seconds() == 95 * 60
    assert goals.stretch_seconds() == 175 * 60


def test_no_stretch_goal_by_default():
    assert GoalsConfig().stretch_seconds() is None


def test_zero_means_off_so_the_toml_can_round_trip():
    """TOML has no null and the spin bottoms out at Off; both write 0."""
    assert GoalsConfig(stretch_minutes=0).stretch_minutes is None


def test_a_stretch_goal_below_the_daily_goal_is_refused():
    with pytest.raises(ValidationError, match="stretch goal must be above"):
        GoalsConfig(daily_minutes=100, stretch_minutes=60)


@pytest.mark.parametrize(
    ("minutes", "starred"),
    [(100, False), (174, False), (175, True), (240, True)],
)
def test_only_great_days_are_starred(stretch_view, minutes, starred):
    assert stretch_view.calendar.meets_stretch(summary(ANCHOR, verified=minutes * 60)) is starred


def test_a_starred_day_is_painted_with_a_star(stretch_view):
    stretch_view.set_summaries({ANCHOR: summary(ANCHOR, verified=200 * 60)})
    assert STAR in cell_pixels(stretch_view.calendar, ANCHOR)


def test_a_merely_green_day_gets_no_star(stretch_view):
    stretch_view.set_summaries({ANCHOR: summary(ANCHOR, verified=100 * 60)})
    assert FILL in cell_pixels(stretch_view.calendar, ANCHOR)  # still green...
    assert STAR not in cell_pixels(stretch_view.calendar, ANCHOR)  # ...but no star


def test_no_star_is_ever_drawn_without_a_stretch_goal(view):
    """The default calendar has no second goal, so a huge day is still just green."""
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=600 * 60)})
    assert STAR not in cell_pixels(view.calendar, ANCHOR)


def test_both_goals_are_named_in_the_hint(stretch_view):
    assert "1h 35m" in stretch_view._hint_lbl.text()
    assert "2h 55m" in stretch_view._hint_lbl.text()  # 175 minutes


def test_the_month_readout_counts_starred_days(stretch_view):
    other = ANCHOR + timedelta(days=1)
    stretch_view.set_summaries(
        {
            ANCHOR: summary(ANCHOR, verified=200 * 60),
            other: summary(other, verified=100 * 60),
        }
    )
    assert "1 ★" in stretch_view._total_lbl.text()


def test_backfilled_time_is_painted_the_same_as_live(view):
    """A met day is a met day. The verified/backfilled split lives in the log, not here."""
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=50 * 60, backfilled=50 * 60)})
    mixed = green_pixels(view.calendar, ANCHOR)

    view.set_summaries({ANCHOR: summary(ANCHOR, verified=100 * 60)})
    live_only = green_pixels(view.calendar, ANCHOR)

    assert mixed > 0
    assert mixed == live_only


# --- the longest run ------------------------------------------------------
def test_no_days_is_no_run():
    assert longest_run([]) == 0


def test_a_single_day_is_a_run_of_one():
    assert longest_run([date(2026, 8, 4)]) == 1


def test_consecutive_days_accumulate():
    days = [date(2026, 8, d) for d in (4, 5, 6, 7)]
    assert longest_run(days) == 4


def test_a_gap_breaks_the_run():
    days = [date(2026, 8, d) for d in (1, 2, 5, 6, 7, 9)]
    assert longest_run(days) == 3  # the 5th-7th, not the 6 days total


def test_order_and_duplicates_do_not_matter():
    days = [date(2026, 8, d) for d in (7, 5, 6, 5, 7)]
    assert longest_run(days) == 3


def test_a_run_can_cross_a_month_boundary():
    days = [date(2026, 7, 30), date(2026, 7, 31), date(2026, 8, 1)]
    assert longest_run(days) == 3


def test_the_readout_reports_the_longest_run_not_the_count(view):
    """Six green days, but the longest unbroken stretch is three."""
    first = ANCHOR.replace(day=1)
    green = [1, 2, 5, 6, 7, 9]
    view.set_summaries(
        {
            first + timedelta(days=d - 1): summary(first + timedelta(days=d - 1), verified=100 * 60)
            for d in green
        }
    )
    assert "best run 3 days" in view._total_lbl.text()


def test_a_lone_green_day_reads_as_one_day(view):
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=100 * 60)})
    assert "best run 1 day" in view._total_lbl.text()
    assert "1 days" not in view._total_lbl.text()  # singular, not "1 days"


def test_a_month_with_nothing_green_says_nothing_about_runs(view):
    view.set_summaries({ANCHOR: summary(ANCHOR, verified=10 * 60)})
    assert "best run" not in view._total_lbl.text()
    assert "10m this month" in view._total_lbl.text()


def test_days_short_of_the_goal_do_not_extend_a_run(view):
    first = ANCHOR.replace(day=1)
    view.set_summaries(
        {
            first: summary(first, verified=100 * 60),
            first + timedelta(days=1): summary(first + timedelta(days=1), verified=20 * 60),
            first + timedelta(days=2): summary(first + timedelta(days=2), verified=100 * 60),
        }
    )
    assert "best run 1 day" in view._total_lbl.text()


# --- the month readout ----------------------------------------------------
def test_the_month_total_counts_only_the_month_shown(view):
    last_month = (ANCHOR.replace(day=1) - timedelta(days=1)).replace(day=10)
    view.set_summaries(
        {
            ANCHOR: summary(ANCHOR, verified=100 * 60),
            ANCHOR + timedelta(days=1): summary(ANCHOR + timedelta(days=1), verified=30 * 60),
            last_month: summary(last_month, verified=100 * 60),
        }
    )

    assert {s.day for s in view.month_summaries()} == {
        ANCHOR,
        ANCHOR + timedelta(days=1),
    }
    assert "2h 10m" in view._total_lbl.text()


def test_the_readout_names_the_goal(view):
    assert "1h 35m" in view._hint_lbl.text()  # 95 minutes, the buffered threshold


# --- reaching it from the window ------------------------------------------
def test_the_menu_switches_between_the_timer_and_the_calendar(qtbot, tmp_path):
    from habito.app import _build_engine_and_store
    from habito.config.models import Config
    from habito.ui.app import _CALENDAR_PAGE, _TIMER_PAGE, HabitoApp

    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    # store built with test_mode=False so the log lives under tmp_path; the *window*
    # still runs in test mode. Otherwise every test shares one scratch file.
    engine, store = _build_engine_and_store(config, test_mode=False)
    app = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(app)
    app.show()
    qtbot.waitExposed(app)

    assert app._pages.currentIndex() == _TIMER_PAGE

    app.show_page(_CALENDAR_PAGE)
    assert app._pages.currentWidget() is app._calendar

    app.show_page(_TIMER_PAGE)
    assert app._pages.currentWidget() is app._view


def test_opening_the_calendar_reads_the_log(qtbot, tmp_path):
    """Whatever is in the store shows up without needing a restart."""
    from habito.app import _build_engine_and_store
    from habito.backfill import build_backfill_events
    from habito.config.models import Config
    from habito.ui.app import _CALENDAR_PAGE, HabitoApp

    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    # store built with test_mode=False so the log lives under tmp_path; the *window*
    # still runs in test mode. Otherwise every test shares one scratch file.
    engine, store = _build_engine_and_store(config, test_mode=False)
    app = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(app)

    when = datetime.combine(ANCHOR, time(9, 0)).astimezone()
    backfilled = build_backfill_events(
        when, work_minutes=25, break_minutes=5, rounds=4, habit="study"
    )
    for event in backfilled:
        store.append(event)

    app.show_page(_CALENDAR_PAGE)
    days = {s.day: s for s in app._calendar.month_summaries()}

    assert ANCHOR in days
    assert days[ANCHOR].total_work_seconds == 100 * 60
    assert app._calendar.calendar.meets_goal(days[ANCHOR])


def test_each_view_gets_a_size_that_suits_it(qtbot, tmp_path):
    """The log is a wide table; the timer is a small widget. They shouldn't share a size."""
    from habito.app import _build_engine_and_store
    from habito.config.models import Config
    from habito.ui.app import _LOG_PAGE, _TIMER_PAGE, HabitoApp

    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    app = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(app)
    app.show()
    qtbot.waitExposed(app)

    timer_size = app.size()
    app.show_page(_LOG_PAGE)
    assert app.width() > timer_size.width()

    app.show_page(_TIMER_PAGE)
    assert app.width() == timer_size.width()


def test_a_view_remembers_the_size_you_gave_it(qtbot, tmp_path):
    from habito.app import _build_engine_and_store
    from habito.config.models import Config
    from habito.ui.app import _LOG_PAGE, _TIMER_PAGE, HabitoApp

    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    app = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(app)
    app.show()
    qtbot.waitExposed(app)

    app.show_page(_LOG_PAGE)
    app.resize(900, 700)
    app.show_page(_TIMER_PAGE)
    app.show_page(_LOG_PAGE)

    assert app.size().width() == 900


# --- month navigation -----------------------------------------------------
def test_qts_own_navigation_bar_is_used(view):
    """Hand-rolling it was a mistake; the built-in one navigates and is keyboard-ready."""
    assert view.calendar.isNavigationBarVisible()
    assert view.calendar.findChild(QWidget, "qt_calendar_navigationbar") is not None


def test_the_cramped_menu_arrow_is_hidden(qapp):
    """Qt draws it in the month button's bottom-right corner, hard against the text."""
    sheet = DARK.stylesheet()
    assert "qt_calendar_monthbutton::menu-indicator" in sheet
    assert "image: none" in sheet


def test_the_arrow_buttons_are_left_unstyled(qapp):
    """Styling QToolButton's box is what stops Qt drawing arrow-type buttons at all."""
    sheet = DARK.stylesheet()
    for name in ("qt_calendar_prevmonth", "qt_calendar_nextmonth"):
        assert name not in sheet


def test_the_month_button_still_opens_its_menu(view):
    """Hiding the indicator is cosmetic — the button keeps its popup."""
    month_button = view.calendar.findChild(QToolButton, "qt_calendar_monthbutton")
    assert month_button is not None
    assert month_button.menu() is not None
    assert month_button.menu().actions()  # the twelve months


def test_the_year_keeps_its_spin_box(view):
    assert view.calendar.findChild(QSpinBox, "qt_calendar_yearedit") is not None


def test_the_prev_and_next_buttons_exist(view):
    for name in ("qt_calendar_prevmonth", "qt_calendar_nextmonth"):
        assert view.calendar.findChild(QToolButton, name) is not None


def test_paging_the_calendar_moves_the_month(view):
    view.show_month(2026, 6)
    assert view.shown_month() == (2026, 6)

    view.calendar.showNextMonth()
    assert view.shown_month() == (2026, 7)

    view.calendar.showPreviousMonth()
    assert view.shown_month() == (2026, 6)


@pytest.mark.parametrize(
    ("start", "expected"),
    [((2026, 12), (2027, 1)), ((2026, 1), (2026, 2))],
)
def test_paging_rolls_over_the_year(view, start, expected):
    view.show_month(*start)
    view.calendar.showNextMonth()
    assert view.shown_month() == expected


def test_the_month_total_follows_the_month_shown(view):
    other = ANCHOR.replace(day=10) - timedelta(days=40)
    view.set_summaries(
        {
            ANCHOR: summary(ANCHOR, verified=100 * 60),
            other: summary(other, verified=30 * 60),
        }
    )
    view.show_month(ANCHOR.year, ANCHOR.month)
    assert "1h 40m this month" in view._total_lbl.text()

    view.show_month(other.year, other.month)
    assert "30m this month" in view._total_lbl.text()


def build_app(qtbot, tmp_path):
    from habito.app import _build_engine_and_store
    from habito.config.models import Config
    from habito.ui.app import HabitoApp

    settings = tmp_path / "config" / "settings.toml"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("[goals]\ndaily_minutes = 100\nbuffer_minutes = 5\n", encoding="utf-8")
    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "config_path": settings,
        }
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    app = HabitoApp(config, engine, store, test_mode=False)
    qtbot.addWidget(app)
    return app, config


def test_changing_the_goal_recolours_the_calendar_without_a_restart(qtbot, tmp_path):
    from habito.ui.settings_view import SettingsValues

    app, _ = build_app(qtbot, tmp_path)
    day = summary(ANCHOR, verified=70 * 60)  # short of the default 95-minute threshold
    app._calendar.set_summaries({ANCHOR: day})
    assert not app._calendar.calendar.meets_goal(day)

    app.on_save_settings(
        SettingsValues(
            break_minutes=5,
            rounds=4,
            daily_minutes=60,
            buffer_minutes=5,
            sound="asterisk",
        )
    )

    assert app._calendar.calendar.meets_goal(day)  # 70m now clears a 55m threshold
    assert "55m" in app._calendar._hint_lbl.text()


def test_the_goal_is_written_back_to_settings_toml(qtbot, tmp_path):
    from habito.ui.settings_view import SettingsValues

    app, config = build_app(qtbot, tmp_path)
    app.on_save_settings(
        SettingsValues(
            break_minutes=5,
            rounds=4,
            daily_minutes=150,
            buffer_minutes=15,
            sound="asterisk",
        )
    )

    written = config.settings_file().read_text(encoding="utf-8")
    assert "daily_minutes = 150" in written
    assert "buffer_minutes = 15" in written


def test_setting_a_stretch_goal_stars_days_without_a_restart(qtbot, tmp_path):
    from habito.ui.settings_view import SettingsValues

    app, _ = build_app(qtbot, tmp_path)
    great = summary(ANCHOR, verified=200 * 60)
    app._calendar.set_summaries({ANCHOR: great})
    assert not app._calendar.calendar.meets_stretch(great)  # no stretch goal yet

    app.on_save_settings(
        SettingsValues(
            break_minutes=5,
            rounds=4,
            daily_minutes=100,
            buffer_minutes=5,
            stretch_minutes=180,
            sound="asterisk",
        )
    )

    assert app._calendar.calendar.meets_stretch(great)
    assert "★" in app._calendar._hint_lbl.text()


def test_turning_the_stretch_goal_off_again_removes_the_star(qtbot, tmp_path):
    from habito.ui.settings_view import SettingsValues

    app, config = build_app(qtbot, tmp_path)

    def save(stretch: int) -> str | None:
        return app.on_save_settings(
            SettingsValues(
                break_minutes=5,
                rounds=4,
                daily_minutes=100,
                buffer_minutes=5,
                stretch_minutes=stretch,
                sound="asterisk",
            )
        )

    save(180)
    assert app._calendar.calendar.stretch_seconds() is not None

    save(0)  # the spin's "Off"
    assert app._calendar.calendar.stretch_seconds() is None
    assert "★" not in app._calendar._hint_lbl.text()
    assert "stretch_minutes = 0" in config.settings_file().read_text(encoding="utf-8")


def test_a_stretch_goal_under_the_daily_goal_is_reported_not_applied(qtbot, tmp_path):
    from habito.ui.settings_view import SettingsValues

    app, _ = build_app(qtbot, tmp_path)
    error = app.on_save_settings(
        SettingsValues(
            break_minutes=5,
            rounds=4,
            daily_minutes=100,
            buffer_minutes=5,
            stretch_minutes=60,
            sound="asterisk",
        )
    )

    assert error is not None
    assert "stretch goal must be above" in error
    assert app._calendar.calendar.stretch_seconds() is None  # nothing was applied


def test_the_stretch_goal_round_trips_through_settings_toml(qtbot, tmp_path):
    from habito.config.loader import load_config
    from habito.ui.settings_view import SettingsValues

    app, config = build_app(qtbot, tmp_path)
    app.on_save_settings(
        SettingsValues(
            break_minutes=5,
            rounds=4,
            daily_minutes=100,
            buffer_minutes=5,
            stretch_minutes=180,
            sound="asterisk",
        )
    )

    reloaded = load_config(project_root=tmp_path, config_path=config.settings_file())
    assert reloaded.goals.stretch_minutes == 180
    assert reloaded.goals.stretch_seconds() == 175 * 60
