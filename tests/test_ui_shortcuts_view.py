"""ShortcutsDialog: the read-only reference list opened from the ☰ menu."""

from __future__ import annotations

from PySide6.QtWidgets import QTreeWidget

from habito.ui.shortcuts_view import SHORTCUTS, ShortcutsDialog


def test_every_shortcut_is_listed(qtbot):
    """SHORTCUTS is what HabitoApp actually binds (app.py._install_shortcuts), so
    checking the dialog shows every entry from it is what keeps this from silently
    drifting out of sync with the real bindings."""
    dialog = ShortcutsDialog()
    qtbot.addWidget(dialog)

    tree = dialog.findChild(QTreeWidget)
    assert tree is not None
    rows = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert item is not None
        rows.append((item.text(0), item.text(1)))
    assert rows == list(SHORTCUTS)
