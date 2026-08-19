"""EntryManagerDialog — the sleep/workout manager: list, add, edit, void.

The list widget is tested in `test_ui_entry_list.py` and the void event itself in
`test_voiding.py`; what belongs here is this dialog's own choices — that the form it opens
is told which entry it is replacing, that an edit submits the void *together with* the
replacement, and that anything which writes re-derives the list from the log.

Driven with wake-ups, as a concrete stand-in for either stream: the dialog is deliberately
ignorant of which one it is showing (rows arrive as `ManagedEntry`, already rendered), so
running it twice against a workout log would only re-test `entry_summaries`.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtWidgets import QDialog

from habito.actions.wakeup import build_wakeup_event
from habito.domain.events import Event, EventVoided, WakeUpLogged, drop_corrected
from habito.ui.dialogs import entry_manager_dialog as emd
from habito.ui.dialogs.entry_manager_dialog import EntryManagerDialog, ManagedEntry
from habito.ui.dialogs.entry_summaries import describe_wakeup

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def a_wakeup(day=4, hour=7):
    return build_wakeup_event(
        datetime(2026, 8, day, hour, 30, tzinfo=CEST),
        datetime(2026, 8, day - 1, 23, 15, tzinfo=CEST),
        habit="sleep",
    )


def dialog_for(qtbot, events=None, open_form=None):
    """A manager over a mutable event log, the way the real one reads its store: `reload`
    folds whatever still stands, and `on_submit` appends."""
    log: list[Event] = list(events or [])
    opened: list[tuple] = []

    def reload():
        entries = [e for e in drop_corrected(log) if isinstance(e, WakeUpLogged)]
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return [ManagedEntry(describe_wakeup(e), e) for e in entries]

    def default_open_form(parent, on_submit, replacing):
        opened.append((parent, replacing))

    dialog = EntryManagerDialog(
        title="Sleep",
        hint="Double-click an entry to edit it, or right-click to void it.",
        empty_text="Nothing logged yet.",
        add_text="Log wake-up…",
        reload=reload,
        open_form=open_form or default_open_form,
        on_submit=log.extend,
        rollover_hour=3,
        now=lambda: NOW,
    )
    qtbot.addWidget(dialog)
    return dialog, log, opened


def rows(dialog):
    tree = dialog.list.tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


class _StubVoidDialog:
    """Stands in for VoidConfirmDialog: appends the real void event on accept, so the
    list's refresh has something genuine to re-derive from."""

    last: _StubVoidDialog | None = None
    accepted = True

    def __init__(self, target, summary, on_submit, rollover_hour, now, parent=None):
        self.target = target
        self.summary = summary
        self.rollover_hour = rollover_hour
        self.now = now
        self._on_submit = on_submit
        _StubVoidDialog.last = self

    def exec(self):
        if not _StubVoidDialog.accepted:
            return QDialog.DialogCode.Rejected
        self._on_submit(
            [emd.build_void_event(self.target, rollover_hour=self.rollover_hour, now=self.now)]
        )
        return QDialog.DialogCode.Accepted


def test_entries_are_listed_newest_first(qtbot):
    dialog, _, _ = dialog_for(qtbot, [a_wakeup(day=3), a_wakeup(day=5)])

    assert len(rows(dialog)) == 2
    assert "2026-08-05" in rows(dialog)[0]
    assert "2026-08-03" in rows(dialog)[1]


def test_an_empty_log_says_so_rather_than_showing_an_empty_list(qtbot):
    dialog, _, _ = dialog_for(qtbot, [])
    assert dialog.list.empty_label.text() == "Nothing logged yet."


def test_the_add_button_is_the_primary_action(qtbot):
    """Logging one is the point of opening the manager; correcting one is the exception."""
    dialog, _, _ = dialog_for(qtbot, [])

    assert dialog.add_button.text() == "Log wake-up…"
    assert dialog.add_button.objectName() == "primary"
    assert dialog.add_button.isDefault()


def test_add_opens_the_form_with_nothing_to_replace(qtbot):
    dialog, _, opened = dialog_for(qtbot, [])

    dialog._add()

    assert opened == [(dialog, None)]


def test_add_re_reads_the_list_afterwards(qtbot):
    """A wake-up logged from inside the manager has to appear in the list behind it."""

    def logs_one(parent, on_submit, replacing):
        on_submit([a_wakeup(day=4)])

    dialog, _, _ = dialog_for(qtbot, [], open_form=logs_one)
    assert rows(dialog) == []

    dialog._add()

    assert len(rows(dialog)) == 1


