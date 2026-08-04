"""Notification sound selection.

Actually making noise needs an audio device, so what's covered here is how a setting is
interpreted — built-in versus file, and what happens when a chosen file goes missing.
"""

from __future__ import annotations

import pytest

from habito.config.models import UIConfig
from habito.ui import sounds


def test_the_catalogue_is_addressable_by_key():
    assert set(sounds.KEYS) == {s.key for s in sounds.CATALOGUE}
    assert sounds.DEFAULT in sounds.BY_KEY
    assert sounds.SILENT in sounds.BY_KEY


def test_every_audible_built_in_maps_to_a_windows_alias():
    """The built-ins are the system's own sounds, not imitations of them."""
    for sound in sounds.CATALOGUE:
        if sound.key != sounds.SILENT:
            assert sound.alias, f"{sound.key} has no system alias"


@pytest.mark.parametrize("key", [s.key for s in sounds.CATALOGUE])
def test_built_in_keys_are_not_mistaken_for_paths(key):
    assert not sounds.is_custom(key)
    assert sounds.label_for(key) == sounds.BY_KEY[key].label


def test_a_path_is_treated_as_a_custom_sound():
    path = r"C:\sounds\my alarm.wav"
    assert sounds.is_custom(path)
    assert sounds.label_for(path) == "my alarm.wav"  # shown by name, not full path


def test_an_empty_setting_is_not_custom():
    assert not sounds.is_custom("")


def test_the_file_filter_covers_the_usual_formats():
    for suffix in (".wav", ".mp3", ".ogg"):
        assert f"*{suffix}" in sounds.FILE_FILTER


# --- playback -------------------------------------------------------------
def test_silent_plays_nothing(qapp, monkeypatch):
    beeps = []
    monkeypatch.setattr(sounds.QApplication, "beep", lambda: beeps.append(1))
    player = sounds.SoundPlayer()

    player.play(sounds.SILENT)
    player.play("")
    assert beeps == []


def test_a_missing_file_falls_back_to_a_beep(qapp, monkeypatch, tmp_path):
    """Better an ugly noise than a phase change you never hear about."""
    beeps = []
    monkeypatch.setattr(sounds.QApplication, "beep", lambda: beeps.append(1))
    player = sounds.SoundPlayer()

    player.play(str(tmp_path / "deleted.wav"))
    assert beeps == [1]


@pytest.mark.skipif(sounds.IS_WINDOWS, reason="Windows plays its own system sounds")
def test_built_ins_fall_back_to_a_beep_off_windows(qapp, monkeypatch):
    beeps = []
    monkeypatch.setattr(sounds.QApplication, "beep", lambda: beeps.append(1))
    sounds.SoundPlayer().play("asterisk")
    assert beeps == [1]


@pytest.mark.skipif(not sounds.IS_WINDOWS, reason="needs the winsound alias API")
def test_built_ins_use_the_windows_alias_api(qapp, monkeypatch):
    import winsound

    played = []
    monkeypatch.setattr(winsound, "PlaySound", lambda name, flags: played.append((name, flags)))
    sounds.SoundPlayer().play("asterisk")

    assert played[0][0] == "SystemAsterisk"
    assert played[0][1] & winsound.SND_ALIAS


# --- config ---------------------------------------------------------------
def test_the_default_config_sound_is_a_real_one():
    assert UIConfig().sound in sounds.BY_KEY


def test_a_file_path_is_accepted_as_a_config_sound():
    """A path that doesn't exist yet mustn't stop the app from starting."""
    assert UIConfig(sound=r"D:\nope\gone.wav").sound == r"D:\nope\gone.wav"
