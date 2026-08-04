"""Test mode must be inert and unmistakable.

Inert: the events log goes to a throwaway file, no evidence worker exists, and
``settings.toml`` is never rewritten. Unmistakable: everything is red.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QLabel

from habito.app import _build_engine_and_store, _events_path
from habito.config.models import Config
from habito.ui import theme
from habito.ui.app import HabitoApp
from habito.ui.settings_view import SettingsValues

SETTINGS = """\
[pomodoro]
work_minutes = 25
break_minutes = 5
rounds = 4
"""


@pytest.fixture
def config(tmp_path) -> Config:
    """A config whose data repo and settings file are both real files we can watch."""
    settings = tmp_path / "config" / "settings.toml"
    settings.parent.mkdir(parents=True)
    settings.write_text(SETTINGS, encoding="utf-8")
    (tmp_path / "data-repo").mkdir()
    return Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path / "data-repo")},
            "project_root": tmp_path,
            "config_path": settings,
        }
    )


def settings(*, brk: int = 5, rounds: int = 4, sound: str = "asterisk") -> SettingsValues:
    return SettingsValues(
        break_minutes=brk,
        rounds=rounds,
        daily_minutes=100,
        buffer_minutes=5,
        sound=sound,
    )


def banner_labels(app: HabitoApp) -> list[QLabel]:
    return [w for w in app.findChildren(QLabel) if w.objectName() == "banner"]


def build_app(qtbot, config: Config, *, test_mode: bool) -> HabitoApp:
    engine, store = _build_engine_and_store(config, test_mode)
    app = HabitoApp(config, engine, store, test_mode=test_mode)
    qtbot.addWidget(app)
    return app


# --- inert ----------------------------------------------------------------
def test_events_go_to_a_throwaway_file_outside_the_data_repo(config):
    live = _events_path(config, test_mode=False)
    test = _events_path(config, test_mode=True)

    assert live == config.events_path()
    assert test != live
    assert config.data_repo_path() not in test.parents


def test_a_session_writes_nothing_into_the_data_repo(qtbot, config):
    app = build_app(qtbot, config, test_mode=True)
    app.on_start()
    app.on_add_time(5)
    app.on_stop()

    assert list(config.data_repo_path().iterdir()) == []


def test_no_evidence_worker_is_attached(qtbot, config):
    app = build_app(qtbot, config, test_mode=True)
    assert app._worker is None


def test_settings_toml_is_not_rewritten(qtbot, config):
    before = config.settings_file().read_text(encoding="utf-8")

    app = build_app(qtbot, config, test_mode=True)
    assert app.on_save_settings(settings(brk=17, rounds=9)) is None
    assert app.on_set_work_minutes(42) is None

    assert config.settings_file().read_text(encoding="utf-8") == before
    # ...but the change still applies to this run, so the mode stays useful for trying things.
    assert app._config.pomodoro.break_minutes == 17
    assert app._config.pomodoro.work_minutes == 42


def test_live_mode_does_rewrite_settings_toml(qtbot, config):
    app = build_app(qtbot, config, test_mode=False)
    assert app.on_save_settings(settings(brk=17, rounds=9)) is None

    assert "break_minutes = 17" in config.settings_file().read_text(encoding="utf-8")


# --- unmistakable ---------------------------------------------------------
def test_accent_is_red_only_in_test_mode():
    assert theme.accent_for(True) == theme.ACCENT_TEST
    assert theme.accent_for(False) == theme.ACCENT_LIVE
    assert theme.ACCENT_TEST != theme.ACCENT_LIVE

    test_sheet = theme.build_stylesheet(theme.accent_for(True))
    live_sheet = theme.build_stylesheet(theme.accent_for(False))
    assert theme.ACCENT_TEST in test_sheet
    assert theme.ACCENT_LIVE not in test_sheet  # no blue survives into a test run
    assert theme.ACCENT_LIVE in live_sheet


def test_window_is_labelled_as_a_test_run(qtbot, config):
    app = build_app(qtbot, config, test_mode=True)
    assert "TEST MODE" in app.windowTitle()

    banners = banner_labels(app)
    assert len(banners) == 1
    assert "nothing is recorded" in banners[0].text()


def test_live_window_has_no_test_banner(qtbot, config):
    app = build_app(qtbot, config, test_mode=False)
    assert "TEST MODE" not in app.windowTitle()

    banners = banner_labels(app)
    assert banners == []
