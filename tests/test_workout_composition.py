"""`_build_workout_store`'s one job: build a third habit's store, but only when the
`extras` flag says to — mirrors test_wakeup_composition.py exactly, since both stores are
built the same way, gated on the same flag."""

from __future__ import annotations

from datetime import UTC, datetime

from habito.actions.workout import build_workout_logged_event
from habito.app import _build_workout_store
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
    assert _build_workout_store(_config(tmp_path)) is None


def test_enabled_builds_a_store_for_the_configured_habit(tmp_path):
    config = _config(tmp_path, enabled=True, workout={"habit": "workout"})

    store = _build_workout_store(config)

    assert isinstance(store, EventStore)
    assert store.habit == "workout"


def test_enabled_with_no_workout_section_uses_the_default_habit(tmp_path):
    config = _config(tmp_path, enabled=True)

    store = _build_workout_store(config)

    assert store is not None
    assert store.habit == "workout"


def test_the_workout_store_is_independent_of_the_study_habit(tmp_path):
    """Reads only its own habit's tree — a workout event never shows up in the study log,
    and vice versa, even though both live under the same data repo root."""
    config = _config(tmp_path, enabled=True, workout={"habit": "workout"})
    store = _build_workout_store(config)
    assert store is not None

    when = datetime(2026, 8, 17, 18, 0, tzinfo=UTC)
    store.append(build_workout_logged_event(when, ["running"], habit="workout"))

    assert len(store.read_all()) == 1
    assert store.root == config.data_repo_path()
