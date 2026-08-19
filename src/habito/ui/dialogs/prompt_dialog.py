"""The shell shared by the two dialogs that interrupt the user with one clear ask: a
centred heading, a message, and a single button — plus the always-on-top behaviour that
gets it seen. PhaseDialog and SessionCompleteDialog differ in what (if anything) goes
between the message and the button, and in how they can be dismissed; that part is theirs.

Topmost is for *arriving* in front, not for staying there: :meth:`present` sets the hint,
and it's on each subclass to decide if/when to drop it again (PhaseDialog does, on focus
loss; see its own docstring).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QWindow
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QVBoxLayout, QWidget

from habito.ui.widgets.controls import COMPACT_DIALOG_WIDTH, Button, label, primary_button


class PromptDialog(QDialog):
    """A centred heading/message with one primary action button below."""

    action_button: Button

    def __init__(self, title: str, body: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(COMPACT_DIALOG_WIDTH)

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(24, 22, 24, 20)
        self._root.setSpacing(10)

        heading = label(title, "heading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._root.addWidget(heading)

        message = label(body)
        message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message.setWordWrap(True)
        self._root.addWidget(message)

    def _add_action_row(self, action: str) -> Button:
        """The centred action button. Called last, once a subclass has added whatever
        goes between the message and it.

        The one row in the app not built by ``widgets.button_row`` — see CLAUDE.md §
        Controls. A prompt whose only button is its action centres it, matching the centred
        heading and message above it; right-aligning a lone button under centred text reads
        as a mistake. A subclass that adds a second button lays out its own ``button_row``
        instead (``SessionCompleteDialog`` does).
        """
        row = QHBoxLayout()
        row.addStretch(1)
        self.action_button = primary_button(action)
        row.addWidget(self.action_button)
        row.addStretch(1)
        self._root.addSpacing(4)
        self._root.addLayout(row)
        return self.action_button

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
        """Set or clear the topmost hint.

        Once the window exists the change goes through :class:`QWindow`, which reorders the
        native window in place. The ``QWidget`` setter would hide it and demand a second
        ``show()`` — which re-raises and re-steals focus, the opposite of dropping topmost.
        """
        handle: QWindow | None = self.windowHandle()
        if handle is None:  # pyright: ignore[reportUnnecessaryComparison]
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        else:
            handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, on)

    def is_always_on_top(self) -> bool:
        # Annotated because the stub types this non-optional; it is None until show().
        handle: QWindow | None = self.windowHandle()
        flags = (
            self.windowFlags()
            if handle is None  # pyright: ignore[reportUnnecessaryComparison]
            else handle.flags()
        )
        return bool(flags & Qt.WindowType.WindowStaysOnTopHint)
