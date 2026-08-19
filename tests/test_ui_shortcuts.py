"""Window-level keyboard shortcuts, delivered as real key events through Qt.

These go through ``QShortcut``, so they only prove anything if the key press travels the
real event path — which is what ``qtbot.keyClick`` on the window gives us.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from PySide6.QtCore import Qt

from habito.app import _build_engine_and_store, _build_wakeup_store, _build_workout_store
from habito.config.models import Config
from habito.engine.pomodoro import State
from habito.ui import theme
from habito.ui.app import HabitoApp


@pytest.fixture
def app(qtbot, tmp_path):
    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    # store built with test_mode=False so the log lives under tmp_path; the *window*
    # still runs in test mode. Otherwise every test shares one scratch file.
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def _window_with_extras(qtbot, tmp_path, wakeup: bool = False, workout: bool = False):
    """A window with the extras stores the flags ask for — the composition root only
    builds each when its habit is configured (see habito.app)."""
    extras: dict[str, object] = {"enabled": True}
    if wakeup:
        extras["wakeup"] = {"habit": "sleep"}
    if workout:
        extras["workout"] = {"habit": "workout"}
    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path, "extras": extras}
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(
        config,
        engine,
        store,
        _build_wakeup_store(config, test_mode=False) if wakeup else None,
        _build_workout_store(config, test_mode=False) if workout else None,
        test_mode=True,
    )
    qtbot.addWidget(window)
    return window


def press(qtbot, window, key, modifier=Qt.KeyboardModifier.ControlModifier):
    qtbot.keyClick(window, key, modifier)


def press_space(qtbot, window):
    """Start/pause/resume is the one shortcut that's deliberately bare — see
    TimerView.focus_first and the SHORTCUTS comment in shortcuts_dialog.py."""
    qtbot.keyClick(window, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier)


def test_space_starts_then_pauses_then_resumes(qtbot, app):
    assert app._engine.state is State.idle

    press_space(qtbot, app)
    assert app._engine.state is State.work

    press_space(qtbot, app)
    assert app._engine.state is State.paused

    press_space(qtbot, app)
    assert app._engine.state is State.work


def test_ctrl_period_stops_the_session(qtbot, app):
    press_space(qtbot, app)
    assert app._engine.state is State.work

    press(qtbot, app, Qt.Key.Key_Period)
    assert app._engine.state is State.done


def test_ctrl_arrows_extend_the_running_round(qtbot, app):
    press_space(qtbot, app)
    before = app._engine.snapshot().phase_target_seconds

    press(qtbot, app, Qt.Key.Key_Up)
    assert app._engine.snapshot().phase_target_seconds == before + 60

    press(qtbot, app, Qt.Key.Key_Down)
    assert app._engine.snapshot().phase_target_seconds == before


def test_ctrl_arrows_set_the_planned_length_while_idle(qtbot, app):
    assert app._engine.state is State.idle

    press(qtbot, app, Qt.Key.Key_Up)
    assert app._config.pomodoro.work_minutes == 26

    press(qtbot, app, Qt.Key.Key_Down)
    assert app._config.pomodoro.work_minutes == 25


def test_ctrl_comma_opens_settings_and_escape_closes_it(qtbot, app):
    press(qtbot, app, Qt.Key.Key_Comma)
    dialog = app._settings_dialog
    assert dialog is not None and dialog.isVisible()

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()


def test_progress_fills_the_whole_window_including_the_menu_row(qtbot, app):
    """The fill is the window's background, so no row sits outside it."""
    app.resize(400, 500)
    qtbot.waitExposed(app)
    app._engine.start()
    app._background.set_progress(0.5, theme.OK)

    image = app._background.grab().toImage()
    fill = app.ui_theme.progress_fill(theme.OK)
    left = int(image.width() * 0.08)

    menu_row_y = app._menu_btn.geometry().center().y()
    assert image.pixelColor(left, menu_row_y) == fill  # the row the ☰ lives in
    assert image.pixelColor(left, 2) == fill  # the very top edge
    assert image.pixelColor(left, image.height() - 2) == fill  # and the very bottom


