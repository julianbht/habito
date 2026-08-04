"""Pydantic models for application configuration (validated on startup)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class PomodoroConfig(BaseModel):
    work_minutes: float = Field(default=25, gt=0)  # fractional for sub-minute rounds
    break_minutes: int = Field(default=5, gt=0)
    rounds: int = Field(default=4, gt=0)


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


class PathsConfig(BaseModel):
    data_repo: str = "../habito-data"
    events_filename: str = "events.jsonl"


class Config(BaseModel):
    """Root config. ``project_root`` is injected by the loader, not read from TOML."""

    pomodoro: PomodoroConfig = Field(default_factory=PomodoroConfig)
    evidence: EvidenceConfig = Field(default_factory=EvidenceConfig)
    ui: UIConfig = Field(default_factory=UIConfig)
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
