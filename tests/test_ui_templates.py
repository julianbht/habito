"""Session templates: the manager, its form, and switching between them on the timer.

The manager is handed a real ``ConfigEditor`` over a real ``Config`` (test mode, so nothing
is written), so "the row changed" has to be a consequence of the config actually changing
— the same reason the log managers are tested through a real log.
"""

from __future__ import annotations

import pytest
from PySide6.QtWidgets import QDialog

from habito.config.editor import ConfigEditor
from habito.config.models import Config, PomodoroConfig, SessionTemplate
from habito.engine.pomodoro import State
from habito.ui.dialogs.template_delete_confirm_dialog import TemplateDeleteConfirmDialog
from habito.ui.dialogs.template_dialog import TemplateDialog
from habito.ui.dialogs.template_manager_dialog import TemplateManagerDialog, describe_template


# --- the model -------------------------------------------------------------
def test_an_unnamed_template_is_labelled_by_its_numbers():
    assert SessionTemplate(work_minutes=25, break_minutes=5, rounds=2).label() == "2 × 25 · 5"


def test_a_named_template_is_labelled_by_its_name():
    assert SessionTemplate(name="Deep work").label() == "Deep work"


def test_a_blank_name_means_unnamed():
    assert SessionTemplate(name="   ").name is None


def test_a_sub_minute_round_keeps_its_fraction_in_the_label():
    assert SessionTemplate(work_minutes=0.5, rounds=1).label() == "1 × 0.5 · 5"


# --- the manager -----------------------------------------------------------
@pytest.fixture
def config(tmp_path) -> Config:
    config = Config.model_validate({"project_root": tmp_path})
    config.pomodoro = PomodoroConfig(
        templates=[SessionTemplate(rounds=4), SessionTemplate(name="Short", rounds=2)]
    )
    return config


@pytest.fixture
def manager(qtbot, config):
    editor = ConfigEditor(config, test_mode=True)
    dialog = TemplateManagerDialog(
        reload=lambda: config.pomodoro,
        on_apply=lambda templates, active: editor.apply_templates(templates, active).message,
    )
    qtbot.addWidget(dialog)
    return dialog


def rows(dialog):
    tree = dialog.list.tree
    return [tree.topLevelItem(i).text(0) for i in range(tree.topLevelItemCount())]


def fill_and_submit(monkeypatch, **fields):
    """Stand in for the user: set the form's fields, then press its primary button."""

    def exec_(self: TemplateDialog) -> int:
        if "name" in fields:
            self.name_edit.setText(fields["name"])
        if "rounds" in fields:
            self.rounds_spin.setValue(fields["rounds"])
        if "work" in fields:
            self.work_spin.setValue(fields["work"])
        self.ok_button.click()
        seen.append(self)
        return self.result()

    seen: list[TemplateDialog] = []
    monkeypatch.setattr(TemplateDialog, "exec", exec_)
    return seen


def test_rows_describe_each_template_and_mark_the_active_one(manager):
    assert rows(manager) == [
        "4 × 25 min, 5 min break  · active",
        "Short — 2 × 25 min, 5 min break",
    ]


def test_adding_a_template_appends_it(manager, config, monkeypatch):
    fill_and_submit(monkeypatch, name="Deep work", rounds=6, work=50)

    manager.add_button.click()

    assert config.pomodoro.templates[-1] == SessionTemplate(
        name="Deep work", work_minutes=50, rounds=6
    )
    assert rows(manager)[-1] == "Deep work — 6 × 50 min, 5 min break"
    assert config.pomodoro.active_template == 0  # adding doesn't switch to it


def test_double_click_edits_that_template_in_place(manager, config, monkeypatch):
    seen = fill_and_submit(monkeypatch, rounds=3)

    manager.list.row_activated.emit(1)

    assert seen[0].windowTitle() == "Edit template"
    assert seen[0].name_edit.text() == "Short"  # seeded from the template being edited
    assert config.pomodoro.templates[1] == SessionTemplate(name="Short", rounds=3)
    assert len(config.pomodoro.templates) == 2


