"""The window that interrupts you when a phase ends.

A Pomodoro that rolls straight from work into a break gives you a break you spent finishing
a sentence. So the engine stops at the boundary and this dialog is what restarts it: it
comes up on top of whatever you're doing, and the next phase begins only when you press the
button — at which point the main window is brought back to the front.

Topmost is for *arriving* in front, not for staying there: the hint is set in
:meth:`~habito.ui.prompt_dialog.PromptDialog.present` and dropped again as soon as you move
to another window.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QWidget

from habito.ui.prompt_dialog import PromptDialog


class PhaseDialog(PromptDialog):
    def __init__(
        self,
        title: str,
        body: str,
        action: str,
        on_accept: Callable[[], None],
        gates_phase: bool = True,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(title, body, parent)
        self._on_accept = on_accept
        # True when the session is parked behind this prompt, so the window knows to take
        # it down again if the session ends some other way (you press stop, say).
        self.gates_phase = gates_phase
        # No close button: the point is that you answer it. Esc is swallowed below.
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        # Deliberately *not* modal: the timer window stays usable, so you can still stop
        # the session instead of taking the break you're being offered.
        self._add_action_row(action)
        self.action_button.clicked.connect(self._accept)

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
