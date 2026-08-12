"""Validate, apply and persist the settings the UI can change.

Two entry points, because there are two ways to change a setting: the timer's duration
field edits one value on its own, and the Settings dialog changes everything at once.
Nothing else needs to reach the config, so nothing else is offered.

The dialog's changes are validated **as one config**. Rejecting the whole set rather than
applying it section by section is what keeps a partly-applied Save from happening — the
old shape would apply the goals, then reject the timezone, and leave the file disagreeing
with the dialog you were still looking at. It also means one write per Save.

Deliberately free of Qt. What counts as a valid setting, and what a failed write should
say, are rules about configuration rather than about widgets, so they're testable without
standing up a window. The side effects that *follow* an accepted change — retuning the
clock, recolouring the calendar, preloading a sound — stay with the window, which is what
owns those things.

The ``Config`` handed in is mutated in place rather than replaced, so everything already
holding a reference to it sees the change.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import ValidationError

from habito.config.loader import save_config
from habito.config.models import Config, GoalsConfig, PomodoroConfig, TimeConfig, UIConfig


@dataclass(frozen=True)
class Applied:
    """What came of an apply attempt.

    Both a rejection and an applied-but-unsaved change carry a message, and the caller
    shows either one the same way. They're still distinct, because only an accepted
    change may trigger the side effects that follow it: a rejected one changed nothing,
    so pushing the (unchanged) values at the views would claim an edit that didn't happen.
    """

    ok: bool
    message: str | None = None


def _rejected(exc: ValidationError) -> Applied:
    """Report the first complaint, named by the field it came from.

    A model-level validator — "the stretch goal must be above the daily goal" — belongs to
    no single field and arrives with a ``loc`` naming only the section, so the section name
    is what gets shown. Either way the message points at somewhere on the dialog.
    """
    first = exc.errors()[0]
    field = first["loc"][-1] if first["loc"] else "value"
    return Applied(False, f"{field}: {first['msg']}")


class ConfigEditor:
    """Applies UI-editable settings to a live ``Config`` and writes it back."""

    def __init__(self, config: Config, test_mode: bool = False) -> None:
        self._config = config
        self._test_mode = test_mode

    def apply_work_minutes(self, minutes: float) -> Applied:
        """Set the round length from the timer, leaving the rest of the Pomodoro alone."""
        try:
            updated = self._config.pomodoro.model_copy(update={"work_minutes": minutes})
            PomodoroConfig.model_validate(updated.model_dump())
        except ValidationError as exc:
            return _rejected(exc)

        self._config.pomodoro = updated
        return self._save()

    def apply_settings(
        self,
        *,
        break_minutes: int,
        rounds: int,
        daily_minutes: int,
        buffer_minutes: int,
        stretch_minutes: int,
        stretch_buffer_minutes: int,
        break_reminder_minutes: int,
        sound: str,
        timezone: str,
        rollover_hour: int,
    ) -> Applied:
        """Everything the Settings dialog can change, accepted or rejected as one piece."""
        try:
            pomodoro = PomodoroConfig(
                work_minutes=self._config.pomodoro.work_minutes,
                break_minutes=break_minutes,
                rounds=rounds,
            )
            goals = GoalsConfig(
                daily_minutes=daily_minutes,
                buffer_minutes=buffer_minutes,
                # The spin's "Off" is 0; the config says "no stretch goal" with null.
                stretch_minutes=stretch_minutes or None,
                stretch_buffer_minutes=stretch_buffer_minutes,
            )
            # model_copy skips validation, so the copy is re-validated to catch a bad value
            # before it reaches the config.
            ui = self._config.ui.model_copy(
                update={"sound": sound, "break_reminder_minutes": break_reminder_minutes}
            )
            UIConfig.model_validate(ui.model_dump())
            time = TimeConfig(timezone=timezone, rollover_hour=rollover_hour)
        except ValidationError as exc:
            return _rejected(exc)

        self._config.pomodoro = pomodoro
        self._config.goals = goals
        self._config.ui = ui
        self._config.time = time
        return self._save()

    def _save(self) -> Applied:
        """Write the config back, unless this run must not touch ``settings.json``.

        A failed write doesn't undo the change — it's already in force for this session —
        so this reports success with a warning rather than a rejection.
        """
        if self._test_mode:
            return Applied(True)
        try:
            save_config(self._config)
        except OSError as exc:
            return Applied(True, f"Applied, but couldn't write settings.json: {exc}")
        return Applied(True)
