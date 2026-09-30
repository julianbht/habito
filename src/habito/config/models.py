"""Pydantic models for application configuration (validated on startup)."""

from __future__ import annotations

from datetime import datetime, time, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from habito.domain.events import HABIT_PATTERN


class SessionTemplate(BaseModel):
    """One session format — how long a round is, the break after it, and how many rounds."""

    # Optional: without one, the numbers themselves are the label.
    name: str | None = None
    work_minutes: float = Field(default=25, gt=0)  # fractional for sub-minute rounds
    break_minutes: int = Field(default=5, gt=0)
    rounds: int = Field(default=4, gt=0)

    @field_validator("name", mode="before")
    @classmethod
    def _blank_means_unnamed(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value

    def format(self) -> str:
        """The numbers alone, e.g. ``4 × 25 · 5``."""
        return f"{self.rounds} × {self.work_minutes:g} · {self.break_minutes}"

    def label(self) -> str:
        """What the timer and the picker show: the name if there is one, else the format."""
        return self.name or self.format()


def _default_templates() -> list[SessionTemplate]:
    return [SessionTemplate(rounds=4), SessionTemplate(rounds=2)]


class PomodoroConfig(BaseModel):
    templates: list[SessionTemplate] = Field(default_factory=_default_templates, min_length=1)
    # An index rather than a name, since names are optional.
    active_template: int = Field(default=0, ge=0)
    # How long after a session was cut short (closing the window mid-round) the next
    # launch still offers to resume it. Past this, the prompt would be asking about work
    # from a sitting long over, so it's left alone rather than offered back.
    resume_window_minutes: int = Field(default=10, gt=0)

    @model_validator(mode="after")
    def _active_template_exists(self) -> PomodoroConfig:
        if self.active_template >= len(self.templates):
            raise ValueError(
                f"active_template {self.active_template} is out of range — there are "
                f"{len(self.templates)} templates"
            )
        return self

    def active(self) -> SessionTemplate:
        return self.templates[self.active_template]


SYSTEM_TZ = "system"
"""``timezone`` value meaning "whatever this computer is set to"."""

COMMON_TIMEZONES: tuple[str, ...] = (
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Athens",
    "Europe/Moscow",
    "America/New_York",
    "America/Chicago",
    "America/Denver",
    "America/Los_Angeles",
    "America/Sao_Paulo",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Asia/Shanghai",
    "Asia/Tokyo",
    "Australia/Sydney",
)
"""What the Settings picker offers, in geographic order rather than alphabetical.

Deliberately a shortlist. Neither Qt nor ``zoneinfo`` has a "popular zones" built-in —
both only offer the full ~600-entry IANA list, which needs a search box to be usable.
``settings.json`` still accepts any valid zone; see :meth:`TimeConfig.choices`.
"""


class TimeConfig(BaseModel):
    """Which wall clock the log, calendar and backfill dialog work in.

    Defaults to the machine's own zone. Set an IANA name (``Europe/Berlin``) when the
    computer is deliberately set to somewhere you aren't, so days still break where your
    day actually breaks. Events already on disk keep the offset they were written with —
    changing this never rewrites history.
    """

    timezone: str = SYSTEM_TZ
    # Where a day breaks. Studying past midnight is normal, and a 00:30 round belongs to
    # the evening it continued, not to the morning after — so the boundary sits in the
    # small hours instead of at 12am.
    rollover_hour: int = Field(default=3, ge=0, le=23)

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        if value == SYSTEM_TZ:
            return value
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(
                f"unknown timezone {value!r} — use an IANA name like 'Europe/Berlin', "
                f"or '{SYSTEM_TZ}' to follow this computer"
            ) from exc
        return value

    def zone(self) -> tzinfo | None:
        """The configured zone, or ``None`` meaning "the machine's".

        ``None`` is what :meth:`datetime.astimezone` already takes to mean local, so
        callers can pass it straight through instead of branching.
        """
        return None if self.timezone == SYSTEM_TZ else ZoneInfo(self.timezone)

    def localize(self, naive: datetime) -> datetime:
        """Read a naive wall-clock time as having been *in* this timezone.

        Not the same as ``naive.astimezone(zone)``, which would read it as machine-local
        and then convert — the wrong reading for a time the user typed while thinking in
        the configured zone.
        """
        zone = self.zone()
        return naive.astimezone() if zone is None else naive.replace(tzinfo=zone)

    def choices(self) -> list[str]:
        """The picker's list: the common zones, plus whatever is actually configured.

        A zone hand-edited into ``settings.json`` isn't in the shortlist, so it's appended
        rather than silently dropped — otherwise opening Settings would offer no way back
        to the setting you already had.
        """
        common = list(COMMON_TIMEZONES)
        if self.timezone not in common and self.timezone != SYSTEM_TZ:
            common.append(self.timezone)
        return common


class EvidenceConfig(BaseModel):
    auto_commit: bool = True
    auto_push: bool = True
    remote: str = "origin"
    branch: str = "main"
    commit_message_template: str = "event: {type} [{origin}] @ {iso}"
    warn_when_unpushed: bool = True


class UIConfig(BaseModel):
    theme: str = "dark"  # "dark" | "light" | "system"
    notifications: bool = True
    # A key from habito.ui.sounds.CATALOGUE, or a path to an audio file. Paths aren't
    # checked here — a sound file going missing between runs isn't a reason to refuse to
    # start, so that's handled at playback time instead.
    sound: str = "notification"
    always_on_top: bool = False
    # A break that ends while you're away from the machine is easy to miss — one nudge,
    # this long after "Break over" first fired, if it's still unacknowledged. Not
    # buffered like the goals: there's no "close enough", so nothing to allow for.
    break_reminder_minutes: int = Field(default=3, ge=1)


class GoalsConfig(BaseModel):
    """What counts as a day's work done, for the calendar.

    Three goals, each a step up: ``low_minutes`` is the one you mean to hit every day and
    it colours the day green; ``middle_minutes`` earns one star on top, ``high_minutes`` a
    second. Thresholds rather than a gradient — "met" and "well past it" are categories,
    and a colour ramp would encode a continuum nobody can read back off a calendar cell.

    Each has its own buffer rather than sharing one: a bigger ask reasonably gets more
    slack for the same "missed it by a bit still counts" reason the low goal has one at
    all. ``_goals_ascend`` still requires each *buffered* threshold to sit above the one
    below it — a generous buffer can't let a star trigger before the level under it would.
    """

    low_minutes: int = Field(default=100, gt=0)  # 4 rounds x 25 minutes
    # Missing the target by a couple of minutes still means you did the work, so the
    # calendar accepts anything within this of the goal.
    low_buffer_minutes: int = Field(default=5, ge=0)
    # None means there isn't one, and no star is ever drawn for it.
    middle_minutes: int | None = Field(default=None, gt=0)
    middle_buffer_minutes: int = Field(default=10, ge=0)
    # Needs a middle goal: a second star with no first would skip a level.
    high_minutes: int | None = Field(default=None, gt=0)
    high_buffer_minutes: int = Field(default=15, ge=0)

    @field_validator("middle_minutes", "high_minutes", mode="before")
    @classmethod
    def _zero_means_off(cls, value: object) -> object:
        """The Settings spins bottom out at "Off", which they report as 0 rather than null."""
        return None if value == 0 else value

    @model_validator(mode="after")
    def _goals_ascend(self) -> GoalsConfig:
        if self.high_minutes is not None and self.middle_minutes is None:
            raise ValueError("the high goal needs a middle goal below it")
        # (name, raw minutes, buffered seconds) for each goal that is set, lowest first.
        steps: list[tuple[str, int, int]] = [("low", self.low_minutes, self.low_seconds())]
        if self.middle_minutes is not None:
            steps.append(
                (
                    "middle",
                    self.middle_minutes,
                    _buffered_seconds(self.middle_minutes, self.middle_buffer_minutes),
                )
            )
        if self.high_minutes is not None:
            steps.append(
                (
                    "high",
                    self.high_minutes,
                    _buffered_seconds(self.high_minutes, self.high_buffer_minutes),
                )
            )
        for (lower, lower_raw, lower_buffered), (upper, upper_raw, upper_buffered) in zip(
            steps, steps[1:], strict=False
        ):
            if upper_raw <= lower_raw:
                raise ValueError(f"the {upper} goal must be above the {lower} goal")
            if upper_buffered < lower_buffered:
                raise ValueError(
                    f"the {upper} allowance makes the {upper} goal easier to reach than the "
                    f"{lower} one — lower it, or raise the {upper} goal"
                )
        return self

    def low_seconds(self) -> int:
        return _buffered_seconds(self.low_minutes, self.low_buffer_minutes)

    def middle_seconds(self) -> int | None:
        """The buffered middle threshold, or ``None`` when no middle goal is set."""
        if self.middle_minutes is None:
            return None
        return _buffered_seconds(self.middle_minutes, self.middle_buffer_minutes)

    def high_seconds(self) -> int | None:
        """The buffered high threshold, or ``None`` when no high goal is set."""
        if self.high_minutes is None:
            return None
        return _buffered_seconds(self.high_minutes, self.high_buffer_minutes)


def _buffered_seconds(minutes: int, buffer_minutes: int) -> int:
    return max(0, minutes - buffer_minutes) * 60


class WakeUpConfig(BaseModel):
    """Where wake-up logs are filed, and what the dialog offers before you type over it."""

    habit: str = Field(default="sleep", pattern=HABIT_PATTERN)
    default_wake_time: time = time(7, 0)
    default_bedtime: time = time(23, 0)


class WorkoutConfig(BaseModel):
    """Where workout events — the catalog and the logged entries alike — are filed."""

    habit: str = Field(default="workout", pattern=HABIT_PATTERN)


class ExtrasConfig(BaseModel):
    """Personal, non-Pomodoro habits (wake-up, workout) — off by default so a build meant
    to be shared doesn't carry them.

    One flag for the whole group, not one per habit: hand-edit only, unlike the rest of
    `Config`, this is a "which build am I running" choice made once per install rather than
    a setting you'd revisit, so it earns no Settings-dialog widget (see CLAUDE.md §
    Settings). The wake-up *defaults* nested inside `wakeup`, by contrast, are things you
    would plausibly tweak — those do get one.
    """

    enabled: bool = False
    wakeup: WakeUpConfig = Field(default_factory=WakeUpConfig)
    workout: WorkoutConfig = Field(default_factory=WorkoutConfig)


class PathsConfig(BaseModel):
    data_repo: str = "../habito-data"


class Config(BaseModel):
    """Root config. ``project_root`` is injected by the loader, not read from the file."""

    # Stamped onto every event, and the directory those events are filed under.
    habit: str = Field(default="study", pattern=HABIT_PATTERN)

    pomodoro: PomodoroConfig = Field(default_factory=PomodoroConfig)
    time: TimeConfig = Field(default_factory=TimeConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    goals: GoalsConfig = Field(default_factory=GoalsConfig)
    extras: ExtrasConfig = Field(default_factory=ExtrasConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    project_root: Path
    config_path: Path | None = None  # the settings.json this config was loaded from

    def settings_file(self) -> Path:
        """The settings.json to read/write (the loaded one, or the default location)."""
        return self.config_path or (self.project_root / "config" / "settings.json")

    def data_repo_path(self) -> Path:
        """Absolute path of the separate git repo that stores the evidence log."""
        p = Path(self.paths.data_repo).expanduser()
        if not p.is_absolute():
            p = (self.project_root / p).resolve()
        return p

    def habit_dir_path(self) -> Path:
        """Absolute path of this habit's log tree inside the data repo."""
        return self.data_repo_path() / self.habit
