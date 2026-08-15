"""TagManagerDialog on its own: a thin shell around TagPicker.

The tree, "+ New tag" and double-click-to-edit behaviour all belong to TagPicker and are
covered once in test_ui_tag_picker.py — this file only checks what this dialog itself
chooses: which TagPicker it builds, and that Close dismisses it without saving anything
(there's nothing left for this dialog to save; TagEditDialog already did, on the spot).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from habito.domain.events import TagDescribed
from habito.ui.dialogs.tag_manager_dialog import TagManagerDialog

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


def test_the_picker_is_not_checkable(qtbot):
    dialog = dialog_for(qtbot, ["topology"])

    assert dialog.picker.selected_tags() == []
    item = dialog.picker.tree.topLevelItem(0)
    assert item is not None
    assert item.data(0, Qt.ItemDataRole.CheckStateRole) is None


def test_new_tag_sits_beside_close_as_the_primary_action(qtbot):
    dialog = dialog_for(qtbot, ["topology"])

    assert dialog.picker.new_tag_button.objectName() == "primary"


def test_close_dismisses_without_appending_anything(qtbot):
    captured: list[TagDescribed] = []
    dialog = dialog_for(qtbot, ["topology"], captured=captured)

    dialog.accept()

    assert captured == []
    assert not dialog.isVisible()
