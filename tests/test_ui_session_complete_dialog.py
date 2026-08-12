"""SessionCompleteDialog on its own: the tag picker and the (unlike PhaseDialog)
unrestricted ways to dismiss it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from habito.ui.session_complete_dialog import SessionCompleteDialog


def make_dialog(known: list[str], answers: list[str | None]) -> SessionCompleteDialog:
    return SessionCompleteDialog(
        "Session complete", "25 min of focus.", "Done", known, answers.append
    )


def test_no_tag_by_default(qtbot):
    answers: list[str | None] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == [None]
    assert not dialog.isVisible()


def test_picking_a_known_tag_reports_it(qtbot):
    answers: list[str | None] = []
    dialog = make_dialog(["linear algebra", "topology"], answers)
    qtbot.addWidget(dialog)
    dialog._tag_box.setCurrentIndex(dialog._tag_box.findData("topology"))

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == ["topology"]


def test_escape_dismisses_it_same_as_no_tag(qtbot):
    """Unlike PhaseDialog: nothing is gated, so there's nothing to strand."""
    answers: list[str | None] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)
    dialog.present()

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert answers == [None]


def test_escape_after_picking_a_tag_still_reports_it(qtbot):
    """Skipping is a choice, not a discard — a pick already made should survive Esc."""
    answers: list[str | None] = []
    dialog = make_dialog(["topology"], answers)
    qtbot.addWidget(dialog)
    dialog._tag_box.setCurrentIndex(dialog._tag_box.findData("topology"))

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert answers == ["topology"]


def test_known_tags_are_offered_alongside_no_tag_and_new_tag(qtbot):
    dialog = make_dialog(["linear algebra", "topology"], [])
    qtbot.addWidget(dialog)

    items = [dialog._tag_box.itemText(i) for i in range(dialog._tag_box.count())]
    assert items[0] == "No tag"
    assert "linear algebra" in items
    assert "topology" in items
    assert items[-1] == "New tag…"


def test_choosing_new_tag_without_typing_anything_falls_back_to_no_tag(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: ("", False)))
    answers: list[str | None] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)

    new_tag_index = dialog._tag_box.count() - 1
    dialog._tag_box.setCurrentIndex(new_tag_index)
    dialog._on_tag_chosen(new_tag_index)

    assert dialog._tag_box.currentIndex() == 0  # back to "No tag"


def test_typing_a_new_tag_adds_and_selects_it(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **kw: ("linear algebra", True))
    )
    answers: list[str | None] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)

    new_tag_index = dialog._tag_box.count() - 1
    dialog._tag_box.setCurrentIndex(new_tag_index)
    dialog._on_tag_chosen(new_tag_index)

    assert dialog.selected_tag() == "linear algebra"

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == ["linear algebra"]


def test_typing_a_tag_that_already_exists_selects_rather_than_duplicates(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: ("topology", True)))
    dialog = make_dialog(["topology"], [])
    qtbot.addWidget(dialog)
    before = dialog._tag_box.count()

    new_tag_index = dialog._tag_box.count() - 1
    dialog._tag_box.setCurrentIndex(new_tag_index)
    dialog._on_tag_chosen(new_tag_index)

    assert dialog._tag_box.count() == before  # no duplicate entry
    assert dialog.selected_tag() == "topology"
