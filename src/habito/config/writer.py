"""Persist UI-editable settings back to ``settings.toml``.

Uses ``tomlkit`` so the file's comments and formatting survive the round-trip — only the
touched values change. Currently just the Pomodoro format is editable in-app; everything
else stays hand-edited in the TOML.
"""

from __future__ import annotations

import tomlkit

from habito.config.models import Config, PomodoroConfig


def save_pomodoro(config: Config, pomodoro: PomodoroConfig) -> None:
    path = config.settings_file()
    doc = tomlkit.parse(path.read_text(encoding="utf-8")) if path.exists() else tomlkit.document()

    table = doc.get("pomodoro")
    if table is None:
        table = tomlkit.table()
        doc["pomodoro"] = table

    table["work_minutes"] = pomodoro.work_minutes
    table["break_minutes"] = pomodoro.break_minutes
    table["rounds"] = pomodoro.rounds

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
