"""TagEditDialog on its own: the one place a tag's name and description get set.

Creating always writes a TagCreated (plus a TagDescribed too, but only with a real
description); editing only ever writes a TagDescribed, and only on a real change. See the
module docstring on habito.ui.dialogs.tag_edit_dialog for why.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from habito.domain.events import Event, TagCreated, TagDescribed
from habito.ui.dialogs.tag_edit_dialog import TagEditDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def dialog_for(qtbot, tag, description="", captured=None):
    dialog = TagEditDialog(
        tag, description, (captured if captured is not None else []).append, "study", NOW
    )
    qtbot.addWidget(dialog)
    return dialog


def test_new_tag_name_is_editable_and_focused(qtbot):
    dialog = dialog_for(qtbot, None)
    dialog.show()  # showEvent is where focus is set — see the dialog's own docstring

    assert not dialog._name.isReadOnly()
    assert dialog.focusWidget() is dialog._name


def test_existing_tag_name_is_read_only(qtbot):
    dialog = dialog_for(qtbot, "topology", "point-set basics")
    dialog.show()

    assert dialog._name.text() == "topology"
    assert dialog._name.isReadOnly()
    assert dialog.focusWidget() is dialog._description


def test_save_is_disabled_until_a_new_tag_has_a_name(qtbot):
    dialog = dialog_for(qtbot, None)
    assert not dialog.save_btn.isEnabled()

    qtbot.keyClicks(dialog._name, "topology")
    assert dialog.save_btn.isEnabled()


def test_creating_with_no_description_writes_only_tag_created(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, None, captured=captured)
    qtbot.keyClicks(dialog._name, "topology")

    qtbot.mouseClick(dialog.save_btn, Qt.MouseButton.LeftButton)

    assert len(captured) == 1
    assert isinstance(captured[0], TagCreated)
    assert captured[0].tag == "topology"
    assert dialog.tag_name == "topology"
    assert not dialog.isVisible()


def test_creating_with_a_description_writes_both_events(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, None, captured=captured)
    qtbot.keyClicks(dialog._name, "topology")
    qtbot.keyClicks(dialog._description, "point-set basics")

    qtbot.mouseClick(dialog.save_btn, Qt.MouseButton.LeftButton)

    assert isinstance(captured[0], TagCreated)
    assert isinstance(captured[1], TagDescribed)
    assert captured[1].description == "point-set basics"


def test_editing_without_changing_the_description_writes_nothing(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, "topology", "point-set basics", captured)

    qtbot.mouseClick(dialog.save_btn, Qt.MouseButton.LeftButton)

    assert captured == []
    assert dialog.tag_name == "topology"


def test_editing_a_changed_description_writes_one_tag_described(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, "topology", "point-set basics", captured)
    dialog._description.selectAll()
    qtbot.keyClicks(dialog._description, "chapters 1-3")

    qtbot.mouseClick(dialog.save_btn, Qt.MouseButton.LeftButton)

    assert len(captured) == 1
    assert isinstance(captured[0], TagDescribed)
    assert captured[0].tag == "topology"
    assert captured[0].description == "chapters 1-3"


def test_cancel_writes_nothing(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, None, captured=captured)
    qtbot.keyClicks(dialog._name, "topology")

    dialog.reject()

    assert captured == []
