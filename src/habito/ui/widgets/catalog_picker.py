"""A checkable ``Name | Description`` tree over a name-and-description catalog, shared by
every place the app picks from one — tags and workouts alike.

It is both the picker and the catalog manager: ticking rows says which entries apply to
whatever the embedding dialog is about, while "+ New …" and double-click-to-edit maintain
the catalog itself. There is no separate manager dialog, because one would be this widget
with the checkboxes turned off and nothing of its own. ``CatalogEditDialog`` writes on Save,
before this widget hears about it, so a description fixed here stands even if the embedding
dialog is then cancelled.

``checked`` seeds which rows start ticked: empty where nothing is picked yet (the
session-end prompt, a fresh log-workout dialog), a session's existing tags in the
retroactive tag/untag picker, where unchecking one is how you take it back off.

``noun`` ("tag" / "workout") reaches "+ New …"'s label, the ``CatalogEditDialog`` it opens,
and the hint; ``build_created``/``build_described`` are the two event-builders the caller
has already bound to their own ``habit``/``now`` — this widget writes nothing itself, it
only hands events from ``CatalogEditDialog`` up through ``on_submit``.

``hint`` is the embedding dialog's own line about what ticking a row means; the
double-click clause is appended here rather than left to each call site, because
double-click is now the only way to reach the editor and a call site that forgot it would
hide the catalog entirely.

"+ New …" is built here (so every call site opens the same ``CatalogEditDialog``) but not
laid out here: what, if anything, sits beside it is each embedding dialog's own layout
choice. It stays a plain button — in every call site some other button is already the
dialog's primary action.

Rows are most-recently-touched first, not alphabetical — the caller hands ``items`` over
already in that order (see ``projections.tags.known_tags`` / ``projections.workouts.
known_workouts``), and this widget preserves it: no sorting is enabled, and an entry just
created or edited moves to the top rather than staying wherever it started.

A row's full description lives in ``Qt.ItemDataRole.UserRole`` — the second column only
ever shows a single-line summary (the tree can't grow a row taller than its neighbours for
one long entry), with the full text as the tooltip.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QDialog, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from habito.ui import theme
from habito.ui.dialogs.catalog_edit_dialog import (
    CatalogEditDialog,
    CreatedBuilder,
    DescribedBuilder,
    SubmitCallback,
)
from habito.ui.widgets.controls import button, label

# Tall enough to show a handful of entries before scrolling, not just the one that fit before.
_TREE_MIN_HEIGHT = 140

# A description can run to a paragraph; a tree row can't. Past this, the row shows a clipped
# first line — the full text is never lost, it's the tooltip.
_SUMMARY_MAX_CHARS = 60


def _summarize(description: str) -> str:
    first_line = description.splitlines()[0] if description else ""
    if len(first_line) > _SUMMARY_MAX_CHARS or "\n" in description:
        return first_line[:_SUMMARY_MAX_CHARS].rstrip() + "…"
    return first_line


class CatalogPicker(QWidget):
    def __init__(
        self,
        items: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        build_created: CreatedBuilder,
        build_described: DescribedBuilder,
        noun: str,
        hint: str = "",
        checked: set[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._build_created = build_created
        self._build_described = build_described
        self._noun = noun
        self._checked = checked or set[str]()

        text = f"{hint} Double-click a {noun} to change its description.".strip()
        self.hint = label(text, "muted")
        self.hint.setWordWrap(True)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.tree.setMinimumHeight(_TREE_MIN_HEIGHT)
        # The check boxes are the selection, so a second highlighted-row one would only be
        # a second thing on screen saying which row you last touched.
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.itemDoubleClicked.connect(self._on_row_double_clicked)
        for item in items:  # already most-recent-first; appending preserves that order
            self._add_row(item, descriptions.get(item, ""))

        self.new_button = button(f"+ New {noun}")
        self.new_button.clicked.connect(self._on_new_item)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.hint)
        root.addWidget(self.tree)

    def _style_row(self, item: QTreeWidgetItem, description: str) -> None:
        item.setForeground(1, QBrush(QColor(theme.MUTED)))
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        checked = item.text(0) in self._checked
        item.setCheckState(0, Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self._set_description(item, description)

    def _add_row(self, name: str, description: str) -> QTreeWidgetItem:
        item = QTreeWidgetItem(self.tree, [name, ""])
        self._style_row(item, description)
        return item

    def _prepend_row(self, name: str, description: str) -> QTreeWidgetItem:
        """An entry just created goes straight to the top — it's the most recently
        touched one there is."""
        item = QTreeWidgetItem([name, ""])
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

    def _find_row(self, name: str) -> QTreeWidgetItem | None:
        matches = self.tree.findItems(name, Qt.MatchFlag.MatchExactly, 0)
        return matches[0] if matches else None

    def _on_row_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        name = item.text(0)
        dialog = CatalogEditDialog(
            self._noun,
            name,
            self._description_of(item),
            self._on_submit,
            self._build_created,
            self._build_described,
            self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_description(item, dialog.description)
            self._move_to_top(item)

    def _on_new_item(self) -> None:
        dialog = CatalogEditDialog(
            self._noun, None, "", self._on_submit, self._build_created, self._build_described, self
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        name = dialog.name
        item = self._find_row(name)
        if item is None:
            item = self._prepend_row(name, dialog.description)
        else:
            self._set_description(item, dialog.description)
            self._move_to_top(item)
        item.setCheckState(0, Qt.CheckState.Checked)

    def selected(self) -> list[str]:
        """Checked entries, in tree order."""
        names: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is not None and item.checkState(0) == Qt.CheckState.Checked:
                names.append(item.text(0))
        return names
