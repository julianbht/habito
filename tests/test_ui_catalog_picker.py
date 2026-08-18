"""CatalogPicker on its own: the name-and-description tree shared by every tag and workout
picker/manager in the app. ``checkable`` is the only thing that varies between call sites —
see the module docstring on habito.ui.widgets.catalog_picker.

Driven here with the real tag event builders (``build_tag_created_event`` /
``build_tag_described_event``) purely as a concrete, already-correct stand-in for "some
builder the caller bound" — this file is about the picker's own mechanics (ordering,
checking, the tree), which don't care what domain the builders belong to. Workout-specific
wiring (which builders `WorkoutLogDialog` passes) is covered in its own test file.

"+ New …" and double-click both hand off to CatalogEditDialog; here that dialog is driven
through its own real Save/Cancel (not just stubbed at the boundary) so this file also
covers what CatalogPicker does with a real write, not just a fabricated result.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt

from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.ui.dialogs.catalog_edit_dialog import CatalogEditDialog
from habito.ui.widgets.catalog_picker import CatalogPicker

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def picker_for(qtbot, items, descriptions=None, checkable=False, checked=None, captured=None):
    picker = CatalogPicker(
        items,
        descriptions or {},
        (captured if captured is not None else []).append,
        lambda name: build_tag_created_event(name, habit="study", now=NOW),
        lambda name, description: build_tag_described_event(
            name, description, habit="study", now=NOW
        ),
        "tag",
        checkable=checkable,
        checked=checked,
    )
    qtbot.addWidget(picker)
    return picker


def row(picker, index: int):
    item = picker.tree.topLevelItem(index)
    assert item is not None
    return item


def drive_edit_dialog(monkeypatch, name: str, description: str = "", accepted: bool = True):
    """Stand in for CatalogEditDialog.exec: types into the real fields and drives the real
    Save/Cancel, so a persisted write is exercised the same way a real click would."""

    def fake_exec(self: CatalogEditDialog) -> int:
        if accepted:
            if not self._name.isReadOnly():
                self._name.setText(name)
            self._description.setPlainText(description)
            self._on_save()
        else:
            self.reject()
        return self.result()

    monkeypatch.setattr(CatalogEditDialog, "exec", fake_exec)


def test_items_are_listed_in_the_given_order_with_their_descriptions(qtbot):
    """Order is the caller's choice (most-recent-first, from known_tags/known_workouts) —
    this widget just preserves it rather than re-sorting."""
    picker = picker_for(qtbot, ["topology", "linear algebra"], {"topology": "point-set basics"})

    assert row(picker, 0).text(0) == "topology"
    assert row(picker, 0).text(1) == "point-set basics"
    assert row(picker, 1).text(0) == "linear algebra"


def test_not_checkable_has_no_check_state(qtbot):
    picker = picker_for(qtbot, ["topology"], checkable=False)

    assert row(picker, 0).data(0, Qt.ItemDataRole.CheckStateRole) is None
    assert picker.selected() == []


def test_checkable_rows_start_unchecked(qtbot):
    picker = picker_for(qtbot, ["topology"], checkable=True)

    assert row(picker, 0).checkState(0) == Qt.CheckState.Unchecked


def test_checking_a_row_reports_it_as_selected(qtbot):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=True)

    row(picker, 1).setCheckState(0, Qt.CheckState.Checked)

    assert picker.selected() == ["topology"]


def test_checked_rows_start_ticked(qtbot):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=True, checked={"topology"})

    assert row(picker, 0).checkState(0) == Qt.CheckState.Unchecked  # linear algebra
    assert row(picker, 1).checkState(0) == Qt.CheckState.Checked  # topology
    assert picker.selected() == ["topology"]


def test_unchecking_a_pre_checked_row_removes_it_from_selected(qtbot):
    picker = picker_for(qtbot, ["topology"], checkable=True, checked={"topology"})

    row(picker, 0).setCheckState(0, Qt.CheckState.Unchecked)

    assert picker.selected() == []


def test_checked_is_ignored_when_not_checkable(qtbot):
    picker = picker_for(qtbot, ["topology"], checkable=False, checked={"topology"})

    assert row(picker, 0).data(0, Qt.ItemDataRole.CheckStateRole) is None


def test_new_button_is_primary_when_not_checkable(qtbot):
    picker = picker_for(qtbot, [], checkable=False)
    assert picker.new_button.objectName() == "primary"


def test_new_button_is_plain_when_checkable(qtbot):
    picker = picker_for(qtbot, [], checkable=True)
    assert picker.new_button.objectName() == ""


def test_new_button_is_labelled_with_the_noun(qtbot):
    picker = picker_for(qtbot, [], checkable=False)
    assert picker.new_button.text() == "+ New tag"


def test_new_item_is_added_to_the_tree(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["topology"], checkable=False)
    drive_edit_dialog(monkeypatch, "probability")

    picker._on_new_item()

    labels = [row(picker, i).text(0) for i in range(picker.tree.topLevelItemCount())]
    assert labels == ["probability", "topology"]


def test_new_item_is_checked_when_checkable(qtbot, monkeypatch):
    picker = picker_for(qtbot, [], checkable=True)
    drive_edit_dialog(monkeypatch, "topology")

    picker._on_new_item()

    assert picker.selected() == ["topology"]


def test_a_second_new_item_does_not_uncheck_the_first(qtbot, monkeypatch):
    """Regression: adding an item used to rebuild the whole tree, wiping every other row's
    check state along with it."""
    picker = picker_for(qtbot, [], checkable=True)
    drive_edit_dialog(monkeypatch, "linear algebra")
    picker._on_new_item()

    drive_edit_dialog(monkeypatch, "topology")
    picker._on_new_item()

    assert set(picker.selected()) == {"linear algebra", "topology"}


def test_new_item_that_already_exists_is_not_duplicated(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["topology"], {"topology": "point-set basics"}, checkable=True)
    drive_edit_dialog(monkeypatch, "topology", "point-set basics")

    picker._on_new_item()

    assert picker.tree.topLevelItemCount() == 1
    assert picker.selected() == ["topology"]


def test_a_new_item_appears_at_the_top(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=False)
    drive_edit_dialog(monkeypatch, "probability")

    picker._on_new_item()

    assert row(picker, 0).text(0) == "probability"


def test_retyping_an_existing_name_moves_it_to_the_top(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=False)
    drive_edit_dialog(monkeypatch, "topology")

    picker._on_new_item()

    assert row(picker, 0).text(0) == "topology"
    assert picker.tree.topLevelItemCount() == 2


def test_cancelling_new_item_adds_nothing(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["topology"], checkable=False)
    drive_edit_dialog(monkeypatch, "probability", accepted=False)

    picker._on_new_item()

    assert picker.tree.topLevelItemCount() == 1


def test_double_clicking_a_row_can_update_its_description(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["topology"], {"topology": "point-set basics"}, checkable=True)
    drive_edit_dialog(monkeypatch, "topology", "chapters 1-3")

    picker._on_row_double_clicked(row(picker, 0), 0)

    assert row(picker, 0).text(1) == "chapters 1-3"
    # Editing a description is not the same as selecting the row.
    assert picker.selected() == []


def test_double_clicking_a_row_moves_it_to_the_top(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=False)
    drive_edit_dialog(monkeypatch, "topology", "chapters 1-3")

    picker._on_row_double_clicked(row(picker, 1), 0)

    assert row(picker, 0).text(0) == "topology"
    assert row(picker, 1).text(0) == "linear algebra"


def test_moving_a_row_to_the_top_keeps_its_check_state(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["linear algebra", "topology"], checkable=True)
    row(picker, 1).setCheckState(0, Qt.CheckState.Checked)  # "topology"
    drive_edit_dialog(monkeypatch, "topology", "chapters 1-3")

    picker._on_row_double_clicked(row(picker, 1), 0)

    assert row(picker, 0).text(0) == "topology"
    assert picker.selected() == ["topology"]


def test_cancelling_the_edit_leaves_the_description_unchanged(qtbot, monkeypatch):
    picker = picker_for(qtbot, ["topology"], {"topology": "point-set basics"})
    drive_edit_dialog(monkeypatch, "topology", "chapters 1-3", accepted=False)

    picker._on_row_double_clicked(row(picker, 0), 0)

    assert row(picker, 0).text(1) == "point-set basics"


def test_a_long_description_is_summarized_with_the_full_text_as_tooltip(qtbot):
    long_text = "x" * 90
    picker = picker_for(qtbot, ["topology"], {"topology": long_text})

    item = row(picker, 0)
    assert item.text(1) != long_text
    assert item.text(1).endswith("…")
    assert item.toolTip(1) == long_text


def test_a_multiline_description_shows_only_its_first_line(qtbot):
    picker = picker_for(qtbot, ["topology"], {"topology": "line one\nline two"})

    item = row(picker, 0)
    assert item.text(1) == "line one…"
    assert item.toolTip(1) == "line one\nline two"


def test_a_short_description_is_shown_in_full(qtbot):
    picker = picker_for(qtbot, ["topology"], {"topology": "short"})

    assert row(picker, 0).text(1) == "short"
