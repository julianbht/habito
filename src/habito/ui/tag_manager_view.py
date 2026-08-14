"""Dialog to give tags an optional longer description — "LinAlg-S" → "Strang, Linear
Algebra and Its Applications" — kept apart from the session-end prompt so writing the long
form is never something a finished pomodoro is waiting on (see CLAUDE.md § Tags).

Produces :class:`~habito.domain.events.TagDescribed` events via
:func:`habito.tagging.build_tag_described_event`, handed to ``on_submit`` one at a time as
each tag is saved. Nothing here touches ``SessionTagged`` — describing a tag and applying
one to a session are different actions on different clocks, so this dialog never closes
itself on save: it's meant for browsing and updating several tags in one visit.

The tag/description list is a two-column ``QTreeWidget``, the same shape LogView uses for
its own read-only rows (flat, unindented, alternating rows, a muted secondary column) —
there's no day-grouping to reuse here, just the look.

Selecting a row is just browsing — the description field stays out of it, so arrowing
through tags never puts one "in edit" by accident. A double-click is the one gesture that
loads a tag's current text into the field and arms Save, because changing a description is
meant to be rare and deliberate, not a side effect of looking.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from habito.domain.events import Event
from habito.tagging import build_tag_described_event
from habito.ui import theme
from habito.ui.widgets import button, label, prompt_new_tag

SubmitCallback = Callable[[Event], None]


class TagManagerDialog(QDialog):
    def __init__(
        self,
        tags: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_submit = on_submit
        self._habit = habit
        self._now = now
        self._tags = sorted(tags)
        self._descriptions = dict(descriptions)
        # The tag currently loaded into the description field for editing, if any —
        # distinct from the tree's selection, which is just browsing.
        self._editing_tag: str | None = None
        self._loaded_description = ""
        self.setWindowTitle("Manage tags")
        self.setMinimumWidth(440)
        self.setMinimumHeight(360)
        self._build()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        hint = "Double-click a tag to change its description."
        root.addWidget(label(hint, "muted"))

        self.tree = QTreeWidget()
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels(["Tag", "Description"])
        self.tree.setIndentation(0)
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QTreeWidget.EditTrigger.NoEditTriggers)
        self._refresh_tree()
        # itemDoubleClicked, not itemActivated: activation also fires on Enter (and, on
        # some platforms, a single click), which would arm editing far too easily.
        self.tree.itemDoubleClicked.connect(self._on_tag_double_clicked)
        root.addWidget(self.tree, 1)

        self.description = QLineEdit()
        self.description.setPlaceholderText("Add description")
        self.description.setMaxLength(200)
        self.description.setEnabled(False)
        root.addWidget(self.description)

        actions = QHBoxLayout()
        new_tag_btn = button("+ New tag")
        new_tag_btn.clicked.connect(self._on_new_tag)
        actions.addWidget(new_tag_btn)
        actions.addStretch(1)
        self.save_btn = button("Save", "primary")
        self.save_btn.setDefault(True)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self._on_save)
        actions.addWidget(self.save_btn)
        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        root.addLayout(actions)

        if self._tags:
            self.tree.setCurrentItem(self._row(self._tags[0]))

    def _refresh_tree(self) -> None:
        self.tree.clear()
        for tag in self._tags:
            item = QTreeWidgetItem(self.tree, [tag, self._descriptions.get(tag, "")])
            item.setForeground(1, QBrush(QColor(theme.MUTED)))
        self.tree.resizeColumnToContents(0)

    def _row(self, tag: str) -> QTreeWidgetItem:
        """The row for ``tag``. Always present — called right after inserting or
        confirming it's already in ``self._tags``, which the tree was just built from."""
        item = self.tree.topLevelItem(self._tags.index(tag))
        assert item is not None
        return item

    def _enter_edit_mode(self, tag: str) -> None:
        self._editing_tag = tag
        self._loaded_description = self._descriptions.get(tag, "")
        self.description.setEnabled(True)
        self.description.setText(self._loaded_description)
        self.description.selectAll()
        self.description.setFocus()
        self.save_btn.setEnabled(True)

    def _exit_edit_mode(self) -> None:
        self._editing_tag = None
        self._loaded_description = ""
        self.description.clear()
        self.description.setEnabled(False)
        self.save_btn.setEnabled(False)

    def _on_tag_double_clicked(self, item: QTreeWidgetItem, column: int) -> None:
        self._enter_edit_mode(item.text(0))

    def _on_new_tag(self) -> None:
        text = prompt_new_tag(self)
        if text is None:
            return
        if text not in self._tags:
            self._tags = sorted([*self._tags, text])
            self._refresh_tree()
        self.tree.setCurrentItem(self._row(text))
        self._enter_edit_mode(text)

    def _on_save(self) -> None:
        tag = self._editing_tag
        text = self.description.text().strip()
        if tag is None or text == self._loaded_description:
            return
        event = build_tag_described_event(tag, text, habit=self._habit, now=self._now)
        self._on_submit(event)
        self._descriptions[tag] = text
        self._refresh_tree()
        self.tree.setCurrentItem(self._row(tag))
        self._exit_edit_mode()
