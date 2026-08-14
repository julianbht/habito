"""The ☰ "Manage tags" dialog: browse every known tag and its description.

Editing itself — name and description, both for a new tag and for changing an existing
one's description — lives entirely in `TagEditDialog`, opened by the `TagPicker` this
dialog wraps. That's also what the session-end "+ Attach tag" prompt is built on
(`SessionCompleteDialog`), so there is exactly one tag list and one tag editor in the app,
not near-duplicates that happen to agree. See CLAUDE.md § Tags for the shape and why.

Nothing here writes an event directly — `TagEditDialog` does that on Save, immediately, so
by the time this dialog is looking at its tree the write already landed. That's why the
dismiss button is "Close," not "Save": there's nothing left to commit. The dialog's own
primary action is "+ New tag" (`TagPicker` styles it that way whenever it isn't checkable —
see its module docstring), sitting beside "Close" the same way every other button row in
this app pairs a primary action with a plain dismiss one, not stacked as two full-width
rows.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from habito.ui.tag_edit_dialog import SubmitCallback
from habito.ui.tag_picker import TagPicker
from habito.ui.widgets import button, label


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
        self.setWindowTitle("Manage tags")
        self.setMinimumWidth(440)
        self.setMinimumHeight(360)
        self._build(tags, descriptions, on_submit, habit, now)

    def _build(
        self,
        tags: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        habit: str,
        now: datetime,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        hint = "Double-click a tag to change its description."
        root.addWidget(label(hint, "muted"))

        self.picker = TagPicker(tags, descriptions, on_submit, habit, now, checkable=False)
        root.addWidget(self.picker, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.picker.new_tag_button)
        actions.addStretch(1)
        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        root.addLayout(actions)
