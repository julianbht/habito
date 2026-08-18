"""A ``Name | Description`` tree over a name-and-description catalog, shared by every
place the app browses, manages, or picks from one — tags and workouts alike. ``checkable``
is what differs between browsing/managing (the ☰ tag/workout manager, off) and picking
which entries apply to something (on) — the session-end tag prompt, the retroactive
per-session tag/untag picker, and the log-workout dialog all use the checkable form.
``checked`` seeds which rows start ticked when checkable: empty where nothing's picked yet
(the session-end prompt, a fresh log-workout dialog), an existing selection for the
retroactive tag/untag picker, where unchecking one is how you take it back off. Everything
else — the two-column tree, "+ New …", double-click to edit — is identical either way,
because it's the same task (look at what's in the catalog, add or fix an entry) with or
without a selection on top of it.

Generalized from what was ``TagPicker``: tags and workouts are unrelated domains (see
``catalog_edit_dialog.py``'s module docstring) that happen to need the identical widget.
``noun`` ("tag" / "workout") only reaches "+ New …"'s label and the ``CatalogEditDialog``
it opens; ``build_created``/``build_described`` are the two event-builders the caller has
already bound to their own ``habit``/``now`` via ``functools.partial`` — this widget writes
nothing itself, it only hands events from ``CatalogEditDialog`` up through ``on_submit``.

"+ New …" is built here (so every call site opens the same ``CatalogEditDialog``) but not
laid out here: what, if anything, sits beside it is each embedding dialog's own layout
choice. Its styling *is* decided here, though, tied to ``checkable`` the same way everything
else is: creating an entry is the whole point of a manager dialog (``checkable=False``), so
it's the primary button there; in a picker, some other button already is the primary
action, so this one stays plain.

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
from habito.ui.widgets.controls import button, primary_button

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
        checkable: bool,
        checked: set[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._build_created = build_created
        self._build_described = build_described
        self._noun = noun
        self._checkable = checkable
        # Only meaningful when checkable: which rows start checked, e.g. a session's
        # existing tags in the retroactive tag/untag picker. Ignored (nothing is ever
        # pre-checked) everywhere else, including the session-end prompt, where a
        # session freshly ending has no tags yet to reflect.
        self._checked = checked or set[str]()

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.tree.setMinimumHeight(_TREE_MIN_HEIGHT)
        self.tree.setSelectionMode(
            QTreeWidget.SelectionMode.NoSelection
            if checkable
            else QTreeWidget.SelectionMode.SingleSelection
        )
        self.tree.itemDoubleClicked.connect(self._on_row_double_clicked)
        for item in items:  # already most-recent-first; appending preserves that order
            self._add_row(item, descriptions.get(item, ""))
        if items and not checkable:
            first = self.tree.topLevelItem(0)
            assert first is not None  # just populated above, from a non-empty items
            self.tree.setCurrentItem(first)

        self.new_button = button(f"+ New {noun}") if checkable else primary_button(f"+ New {noun}")
        self.new_button.clicked.connect(self._on_new_item)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self.tree)

    def _style_row(self, item: QTreeWidgetItem, description: str) -> None:
        item.setForeground(1, QBrush(QColor(theme.MUTED)))
        if self._checkable:
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
        if self._checkable:
            item.setCheckState(0, Qt.CheckState.Checked)
        self.tree.setCurrentItem(item)

    def selected(self) -> list[str]:
        """Checked entries, in tree order. Meaningless (always empty) when not checkable."""
        names: list[str] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item is not None and item.checkState(0) == Qt.CheckState.Checked:
                names.append(item.text(0))
        return names
