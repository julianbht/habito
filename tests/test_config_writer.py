from __future__ import annotations

from habito.config.loader import load_config
from habito.config.models import PomodoroConfig
from habito.config.writer import save_pomodoro


def test_save_pomodoro_updates_values_and_preserves_comments(tmp_path):
    cfg_file = tmp_path / "config" / "settings.toml"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(
        "# my custom comment\n"
        "[pomodoro]\n"
        "work_minutes = 25  # inline note\n"
        "break_minutes = 5\n"
        "rounds = 4\n"
        "quick_add_minutes = [1, 3, 5]\n",
        encoding="utf-8",
    )

    config = load_config(project_root=tmp_path, config_path=cfg_file)
    save_pomodoro(
        config,
        PomodoroConfig(work_minutes=50, break_minutes=10, rounds=2, quick_add_minutes=[1, 3, 5]),
    )

    text = cfg_file.read_text(encoding="utf-8")
    assert "# my custom comment" in text
    assert "inline note" in text  # comments survive the round-trip

    reloaded = load_config(project_root=tmp_path, config_path=cfg_file)
    assert reloaded.pomodoro.work_minutes == 50
    assert reloaded.pomodoro.break_minutes == 10
    assert reloaded.pomodoro.rounds == 2
    assert reloaded.pomodoro.quick_add_minutes == [1, 3, 5]  # untouched field preserved


def test_save_pomodoro_creates_section_when_missing(tmp_path):
    cfg_file = tmp_path / "settings.toml"
    cfg_file.write_text("[ui]\ntheme = \"dark\"\n", encoding="utf-8")

    config = load_config(project_root=tmp_path, config_path=cfg_file)
    save_pomodoro(config, PomodoroConfig(work_minutes=30, break_minutes=6, rounds=3))

    reloaded = load_config(project_root=tmp_path, config_path=cfg_file)
    assert reloaded.pomodoro.work_minutes == 30
    assert reloaded.ui.theme == "dark"  # existing section untouched
