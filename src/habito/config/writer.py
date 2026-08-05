"""Persist UI-editable settings back to ``settings.toml``.

Uses ``tomlkit`` so the file's comments and formatting survive the round-trip — only the
touched values change. Everything not editable in-app stays hand-edited in the TOML.
"""

from __future__ import annotations

import tomlkit

from habito.config.models import Config, GoalsConfig, PomodoroConfig, TimeConfig, UIConfig


def _save_section(config: Config, section: str, values: dict[str, object]) -> None:
    """Merge ``values`` into ``[section]``, leaving the rest of the document untouched."""
    path = config.settings_file()
    doc = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()

    table = doc.get(section)
    if table is None:
        table = tomlkit.table()
        doc[section] = table

    for key, value in values.items():
        table[key] = value

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _tidy(value: float) -> float | int:
    """Write 25 rather than 25.0; keep the precision only when it's actually used."""
    return int(value) if float(value).is_integer() else round(value, 4)


def save_pomodoro(config: Config, pomodoro: PomodoroConfig) -> None:
    _save_section(
        config,
        "pomodoro",
        {
            "work_minutes": _tidy(pomodoro.work_minutes),
            "break_minutes": pomodoro.break_minutes,
            "rounds": pomodoro.rounds,
        },
    )


def save_ui(config: Config, ui: UIConfig) -> None:
    """Only the parts of ``[ui]`` the Settings window can change."""
    _save_section(config, "ui", {"sound": ui.sound})


def save_time(config: Config, time_config: TimeConfig) -> None:
    _save_section(
        config,
        "time",
        {
            "timezone": time_config.timezone,
            "rollover_hour": time_config.rollover_hour,
        },
    )


def save_goals(config: Config, goals: GoalsConfig) -> None:
    _save_section(
        config,
        "goals",
        {"daily_minutes": goals.daily_minutes, "buffer_minutes": goals.buffer_minutes},
    )
