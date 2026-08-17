"""RetractConfirmDialog — confirming (or backing out of) voiding one session.

Same events, same rules as before (test_retraction.py covers where they land); this is
just the dialog wiring: what Retract & commit submits, what Cancel doesn't, and that a
session spanning the rollover still gets one retraction per day.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from habito.actions.backfill import build_backfill_events
from habito.domain.events import Origin, SessionRetracted
from habito.projections.sessions import summarize_sessions
from habito.ui.dialogs.retract_confirm_dialog import RetractConfirmDialog, describe_session

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def session_on(day, hour=6, rounds=2):
    events = build_backfill_events(
        datetime(2026, 8, day, hour, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=rounds,
        habit="study",
    )
    return summarize_sessions(events)[0]


def dialog_for(qtbot, session, captured=None):
    dialog = RetractConfirmDialog(
        session,
        on_submit=(captured if captured is not None else []).extend,
        habit="study",
        now=NOW,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_a_row_says_enough_to_tell_two_sessions_apart(qtbot):
    session = session_on(4)
    text = describe_session(session)
    assert "2026-08-04 06:00" in text
    assert "1h 40m" in text
    assert "backfilled" in text


def test_a_session_spanning_the_rollover_says_so(qtbot):
    events = build_backfill_events(
        datetime(2026, 8, 4, 23, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=5,
        habit="study",
    )
    session = summarize_sessions(events, rollover_hour=3)[0]
    assert "spans 2 days" in describe_session(session)


def test_submitting_emits_a_retraction_for_the_session(qtbot):
    captured = []
    session = session_on(3)
    dialog = dialog_for(qtbot, session, captured)

    dialog.reason.setText("  wrong date  ")
    dialog._submit()

    (event,) = captured
    assert isinstance(event, SessionRetracted)
    assert event.session_id == session.session_id
    assert event.target_date.day == 3
    assert event.reason == "wrong date"  # trimmed
    assert event.origin is Origin.live  # the correction is made in the moment


def test_submitting_accepts_the_dialog(qtbot):
    dialog = dialog_for(qtbot, session_on(3))
    dialog._submit()
    assert not dialog.isVisible()


def test_cancelling_submits_nothing(qtbot):
    captured = []
    dialog = dialog_for(qtbot, session_on(3), captured)

    dialog.reject()

    assert captured == []


def test_one_retraction_per_day_spanned(qtbot):
    captured = []
    events = build_backfill_events(
        datetime(2026, 8, 4, 23, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=5,
        habit="study",
    )
    session = summarize_sessions(events, rollover_hour=3)[0]
    dialog = dialog_for(qtbot, session, captured)

    dialog._submit()

    assert len(captured) == 2
    assert {e.target_date.day for e in captured} == {4, 5}
