"""`_build_wakeup_store`'s one job: build a second habit's store, but only when the
`extras` flag says to. Everything past that point reuses `EventStore` unchanged."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from habito.actions.wakeup import build_wakeup_event
from habito.app import _build_wakeup_store
from habito.config.models import Config
from habito.storage.event_store import EventStore


def _config(tmp_path, **extras) -> Config:
    return Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "extras": extras,
        }
    )


def test_disabled_by_default_builds_no_store(tmp_path):
    assert _build_wakeup_store(_config(tmp_path)) is None


def test_enabled_builds_a_store_for_the_configured_habit(tmp_path):
    config = _config(tmp_path, enabled=True, wakeup={"habit": "sleep"})

    store = _build_wakeup_store(config)

    assert isinstance(store, EventStore)
    assert store.habit == "sleep"


def test_the_wakeup_store_is_independent_of_the_study_habit(tmp_path):
    """Reads only its own habit's tree — a wake-up event never shows up in the study log,
    and vice versa, even though both live under the same data repo root."""
    config = _config(tmp_path, enabled=True, wakeup={"habit": "sleep"})
    store = _build_wakeup_store(config)
    assert store is not None

    wake = datetime(2026, 8, 17, 7, 0, tzinfo=UTC)
    store.append(build_wakeup_event(wake, wake - timedelta(hours=8), habit="sleep"))

    assert len(store.read_all()) == 1
    assert store.root == config.data_repo_path()
