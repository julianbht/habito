"""A one-column list of log entries with a right-click menu per row.

The list half of every manager dialog — sessions, sleep, workouts — so the three differ
only in what a row says and what its menu offers, not in how the list itself looks or
behaves. Rows are plain strings; the dialog embedding this keeps the typed objects behind
them and gets back the index it handed in.

A ``QTreeWidget`` rather than a ``QListWidget``, matching the log view and the catalog
picker, so it picks up the theme's tree styling instead of falling back to the native list
style. Non-editable and non-selectable: a row is acted on by double-click or by its
right-click menu, so a selection would only be decoration.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget

from habito.ui.widgets.controls import label


class EntryList(QWidget):
    row_menu_requested = Signal(int, QPoint)
    """Row index, and the position to pop a menu up at, already in global coordinates."""

    row_activated = Signal(int)
    """A row was double-clicked. Left to the embedding dialog to interpret — same gesture
    the catalog picker uses to edit an entry — and simply unconnected where a list has no
    one obvious action to open."""

    def __init__(self, hint: str, empty_text: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._empty_text = empty_text

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        root.addWidget(label(hint, "muted"))

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        root.addWidget(self.tree, 1)

        self._empty_lbl = label("", "muted")
        root.addWidget(self._empty_lbl)

    def set_rows(self, rows: Sequence[str]) -> None:
        """Replace every row, and show the empty message when there are none left."""
        self.tree.clear()
        for text in rows:
            QTreeWidgetItem(self.tree, [text])
        self._empty_lbl.setText("" if rows else self._empty_text)

    def _on_double_click(self, item: QTreeWidgetItem, column: int) -> None:
        self.row_activated.emit(self.tree.indexOfTopLevelItem(item))

    def _on_context_menu(self, pos: QPoint) -> None:
        item = self.tree.itemAt(pos)
        if item is None:
            return
        row = self.tree.indexOfTopLevelItem(item)
        self.row_menu_requested.emit(row, self.tree.viewport().mapToGlobal(pos))
