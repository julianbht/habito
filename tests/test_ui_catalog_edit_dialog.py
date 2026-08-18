"""CatalogEditDialog on its own: the one place a catalog entry's name and description get
set, shared by every tag and workout editor in the app.

Creating always writes a "created" event (plus a "described" one too, but only with a real
description); editing only ever writes a "described" event, and only on a real change. See
the module docstring on habito.ui.dialogs.catalog_edit_dialog for why. Driven here with the
real tag builders as a concrete stand-in for "whatever the caller bound" — this file is
about the dialog's own choices (what it writes, and when), not about tags specifically.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.domain.events import Event, TagCreated, TagDescribed
from habito.ui.dialogs.catalog_edit_dialog import CatalogEditDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def dialog_for(qtbot, name, description="", captured=None):
    dialog = CatalogEditDialog(
        "tag",
        name,
        description,
        (captured if captured is not None else []).append,
        lambda n: build_tag_created_event(n, habit="study", now=NOW),
        lambda n, d: build_tag_described_event(n, d, habit="study", now=NOW),
    )
    qtbot.addWidget(dialog)
    return dialog


def test_new_name_is_editable_and_focused(qtbot):
    dialog = dialog_for(qtbot, None)
    dialog.show()  # showEvent is where focus is set — see the dialog's own docstring

    assert not dialog._name.isReadOnly()
    assert dialog.focusWidget() is dialog._name


def test_existing_name_is_read_only(qtbot):
    dialog = dialog_for(qtbot, "topology", "point-set basics")
    dialog.show()

    assert dialog._name.text() == "topology"
    assert dialog._name.isReadOnly()
    assert dialog.focusWidget() is dialog._description


def test_title_names_the_noun(qtbot):
    assert dialog_for(qtbot, None).windowTitle() == "New tag"
    assert dialog_for(qtbot, "topology").windowTitle() == "Edit tag"


def test_save_is_disabled_until_a_new_entry_has_a_name(qtbot):
    dialog = dialog_for(qtbot, None)
    assert not dialog.save_btn.isEnabled()

    qtbot.keyClicks(dialog._name, "topology")
    assert dialog.save_btn.isEnabled()


def test_creating_with_no_description_writes_only_the_created_event(qtbot):
    captured: list[Event] = []
    dialog = dialog_for(qtbot, None, captured=captured)
    qtbot.keyClicks(dialog._name, "topology")

    qtbot.mouseClick(dialog.save_btn, Qt.MouseButton.LeftButton)

    assert len(captured) == 1
    assert isinstance(captured[0], TagCreated)
    assert captured[0].tag == "topology"
    assert dialog.name == "topology"
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
    assert dialog.name == "topology"


def test_editing_a_changed_description_writes_one_described_event(qtbot):
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
