"""Reading and writing ``settings.json``.

A save writes the whole config rather than the touched section, so the thing worth
asserting is that a round-trip brings back the settings the UI can't reach as well as the
ones it can.
"""

from __future__ import annotations

import json

from habito.config.loader import load_config, save_config


def test_saving_preserves_the_settings_the_ui_cannot_reach(tmp_path):
    cfg_file = tmp_path / "config" / "settings.json"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(
        json.dumps(
            {
                "habit": "reading",
                "pomodoro": {"work_minutes": 25, "break_minutes": 5, "rounds": 4},
                "evidence": {"branch": "trunk", "auto_push": False},
                "paths": {"data_repo": "../elsewhere"},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(project_root=tmp_path, config_path=cfg_file)
    config.pomodoro = config.pomodoro.model_copy(update={"work_minutes": 50})
    save_config(config)

    reloaded = load_config(project_root=tmp_path, config_path=cfg_file)
    assert reloaded.pomodoro.work_minutes == 50
    # None of these have a widget, so only the round-trip keeps them.
    assert reloaded.habit == "reading"
    assert reloaded.evidence.branch == "trunk"
    assert reloaded.evidence.auto_push is False
    assert reloaded.paths.data_repo == "../elsewhere"


def test_the_injected_paths_are_not_written_to_the_file(tmp_path):
    """``project_root`` and ``config_path`` come from the loader, not the file."""
    cfg_file = tmp_path / "settings.json"
    config = load_config(project_root=tmp_path, config_path=cfg_file)

    save_config(config)

    written = json.loads(cfg_file.read_text(encoding="utf-8"))
    assert "project_root" not in written
    assert "config_path" not in written


def test_a_missing_file_loads_the_defaults(tmp_path):
    config = load_config(project_root=tmp_path, config_path=tmp_path / "nope.json")

    assert config.pomodoro.rounds == 4
    assert config.goals.daily_minutes == 100
