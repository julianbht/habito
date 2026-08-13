"""Wiring between session completion and the tag prompt.

SessionCompleteDialog's own behaviour (the picker, Esc, "New tag…") is covered in
test_ui_session_complete_dialog.py — these tests are only about what the window does
with the answer: HabitoApp._prompt and _on_session_complete_accepted.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.domain.events import SessionTagged
from habito.engine.pomodoro import State
from habito.ui.app import HabitoApp
from habito.ui.session_complete_dialog import SessionCompleteDialog


def build(qtbot, tmp_path, *, rounds: int = 1):
    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "pomodoro": {"rounds": rounds},
        }
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    window.show()
    qtbot.waitExposed(window)
    return window, store


def finish_the_session(window):
    """Drive a whole session to completion, whatever its round count."""
    window.on_start()
    for _ in range(window._config.pomodoro.rounds * 2 - 1):
        window._engine.skip()
        window._repaint()
        window._engine.acknowledge()
        window._repaint()


def last_row(dialog: SessionCompleteDialog):
    """``topLevelItem`` is stubbed as ``| None``; the "+ New tag…" row is always there."""
    item = dialog._tag_tree.topLevelItem(dialog._tag_tree.topLevelItemCount() - 1)
    assert item is not None
    return item


def pick_new_tag(qtbot, monkeypatch, dialog: SessionCompleteDialog, tag: str) -> None:
    monkeypatch.setattr(QInputDialog, "getText", staticmethod(lambda *a, **kw: (tag, True)))
    dialog._reveal_tag_tree()
    dialog._on_tag_item_clicked(last_row(dialog), 0)


def test_finishing_a_session_shows_the_tag_prompt_not_the_phase_prompt(qtbot, tmp_path):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)

    assert window._engine.state is State.done
    assert isinstance(window._phase_dialog, SessionCompleteDialog)
    assert window._phase_dialog.action_button.text() == "Done"


def test_choosing_a_tag_appends_a_session_tagged_event(qtbot, tmp_path, monkeypatch):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)
    session_id = window._engine.session_id

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "linear algebra")
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    tagged = [e for e in store.read_all() if isinstance(e, SessionTagged)]
    assert len(tagged) == 1
    assert tagged[0].tag == "linear algebra"
    assert tagged[0].session_id == session_id
    assert window._phase_dialog is None


def test_checking_two_tags_appends_one_session_tagged_event_each(qtbot, tmp_path, monkeypatch):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)
    session_id = window._engine.session_id

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "linear algebra")
    pick_new_tag(qtbot, monkeypatch, dialog, "topology")
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    tagged = [e for e in store.read_all() if isinstance(e, SessionTagged)]
    assert {e.tag for e in tagged} == {"linear algebra", "topology"}
    assert all(e.session_id == session_id for e in tagged)


def test_skipping_the_prompt_appends_nothing(qtbot, tmp_path):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    assert [e for e in store.read_all() if isinstance(e, SessionTagged)] == []
    assert window._phase_dialog is None


def test_dismissing_with_escape_appends_nothing(qtbot, tmp_path):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    qtbot.keyClick(dialog, Qt.Key.Key_Escape)

    assert [e for e in store.read_all() if isinstance(e, SessionTagged)] == []
    assert window._phase_dialog is None


def test_a_second_session_completes_normally_after_a_tag_was_recorded(qtbot, tmp_path, monkeypatch):
    """The tag event must not confuse anything reading the store afterwards."""
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)
    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "linear algebra")
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    window.on_start()
    window._engine.skip()
    window._repaint()

    assert window._engine.state is State.done
    assert isinstance(window._phase_dialog, SessionCompleteDialog)


def test_the_prompt_offers_a_tag_used_in_an_earlier_session(qtbot, tmp_path, monkeypatch):
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)
    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "topology")
    qtbot.mouseClick(dialog.action_button, Qt.MouseButton.LeftButton)

    # A fresh window over the same store: "topology" should already be offered.
    engine, _ = _build_engine_and_store(window._config, test_mode=False)
    window2 = HabitoApp(window._config, engine, store, test_mode=True)
    qtbot.addWidget(window2)
    finish_the_session(window2)

    dialog2 = window2._phase_dialog
    assert isinstance(dialog2, SessionCompleteDialog)
    tree = dialog2._tag_tree
    labels = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert item is not None
        labels.append(item.text(0))
    assert "topology" in labels
