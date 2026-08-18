"""CatalogManagerDialog on its own: a thin shell around CatalogPicker, used today only by
the ☰ "Manage tags" dialog (see catalog_manager_dialog.py's module docstring for why
workouts don't get a second instance of this).

The tree, "+ New …" and double-click-to-edit behaviour all belong to CatalogPicker and are
covered once in test_ui_catalog_picker.py — this file only checks what this dialog itself
chooses: which CatalogPicker it builds, and that Close dismisses it without saving anything
(there's nothing left for this dialog to save; CatalogEditDialog already did, on the spot).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.domain.events import TagDescribed
from habito.ui.dialogs.catalog_manager_dialog import CatalogManagerDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def dialog_for(qtbot, items, descriptions=None, captured=None):
    dialog = CatalogManagerDialog(
        title="Manage tags",
        hint="Double-click a tag to change its description.",
        noun="tag",
        items=items,
        descriptions=descriptions or {},
        on_submit=(captured if captured is not None else []).append,
        build_created=lambda name: build_tag_created_event(name, habit="study", now=NOW),
        build_described=lambda name, description: build_tag_described_event(
            name, description, habit="study", now=NOW
        ),
    )
    qtbot.addWidget(dialog)
    return dialog


def test_the_title_and_hint_are_whatever_the_caller_passed(qtbot):
    dialog = dialog_for(qtbot, ["topology"])
    assert dialog.windowTitle() == "Manage tags"


def test_the_picker_is_not_checkable(qtbot):
    dialog = dialog_for(qtbot, ["topology"])

    assert dialog.picker.selected() == []
    item = dialog.picker.tree.topLevelItem(0)
    assert item is not None
    assert item.data(0, Qt.ItemDataRole.CheckStateRole) is None


def test_new_button_sits_beside_close_as_the_primary_action(qtbot):
    dialog = dialog_for(qtbot, ["topology"])

    assert dialog.picker.new_button.objectName() == "primary"


def test_close_dismisses_without_appending_anything(qtbot):
    captured: list[TagDescribed] = []
    dialog = dialog_for(qtbot, ["topology"], captured=captured)

    dialog.accept()

    assert captured == []
    assert not dialog.isVisible()
