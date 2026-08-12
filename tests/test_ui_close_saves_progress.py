"""Closing the window mid-round must not drop the work in progress.

Before this, ``closeEvent`` tore the window down without ever calling
``engine.stop()``, so the round in flight had no ``RoundEnded``/``SessionEnded`` event —
nothing for the store (or a future resume feature) to find. ``on_stop`` — the same path
the Stop button uses — finalises it honestly, the same way a mid-round quit already
behaves as if you'd hit Stop yourself.
"""

from __future__ import annotations

import pytest

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.domain.events import RoundEnded, SessionEnded, SessionStarted
from habito.engine.pomodoro import State
from habito.ui.app import HabitoApp


@pytest.fixture
def app(qtbot, tmp_path):
    config = Config.model_validate(
        {"paths": {"data_repo": str(tmp_path)}, "project_root": tmp_path}
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window


def test_closing_mid_round_persists_the_round_and_session(qtbot, app):
    app.on_start()
    assert app._engine.state is State.work
    qtbot.wait(50)  # let a little real work time accrue

    app.close()

    assert app._engine.state is State.done
    events = app._store.read_all()
    session_id = next(e for e in events if isinstance(e, SessionStarted)).session_id
    round_ended = next(e for e in events if isinstance(e, RoundEnded))
    session_ended = next(e for e in events if isinstance(e, SessionEnded))
    assert round_ended.session_id == session_id
    assert round_ended.work_seconds >= 0
    assert session_ended.session_id == session_id
    assert session_ended.total_work_seconds == round_ended.work_seconds


def test_closing_while_idle_writes_nothing(qtbot, app):
    app.close()

    assert app._store.read_all() == []
