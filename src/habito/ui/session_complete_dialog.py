"""The prompt shown when a session finishes: an optional tag, then dismiss.

Unlike :class:`~habito.ui.phase_dialog.PhaseDialog`, nothing here "gates" a phase — the
session already ended, nothing is waiting on this dialog — so Esc or the close button
dismissing it plainly (same as leaving the tag blank and pressing the action button) is
the right default, not something to swallow.

The tag picker is a plain, non-editable combo plus a "New tag…" sentinel that opens a
one-line text prompt, the same shape as the sound picker in Settings — not an editable
combo box, which has caused hard Qt aborts elsewhere in this app (see CLAUDE.md).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QVBoxLayout,
    QWidget,
)

from habito.ui.widgets import button, label

_NO_TAG = ""
_NEW_TAG = "__new_tag__"


class SessionCompleteDialog(QDialog):
    # Never gates a phase — see the module docstring. HabitoApp checks this the same way
    # it checks PhaseDialog.gates_phase, so the two dialogs share one call site.
    gates_phase = False

    def __init__(
        self,
        title: str,
        body: str,
        action: str,
        known_tags: list[str],
        on_accept: Callable[[str | None], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_accept = on_accept
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        self._build(title, body, action, known_tags)

    def _build(self, title: str, body: str, action: str, known_tags: list[str]) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 20)
        root.setSpacing(10)

        heading = label(title, "heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(heading)

        message = label(body)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        root.addWidget(message)

        self._tag_box = QComboBox()
        self._tag_box.addItem("No tag", _NO_TAG)
        for tag in known_tags:
            self._tag_box.addItem(tag, tag)
        self._tag_box.insertSeparator(self._tag_box.count())
        self._tag_box.addItem("New tag…", _NEW_TAG)
        self._tag_box.setToolTip("Optional — what you were working on")
        self._tag_box.activated.connect(self._on_tag_chosen)
        root.addWidget(self._tag_box)

        row = QHBoxLayout()
        row.addStretch(1)
        self.action_button = button(action, "primary")
        self.action_button.setMinimumHeight(38)
        self.action_button.setDefault(True)
        self.action_button.clicked.connect(self._accept)
        row.addWidget(self.action_button)
        row.addStretch(1)
        root.addSpacing(4)
        root.addLayout(row)

    def _on_tag_chosen(self, index: int) -> None:
        if self._tag_box.itemData(index) != _NEW_TAG:
            return
        text, ok = QInputDialog.getText(self, "New tag", "Tag:")
        text = text.strip()
        if ok and text:
            self._add_tag(text)
        else:
            self._tag_box.setCurrentIndex(0)  # back to "No tag"

    def _add_tag(self, tag: str) -> None:
        """Select an existing entry rather than duplicate it, same as the sound
        picker's "choose a file" does for a repeat pick."""
        existing = self._tag_box.findData(tag)
        if existing >= 0:
            self._tag_box.setCurrentIndex(existing)
            return
        insert_at = self._tag_box.count() - 2  # before the separator and "New tag…"
        self._tag_box.insertItem(insert_at, tag, tag)
        self._tag_box.setCurrentIndex(insert_at)

    def selected_tag(self) -> str | None:
        tag = self._tag_box.currentData()
        return tag or None

    def present(self) -> None:
        """Put it in front of whatever the user is looking at."""
        self.set_always_on_top(True)  # before show(), so it opens above the foreground app
        self.show()
        self.raise_()
        self.activateWindow()
        self.action_button.setFocus(Qt.FocusReason.OtherFocusReason)
        app = QApplication.instance()
        if isinstance(app, QApplication):
            app.alert(self, 0)  # flash the taskbar until it's noticed

    def set_always_on_top(self, on: bool) -> None:
        handle: QWindow | None = self.windowHandle()
        if handle is None:  # pyright: ignore[reportUnnecessaryComparison]
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        else:
            handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, on)

    def _accept(self) -> None:
        tag = self.selected_tag()
        self.accept()
        self._on_accept(tag)

    def reject(self) -> None:
        """Esc or the close button — same as choosing "No tag" and pressing the button."""
        tag = self.selected_tag()
        super().reject()
        self._on_accept(tag)
