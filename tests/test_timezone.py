"""The configured timezone, end to end: config → clock → event offsets → projection.

The scenario throughout is the one this setting exists for — a machine deliberately set
to New York while the person using it is in Berlin.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from PySide6.QtCore import QTime

from habito.config.models import SYSTEM_TZ, TimeConfig
from habito.domain.events import logical_date, logical_day
from habito.engine.clock import FakeClock, SystemClock

BERLIN = ZoneInfo("Europe/Berlin")
NEW_YORK = ZoneInfo("America/New_York")


# --- config ---------------------------------------------------------------
def test_system_is_the_default_and_means_no_zone():
    config = TimeConfig()
    assert config.timezone == SYSTEM_TZ
    assert config.zone() is None


def test_a_named_zone_resolves():
    assert TimeConfig(timezone="Europe/Berlin").zone() == BERLIN


def test_an_unknown_zone_is_refused_at_load_time():
    with pytest.raises(ValidationError, match="unknown timezone"):
        TimeConfig(timezone="Europe/Berlim")


def test_every_offered_zone_actually_resolves():
    """Windows ships no tz database, so these all fail without the tzdata dependency."""
    for name in TimeConfig().choices():
        assert ZoneInfo(name) is not None


def test_a_hand_edited_zone_is_kept_in_the_picker():
    """Otherwise opening Settings would silently offer no way back to your own setting."""
    config = TimeConfig(timezone="Pacific/Auckland")
    assert "Pacific/Auckland" in config.choices()
    assert "Pacific/Auckland" not in TimeConfig().choices()  # not in the shortlist


# --- localizing typed-in times (the backfill path) ------------------------
def test_a_typed_time_is_read_as_being_in_the_configured_zone():
    """Not converted from the machine's zone — read as already being in Berlin."""
    typed = datetime(2026, 8, 4, 23, 50)
    stamped = TimeConfig(timezone="Europe/Berlin").localize(typed)

    assert stamped.hour == 23  # the wall-clock reading is preserved
    assert stamped.utcoffset().total_seconds() == 2 * 3600  # CEST
    assert stamped.astimezone(UTC).hour == 21


def test_localize_follows_the_machine_when_set_to_system():
    typed = datetime(2026, 8, 4, 23, 50)
    stamped = TimeConfig().localize(typed)
    assert stamped.tzinfo is not None
    assert stamped.hour == 23


# --- the clock ------------------------------------------------------------
def test_the_clock_reports_the_configured_zones_offset():
    clock = SystemClock(BERLIN)
    assert clock.utc_offset_minutes() in (60, 120)  # CET or CEST, whenever this runs


def test_the_clock_tracks_dst_rather_than_assuming_a_fixed_offset():
    """Same zone, two dates, two offsets — resolved at the instant, not hardcoded."""
    summer = FakeClock(start=datetime(2026, 8, 4, 12, 0, tzinfo=UTC))
    winter = FakeClock(start=datetime(2026, 1, 4, 12, 0, tzinfo=UTC))
    summer.set_zone(BERLIN)
    winter.set_zone(BERLIN)

    assert summer.utc_offset_minutes() == 120  # CEST
    assert winter.utc_offset_minutes() == 60  # CET


def test_today_differs_between_zones_at_the_same_instant():
    """01:00 in Berlin is still the previous evening in New York."""
    instant = datetime(2026, 8, 5, 23, 0, tzinfo=UTC)  # 01:00 Aug 6 in Berlin

    berlin = FakeClock(start=instant)
    berlin.set_zone(BERLIN)
    new_york = FakeClock(start=instant)
    new_york.set_zone(NEW_YORK)

    assert logical_day(berlin.local_now()) == date(2026, 8, 6)
    assert logical_day(new_york.local_now()) == date(2026, 8, 5)


