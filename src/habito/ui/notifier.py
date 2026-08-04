"""Telling you a phase ended when you're not looking at the window.

A Pomodoro you have to watch defeats the point, so phase changes are announced three ways:
a system-tray message, a taskbar/dock alert, and a sound. Which of those actually land
depends on the desktop, hence all three rather than picking one. The sound is chosen in
Settings; see :mod:`habito.ui.sounds`.

Deciding *what* to say is a pure function (:func:`notification_for`) kept apart from
delivering it, so the interesting half is testable without a desktop.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PySide6.QtWidgets import QApplication, QStyle, QSystemTrayIcon, QWidget

from habito.engine.pomodoro import EngineState, State
from habito.ui.sounds import DEFAULT as DEFAULT_SOUND
from habito.ui.sounds import SoundPlayer
from habito.ui.widgets import format_duration

_MESSAGE_MS = 6000


@dataclass(frozen=True)
class Notification:
    title: str
    body: str


def notification_for(previous: State, snap: EngineState) -> Notification | None:
    """What to announce when the engine leaves ``previous`` for ``snap.state``.

    Only automatic transitions are worth announcing — you already know about the ones you
    triggered yourself, and the caller suppresses those.
    """
    current = snap.state
    if previous == current:
        return None

    if previous is State.work and current is State.break_:
        return Notification(
            "Break time",
            f"Round {snap.round_index} of {snap.total_rounds} done — step away.",
        )
    if previous is State.break_ and current is State.work:
        return Notification(
            "Back to work",
            f"Round {snap.round_index} of {snap.total_rounds}.",
        )
    if previous in (State.work, State.break_) and current is State.done:
        return Notification(
            "Session complete",
            f"{format_duration(snap.session_work_seconds)} of focus. Nicely done.",
        )
    return None


class Sink(Protocol):
    """Somewhere for a notification to go — the desktop, or a list in a test."""

    def send(self, note: Notification) -> None: ...


class DesktopNotifier:
    def __init__(
        self,
        window: QWidget,
        player: SoundPlayer,
        sound: str = DEFAULT_SOUND,
        enabled: bool = True,
    ) -> None:
        self._window = window
        self._player = player
        self._sound = sound
        self._enabled = enabled
        self._tray: QSystemTrayIcon | None = None
        if enabled and QSystemTrayIcon.isSystemTrayAvailable():
            style = window.style()
            icon = style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation)
            self._tray = QSystemTrayIcon(icon, window)
            self._tray.setToolTip("Habito")
            self._tray.show()

    def set_sound(self, sound: str) -> None:
        self._sound = sound

    def send(self, note: Notification) -> None:
        if not self._enabled:
            return
        if self._tray is not None:
            self._tray.showMessage(
                note.title, note.body, QSystemTrayIcon.MessageIcon.Information, _MESSAGE_MS
            )
        app = QApplication.instance()
        if isinstance(app, QApplication):
            # Flash the taskbar entry until the window is looked at (0 = until focused).
            app.alert(self._window, 0)
        self._player.play(self._sound)

    def close(self) -> None:
        if self._tray is not None:
            self._tray.hide()
            self._tray = None
