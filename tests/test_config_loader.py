"""Reading and writing the settings files.

A save writes the whole config rather than the touched section, so the thing worth
asserting is that a round-trip brings back the settings the UI can't reach as well as the
ones it can. Without ``--config``, saves go to the gitignored local file and the committed
shared file is only ever read.
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
                "pomodoro": {"templates": [{"name": "Deep work", "rounds": 6}]},
                "evidence": {"branch": "trunk", "auto_push": False},
                "paths": {"data_repo": "../elsewhere"},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(project_root=tmp_path, config_path=cfg_file)
    config.pomodoro = config.pomodoro.model_copy(update={"resume_window_minutes": 20})
    save_config(config)

    reloaded = load_config(project_root=tmp_path, config_path=cfg_file)
    assert reloaded.pomodoro.resume_window_minutes == 20
    assert reloaded.pomodoro.active().name == "Deep work"
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

    assert [t.label() for t in config.pomodoro.templates] == ["4 × 25 · 5", "2 × 25 · 5"]
    assert config.pomodoro.active().rounds == 4
    assert config.goals.low_minutes == 100


def test_extras_defaults_off_and_missing_key_falls_back(tmp_path):
    """No `extras` key at all in the file — old settings.json files predate it."""
    config = load_config(project_root=tmp_path, config_path=tmp_path / "nope.json")

    assert config.extras.enabled is False
    assert config.extras.wakeup.habit == "sleep"


def test_saving_preserves_a_hand_set_extras_flag(tmp_path):
    """`extras.enabled` has no Settings-dialog widget — only the round-trip keeps it."""
    cfg_file = tmp_path / "config" / "settings.json"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text(
        json.dumps({"extras": {"enabled": True, "wakeup": {"habit": "sleep"}}}),
        encoding="utf-8",
    )

    config = load_config(project_root=tmp_path, config_path=cfg_file)
    save_config(config)

    reloaded = load_config(project_root=tmp_path, config_path=cfg_file)
    assert reloaded.extras.enabled is True
    assert reloaded.extras.wakeup.habit == "sleep"


def _write(path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_without_a_local_file_the_shared_one_is_read_and_left_unwritten(tmp_path):
    shared = tmp_path / "config" / "settings.json"
    _write(shared, {"goals": {"low_minutes": 50}})

    config = load_config(project_root=tmp_path)
    assert config.goals.low_minutes == 50

    config.goals = config.goals.model_copy(update={"low_minutes": 70})
    save_config(config)

    assert json.loads(shared.read_text(encoding="utf-8")) == {"goals": {"low_minutes": 50}}
    local = tmp_path / "config" / "settings.local.json"
    assert json.loads(local.read_text(encoding="utf-8"))["goals"]["low_minutes"] == 70


def test_a_local_file_wins_over_the_shared_one(tmp_path):
    _write(tmp_path / "config" / "settings.json", {"goals": {"low_minutes": 50}})
    _write(tmp_path / "config" / "settings.local.json", {"goals": {"low_minutes": 70}})

    assert load_config(project_root=tmp_path).goals.low_minutes == 70