def test_tab_from_the_timer_reaches_the_menu(qtbot, app):
    app.on_start()  # stop is disabled while idle, and Qt skips disabled widgets
    stop = app._view.stop_button()
    assert stop.isEnabled()

    stop.setFocus()
    qtbot.keyClick(app.focusWidget(), Qt.Key.Key_Tab)
    assert app.focusWidget() is app._menu_btn


def test_shortcuts_menu_entry_opens_the_dialog(qtbot, app, monkeypatch):
    from habito.ui.dialogs.shortcuts_dialog import ShortcutsDialog

    opened = []
    monkeypatch.setattr(ShortcutsDialog, "exec", lambda self: opened.append(self) or 0)

    app.on_open_shortcuts()

    assert len(opened) == 1


def test_settings_shortcut_does_not_stack_duplicate_dialogs(qtbot, app):
    press(qtbot, app, Qt.Key.Key_Comma)
    first = app._settings_dialog
    press(qtbot, app, Qt.Key.Key_Comma)

    assert app._settings_dialog is first


def entries(app) -> list[str]:
    """The ☰ menu's entries in order, separators as empty strings."""
    return ["" if a.isSeparator() else a.text() for a in app.build_menu().actions()]


def test_settings_is_the_last_menu_entry(qtbot, app):
    """One entry per stream you log, then Settings where you'd expect it: at the bottom."""
    assert entries(app) == [
        "Timer",
        "Calendar",
        "Log",
        "",
        "Sessions…",
        "Shortcuts…",
        "Settings…",
    ]


def test_backfill_has_no_menu_entry_of_its_own(qtbot, app):
    """It's the sessions manager's primary button — adding a session and correcting one
    belong in the same window, not in two entries you have to know are related."""
    assert "Backfill…" not in entries(app)


def test_tags_have_no_menu_entry_of_their_own(qtbot, app):
    """A tag only ever means something on a session, and the picker inside "Manage tags…"
    is the catalog manager (see catalog_picker.py)."""
    assert "Manage tags…" not in entries(app)


def test_opening_manage_sessions_launches_the_dialog(qtbot, app, monkeypatch):
    from habito.ui.dialogs.manage_sessions_dialog import ManageSessionsDialog

    opened = []
    monkeypatch.setattr(ManageSessionsDialog, "exec", lambda self: opened.append(self) or 0)

    app.on_open_manage_sessions()

    assert len(opened) == 1


def test_sleep_is_absent_when_extras_are_disabled(qtbot, app):
    """Off by default — the whole point of the flag (see CLAUDE.md § Extras)."""
    assert "Sleep…" not in entries(app)


def test_sleep_appears_between_sessions_and_shortcuts_when_enabled(qtbot, tmp_path):
    window = _window_with_extras(qtbot, tmp_path, wakeup=True)

    listed = entries(window)
    assert listed.index("Sessions…") < listed.index("Sleep…") < listed.index("Shortcuts…")


def test_opening_manage_wakeups_launches_the_manager_not_the_log_form(qtbot, tmp_path, monkeypatch):
    """The manager is the door; the logging form opens from its "Log wake-up…" button, so
    you can see whether you already logged today before adding another."""
    from habito.ui.dialogs.entry_manager_dialog import EntryManagerDialog
    from habito.ui.dialogs.wakeup_dialog import WakeUpDialog

    window = _window_with_extras(qtbot, tmp_path, wakeup=True)
    opened, forms = [], []
    monkeypatch.setattr(EntryManagerDialog, "exec", lambda self: opened.append(self) or 0)
    monkeypatch.setattr(WakeUpDialog, "exec", lambda self: forms.append(self) or 0)

    window.on_open_manage_wakeups()

    assert len(opened) == 1
    assert forms == []


def test_the_wakeup_form_opens_from_the_manager_seeded_from_config(qtbot, tmp_path, monkeypatch):
    from habito.ui.dialogs.wakeup_dialog import WakeUpDialog

    window = _window_with_extras(qtbot, tmp_path, wakeup=True)
    opened = []
    monkeypatch.setattr(WakeUpDialog, "exec", lambda self: opened.append(self) or 0)

    window._open_wakeup_form(window, lambda events: None, None)

    assert len(opened) == 1
    assert opened[0].windowTitle() == "Log wake-up"


