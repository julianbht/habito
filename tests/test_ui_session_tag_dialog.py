"""SessionTagDialog on its own: a thin shell around CatalogPicker, like CatalogManagerDialog,
but checkable and pre-seeded with a session's current tags — see test_ui_catalog_picker.py
for the tree/"+ New tag"/double-click behaviour this reuses unchanged.

What's actually this dialog's own job: diffing the tree's final checked state against what
the session had when it opened into exactly the SessionTagged/SessionUntagged events that
changed, only on "Apply Tags" — not per click, and not at all on Cancel — plus the muted
status line that tracks that same diff live.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from PySide6.QtCore import Qt

from habito.domain.events import Event, SessionTagged, SessionUntagged
from habito.ui.dialogs.session_tag_dialog import SessionTagDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)
SESSION = uuid4()


def dialog_for(qtbot, known_tags, current_tags=None, descriptions=None, captured=None):
    sink = captured if captured is not None else []

    def on_submit(events):
        sink.extend(events)

    dialog = SessionTagDialog(
        SESSION,
        current_tags or set(),
        known_tags,
        descriptions or {},
        on_submit,
        habit="study",
        now=NOW,
    )
    qtbot.addWidget(dialog)
    return dialog


def row(dialog, index: int):
    item = dialog.tag_picker.tree.topLevelItem(index)
    assert item is not None
    return item


def test_the_sessions_current_tags_start_checked(qtbot):
    dialog = dialog_for(qtbot, ["linear algebra", "topology"], current_tags={"topology"})

    assert set(dialog.tag_picker.selected()) == {"topology"}


def test_apply_tags_is_the_primary_button(qtbot):
    dialog = dialog_for(qtbot, [])
    assert dialog._done_btn.text() == "Apply Tags"
    assert dialog._done_btn.objectName() == "primary"


def test_new_tag_button_is_plain_since_apply_tags_is_primary(qtbot):
    dialog = dialog_for(qtbot, [])
    assert dialog.tag_picker.new_button.objectName() == ""


def test_the_status_line_starts_at_no_changes(qtbot):
    dialog = dialog_for(qtbot, ["topology"], current_tags={"topology"})
    assert dialog._status.text() == "No changes"


def test_the_status_line_counts_a_single_change(qtbot):
    dialog = dialog_for(qtbot, ["topology"])
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)
    assert dialog._status.text() == "1 tag changed"


def test_the_status_line_counts_multiple_changes(qtbot):
    dialog = dialog_for(qtbot, ["linear algebra", "topology"], current_tags={"topology"})
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)  # linear algebra: newly tagged
    row(dialog, 1).setCheckState(0, Qt.CheckState.Unchecked)  # topology: newly untagged
    assert dialog._status.text() == "2 tags changed"


def test_the_status_line_returns_to_no_changes_when_toggled_back(qtbot):
    """The diff is against what the session *had*, not a history of clicks — checking then
    unchecking the same row nets to nothing."""
    dialog = dialog_for(qtbot, ["topology"])
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)
    row(dialog, 0).setCheckState(0, Qt.CheckState.Unchecked)
    assert dialog._status.text() == "No changes"


def test_accepting_with_no_changes_submits_nothing(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, ["topology"], current_tags={"topology"}, captured=captured)

    dialog._accept()

    assert captured == []
    assert not dialog.isVisible()


def test_checking_a_new_tag_and_applying_attaches_it(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, ["topology"], captured=captured)
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)

    dialog._accept()

    assert len(captured) == 1
    event = captured[0]
    assert isinstance(event, SessionTagged)
    assert event.session_id == SESSION
    assert event.tag == "topology"
    assert event.habit == "study"


def test_unchecking_an_existing_tag_and_applying_removes_it(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, ["topology"], current_tags={"topology"}, captured=captured)
    row(dialog, 0).setCheckState(0, Qt.CheckState.Unchecked)

    dialog._accept()

    assert len(captured) == 1
    event = captured[0]
    assert isinstance(event, SessionUntagged)
    assert event.session_id == SESSION
    assert event.tag == "topology"


def test_tagging_one_and_untagging_another_in_the_same_apply_writes_both(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(
        qtbot, ["linear algebra", "topology"], current_tags={"topology"}, captured=captured
    )
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)  # linear algebra: newly tagged
    row(dialog, 1).setCheckState(0, Qt.CheckState.Unchecked)  # topology: newly untagged

    dialog._accept()

    tagged = [e for e in captured if isinstance(e, SessionTagged)]
    untagged = [e for e in captured if isinstance(e, SessionUntagged)]
    assert [e.tag for e in tagged] == ["linear algebra"]
    assert [e.tag for e in untagged] == ["topology"]


def test_cancelling_submits_nothing_even_after_checking_a_tag(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, ["topology"], captured=captured)
    row(dialog, 0).setCheckState(0, Qt.CheckState.Checked)

    dialog.reject()

    assert captured == []
