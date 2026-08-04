"""Load and validate ``config/settings.toml`` into a :class:`Config`."""

from __future__ import annotations

import tomllib
from pathlib import Path

from .models import Config

_CONFIG_RELPATH = Path("config") / "settings.toml"


def find_project_root(start: Path | None = None) -> Path:
    """Walk upward from ``start`` (or this file) until a ``pyproject.toml`` is found."""
    here = (start or Path(__file__)).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


def load_config(
    project_root: Path | None = None,
    config_path: Path | None = None,
) -> Config:
    """Read the TOML config (missing keys fall back to model defaults)."""
    if project_root is None:
        project_root = find_project_root()
    if config_path is None:
        config_path = project_root / _CONFIG_RELPATH

    data: dict = {}
    if config_path.exists():
        with config_path.open("rb") as f:
            data = tomllib.load(f)

    data["project_root"] = project_root
    data["config_path"] = config_path
    return Config.model_validate(data)