def test_workouts_are_absent_when_extras_are_disabled(qtbot, app):
    """Off by default — the whole point of the flag (see CLAUDE.md § Extras)."""
    assert "Workouts…" not in entries(app)


def test_workouts_appear_after_sleep_when_enabled(qtbot, tmp_path):
    window = _window_with_extras(qtbot, tmp_path, wakeup=True, workout=True)

    listed = entries(window)
    assert listed.index("Sleep…") + 1 == listed.index("Workouts…")
    assert listed.index("Workouts…") < listed.index("Shortcuts…")


def test_no_separate_workout_catalog_entry(qtbot, tmp_path):
    """The picker inside "Log workout" is the catalog manager, so there is nothing a
    standalone one would add (see catalog_picker.py)."""
    window = _window_with_extras(qtbot, tmp_path, workout=True)

    assert "Workout types…" not in entries(window)
    assert "Manage workouts…" not in entries(window)


def test_opening_manage_workouts_launches_the_manager_not_the_log_form(
    qtbot, tmp_path, monkeypatch
):
    from habito.ui.dialogs.entry_manager_dialog import EntryManagerDialog
    from habito.ui.dialogs.workout_log_dialog import WorkoutLogDialog

    window = _window_with_extras(qtbot, tmp_path, workout=True)
    opened, forms = [], []
    monkeypatch.setattr(EntryManagerDialog, "exec", lambda self: opened.append(self) or 0)
    monkeypatch.setattr(WorkoutLogDialog, "exec", lambda self: forms.append(self) or 0)

    window.on_open_manage_workouts()

    assert len(opened) == 1
    assert forms == []


def test_the_workout_form_opens_from_the_manager(qtbot, tmp_path, monkeypatch):
    from habito.ui.dialogs.workout_log_dialog import WorkoutLogDialog

    window = _window_with_extras(qtbot, tmp_path, workout=True)
    opened = []
    monkeypatch.setattr(WorkoutLogDialog, "exec", lambda self: opened.append(self) or 0)

    window._open_workout_form(window, lambda events: None, None)

    assert len(opened) == 1
    assert opened[0].windowTitle() == "Log workout"


def test_editing_an_entry_opens_the_same_form_pre_filled(qtbot, tmp_path, monkeypatch):
    """One form for both, so "Edit…" can't drift out of step with "Log workout…"."""
    from habito.actions.workout import build_workout_logged_event
    from habito.ui.dialogs.workout_log_dialog import WorkoutLogDialog

    window = _window_with_extras(qtbot, tmp_path, workout=True)
    logged = build_workout_logged_event(
        datetime(2026, 8, 4, 18, 0, tzinfo=timezone(timedelta(hours=2))),
        ["running"],
        habit="workout",
    )
    window._append_workout([logged])  # it is a standing entry, so its workout is known
    opened = []
    monkeypatch.setattr(WorkoutLogDialog, "exec", lambda self: opened.append(self) or 0)

    window._open_workout_form(window, lambda events: None, logged)

    assert opened[0].windowTitle() == "Edit workout log"
    assert opened[0].picker.selected() == ["running"]


def test_the_current_view_is_ticked_in_the_menu(qtbot, app):
    from habito.ui.app import _LOG_PAGE

    app.show_page(_LOG_PAGE)
    checked = [a.text() for a in app.build_menu().actions() if a.isChecked()]
    assert checked == ["Log"]


# --- window flags ---------------------------------------------------------
def test_always_on_top_builds_the_window(qtbot, tmp_path):
    """`always_on_top = true` used to name a Qt flag that doesn't exist, so turning the
    setting on raised AttributeError before the window ever appeared."""
    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "ui": {"always_on_top": True},
        }
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)

    assert window.windowFlags() & Qt.WindowType.WindowStaysOnTopHint


def test_always_on_top_off_by_default(qtbot, app):
    assert not (app.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
