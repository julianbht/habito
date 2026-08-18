"""ManageSessionsDialog — the session list and its right-click menu.

The two actions it opens (RetractConfirmDialog, SessionTagDialog) are each tested on their
own; what belongs here is this dialog's own choices: which session a click resolves to,
what each gets handed, and what happens to the list afterwards (a retracted row disappears,
a session's cached tags follow what its tag dialog reports back).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QDialog

from habito.actions.backfill import build_backfill_events
from habito.actions.retraction import build_retraction_events
from habito.projections.sessions import summarize_sessions
from habito.ui.dialogs import manage_sessions_dialog as msd
from habito.ui.dialogs.manage_sessions_dialog import ManageSessionsDialog
from habito.ui.dialogs.retract_confirm_dialog import describe_session

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


def dialog_for(
    qtbot,
    sessions,
    session_tags_by_id=None,
    known_tags=None,
    descriptions=None,
    captured=None,
):
    dialog = ManageSessionsDialog(
        sessions=sessions,
        session_tags_by_id=session_tags_by_id or {},
        known_tags=known_tags or [],
        descriptions=descriptions or {},
        on_submit=(captured if captured is not None else []).extend,
        habit="study",
        now=NOW,
    )
    qtbot.addWidget(dialog)
    return dialog


def row(dialog, index):
    item = dialog.list.topLevelItem(index)
    assert item is not None  # the test already knows this row exists
    return item


class _StubTagDialog:
    """Stands in for SessionTagDialog: records what it was constructed with, reports
    back a chosen final tag set instead of driving a real CatalogPicker."""

    last: _StubTagDialog | None = None

    def __init__(
        self, session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent=None
    ):
        self.session_id = session_id
        self.current_tags = current_tags
        self.known_tags = known_tags
        self.descriptions = descriptions
        self.final_tags = current_tags
        self.accepted = True
        _StubTagDialog.last = self

    class _Picker:
        def __init__(self, outer: _StubTagDialog) -> None:
            self._outer = outer

        def selected(self):
            return sorted(self._outer.final_tags)

    @property
    def tag_picker(self):
        return _StubTagDialog._Picker(self)

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected


class _StubRetractDialog:
    """Stands in for RetractConfirmDialog: records what it was constructed with,
    reports back whether it was "accepted" instead of driving a real reason field."""

    last: _StubRetractDialog | None = None

    def __init__(self, session, on_submit, habit, now, parent=None):
        self.session = session
        self.accepted = True
        _StubRetractDialog.last = self

    def exec(self):
        return QDialog.DialogCode.Accepted if self.accepted else QDialog.DialogCode.Rejected


def test_sessions_are_listed_newest_first(qtbot):
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions)

    assert dialog.list.topLevelItemCount() == 2
    assert "2026-08-05" in row(dialog, 0).text(0)
    assert "2026-08-03" in row(dialog, 1).text(0)


def test_a_row_says_enough_to_tell_two_sessions_apart(qtbot):
    session = sessions_from(session_on(4))[0]
    text = describe_session(session)
    assert "2026-08-04 06:00" in text
    assert "1h 40m" in text
    assert "backfilled" in text


def test_an_already_retracted_session_is_not_offered(qtbot):
    events = list(session_on(3)) + list(session_on(5))
    stale = summarize_sessions(events)[0]
    events += build_retraction_events(stale.session_id, stale.days, habit="study", now=NOW)

    dialog = dialog_for(qtbot, summarize_sessions(events))

    assert dialog.list.topLevelItemCount() == 1
    assert "2026-08-03" in row(dialog, 0).text(0)


def test_an_empty_log_says_so_rather_than_showing_an_empty_list(qtbot):
    dialog = dialog_for(qtbot, [])
    assert "Nothing to manage" in dialog._empty_lbl.text()


def test_row_at_resolves_a_click_to_the_right_session(qtbot):
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions)
    dialog.show()
    qtbot.waitExposed(dialog)

    pos = dialog.list.visualItemRect(row(dialog, 1)).center()
    assert dialog._row_at(pos) is sessions[1]


def test_row_at_is_none_below_every_row(qtbot):
    dialog = dialog_for(qtbot, sessions_from(session_on(3)))
    dialog.show()
    qtbot.waitExposed(dialog)

    below_everything = dialog.list.rect().bottomLeft()
    assert dialog._row_at(below_everything) is None


def test_manage_tags_seeds_the_picker_with_the_sessions_current_tags(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "SessionTagDialog", _StubTagDialog)
    sessions = sessions_from(session_on(3))
    session = sessions[0]
    dialog = dialog_for(
        qtbot,
        sessions,
        session_tags_by_id={session.session_id: {"topology"}},
        known_tags=["topology", "linear algebra"],
    )

    dialog._open_tag_dialog(session)

    stub = _StubTagDialog.last
    assert stub is not None
    assert stub.session_id == session.session_id
    assert stub.current_tags == {"topology"}
    assert stub.known_tags == ["topology", "linear algebra"]


def test_manage_tags_updates_the_cached_tags_on_accept(qtbot, monkeypatch):
    """A real SessionTagDialog reports its final checked state via
    tag_picker.selected() once accepted — that's what should end up cached, not
    whatever the session had when the dialog opened."""

    def opens_already_changed(
        session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent=None
    ):
        stub = _StubTagDialog(
            session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent
        )
        stub.final_tags = {"topology", "linear algebra"}
        return stub

    monkeypatch.setattr(msd, "SessionTagDialog", opens_already_changed)
    sessions = sessions_from(session_on(3))
    session = sessions[0]
    dialog = dialog_for(qtbot, sessions, session_tags_by_id={session.session_id: {"topology"}})

    dialog._open_tag_dialog(session)

    assert dialog._session_tags_by_id[session.session_id] == {"topology", "linear algebra"}


def test_manage_tags_does_not_update_the_cache_when_cancelled(qtbot, monkeypatch):
    """Even a dialog that *would* report a changed final set must not have it applied if
    it was cancelled rather than accepted — Cancel means "never mind", same as everywhere
    else in the app."""

    def opens_then_cancelled(
        session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent=None
    ):
        stub = _StubTagDialog(
            session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent
        )
        stub.final_tags = {"linear algebra"}  # what it would have reported, if accepted
        stub.accepted = False
        return stub

    monkeypatch.setattr(msd, "SessionTagDialog", opens_then_cancelled)
    sessions = sessions_from(session_on(3))
    session = sessions[0]
    dialog = dialog_for(qtbot, sessions, session_tags_by_id={session.session_id: {"topology"}})

    dialog._open_tag_dialog(session)

    assert dialog._session_tags_by_id[session.session_id] == {"topology"}


def test_retract_removes_the_row_on_accept(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "RetractConfirmDialog", _StubRetractDialog)
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions)

    dialog._open_retract_dialog(sessions[1])  # the older one

    assert dialog.list.topLevelItemCount() == 1
    assert "2026-08-05" in row(dialog, 0).text(0)


def test_retract_leaves_the_row_when_cancelled(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "RetractConfirmDialog", _StubRetractDialog)
    sessions = sessions_from(session_on(3), session_on(5))
    dialog = dialog_for(qtbot, sessions)

    def cancelled_dialog(session, on_submit, habit, now, parent=None):
        stub = _StubRetractDialog(session, on_submit, habit, now, parent)
        stub.accepted = False
        return stub

    monkeypatch.setattr(msd, "RetractConfirmDialog", cancelled_dialog)
    dialog._open_retract_dialog(sessions[1])

    assert dialog.list.topLevelItemCount() == 2


def test_close_dismisses_without_appending_anything(qtbot):
    captured = []
    dialog = dialog_for(qtbot, sessions_from(session_on(3)), captured=captured)

    dialog.accept()

    assert captured == []
    assert not dialog.isVisible()
