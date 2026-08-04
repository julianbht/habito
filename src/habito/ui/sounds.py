"""Notification sounds: the platform's own, or a file you point at.

Windows exposes its system sounds through ``winsound``'s alias API, so the built-ins are
the real thing rather than an imitation of one — they follow whatever the user has set in
Sound settings. Elsewhere there's no equivalent, so the built-ins fall back to Qt's beep
and a custom file is the way to get something specific.

A setting is either a key from :data:`CATALOGUE` or a path to an audio file; anything that
isn't a known key is treated as a path.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import QApplication

IS_WINDOWS = sys.platform == "win32"

SILENT = "none"


@dataclass(frozen=True)
class Sound:
    key: str
    label: str
    alias: str | None = None  # the Windows registry event name, when there is one


# Windows' documented system-sound aliases. The labels match what Sound settings calls
# them, so what you pick here is what you'd go and change there.
CATALOGUE: tuple[Sound, ...] = (
    Sound("asterisk", "Asterisk", "SystemAsterisk"),
    Sound("notification", "Notification", "Notification.Default"),
    Sound("exclamation", "Exclamation", "SystemExclamation"),
    Sound("question", "Question", "SystemQuestion"),
    Sound("critical", "Critical stop", "SystemHand"),
    Sound("default", "Default beep", "SystemDefault"),
    Sound(SILENT, "Silent"),
)

BY_KEY: dict[str, Sound] = {sound.key: sound for sound in CATALOGUE}
KEYS: tuple[str, ...] = tuple(BY_KEY)
DEFAULT = "notification"

AUDIO_SUFFIXES = (".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma")
FILE_FILTER = "Audio (" + " ".join(f"*{s}" for s in AUDIO_SUFFIXES) + ");;All files (*)"


def is_custom(setting: str) -> bool:
    """True when the setting names a file rather than one of the built-ins."""
    return bool(setting) and setting not in BY_KEY


def label_for(setting: str) -> str:
    if is_custom(setting):
        return Path(setting).name
    sound = BY_KEY.get(setting)
    return sound.label if sound else setting


class SoundPlayer:
    """Plays whatever a sound setting names.

    The ``QMediaPlayer`` is kept as an attribute rather than a local: it plays
    asynchronously, and one that goes out of scope is collected mid-sound.
    """

    def __init__(self) -> None:
        self._player: QMediaPlayer | None = None
        self._output: QAudioOutput | None = None

    def play(self, setting: str) -> None:
        if not setting or setting == SILENT:
            return
        if is_custom(setting):
            self._play_file(Path(setting))
            return
        sound = BY_KEY[setting]
        if IS_WINDOWS and sound.alias:
            self._play_alias(sound.alias)
        else:
            QApplication.beep()

    @staticmethod
    def _play_alias(alias: str) -> None:
        import winsound

        try:
            winsound.PlaySound(alias, winsound.SND_ALIAS | winsound.SND_ASYNC)
        except RuntimeError:
            QApplication.beep()

    def _play_file(self, path: Path) -> None:
        if not path.is_file():
            QApplication.beep()  # the file moved; better a noise than silence
            return
        if self._player is None:
            self._output = QAudioOutput()
            self._player = QMediaPlayer()
            self._player.setAudioOutput(self._output)
        self._player.setSource(QUrl.fromLocalFile(str(path)))
        self._player.play()

    def preload(self, setting: str) -> None:
        """Kept for symmetry with the settings flow; nothing needs warming up now."""