def test_a_duplicate_label_is_refused_and_the_form_stays_open(manager, config, monkeypatch):
    seen = fill_and_submit(monkeypatch, name="Short")

    manager.add_button.click()

    assert seen[0].result() != QDialog.DialogCode.Accepted
    assert "already a template called 'Short'" in seen[0]._error.text()
    assert len(config.pomodoro.templates) == 2


def test_editing_a_template_may_keep_its_own_label(manager, config, monkeypatch):
    """Only *other* templates count as a clash."""
    fill_and_submit(monkeypatch, work=30)

    manager.list.row_activated.emit(1)

    assert config.pomodoro.templates[1].work_minutes == 30


def confirm_delete(monkeypatch, answer: QDialog.DialogCode) -> None:
    monkeypatch.setattr(TemplateDeleteConfirmDialog, "exec", lambda self: answer)


def test_deleting_the_active_template_falls_back_to_the_first(manager, config, monkeypatch):
    config.pomodoro = PomodoroConfig(
        templates=[SessionTemplate(rounds=4), SessionTemplate(rounds=2)], active_template=1
    )
    confirm_delete(monkeypatch, QDialog.DialogCode.Accepted)

    manager._delete(1)

    assert [t.rounds for t in config.pomodoro.templates] == [4]
    assert config.pomodoro.active_template == 0


def test_deleting_one_above_the_active_keeps_the_same_one_active(manager, config, monkeypatch):
    config.pomodoro = PomodoroConfig(
        templates=[SessionTemplate(rounds=4), SessionTemplate(rounds=2)], active_template=1
    )
    confirm_delete(monkeypatch, QDialog.DialogCode.Accepted)

    manager._delete(0)

    assert config.pomodoro.active().rounds == 2


def test_backing_out_of_the_delete_changes_nothing(manager, config, monkeypatch):
    before = config.pomodoro
    confirm_delete(monkeypatch, QDialog.DialogCode.Rejected)

    manager._delete(0)

    assert config.pomodoro is before


def test_describe_leaves_the_active_marker_off_when_asked():
    assert describe_template(SessionTemplate(), active=False) == "4 × 25 min, 5 min break"


# --- switching on the timer -------------------------------------------------
@pytest.fixture
def app(qtbot, tmp_path):
    from habito.app import _build_engine_and_store
    from habito.ui.app import HabitoApp

    config = Config.model_validate(
        {
            "paths": {"data_repo": str(tmp_path)},
            "project_root": tmp_path,
            "pomodoro": {
                "templates": [{"rounds": 4}, {"name": "Short", "rounds": 2, "work_minutes": 15}]
            },
        }
    )
    engine, store = _build_engine_and_store(config, test_mode=False)
    window = HabitoApp(config, engine, store, test_mode=True)
    qtbot.addWidget(window)
    return window


def test_switching_moves_on_to_the_next_template_and_wraps(app):
    app.on_next_template()
    assert app._config.pomodoro.active().name == "Short"
    assert app._view._template_btn.text() == "Short"
    assert app._view._spin.value() == 15 * 60
    assert app._engine.snapshot().total_rounds == 2  # the engine runs the new one

    app.on_next_template()
    assert app._config.pomodoro.active_template == 0


def test_switching_is_refused_mid_session(app):
    app.on_start()
    assert app._engine.state is State.work

    app.on_next_template()

    assert app._config.pomodoro.active_template == 0


def test_the_duration_field_edits_the_active_template(app):
    app.on_next_template()

    app.on_set_work_minutes(20)

    assert app._config.pomodoro.templates[1].work_minutes == 20
    assert app._config.pomodoro.templates[0].work_minutes == 25


def test_an_unnamed_templates_label_follows_its_work_length(app):
    app.on_set_work_minutes(30)
    assert app._view._template_btn.text() == "4 × 30 · 5"
