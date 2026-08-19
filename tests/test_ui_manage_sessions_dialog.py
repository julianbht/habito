"""ManageSessionsDialog — the session list, its right-click menu, and its Backfill button.

The three dialogs it opens (RetractConfirmDialog, SessionTagDialog, BackfillDialog) are
each tested on their own, and the list widget in `test_ui_entry_list.py`; what belongs here
is this dialog's own choices: which session a row resolves to, what each sub-dialog gets
handed, and that the list re-derives from the log after anything writes.

That last one is the reason the fixture drives a real event list rather than a fixed
snapshot: the dialog is given a `reload` callable, so "the row disappeared" has to be a
consequence of the retraction actually landing in the log, not of the dialog patching its
own state.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QDialog

from habito.actions.backfill import build_backfill_events
from habito.actions.retraction import build_retraction_events
from habito.actions.tagging import build_session_tagged_event, build_tag_created_event
from habito.projections.sessions import summarize_sessions
from habito.projections.tags import known_tags, session_tags, tag_descriptions
from habito.ui.dialogs import manage_sessions_dialog as msd
from habito.ui.dialogs.manage_sessions_dialog import ManageSessionsDialog, SessionsSnapshot
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


def dialog_for(qtbot, events=None, open_backfill=None):
    """A dialog over a mutable event log, the way the real one reads its store: `reload`
    folds whatever is in `log` right now, and `on_submit` appends to it."""
    log = list(events or [])

    def reload() -> SessionsSnapshot:
        sessions = summarize_sessions(log)
        return SessionsSnapshot(
            sessions=sessions,
            tags_by_session={s.session_id: session_tags(log, s.session_id) for s in sessions},
            known_tags=known_tags(log, "study"),
            descriptions=tag_descriptions(log, "study"),
        )

    dialog = ManageSessionsDialog(
        reload=reload,
        on_submit=log.extend,
        habit="study",
        now=lambda: NOW,
        open_backfill=open_backfill or (lambda _parent: None),
    )
    qtbot.addWidget(dialog)
    return dialog, log


def rows(dialog):
    tree = dialog.list.tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


class _StubTagDialog:
    """Stands in for SessionTagDialog: records what it was constructed with, and appends
    whatever it was told to instead of driving a real CatalogPicker."""

    last: _StubTagDialog | None = None
    writes: list = []

    def __init__(
        self, session_id, current_tags, known_tags, descriptions, on_submit, habit, now, parent=None
    ):
        self.session_id = session_id
        self.current_tags = current_tags
        self.known_tags = known_tags
        self.descriptions = descriptions
        self.now = now
        self.accepted = True
        self._on_submit = on_submit
        _StubTagDialog.last = self

    def exec(self):
        if not self.accepted:
            return QDialog.DialogCode.Rejected
        self._on_submit(list(_StubTagDialog.writes))
        return QDialog.DialogCode.Accepted


class _StubRetractDialog:
    """Stands in for RetractConfirmDialog: appends the real retraction events on accept,
    so the list's refresh has something genuine to re-derive from."""

    last: _StubRetractDialog | None = None
    accepted = True

    def __init__(self, session, on_submit, habit, now, parent=None):
        self.session = session
        self.now = now
        self._on_submit = on_submit
        self._habit = habit
        _StubRetractDialog.last = self

    def exec(self):
        if not _StubRetractDialog.accepted:
            return QDialog.DialogCode.Rejected
        self._on_submit(
            build_retraction_events(
                self.session.session_id, self.session.days, habit=self._habit, now=self.now
            )
        )
        return QDialog.DialogCode.Accepted


def test_sessions_are_listed_newest_first(qtbot):
    dialog, _ = dialog_for(qtbot, session_on(3) + session_on(5))

    assert len(rows(dialog)) == 2
    assert "2026-08-05" in rows(dialog)[0]
    assert "2026-08-03" in rows(dialog)[1]


def test_a_row_says_enough_to_tell_two_sessions_apart(qtbot):
    session = summarize_sessions(session_on(4))[0]
    text = describe_session(session)
    assert "2026-08-04 06:00" in text
    assert "1h 40m" in text
    assert "backfilled" in text


