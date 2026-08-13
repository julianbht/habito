"""TagManagerDialog: browsing tags and changing what they mean.

Selecting a row is just browsing — double-click is the one gesture that arms editing, so
these tests drive it directly the same way other list/tree dialogs in this suite do (see
test_ui_retract_dialog.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from habito.domain.events import TagDescribed
from habito.ui.tag_manager_view import TagManagerDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def dialog_for(qtbot, tags, descriptions=None, captured=None):
    dialog = TagManagerDialog(
        tags=tags,
        descriptions=descriptions or {},
        on_submit=(captured if captured is not None else []).append,
        habit="study",
        now=NOW,
    )
    qtbot.addWidget(dialog)
    return dialog


def row(dialog, index: int):
    """``topLevelItem`` is stubbed as ``| None``; the fixed tags this suite builds from
    guarantee the index is always in range."""
    item = dialog.tree.topLevelItem(index)
    assert item is not None
    return item


def test_tags_are_listed_alphabetically_with_their_descriptions(qtbot):
    dialog = dialog_for(qtbot, ["topology", "linear algebra"], {"topology": "point-set basics"})

    assert row(dialog, 0).text(0) == "linear algebra"
    assert row(dialog, 1).text(0) == "topology"
    assert row(dialog, 1).text(1) == "point-set basics"


def test_selecting_a_row_does_not_arm_editing(qtbot):
    """Browsing must never look like the start of an edit."""
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"})
    dialog.tree.setCurrentItem(row(dialog, 0))

    assert not dialog.description.isEnabled()
    assert not dialog.save_btn.isEnabled()
    assert dialog.description.text() == ""


def test_double_clicking_a_tag_loads_its_description_and_arms_save(qtbot):
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"})
    dialog._on_tag_double_clicked(row(dialog, 0), 0)

    assert dialog.description.isEnabled()
    assert dialog.description.text() == "point-set basics"
    assert dialog.save_btn.isEnabled()


def test_saving_a_changed_description_appends_a_tag_described_event(qtbot):
    captured: list[TagDescribed] = []
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"}, captured)
    dialog._on_tag_double_clicked(row(dialog, 0), 0)
    dialog.description.setText("point-set topology, chapters 1-3")

    dialog._on_save()

    assert len(captured) == 1
    assert captured[0].tag == "topology"
    assert captured[0].description == "point-set topology, chapters 1-3"
    assert row(dialog, 0).text(1) == "point-set topology, chapters 1-3"


def test_saving_exits_edit_mode(qtbot):
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"})
    dialog._on_tag_double_clicked(row(dialog, 0), 0)
    dialog.description.setText("new text")

    dialog._on_save()

    assert not dialog.description.isEnabled()
    assert not dialog.save_btn.isEnabled()
    assert dialog.description.text() == ""


def test_saving_unchanged_text_appends_nothing(qtbot):
    captured: list[TagDescribed] = []
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"}, captured)
    dialog._on_tag_double_clicked(row(dialog, 0), 0)

    dialog._on_save()  # nothing typed, text still matches what was loaded

    assert captured == []


def test_new_tag_is_added_and_armed_for_editing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **kw: ("probability", True))
    )
    dialog = dialog_for(qtbot, ["topology"])

    dialog._on_new_tag()

    assert dialog.tree.topLevelItemCount() == 2
    assert dialog.description.isEnabled()
    assert dialog.description.text() == ""


def test_new_tag_that_already_exists_selects_rather_than_duplicates(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: ("topology", True)))
    dialog = dialog_for(qtbot, ["topology"], {"topology": "point-set basics"})

    dialog._on_new_tag()

    assert dialog.tree.topLevelItemCount() == 1
    assert dialog.description.text() == "point-set basics"  # loaded, not blank
