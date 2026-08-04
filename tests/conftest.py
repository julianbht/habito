from __future__ import annotations

from habito.config.models import PomodoroConfig


def make_config(work=25, brk=5, rounds=4) -> PomodoroConfig:
    return PomodoroConfig(work_minutes=work, break_minutes=brk, rounds=rounds)