def test_an_already_retracted_session_is_not_offered(qtbot):
    events = session_on(3) + session_on(5)
    stale = summarize_sessions(events)[0]
    events += build_retraction_events(stale.session_id, stale.days, habit="study", now=NOW)

    dialog, _ = dialog_for(qtbot, events)

    assert len(rows(dialog)) == 1
    assert "2026-08-03" in rows(dialog)[0]


def test_an_empty_log_says_so_rather_than_showing_an_empty_list(qtbot):
    dialog, _ = dialog_for(qtbot, [])
    assert "Nothing to manage" in dialog.list.empty_label.text()


def test_manage_tags_seeds_the_picker_with_the_sessions_current_tags(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "SessionTagDialog", _StubTagDialog)
    events = session_on(3)
    session = summarize_sessions(events)[0]
    events = events + [
        build_tag_created_event("linear algebra", habit="study", now=NOW),
        build_session_tagged_event(session.session_id, "topology", habit="study", now=NOW),
    ]
    dialog, _ = dialog_for(qtbot, events)

    dialog._open_tag_dialog(summarize_sessions(events)[0])

    stub = _StubTagDialog.last
    assert stub is not None
    assert stub.session_id == session.session_id
    assert stub.current_tags == {"topology"}
    assert set(stub.known_tags) == {"topology", "linear algebra"}


def test_manage_tags_re_reads_the_list_after_it_writes(qtbot, monkeypatch):
    """The tags a row's dialog opens with come from `reload`, so a tag attached in one
    pass is already there the next time the same row is opened."""
    monkeypatch.setattr(msd, "SessionTagDialog", _StubTagDialog)
    events = session_on(3)
    session = summarize_sessions(events)[0]
    dialog, _ = dialog_for(qtbot, events)
    _StubTagDialog.writes = [
        build_session_tagged_event(session.session_id, "topology", habit="study", now=NOW)
    ]

    dialog._open_tag_dialog(session)
    _StubTagDialog.writes = []
    dialog._open_tag_dialog(session)

    assert _StubTagDialog.last is not None
    assert _StubTagDialog.last.current_tags == {"topology"}


def test_retract_removes_the_row_on_accept(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "RetractConfirmDialog", _StubRetractDialog)
    _StubRetractDialog.accepted = True
    events = session_on(3) + session_on(5)
    dialog, log = dialog_for(qtbot, events)
    older = summarize_sessions(events)[1]

    dialog._open_retract_dialog(older)

    assert len(rows(dialog)) == 1
    assert "2026-08-05" in rows(dialog)[0]
    assert any(e.type == "session_retracted" for e in log)


def test_retract_leaves_the_row_when_cancelled(qtbot, monkeypatch):
    monkeypatch.setattr(msd, "RetractConfirmDialog", _StubRetractDialog)
    _StubRetractDialog.accepted = False
    events = session_on(3) + session_on(5)
    dialog, log = dialog_for(qtbot, events)

    dialog._open_retract_dialog(summarize_sessions(events)[1])

    assert len(rows(dialog)) == 2
    assert not any(e.type == "session_retracted" for e in log)
    _StubRetractDialog.accepted = True


def test_the_sub_dialogs_get_the_current_time_not_one_fixed_at_construction(qtbot, monkeypatch):
    """A manager can sit open for a long time, and a retraction records when it was made."""
    monkeypatch.setattr(msd, "RetractConfirmDialog", _StubRetractDialog)
    events = session_on(3)
    dialog, _ = dialog_for(qtbot, events)

    dialog._open_retract_dialog(summarize_sessions(events)[0])

    assert _StubRetractDialog.last is not None
    assert _StubRetractDialog.last.now == NOW


def test_backfill_opens_the_form_and_re_reads_the_list_afterwards(qtbot):
    """Backfill is the manager's primary button rather than its own menu entry, so a
    session added there has to appear in the list behind it."""
    added: list = []

    def open_backfill(parent):
        added.append(parent)

    dialog, log = dialog_for(qtbot, [], open_backfill=open_backfill)
    assert rows(dialog) == []

    log.extend(session_on(4))
    dialog._backfill()

    assert added == [dialog]
    assert len(rows(dialog)) == 1
    assert "2026-08-04" in rows(dialog)[0]


def test_close_dismisses_without_appending_anything(qtbot):
    dialog, log = dialog_for(qtbot, session_on(3))
    before = len(log)

    dialog.accept()

    assert len(log) == before
    assert not dialog.isVisible()
