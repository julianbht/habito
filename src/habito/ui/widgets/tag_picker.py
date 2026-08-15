"""The tag list, shared by the tag manager and the session-end prompt — one widget, not
two views that happen to look alike. ``checkable`` is the only thing that differs between
them: off for browsing/managing (the ☰ tag manager), on for picking which tags apply to the
session that just ended. Everything else — the two-column ``Tag | Description`` tree,
"+ New tag", double-click to edit — is identical either way, because it's the same task
(look at what tags exist, add or fix one) with or without a selection on top of it.

"+ New tag" is built here (so both call sites open the same `TagEditDialog`) but not laid
out here: what, if anything, sits beside it is each embedding dialog's own layout choice —
see `tag_manager_dialog.py` and `session_complete_dialog.py`. Its styling *is* decided here,
though, tied to ``checkable`` the same way everything else is: creating a tag is the whole
point of the tag manager (``checkable=False``), so it's the primary button there; in the
session-end picker "Done" already is the primary action, so it stays plain.

Rows are most-recently-touched first, not alphabetical — the caller hands ``tags`` over
already in that order (see `projections.tags.known_tags`), and this widget preserves it: no
sorting is enabled, and a tag just created or edited moves to the top rather than staying
wherever it started, the same way the log itself would rank it if reopened fresh.

A row's full description lives in ``Qt.ItemDataRole.UserRole`` — the second column only
ever shows a single-line summary (the tree can't grow a row taller than its neighbours for
one long entry), with the full text as the tooltip.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QDialog, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from habito.domain.events import Event
from habito.ui import theme
from habito.ui.dialogs.tag_edit_dialog import TagEditDialog
from habito.ui.widgets import button, primary_button

SubmitCallback = Callable[[Event], None]

# Tall enough to show a handful of tags before scrolling, not just the one that fit before.
_TAG_TREE_MIN_HEIGHT = 140

# A dialog built around this widget — the tag manager always, the session-end prompt once
# its tag section is revealed — sizes itself to these, so the same tree reads the same size
# everywhere it appears rather than each embedding dialog picking its own.
DIALOG_MIN_WIDTH = 440
DIALOG_MIN_HEIGHT = 360

# A description can run to a paragraph; a tree row can't. Past this, the row shows a clipped
# first line — the full text is never lost, it's the tooltip.
_SUMMARY_MAX_CHARS = 60


def _summarize(description: str) -> str:
    first_line = description.splitlines()[0] if description else ""
    if len(first_line) > _SUMMARY_MAX_CHARS or "\n" in description:
        return first_line[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return first_line


class TagPicker(QWidget):
    def __init__(
        self,
        tags: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        checkable: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self._checkable = checkable

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.tree.setMinimumHeight(_TAG_TREE_MIN_HEIGHT)
        self.tree.setSelectionMode(
            QTreeWidget.SelectionMode.NoSelection
            if checkable
            else QTreeWidget.SelectionMode.SingleSelection
        )
        self.tree.itemDoubleClicked.connect(self._on_row_double_clicked)
        for tag in tags:  # already most-recent-first; appending preserves that order
            self._add_row(tag, descriptions.get(tag, ""))
        if tags and not checkable:
            first = self.tree.topLevelItem(0)
            assert first is not None  # just populated above, from a non-empty tags
            self.tree.setCurrentItem(first)

        self.new_tag_button = button("+ New tag") if checkable else primary_button("+ New tag")
        self.new_tag_button.clicked.connect(self._on_new_tag)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tree)

    def _style_row(self, item: QTreeWidgetItem, description: str) -> None:
        item.setForeground(1, QBrush(QColor(theme.MUTED)))
        if self._checkable:
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
        self._set_description(item, description)

    def _add_row(self, tag: str, description: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self.tree, [tag, ""])
        self._style_row(item, description)
        return item

    def _prepend_row(self, tag: str, description: str) -> QTreeWidgetItem:
        """A tag just created goes straight to the top — it's the most recently touched
        one there is."""
        item = QTreeWidgetItem([tag, ""])
        self.tree.insertTopLevelItem(0, item)
        self._style_row(item, description)
        return item

    def _move_to_top(self, item: QTreeWidgetItem) -> None:
        """``takeTopLevelItem``/``insertTopLevelItem`` relocate the same item object, so
        its check state, flags and data travel with it — nothing is rebuilt."""
        index = self.tree.indexOfTopLevelItem(item)
        self.tree.takeTopLevelItem(index)
        self.tree.insertTopLevelItem(0, item)

    def _description_of(self, item: QTreeWidgetItem) -> str:
        return item.data(0, Qt.ItemDataRole.UserRole) or ""

    def _set_description(self, item: QTreeWidgetItem, description: str) -> None:
        item.setData(0, Qt.ItemDataRole.UserRole, description)
        item.setText(1, _summarize(description))
        item.setToolTip(1, description)

    def _find_row(self, tag: str) -> QTreeWidgetItem | None:
        matches = self.tree.findItems(tag, Qt.MatchFlag.MatchExactly, 0)
        return matches[0] if matches else None

    def _on_row_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        tag = item.text(0)
        dialog = TagEditDialog(
            tag, self._description_of(item), self._on_submit, self._habit, self._now, self
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_description(item, dialog.description)
            self._move_to_top(item)

    def _on_new_tag(self) -> None:
        dialog = TagEditDialog(None, "", self._on_submit, self._habit, self._now, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        tag = dialog.tag_name
        item = self._find_row(tag)
        if item is None:
            item = self._prepend_row(tag, dialog.description)
        else:
            self._set_description(item, dialog.description)
            self._move_to_top(item)
        if self._checkable:
            item.setCheckState(0, Qt.CheckState.Checked)
        self.tree.setCurrentItem(item)

    def selected_tags(self) -> list[str]:
        """Checked tags, in tree order. Meaningless (always empty) when not checkable."""
        tags: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is not None and item.checkState(0) == Qt.CheckState.Checked:
                tags.append(item.text(0))
        return tags
