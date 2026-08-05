"""Pydantic models for application configuration (validated on startup)."""

from __future__ import annotations

from datetime import datetime, tzinfo
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator


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
``settings.toml`` still accepts any valid zone; see :meth:`TimeConfig.choices`.
"""


class TimeConfig(BaseModel):
    """Which wall clock the log, calendar and backfill dialog work in.

    Defaults to the machine's own zone. Set an IANA name (``Europe/Berlin``) when the
    computer is deliberately set to somewhere you aren't, so days still break where your
    day actually breaks. Events already on disk keep the offset they were written with —
    changing this never rewrites history.
    """

    timezone: str = SYSTEM_TZ

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

        A zone hand-edited into ``settings.toml`` isn't in the shortlist, so it's appended
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
    """What counts as a day's work done, for the calendar."""

    daily_minutes: int = Field(default=100, gt=0)  # 4 rounds x 25 minutes
    # Missing the target by a couple of minutes still means you did the work, so the
    # calendar accepts anything within this of the goal.
    buffer_minutes: int = Field(default=5, ge=0)

    def threshold_seconds(self) -> int:
        return max(0, self.daily_minutes - self.buffer_minutes) * 60


class PathsConfig(BaseModel):
    data_repo: str = "../habito-data"
    events_filename: str = "events.jsonl"


class Config(BaseModel):
    """Root config. ``project_root`` is injected by the loader, not read from TOML."""

    pomodoro: PomodoroConfig = Field(default_factory=PomodoroConfig)
    time: TimeConfig = Field(default_factory=TimeConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
    goals: GoalsConfig = Field(default_factory=GoalsConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    project_root: Path
    config_path: Path | None = None  # the settings.toml this config was loaded from

    def settings_file(self) -> Path:
        """The settings.toml to read/write (the loaded one, or the default location)."""
        return self.config_path or (self.project_root / "config" / "settings.toml")

    def data_repo_path(self) -> Path:
        """Absolute path of the separate git repo that stores the evidence log."""
        p = Path(self.paths.data_repo).expanduser()
        if not p.is_absolute():
            p = (self.project_root / p).resolve()
        return p

    def events_path(self) -> Path:
        """Absolute path of the events.jsonl file inside the data repo."""
        return self.data_repo_path() / self.paths.events_filename
