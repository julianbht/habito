"""Read ``config/settings.json`` and ``config/settings.local.json``, write the local one.

``settings.json`` is committed and holds the shared settings. ``settings.local.json`` is
gitignored and holds this machine's own copy. The app reads the local file when it exists
and the shared one otherwise, and every save goes to the local file. So a change made in
the UI never shows up as an uncommitted edit, and the shared file only changes by hand.

JSON rather than TOML because the file is not meant to be read for explanation — the
models are. Once comments stop being worth preserving, TOML costs a third-party writer
(``tomllib`` is read-only) to produce a file with no comments in it, while JSON is
``json.loads`` in and ``model_dump_json`` out. That in turn is what lets a save write the
*whole* config instead of merging one section at a time.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import Config

_SHARED_RELPATH = Path("config") / "settings.json"
LOCAL_RELPATH = Path("config") / "settings.local.json"

# Injected by the loader rather than read from the file, so they must not be written back.
_INJECTED = {"project_root", "config_path"}


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
    """Read the JSON config (missing keys fall back to model defaults).

    An explicit ``config_path`` is both read and written. Without one, the local file is
    read if it exists, else the shared one, and saves go to the local file.
    """
    if project_root is None:
        project_root = find_project_root()
    if config_path is None:
        config_path = project_root / LOCAL_RELPATH
        read_path = config_path if config_path.exists() else project_root / _SHARED_RELPATH
    else:
        read_path = config_path

    data: dict[str, object] = {}
    if read_path.exists():
        data = json.loads(read_path.read_text(encoding="utf-8"))

    data["project_root"] = project_root
    data["config_path"] = config_path
    return Config.model_validate(data)


def save_config(config: Config) -> None:
    """Write the whole config back, replacing the file.

    Every key the file can hold is on the model, so a round-trip preserves the settings the
    UI can't reach as faithfully as the ones it can. The trade is that a hand-edit made
    *while the app is running* is lost at the next save — acceptable, and the reason the
    old section-merge existed.
    """
    path = config.settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(config.model_dump_json(indent=2, exclude=_INJECTED) + "\n", encoding="utf-8")
