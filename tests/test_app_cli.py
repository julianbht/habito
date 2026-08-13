"""main()'s config-path selection: which settings file --test-mode and --config pick.

Routed through the `doctor` subcommand, a plain function call with no Qt event loop to
work around — `run` would otherwise block on qt_app.exec().
"""

from __future__ import annotations

from unittest.mock import patch

from habito import app as app_module


def test_test_mode_defaults_to_test_settings_json(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "find_project_root", lambda: tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test-settings.json").write_text('{"pomodoro": {"rounds": 1}}', encoding="utf-8")

    with patch.object(app_module, "doctor", return_value=0) as doctor:
        app_module.main(["doctor", "--test-mode"])

    config = doctor.call_args[0][0]
    assert config.pomodoro.rounds == 1
    assert config.config_path == config_dir / "test-settings.json"


def test_without_test_mode_the_real_settings_file_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "find_project_root", lambda: tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "test-settings.json").write_text('{"pomodoro": {"rounds": 1}}', encoding="utf-8")

    with patch.object(app_module, "doctor", return_value=0) as doctor:
        app_module.main(["doctor"])

    config = doctor.call_args[0][0]
    # config/settings.json doesn't exist, so this is the built-in default — proof
    # config/test-settings.json was never consulted.
    assert config.pomodoro.rounds == 4
    assert config.config_path == config_dir / "settings.json"


def test_explicit_config_wins_over_the_test_mode_default(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "find_project_root", lambda: tmp_path)
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    real = config_dir / "settings.json"
    real.write_text('{"pomodoro": {"rounds": 7}}', encoding="utf-8")
    (config_dir / "test-settings.json").write_text('{"pomodoro": {"rounds": 1}}', encoding="utf-8")

    with patch.object(app_module, "doctor", return_value=0) as doctor:
        app_module.main(["doctor", "--test-mode", "--config", str(real)])

    config = doctor.call_args[0][0]
    assert config.pomodoro.rounds == 7
