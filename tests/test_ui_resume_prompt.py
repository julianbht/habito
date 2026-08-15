"""HabitoApp.offer_resume: wiring between find_resumable and the prompt dialog.

find_resumable's own decision logic (what counts as resumable, what phase/remaining
time it implies) is covered in test_projections_resume.py — these tests are only about
what the window does with that answer: ask, apply on Accept, leave alone on Reject/none.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from PySide6.QtWidgets import QDialog

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.domain.events import Origin, RoundEnded, RoundStarted, SessionEnded, SessionStarted
from habito.engine.pomodoro import State
from habito.ui.app import HabitoApp
from habito.ui.dialogs.resume_dialog import ResumePromptDialog


def _config(tmp_path, resume_window_minutes=30):
    return Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "pomodoro": {"resume_window_minutes": resume_window_minutes},
        }
    )


def _leave_interrupted_session(store, *, when: datetime, work_seconds: int = 15 * 60) -> None:
    """Write the events an interrupted round leaves behind, directly — no live clock
    needed, and it lets the tests control ``interrupted_at`` precisely."""
    session_id = uuid4()
    habit = "study"
    ended_at = when + timedelta(seconds=work_seconds)
    store.append(
        SessionStarted(
            timestamp=when,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit=habit,
            session_id=session_id,
            work_minutes=25,
            break_minutes=5,
            planned_rounds=4,
        )
    )
    store.append(
        RoundStarted(
            timestamp=when,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit=habit,
            session_id=session_id,
            round_index=1,
        )
    )
    store.append(
        RoundEnded(
            timestamp=ended_at,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit=habit,
            session_id=session_id,
            round_index=1,
            work_seconds=work_seconds,
        )
    )
    store.append(
        SessionEnded(
            timestamp=ended_at,
            tz_offset_minutes=0,
            origin=Origin.live,
            habit=habit,
            session_id=session_id,
            total_work_seconds=work_seconds,
        )
    )


def _window(qtbot, config, test_mode=True):
    engine, store = _build_engine_and_store(config, test_mode=False)
    win = HabitoApp(config, engine, store, test_mode=test_mode)
    qtbot.addWidget(win)
    return win


def test_recent_interruption_prompts_and_resume_seeds_the_engine(qtbot, tmp_path, monkeypatch):
    config = _config(tmp_path)
    engine, store = _build_engine_and_store(config, test_mode=False)
    _leave_interrupted_session(store, when=datetime.now(UTC) - timedelta(minutes=5))
    win = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(win)

    monkeypatch.setattr(ResumePromptDialog, "exec", lambda self: QDialog.DialogCode.Accepted)
    win.offer_resume()

    assert win._engine.state is State.work
    assert win._engine.snapshot().round_index == 1
    assert win._engine.remaining_seconds() == 10 * 60  # 25 min target - 15 min already logged


def test_declining_the_prompt_leaves_the_engine_idle(qtbot, tmp_path, monkeypatch):
    config = _config(tmp_path)
    engine, store = _build_engine_and_store(config, test_mode=False)
    _leave_interrupted_session(store, when=datetime.now(UTC) - timedelta(minutes=5))
    win = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(win)

    monkeypatch.setattr(ResumePromptDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    win.offer_resume()

    assert win._engine.state is State.idle


def test_an_old_interruption_is_not_even_offered(qtbot, tmp_path, monkeypatch):
    config = _config(tmp_path, resume_window_minutes=30)
    engine, store = _build_engine_and_store(config, test_mode=False)
    _leave_interrupted_session(store, when=datetime.now(UTC) - timedelta(hours=2))
    win = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(win)

    def _fail_if_constructed(self, *a, **kw):
        raise AssertionError("resume prompt should not appear for a stale interruption")

    monkeypatch.setattr(ResumePromptDialog, "__init__", _fail_if_constructed)
    win.offer_resume()

    assert win._engine.state is State.idle


def test_no_prior_session_is_silent(qtbot, tmp_path, monkeypatch):
    config = _config(tmp_path)
    win = _window(qtbot, config)

    def _fail_if_constructed(self, *a, **kw):
        raise AssertionError("nothing to resume — the dialog should never be built")

    monkeypatch.setattr(ResumePromptDialog, "__init__", _fail_if_constructed)
    win.offer_resume()  # must not raise

    assert win._engine.state is State.idle
