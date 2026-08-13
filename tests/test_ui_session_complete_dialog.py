"""SessionCompleteDialog on its own: the tag tree and the (unlike PhaseDialog)
unrestricted ways to dismiss it.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from habito.ui.session_complete_dialog import SessionCompleteDialog


def make_dialog(
    known: list[str],
    answers: list[list[str]],
    descriptions: dict[str, str] | None = None,
) -> SessionCompleteDialog:
    return SessionCompleteDialog(
        "Session complete", "25 min of focus.", "Done", known, answers.append, descriptions
    )


def check(dialog: SessionCompleteDialog, tag: str) -> None:
    """Reveal the tree if needed, then check ``tag``'s box."""
    if not dialog._tag_tree.isVisible():
        dialog._reveal_tag_tree()
    item = dialog._tag_tree.findItems(tag, Qt.MatchFlag.MatchExactly, 0)[0]
    item.setCheckState(0, Qt.CheckState.Checked)


def row(dialog: SessionCompleteDialog, index: int):
    """``topLevelItem`` is stubbed as ``| None``; the index is always in range here."""
    item = dialog._tag_tree.topLevelItem(index)
    assert item is not None
    return item


def last_row(dialog: SessionCompleteDialog):
    """The tree's last row — always "+ New tag…"."""
    return row(dialog, dialog._tag_tree.topLevelItemCount() - 1)


def test_no_tags_by_default(qtbot):
    answers: list[list[str]] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == [[]]
    assert not dialog.isVisible()


def test_checking_a_known_tag_reports_it(qtbot):
    answers: list[list[str]] = []
    dialog = make_dialog(["linear algebra", "topology"], answers)
    qtbot.addWidget(dialog)
    check(dialog, "topology")

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == [["topology"]]


def test_checking_more_than_one_tag_reports_all_of_them(qtbot):
    answers: list[list[str]] = []
    dialog = make_dialog(["linear algebra", "topology"], answers)
    qtbot.addWidget(dialog)
    check(dialog, "linear algebra")
    check(dialog, "topology")

    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == [["linear algebra", "topology"]]


def test_escape_dismisses_it_same_as_no_tags(qtbot):
    """Unlike PhaseDialog: nothing is gated, so there's nothing to strand."""
    answers: list[list[str]] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)
    dialog.present()

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert not dialog.isVisible()
    assert answers == [[]]


def test_escape_after_checking_a_tag_still_reports_it(qtbot):
    """Skipping is a choice, not a discard — a check already made should survive Esc."""
    answers: list[list[str]] = []
    dialog = make_dialog(["topology"], answers)
    qtbot.addWidget(dialog)
    check(dialog, "topology")

    qtbot.keyClick(dialog, Qt.Key.Key_Escape)
    assert answers == [["topology"]]


def test_the_tree_starts_hidden_behind_the_link(qtbot):
    dialog = make_dialog(["topology"], [])
    qtbot.addWidget(dialog)
    dialog.show()  # isVisible() only reflects reality once the window is actually shown

    assert not dialog._tag_tree.isVisible()
    assert dialog._attach_tag_link.isVisible()
    qtbot.mouseClick(dialog._attach_tag_link, Qt.MouseButton.LeftButton)
    assert dialog._tag_tree.isVisible()
    assert not dialog._attach_tag_link.isVisible()


def test_known_tags_are_offered_alongside_new_tag(qtbot):
    dialog = make_dialog(["linear algebra", "topology"], [])
    qtbot.addWidget(dialog)

    labels = [row(dialog, i).text(0) for i in range(dialog._tag_tree.topLevelItemCount())]
    assert labels == ["linear algebra", "topology", "+ New tag…"]


def test_a_known_description_shows_alongside_its_tag(qtbot):
    dialog = make_dialog(["topology"], [], descriptions={"topology": "point-set basics"})
    qtbot.addWidget(dialog)

    assert row(dialog, 0).text(1) == "point-set basics"


def test_choosing_new_tag_without_typing_anything_adds_nothing(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: ("", False)))
    dialog = make_dialog([], [])
    qtbot.addWidget(dialog)
    dialog._reveal_tag_tree()

    new_row = last_row(dialog)
    dialog._on_tag_item_clicked(new_row, 0)

    assert dialog._tag_tree.topLevelItemCount() == 1  # just "+ New tag…"
    assert dialog.selected_tags() == []


def test_typing_a_new_tag_adds_and_checks_it(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(
        QInputDialog, "getText", staticmethod(lambda *a, **kw: ("linear algebra", True))
    )
    answers: list[list[str]] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)
    dialog._reveal_tag_tree()

    new_row = last_row(dialog)
    dialog._on_tag_item_clicked(new_row, 0)

    assert dialog.selected_tags() == ["linear algebra"]
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)
    assert answers == [["linear algebra"]]


def test_typing_a_tag_that_already_exists_checks_rather_than_duplicates(qtbot, monkeypatch):
    from PySide6.QtWidgets import QInputDialog

    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: ("topology", True)))
    dialog = make_dialog(["topology"], [])
    qtbot.addWidget(dialog)
    dialog._reveal_tag_tree()
    before = dialog._tag_tree.topLevelItemCount()

    new_row = last_row(dialog)
    dialog._on_tag_item_clicked(new_row, 0)

    assert dialog._tag_tree.topLevelItemCount() == before  # no duplicate row
    assert dialog.selected_tags() == ["topology"]
