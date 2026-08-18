"""The ☰ "Manage tags" dialog: browse every known tag and its description.

Editing itself lives entirely in ``CatalogEditDialog``, opened by the ``CatalogPicker`` this
dialog wraps — the same picker and editor the session-end tag prompt and the retroactive
tag/untag picker also embed, so there is exactly one tag list and one editor shape in the
app, not near-duplicates that happen to agree. See CLAUDE.md § Tags.

Not reused for workouts, even though ``CatalogPicker``/``CatalogEditDialog`` are shared with
tags: a workout's checkable picker (in ``WorkoutLogDialog``) already offers the identical
create/edit-description capability — double-click a row, "+ New workout" — so a standalone,
non-logging manager would be a strict subset with nothing of its own. Tags need one anyway
because their checkable pickers only ever appear *inside* a session-tagging flow, with no
"just edit the catalog" entry point otherwise.

Nothing here writes an event directly — ``CatalogEditDialog`` does that on Save,
immediately, so by the time this dialog is looking at its tree the write already landed.
That's why the dismiss button is "Close," not "Save": there's nothing left to commit. The
dialog's own primary action is "+ New …" (``CatalogPicker`` styles it that way whenever it
isn't checkable), sitting beside "Close" the same way every other button row in this app
pairs a primary action with a plain dismiss one, not stacked as two full-width rows.
"""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QHBoxLayout, QVBoxLayout, QWidget

from habito.ui.dialogs.catalog_edit_dialog import CreatedBuilder, DescribedBuilder, SubmitCallback
from habito.ui.widgets.catalog_picker import CatalogPicker
from habito.ui.widgets.controls import BROWSE_DIALOG_HEIGHT, BROWSE_DIALOG_WIDTH, button, label


class CatalogManagerDialog(QDialog):
    def __init__(
        self,
        title: str,
        hint: str,
        noun: str,
        items: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        build_created: CreatedBuilder,
        build_described: DescribedBuilder,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self._build(hint, noun, items, descriptions, on_submit, build_created, build_described)

    def _build(
        self,
        hint: str,
        noun: str,
        items: list[str],
        descriptions: dict[str, str],
        on_submit: SubmitCallback,
        build_created: CreatedBuilder,
        build_described: DescribedBuilder,
    ) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        root.addWidget(label(hint, "muted"))

        self.picker = CatalogPicker(
            items, descriptions, on_submit, build_created, build_described, noun, checkable=False
        )
        root.addWidget(self.picker, 1)

        actions = QHBoxLayout()
        actions.addWidget(self.picker.new_button)
        actions.addStretch(1)
        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        actions.addWidget(close_btn)
        root.addLayout(actions)
