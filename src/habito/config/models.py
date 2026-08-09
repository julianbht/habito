"""Pydantic models for application configuration (validated on startup)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from habito.domain.events import HABIT_PATTERN


class PomodoroConfig(BaseModel):
    work_minutes: float = Field(default=25, gt=0)  # fractional for sub-minute rounds
    break_minutes: int = Field(default=5, gt=0)
    rounds: int = Field(default=4, gt=0)


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


class GoalsConfig(BaseModel):
    """What counts as a day's work done, for the calendar.

    Two goals, deliberately different in kind: ``daily_minutes`` is the one you mean to hit
    every day and it colours the day green; ``stretch_minutes`` is the great-day mark and
    earns a star on top. Two thresholds rather than a gradient — "met" and "well past it"
    are categories, and a colour ramp would encode a continuum nobody can read back off a
    calendar cell.
    """

    daily_minutes: int = Field(default=100, gt=0)  # 4 rounds x 25 minutes
    # Missing the target by a couple of minutes still means you did the work, so the
    # calendar accepts anything within this of the goal.
    buffer_minutes: int = Field(default=5, ge=0)
    # The great-day mark. None means there isn't one, and no star is ever drawn.
    stretch_minutes: int | None = Field(default=None, gt=0)

    @field_validator("stretch_minutes", mode="before")
    @classmethod
    def _zero_means_off(cls, value: object) -> object:
        """The Settings spin bottoms out at "Off", which it reports as 0 rather than null."""
        return None if value == 0 else value

    @model_validator(mode="after")
    def _stretch_sits_above_daily(self) -> GoalsConfig:
        if self.stretch_minutes is not None and self.stretch_minutes <= self.daily_minutes:
            raise ValueError("the stretch goal must be above the daily goal")
        return self

    def threshold_seconds(self) -> int:
        return max(0, self.daily_minutes - self.buffer_minutes) * 60

    def stretch_seconds(self) -> int | None:
        """The buffered stretch threshold, or ``None`` when no stretch goal is set.

        The buffer applies here too: if 95 minutes counts as a 100-minute goal, 145 has to
        count as 150, or the two goals would behave inconsistently for no good reason.
        """
        if self.stretch_minutes is None:
            return None
        return max(0, self.stretch_minutes - self.buffer_minutes) * 60


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
