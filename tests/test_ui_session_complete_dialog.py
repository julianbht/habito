"""SessionCompleteDialog on its own: the tag picker's visibility and (unlike PhaseDialog)
unrestricted ways to dismiss it.

TagPicker's own mechanics (the tree, "+ New tag", double-click-to-edit) are covered once in
test_ui_tag_picker.py — this file only checks what this dialog does with what's checked:
report it through ``on_accept``, and treat Esc the same as pressing the button.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog

from habito.ui.session_complete_dialog import SessionCompleteDialog
from habito.ui.tag_edit_dialog import TagEditDialog

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def make_dialog(
    known: list[str],
    answers: list[list[str]],
    descriptions: dict[str, str] | None = None,
) -> SessionCompleteDialog:
    return SessionCompleteDialog(
        "Session complete",
        "25 min of focus.",
        "Done",
        known,
        on_accept=answers.append,
        on_describe_tag=lambda event: None,
        habit="study",
        now=NOW,
        descriptions=descriptions,
    )


def check(dialog: SessionCompleteDialog, tag: str) -> None:
    """Reveal the picker if needed, then check ``tag``'s box."""
    if not dialog.tag_picker.isVisible():
        dialog._reveal_tag_picker()
    item = dialog.tag_picker.tree.findItems(tag, Qt.MatchFlag.MatchExactly, 0)[0]
    item.setCheckState(0, Qt.CheckState.Checked)


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


def test_the_picker_starts_hidden_behind_the_link(qtbot):
    dialog = make_dialog(["topology"], [])
    qtbot.addWidget(dialog)
    dialog.show()  # isVisible() only reflects reality once the window is actually shown

    assert not dialog.tag_picker.isVisible()
    assert dialog._attach_tag_link.isVisible()
    qtbot.mouseClick(dialog._attach_tag_link, Qt.MouseButton.LeftButton)
    assert dialog.tag_picker.isVisible()
    assert not dialog._attach_tag_link.isVisible()


def test_creating_a_new_tag_and_finishing_reports_it(qtbot, monkeypatch):
    """End-to-end through the picker: TagPicker and TagEditDialog have their own
    mechanics covered elsewhere — this just checks the pieces are wired together."""

    def fake_exec(self: TagEditDialog) -> int:
        self.tag_name = "linear algebra"
        self.description = ""
        return QDialog.DialogCode.Accepted

    monkeypatch.setattr(TagEditDialog, "exec", fake_exec)
    answers: list[list[str]] = []
    dialog = make_dialog([], answers)
    qtbot.addWidget(dialog)
    dialog._reveal_tag_picker()

    dialog.tag_picker._on_new_tag()
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    assert answers == [["linear algebra"]]
