"""The window that interrupts you when a phase ends.

A Pomodoro that rolls straight from work into a break gives you a break you spent finishing
a sentence. So the engine stops at the boundary and this dialog is what restarts it: it
comes up on top of whatever you're doing, and the next phase begins only when you press the
button — at which point the main window is brought back to the front.

Topmost is for *arriving* in front, not for staying there: the hint is set in
:meth:`present` and dropped again as soon as you move to another window.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent, QWindow
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QVBoxLayout, QWidget

from habito.ui.widgets import button, label


class PhaseDialog(QDialog):
    def __init__(
        self,
        title: str,
        body: str,
        action: str,
        on_accept: Callable[[], None],
        gates_phase: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._on_accept = on_accept
        # True when the session is parked behind this prompt, so the window knows to take
        # it down again if the session ends some other way (you press stop, say).
        self.gates_phase = gates_phase
        self.setWindowTitle(title)
        self.setMinimumWidth(320)
        # No close button: the point is that you answer it. Esc is swallowed below.
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        # Deliberately *not* modal: the timer window stays usable, so you can still stop
        # the session instead of taking the break you're being offered.
        self._build(title, body, action)

    def _build(self, title: str, body: str, action: str) -> None:
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
        # Annotated because the stub types this non-optional; it is None until show().
        handle: QWindow | None = self.windowHandle()
        if handle is None:  # pyright: ignore[reportUnnecessaryComparison]
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, on)
        else:
            handle.setFlag(Qt.WindowType.WindowStaysOnTopHint, on)

    def is_always_on_top(self) -> bool:
        handle: QWindow | None = self.windowHandle()
        flags = (
            self.windowFlags()
            if handle is None  # pyright: ignore[reportUnnecessaryComparison]
            else handle.flags()
        )
        return bool(flags & Qt.WindowType.WindowStaysOnTopHint)

    def event(self, event: QEvent) -> bool:
        """Drop topmost as soon as focus moves elsewhere."""
        if event.type() == QEvent.Type.WindowDeactivate:
            self.set_always_on_top(False)
        return super().event(event)

    def _accept(self) -> None:
        self.accept()
        self._on_accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt override)
        """Swallow Esc — dismissing this without answering would strand the session."""
        if event.key() == Qt.Key.Key_Escape:
            event.ignore()
            return
        super().keyPressEvent(event)
