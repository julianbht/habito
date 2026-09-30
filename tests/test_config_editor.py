"""The apply-and-persist rules, without a window.

Only what belongs to the editor itself: whether a change was accepted, and what happens
to the config when it wasn't. The side effects an accepted change triggers are the
window's, and are tested where they live — in the calendar, timer and test-mode suites.
"""

from __future__ import annotations

from datetime import time

from habito.config.editor import ConfigEditor
from habito.config.models import Config, PomodoroConfig, SessionTemplate

_VALID = {
    "resume_window_minutes": 10,
    "low_minutes": 100,
    "low_buffer_minutes": 5,
    "middle_minutes": 0,
    "middle_buffer_minutes": 10,
    "high_minutes": 0,
    "high_buffer_minutes": 15,
    "break_reminder_minutes": 3,
    "sound": "asterisk",
    "timezone": "Europe/Berlin",
    "rollover_hour": 3,
}


def build_config(tmp_path) -> Config:
    settings = tmp_path / "config" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    return Config.model_validate({"project_root": tmp_path, "config_path": settings})


def test_a_rejected_change_leaves_the_whole_config_untouched(tmp_path):
    """One bad value rejects the entire Save, so no section is left half-applied."""
    config = build_config(tmp_path)
    before_goals, before_time = config.goals, config.time

    # The middle goal has to sit above the low one — a model-level rule, so it arrives
    # named by its section rather than by a field.
    outcome = ConfigEditor(config).apply_settings(
        **{**_VALID, "middle_minutes": 60, "rollover_hour": 5}
    )

    assert not outcome.ok
    assert outcome.message is not None
    assert "middle goal must be above" in outcome.message
    assert config.goals is before_goals
    assert config.time is before_time  # the valid part of the same Save didn't land either


def test_a_field_level_rejection_is_named_by_its_field(tmp_path):
    config = build_config(tmp_path)

    outcome = ConfigEditor(config).apply_settings(**{**_VALID, "timezone": "Mars/Olympus"})

    assert not outcome.ok
    assert outcome.message is not None
    assert outcome.message.startswith("timezone: ")
    assert config.time.timezone != "Mars/Olympus"


def test_an_unwritable_settings_file_still_applies_the_change(tmp_path):
    """A failed write is a warning, not a rejection — the change is in force this session."""
    config = build_config(tmp_path)
    # A file where the settings directory should be, so writing the JSON raises OSError.
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    config.config_path = blocked / "settings.json"

    outcome = ConfigEditor(config).apply_settings(**{**_VALID, "low_minutes": 60})

    assert outcome.ok
    assert outcome.message is not None
    assert "couldn't write settings.json" in outcome.message
    assert config.goals.low_minutes == 60  # applied regardless


def test_the_timer_changes_only_the_active_templates_round_length(tmp_path):
    """The duration field edits work_minutes; break, rounds and the other templates are
    not its business."""
    config = build_config(tmp_path)
    config.pomodoro = PomodoroConfig(
        templates=[SessionTemplate(rounds=4), SessionTemplate(rounds=2)], active_template=1
    )

    outcome = ConfigEditor(config).apply_work_minutes(0.5)

    assert outcome.ok
    first, second = config.pomodoro.templates
    assert second.work_minutes == 0.5  # fractional survives the trip
    assert (second.break_minutes, second.rounds) == (5, 2)
    assert first.work_minutes == 25


def test_the_timer_rejects_a_zero_length_round(tmp_path):
    config = build_config(tmp_path)

    outcome = ConfigEditor(config).apply_work_minutes(0)

    assert not outcome.ok
    assert outcome.message is not None
    assert outcome.message.startswith("work_minutes: ")
    assert config.pomodoro.active().work_minutes == 25


def test_templates_are_replaced_as_one_list(tmp_path):
    config = build_config(tmp_path)
    templates = [SessionTemplate(name="Deep work", rounds=6), SessionTemplate(rounds=1)]

    outcome = ConfigEditor(config).apply_templates(templates, 1)

    assert outcome.ok
    assert config.pomodoro.templates == templates
    assert config.pomodoro.active().rounds == 1
    assert config.pomodoro.resume_window_minutes == 10  # untouched


def test_an_empty_template_list_is_refused(tmp_path):
    """There is always a template to run."""
    config = build_config(tmp_path)
    before = config.pomodoro

    outcome = ConfigEditor(config).apply_templates([], 0)

    assert not outcome.ok
    assert config.pomodoro is before


def test_an_active_index_past_the_end_is_refused(tmp_path):
    config = build_config(tmp_path)

    outcome = ConfigEditor(config).apply_templates([SessionTemplate()], 1)

    assert not outcome.ok
    assert outcome.message is not None
    assert "out of range" in outcome.message


def test_settings_leave_the_templates_alone(tmp_path):
    config = build_config(tmp_path)
    before = config.pomodoro.templates

    outcome = ConfigEditor(config).apply_settings(**{**_VALID, "resume_window_minutes": 30})

    assert outcome.ok
    assert config.pomodoro.templates == before
    assert config.pomodoro.resume_window_minutes == 30


def test_omitting_the_wakeup_defaults_leaves_them_unchanged(tmp_path):
    """None means the section wasn't on screen (extras disabled) — not "clear it"."""
    config = build_config(tmp_path)
    before = config.extras.wakeup

    outcome = ConfigEditor(config).apply_settings(**_VALID)

    assert outcome.ok
    assert config.extras.wakeup == before


def test_the_wakeup_defaults_apply_when_both_are_given(tmp_path):
    config = build_config(tmp_path)

    outcome = ConfigEditor(config).apply_settings(
        **_VALID, default_wake_time=time(6, 30), default_bedtime=time(22, 45)
    )

    assert outcome.ok
    assert config.extras.wakeup.default_wake_time == time(6, 30)
    assert config.extras.wakeup.default_bedtime == time(22, 45)
    # Untouched by an edit that has nothing to do with it.
    assert config.extras.wakeup.habit == "sleep"