def test_edit_opens_the_form_told_which_entry_it_replaces(qtbot):
    wakeup = a_wakeup()
    dialog, _, opened = dialog_for(qtbot, [wakeup])

    dialog._edit(ManagedEntry(describe_wakeup(wakeup), wakeup))

    assert opened == [(dialog, wakeup)]


def test_double_clicking_a_row_edits_it(qtbot):
    """Same gesture that edits a catalog entry one dialog further in."""
    wakeup = a_wakeup()
    dialog, _, opened = dialog_for(qtbot, [wakeup])

    dialog.list.row_activated.emit(0)

    assert opened == [(dialog, wakeup)]


def test_double_clicking_past_the_last_row_does_nothing(qtbot):
    dialog, _, opened = dialog_for(qtbot, [a_wakeup()])

    dialog.list.row_activated.emit(7)

    assert opened == []


def test_editing_submits_the_void_together_with_the_replacement(qtbot):
    """One submit, so the log never holds the correction without what it corrects, or the
    other way round."""
    wrong = a_wakeup(hour=7)
    right = a_wakeup(hour=8)

    def replaces_it(parent, on_submit, replacing):
        on_submit([right])

    dialog, log, _ = dialog_for(qtbot, [wrong], open_form=replaces_it)

    dialog._edit(ManagedEntry(describe_wakeup(wrong), wrong))

    voids = [e for e in log if isinstance(e, EventVoided)]
    assert [v.target_event_id for v in voids] == [wrong.event_id]
    assert log[-1] is right
    assert [e.event_id for e in drop_corrected(log) if isinstance(e, WakeUpLogged)] == [
        right.event_id
    ]


def test_cancelling_an_edit_writes_no_void(qtbot):
    """The void is built inside the form's submit, so backing out of the form leaves the
    entry exactly as it was."""
    wakeup = a_wakeup()
    dialog, log, _ = dialog_for(qtbot, [wakeup])  # the default form submits nothing

    dialog._edit(ManagedEntry(describe_wakeup(wakeup), wakeup))

    assert log == [wakeup]
    assert len(rows(dialog)) == 1


def test_void_hands_the_confirm_dialog_the_row_it_was_opened_on(qtbot, monkeypatch):
    monkeypatch.setattr(emd, "VoidConfirmDialog", _StubVoidDialog)
    _StubVoidDialog.accepted = True
    wakeup = a_wakeup()
    dialog, _, _ = dialog_for(qtbot, [wakeup])
    entry = ManagedEntry(describe_wakeup(wakeup), wakeup)

    dialog._void(entry)

    stub = _StubVoidDialog.last
    assert stub is not None
    assert stub.target is wakeup
    assert stub.summary == entry.summary
    assert stub.rollover_hour == 3
    assert stub.now == NOW  # read afresh, not fixed when the manager was constructed


def test_void_removes_the_row_on_accept(qtbot, monkeypatch):
    monkeypatch.setattr(emd, "VoidConfirmDialog", _StubVoidDialog)
    _StubVoidDialog.accepted = True
    older, newer = a_wakeup(day=3), a_wakeup(day=5)
    dialog, log, _ = dialog_for(qtbot, [older, newer])

    dialog._void(ManagedEntry(describe_wakeup(older), older))

    assert len(rows(dialog)) == 1
    assert "2026-08-05" in rows(dialog)[0]
    assert any(isinstance(e, EventVoided) for e in log)


def test_void_leaves_the_row_when_cancelled(qtbot, monkeypatch):
    monkeypatch.setattr(emd, "VoidConfirmDialog", _StubVoidDialog)
    _StubVoidDialog.accepted = False
    wakeup = a_wakeup()
    dialog, log, _ = dialog_for(qtbot, [wakeup])

    dialog._void(ManagedEntry(describe_wakeup(wakeup), wakeup))

    assert len(rows(dialog)) == 1
    assert log == [wakeup]
    _StubVoidDialog.accepted = True


def test_close_dismisses_without_appending_anything(qtbot):
    dialog, log, _ = dialog_for(qtbot, [a_wakeup()])

    dialog.accept()

    assert len(log) == 1
    assert not dialog.isVisible()
