"""The notification sounds, synthesized rather than shipped.

Generating tones keeps the repo free of binary assets and makes the whole catalogue one
short table to edit. Each sound is a run of tones; a tone at 0 Hz is a gap, and every tone
is faded in and out over a few milliseconds so it doesn't click.

Building the audio (:func:`wav_bytes`) is pure and testable; :class:`SoundPlayer` is the
part that needs a working audio device.
"""

from __future__ import annotations

import io
import math
import struct
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication

SAMPLE_RATE = 44100
_FADE_MS = 6  # long enough to kill the click, short enough not to soften the attack

# Sounds handled by the platform rather than by us.
SILENT = "none"
SYSTEM = "system"


@dataclass(frozen=True)
class Tone:
    hz: float  # 0 for a gap
    ms: int
    gain: float = 0.45


@dataclass(frozen=True)
class Sound:
    key: str
    label: str
    tones: tuple[Tone, ...] = ()


CATALOGUE: tuple[Sound, ...] = (
    Sound(SYSTEM, "System beep"),
    Sound("chime", "Chime", (Tone(880, 120), Tone(1174, 240))),
    Sound("ping", "Ping", (Tone(1046, 150),)),
    Sound(
        "soft",
        "Soft",
        (Tone(523, 220, gain=0.26), Tone(659, 300, gain=0.26)),
    ),
    Sound(
        "alert",
        "Alert",
        (
            Tone(1318, 80),
            Tone(0, 70),
            Tone(1318, 80),
            Tone(0, 70),
            Tone(1318, 140),
        ),
    ),
    Sound(SILENT, "Silent"),
)

BY_KEY: dict[str, Sound] = {sound.key: sound for sound in CATALOGUE}
KEYS: tuple[str, ...] = tuple(BY_KEY)
DEFAULT = "chime"


def label_for(key: str) -> str:
    sound = BY_KEY.get(key)
    return sound.label if sound else key


def wav_bytes(sound: Sound, sample_rate: int = SAMPLE_RATE) -> bytes:
    """Render ``sound`` to a mono 16-bit WAV."""
    frames = bytearray()
    for tone in sound.tones:
        total = int(sample_rate * tone.ms / 1000)
        fade = max(1, min(int(sample_rate * _FADE_MS / 1000), total // 2))
        for i in range(total):
            if i < fade:
                envelope = i / fade
            elif i >= total - fade:
                envelope = (total - i) / fade
            else:
                envelope = 1.0
            value = math.sin(2 * math.pi * tone.hz * i / sample_rate)
            frames += struct.pack("<h", int(value * tone.gain * envelope * 32767))

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(bytes(frames))
    return buffer.getvalue()


class SoundPlayer:
    """Plays a catalogue sound by key, materializing the audio on first use.

    ``QSoundEffect`` wants a file, so rendered WAVs are cached in a temp directory and the
    effects themselves are kept alive — loading is asynchronous, and an effect that goes out
    of scope stops mid-play.
    """

    def __init__(self, cache_dir: Path | None = None) -> None:
        self._dir = cache_dir or Path(tempfile.gettempdir()) / "habito-sounds"
        self._effects: dict[str, QSoundEffect] = {}

    def wav_path(self, key: str) -> Path:
        """Write the sound to the cache if it isn't there yet, and return its path."""
        sound = BY_KEY[key]
        path = self._dir / f"{key}.wav"
        if not path.exists():
            self._dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(wav_bytes(sound))
        return path

    def preload(self, key: str) -> None:
        """Get an effect ready ahead of time, so the first notification isn't silent."""
        if key in (SILENT, SYSTEM) or key not in BY_KEY:
            return
        self._effect(key)

    def play(self, key: str) -> None:
        if key == SILENT:
            return
        if key == SYSTEM or key not in BY_KEY:
            QApplication.beep()
            return
        self._effect(key).play()

    def _effect(self, key: str) -> QSoundEffect:
        effect = self._effects.get(key)
        if effect is None:
            effect = QSoundEffect()
            effect.setSource(QUrl.fromLocalFile(str(self.wav_path(key))))
            self._effects[key] = effect
        return effect
