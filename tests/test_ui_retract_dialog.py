"""The retract dialog — picking a session and voiding it.

The dialog is the only place a retraction is made by hand, so these cover what it offers
and what it emits; the rules about where those events land live in test_retraction.py.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from habito.actions.backfill import build_backfill_events
from habito.actions.retraction import build_retraction_events
from habito.domain.events import Origin, SessionRetracted
from habito.projections.sessions import summarize_sessions
from habito.ui.dialogs.retract_dialog import RetractDialog, describe_session

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def session_on(day, hour=6, rounds=2):
    return build_backfill_events(
        datetime(2026, 8, day, hour, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=rounds,
        habit="study",
    )


def sessions_from(*event_lists):
    events = [e for group in event_lists for e in group]
    return summarize_sessions(events)


def dialog_for(qtbot, sessions, captured=None):
    dialog = RetractDialog(
        sessions=sessions,
        on_submit=(captured if captured is not None else []).append,
        habit="study",
        now=NOW,
    )
    qtbot.addWidget(dialog)
    return dialog


def test_sessions_are_listed_newest_first(qtbot):
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions)

    assert dialog.list.count() == 2
    assert "2026-08-05" in dialog.list.item(0).text()
    assert "2026-08-03" in dialog.list.item(1).text()


def test_the_newest_session_is_preselected(qtbot):
    """A correction usually follows the mistake straight away."""
    dialog = dialog_for(qtbot, sessions_from(session_on(3), session_on(5)))
    assert dialog.list.currentRow() == 0
    picked = dialog._selected()
    assert picked is not None
    assert picked.started.day == 5


def test_a_row_says_enough_to_tell_two_sessions_apart(qtbot):
    session = sessions_from(session_on(4))[0]
    text = describe_session(session)
    assert "2026-08-04 06:00" in text
    assert "1h 40m" in text
    assert "backfilled" in text


def test_submitting_emits_a_retraction_for_the_picked_session(qtbot):
    captured = []
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions, captured)

    dialog.list.setCurrentRow(1)  # the 3rd
    dialog.reason.setText("  wrong date  ")
    dialog._submit()

    (event,) = captured[0]
    assert isinstance(event, SessionRetracted)
    assert event.session_id == sessions[1].session_id
    assert event.target_date.day == 3
    assert event.reason == "wrong date"  # trimmed
    assert event.origin is Origin.live  # the correction is made in the moment


def test_an_already_retracted_session_is_not_offered(qtbot):
    events = list(session_on(3)) + list(session_on(5))
    stale = summarize_sessions(events)[0]
    events += build_retraction_events(stale.session_id, stale.days, habit="study", now=NOW)

    dialog = dialog_for(qtbot, summarize_sessions(events))

    assert dialog.list.count() == 1
    assert "2026-08-03" in dialog.list.item(0).text()


def test_an_empty_log_disables_the_button_rather_than_failing(qtbot):
    from PySide6.QtWidgets import QDialogButtonBox

    dialog = dialog_for(qtbot, [])
    ok = dialog._buttons.button(QDialogButtonBox.StandardButton.Ok)

    assert not ok.isEnabled()
    assert "Nothing to retract" in dialog._error.text()


def test_a_session_spanning_the_rollover_says_so(qtbot):
    sessions = summarize_sessions(session_on(4, hour=23, rounds=5), rollover_hour=3)
    assert "spans 2 days" in describe_session(sessions[0])


def test_the_dialog_emits_one_retraction_per_day_spanned(qtbot):
    captured = []
    sessions = summarize_sessions(session_on(4, hour=23, rounds=5), rollover_hour=3)
    dialog = dialog_for(qtbot, sessions, captured)
    dialog._submit()

    assert len(captured[0]) == 2
    assert {e.target_date.day for e in captured[0]} == {4, 5}
