"""Window-level keyboard shortcuts, delivered as real key events through Qt.

These go through ``QShortcut``, so they only prove anything if the key press travels the
real event path — which is what ``qtbot.keyClick`` on the window gives us.
"""

from __future__ import annotations

import pytest
from PySide6.QtCore import Qt

from habito.app import _build_engine_and_store
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


def press(qtbot, window, key, modifier=Qt.KeyboardModifier.ControlModifier):
    qtbot.keyClick(window, key, modifier)


def press_space(qtbot, window):
    """Start/pause/resume is the one shortcut that's deliberately bare — see
    TimerView.focus_first and the SHORTCUTS comment in settings_view.py."""
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
    from habito.ui.shortcuts_view import ShortcutsDialog

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
    """The corrections sit above it, so Settings is where you'd expect: at the bottom."""
    assert entries(app) == [
        "Timer",
        "Calendar",
        "Log",
        "",
        "Backfill…",
        "Retract session…",
        "Shortcuts…",
        "Settings…",
    ]


def test_backfill_comes_before_settings(qtbot, app):
    listed = entries(app)
    assert listed.index("Backfill…") < listed.index("Settings…")


def test_the_two_corrections_are_grouped(qtbot, app):
    """Backfill and Retract are the pair of by-hand corrections, so they sit together."""
    listed = entries(app)
    assert listed.index("Retract session…") == listed.index("Backfill…") + 1


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
