"""Wiring between session completion and the tag prompt.

SessionCompleteDialog's own behaviour (the picker, Esc) is covered in
test_ui_session_complete_dialog.py, and TagPicker/TagEditDialog's in their own files —
these tests are only about what the window does with the answer: HabitoApp._prompt and
_on_session_complete_accepted, including that a tag described mid-attach actually reaches
the store (on_describe_tag), not just the checked-tags-become-SessionTagged path.
"""

from __future__ import annotations

from PySide6.QtCore import Qt

from habito.app import _build_engine_and_store
from habito.config.models import Config
from habito.domain.events import SessionTagged, TagDescribed
from habito.engine.clock import FakeClock
from habito.engine.pomodoro import PomodoroEngine, State
from habito.projections.daily import summary_for
from habito.storage.event_store import EventStore
from habito.ui.app import HabitoApp
from habito.ui.dialogs.session_complete_dialog import SessionCompleteDialog
from habito.ui.dialogs.tag_edit_dialog import TagEditDialog


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


def pick_new_tag(
    qtbot, monkeypatch, dialog: SessionCompleteDialog, tag: str, description: str = ""
) -> None:
    def fake_exec(self: TagEditDialog) -> int:
        if not self._name.isReadOnly():
            self._name.setText(tag)
        self._description.setPlainText(description)
        self._on_save()
        return self.result()

    monkeypatch.setattr(TagEditDialog, "exec", fake_exec)
    dialog._reveal_tag_picker()
    dialog.tag_picker._on_new_tag()


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


def test_describing_a_new_tag_while_attaching_reaches_the_store_immediately(
    qtbot, tmp_path, monkeypatch
):
    """The description is a TagDescribed, written the moment TagEditDialog saves it — not
    deferred until (or dependent on) the outer session-complete prompt being accepted."""
    window, store = build(qtbot, tmp_path)
    finish_the_session(window)

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "linear algebra", description="Strang, ch. 1-3")

    described = [e for e in store.read_all() if isinstance(e, TagDescribed)]
    assert len(described) == 1
    assert described[0].tag == "linear algebra"
    assert described[0].description == "Strang, ch. 1-3"
    # Not attached yet — that only happens once Done is pressed.
    assert [e for e in store.read_all() if isinstance(e, SessionTagged)] == []


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


def build_with_fake_clock(qtbot, tmp_path, *, rounds: int = 2):
    """Like `build`, but a FakeClock so phases can actually elapse instead of skipping
    instantly at t=0 — needed to get nonzero recorded work_seconds."""
    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "pomodoro": {"rounds": rounds},
        }
    )
    store = EventStore(config.data_repo_path(), config.habit, config.time.rollover_hour)
    clock = FakeClock()
    engine = PomodoroEngine(config.pomodoro, sink=store.append, clock=clock, habit=config.habit)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    return window, store, clock


def finish_the_session_with_elapsed_time(window, clock):
    """Like `finish_the_session`, but each phase elapses a minute before it's skipped, so
    the recorded work/break seconds — and therefore today's total — are nonzero."""
    window.on_start()
    for _ in range(window._config.pomodoro.rounds * 2 - 1):
        clock.advance(60)
        window._engine.skip()
        window._repaint()
        window._engine.acknowledge()
        window._repaint()


def test_describing_a_new_tag_after_finishing_does_not_double_count_today(
    qtbot, tmp_path, monkeypatch
):
    """Regression: the just-finished session's rounds are already in the store by the
    time this prompt shows (sink=store.append), and the engine snapshot still adds the
    same session's total on top of the baseline until the next on_start(). Recomputing
    the baseline here (_append_all, for the TagDescribed the new tag writes) must not
    fold that session's own rounds back in a second time."""
    window, store, clock = build_with_fake_clock(qtbot, tmp_path, rounds=2)
    finish_the_session_with_elapsed_time(window, clock)

    expected = summary_for(
        store.read_all(), window._today(), window._config.time.rollover_hour
    ).total_work_seconds
    assert expected > 0

    dialog = window._phase_dialog
    assert isinstance(dialog, SessionCompleteDialog)
    pick_new_tag(qtbot, monkeypatch, dialog, "linear algebra", description="Strang, ch. 1-3")

    displayed = window._today_baseline + window._engine.snapshot().session_work_seconds
    assert displayed == expected


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
    tree = dialog2.tag_picker.tree
    labels = []
    for i in range(tree.topLevelItemCount()):
        item = tree.topLevelItem(i)
        assert item is not None
        labels.append(item.text(0))
    assert "topology" in labels
