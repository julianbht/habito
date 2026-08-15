"""Read-only reference: every keyboard shortcut the app binds, in one table.

Opened from the ☰ menu rather than living in Settings — nothing here is a setting (there's
nothing to change), so it doesn't belong in a dialog whose whole point is editable fields.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from habito.ui.widgets import BROWSE_DIALOG_HEIGHT, BROWSE_DIALOG_WIDTH

# The single source for the app's keyboard shortcuts: shown here, and what
# HabitoApp._install_shortcuts binds against (zipped with its slots there, in this
# order) — so a key combo only ever needs to be written once.
#
# All Ctrl-prefixed except Start/pause: a QShortcut on the window steals a bare key from
# whatever button currently has focus rather than letting the button handle its own
# click — confirmed empirically, not just suspected. Plain Space is safe only because
# TimerView.focus_first() always puts focus on the Play button, never a text-editable
# widget, so Space means the same thing whether it's caught by the button or by this
# shortcut. Stop, Settings and the round-length adjustment stay Ctrl-prefixed because
# their bare keys (".", ",", the arrow keys a spin box already binds natively) don't have
# that guarantee.
SHORTCUTS: tuple[tuple[str, str], ...] = (
    ("Space", "Start / pause / resume"),
    ("Ctrl+.", "Stop"),
    ("Ctrl+,", "Settings"),
    ("Ctrl+Up", "Extend the round (or +1 min while idle)"),
    ("Ctrl+Down", "Shorten the round (or -1 min while idle)"),
)


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        tree = QTreeWidget()
        tree.setHeaderLabels(["Shortcut", "Action"])
        tree.setRootIsDecorated(False)
        tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        tree.setUniformRowHeights(True)
        tree.setIndentation(0)
        for keys, description in SHORTCUTS:
            QTreeWidgetItem(tree, [keys, description])
        tree.resizeColumnToContents(0)
        root.addWidget(tree, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
