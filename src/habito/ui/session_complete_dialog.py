"""The prompt shown when a session finishes: an optional tag or two, then dismiss.

Unlike :class:`~habito.ui.phase_dialog.PhaseDialog`, nothing here "gates" a phase — the
session already ended, nothing is waiting on this dialog — so Esc or the close button
dismissing it plainly (same as attaching no tags and pressing the action button) is the
right default, not something to swallow.

Tags start hidden behind a "+ Attach tag" link, not an always-visible picker: the common
case is skipping the prompt entirely, and a control that's never used shouldn't be the
first thing on screen every time a session ends. "Attach", not "add" — this dialog only
ever links an existing or freshly-typed tag to *this session* (SessionTagged); it never
defines a tag the way the tag manager's "+ New tag" does, so the two shouldn't share a verb.

Clicking the link reveals a two-column ``Tag | Description`` tree — the same flat,
muted-second-column look as the tag manager, so the picker doesn't read as a different app
once it appears — with checkboxes for multi-select (a session covering more than one thing
can carry more than one tag) plus a "+ New tag…" row that opens the same one-line prompt
the tag manager's "+ New tag" does (:func:`habito.ui.widgets.prompt_new_tag`), not an
editable combo box, which has caused hard Qt aborts elsewhere in this app (see CLAUDE.md).

A tag's longer description lives in the tag manager, not here — writing that down is never
something a finished pomodoro should be waiting on. Only an already-written description
shows up, alongside its tag, for a reminder of what a short tag stands for.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QHBoxLayout, QTreeWidget, QTreeWidgetItem, QWidget

from habito.ui import theme
from habito.ui.prompt_dialog import PromptDialog
from habito.ui.widgets import button, prompt_new_tag

_TAG_ROLE = Qt.ItemDataRole.UserRole + 1
_NEW_TAG: Final = "__new_tag__"

# Tall enough to show a handful of tags before scrolling, not just the one that fit before.
_TAG_TREE_MIN_HEIGHT = 140


class SessionCompleteDialog(PromptDialog):
    # Never gates a phase — see the module docstring. HabitoApp checks this the same way
    # it checks PhaseDialog.gates_phase, so the two dialogs share one call site.
    gates_phase = False

    def __init__(
        self,
        title: str,
        body: str,
        action: str,
        known_tags: list[str],
        on_accept: Callable[[list[str]], None],
        descriptions: dict[str, str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, body, parent)
        self._on_accept = on_accept
        self._build(known_tags, descriptions or {})
        self._add_action_row(action)
        self.action_button.clicked.connect(self._accept)

    def _build(self, known_tags: list[str], descriptions: dict[str, str]) -> None:
        # Shrink-wrapped and centred, like the action button below — not stretched to the
        # dialog's full width, which left its text pinned to the left edge under a centred
        # heading and message.
        link_row = QHBoxLayout()
        link_row.addStretch(1)
        self._attach_tag_link = button("+ Attach tag", "link")
        self._attach_tag_link.setToolTip("Optional — attach a tag for what you were working on")
        self._attach_tag_link.clicked.connect(self._reveal_tag_tree)
        link_row.addWidget(self._attach_tag_link)
        link_row.addStretch(1)
        self._root.addLayout(link_row)

        self._tag_tree = QTreeWidget()
        self._tag_tree.setColumnCount(2)
        self._tag_tree.setHeaderHidden(True)
        self._tag_tree.setIndentation(0)
        self._tag_tree.setRootIsDecorated(False)
        self._tag_tree.setAlternatingRowColors(True)
        self._tag_tree.setSelectionMode(QTreeWidget.SelectionMode.NoSelection)
        self._tag_tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._tag_tree.setMinimumHeight(_TAG_TREE_MIN_HEIGHT)
        self._tag_tree.setVisible(False)
        for tag in known_tags:
            item = QTreeWidgetItem(self._tag_tree, [tag, descriptions.get(tag, "")])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Unchecked)
            item.setForeground(1, QBrush(QColor(theme.MUTED)))
            if description := descriptions.get(tag):
                item.setToolTip(1, description)
        new_item = QTreeWidgetItem(self._tag_tree, ["+ New tag…", ""])
        new_item.setData(0, _TAG_ROLE, _NEW_TAG)
        self._tag_tree.itemClicked.connect(self._on_tag_item_clicked)
        self._tag_tree.resizeColumnToContents(0)
        self._root.addWidget(self._tag_tree)

    def _reveal_tag_tree(self) -> None:
        self._attach_tag_link.setVisible(False)
        self._tag_tree.setVisible(True)

    def _on_tag_item_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        if item.data(0, _TAG_ROLE) != _NEW_TAG:
            return
        text = prompt_new_tag(self)
        if text is not None:
            self._add_checked_tag(text)

    def _add_checked_tag(self, tag: str) -> None:
        """Check an existing entry rather than duplicate it, same as the sound
        picker's "choose a file" does for a repeat pick."""
        for item in self._tag_tree.findItems(tag, Qt.MatchFlag.MatchExactly, 0):
            if item.data(0, _TAG_ROLE) != _NEW_TAG:
                item.setCheckState(0, Qt.CheckState.Checked)
                return
        item = QTreeWidgetItem([tag, ""])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        item.setCheckState(0, Qt.CheckState.Checked)
        # Before "+ New tag…", the tree's last row.
        self._tag_tree.insertTopLevelItem(self._tag_tree.topLevelItemCount() - 1, item)

    def selected_tags(self) -> list[str]:
        tags: list[str] = []
        for i in range(self._tag_tree.topLevelItemCount()):
            item = self._tag_tree.topLevelItem(i)
            if item is None or item.data(0, _TAG_ROLE) == _NEW_TAG:
                continue
            if item.checkState(0) == Qt.CheckState.Checked:
                tags.append(item.text(0))
        return tags

    def _accept(self) -> None:
        tags = self.selected_tags()
        self.accept()
        self._on_accept(tags)

    def reject(self) -> None:
        """Esc or the close button — same as attaching no tags and pressing the button."""
        tags = self.selected_tags()
        super().reject()
        self._on_accept(tags)