def test_the_rollover_hour_keeps_the_small_hours_on_the_previous_day():
    """At 01:00 with a 3am rollover, "today" is still yesterday."""
    late = FakeClock(start=datetime(2026, 8, 5, 23, 0, tzinfo=UTC))  # 01:00 Aug 6 Berlin
    late.set_zone(BERLIN)

    assert logical_day(late.local_now(), rollover_hour=0) == date(2026, 8, 6)
    assert logical_day(late.local_now(), rollover_hour=3) == date(2026, 8, 5)


# --- what the log actually records ---------------------------------------
def test_events_land_on_the_configured_zones_day_not_the_machines():
    """The bug this setting fixes: a Berlin evening filed under the New York day."""
    from habito.config.models import PomodoroConfig
    from habito.engine.pomodoro import PomodoroEngine

    # 22:30 Berlin on Aug 5 — which is 16:30 on Aug 5 in New York, same day here, but
    # the offset recorded on the event is what decides the calendar.
    instant = datetime(2026, 8, 5, 20, 30, tzinfo=UTC)
    events = []
    clock = FakeClock(start=instant)
    clock.set_zone(BERLIN)
    PomodoroEngine(PomodoroConfig(), sink=events.append, clock=clock, habit="study").start()

    assert events[0].tz_offset_minutes == 120
    assert logical_date(events[0]) == date(2026, 8, 5)


def test_changing_the_zone_moves_which_day_new_events_belong_to():
    from habito.config.models import PomodoroConfig
    from habito.engine.pomodoro import PomodoroEngine

    instant = datetime(2026, 8, 5, 23, 30, tzinfo=UTC)  # 01:30 Aug 6 Berlin
    events = []
    clock = FakeClock(start=instant)
    engine = PomodoroEngine(PomodoroConfig(), sink=events.append, clock=clock, habit="study")

    clock.set_zone(NEW_YORK)
    engine.start()
    clock.set_zone(BERLIN)
    engine.stop()

    assert logical_date(events[0]) == date(2026, 8, 5)  # still Aug 5 in New York
    assert logical_date(events[-1]) == date(2026, 8, 6)  # already Aug 6 in Berlin


# --- the pickers ----------------------------------------------------------
def test_the_settings_picker_reports_the_chosen_zone(qtbot):
    from habito.config.models import PomodoroConfig
    from habito.ui.settings_view import SettingsDialog

    dialog = SettingsDialog(controller=None, pomodoro=PomodoroConfig())
    qtbot.addWidget(dialog)

    assert dialog.values().timezone == SYSTEM_TZ  # opens on whatever is configured
    dialog._tz_box.setCurrentIndex(dialog._tz_box.findData("Europe/Berlin"))
    assert dialog.values().timezone == "Europe/Berlin"


def test_the_picker_opens_on_a_hand_edited_zone_outside_the_shortlist(qtbot):
    from habito.config.models import PomodoroConfig
    from habito.ui.settings_view import SettingsDialog

    dialog = SettingsDialog(
        controller=None,
        pomodoro=PomodoroConfig(),
        time_config=TimeConfig(timezone="Pacific/Auckland"),
    )
    qtbot.addWidget(dialog)

    assert dialog.values().timezone == "Pacific/Auckland"


def test_the_backfill_dialog_stamps_the_configured_zone(qtbot):
    """A time typed here is Berlin wall-clock, however the computer is set."""
    from habito.ui.backfill_view import BackfillDialog

    captured = []
    dialog = BackfillDialog(
        on_submit=captured.append,
        default_work=25,
        default_break=5,
        default_rounds=1,
        habit="study",
        time_config=TimeConfig(timezone="Europe/Berlin"),
        today=date(2026, 8, 5),
    )
    qtbot.addWidget(dialog)

    assert dialog._date.date().toPython() == date(2026, 8, 5)
    dialog._time.setTime(QTime(23, 50))
    dialog._submit()

    started = captured[0][0]
    assert started.tz_offset_minutes == 120  # CEST, not the machine's offset
    assert logical_date(started) == date(2026, 8, 5)  # 23:50 is still the 5th in Berlin
