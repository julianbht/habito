"""The WorkoutLogDialog's own choices: defaults, the embedded picker, and what
gets built on submit — the workout extra's mirror of test_ui_wakeup_dialog.py, plus
coverage for the multi-select picker WakeUpDialog doesn't have.

What a `Stepper` does is proved once in test_widgets.py; the timezone-localizing behaviour
this dialog shares with Backfill/WakeUp is proved once in test_timezone.py; the picker's own
mechanics (the tree, "+ New …", double-click) are proved once in test_ui_catalog_picker.py.
What's left here is this dialog's own wiring: which picker it builds, and what it does with
a Cancel/submit.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

from PySide6.QtCore import QDate, Qt, QTime
from PySide6.QtWidgets import QDialogButtonBox

from habito.actions.workout import build_workout_logged_event
from habito.config.models import TimeConfig
from habito.domain.events import Event, WorkoutCreated, WorkoutLogged
from habito.ui.dialogs.catalog_edit_dialog import CatalogEditDialog
from habito.ui.dialogs.workout_log_dialog import WorkoutLogDialog

NOW = datetime(2026, 8, 17, 18, 30, tzinfo=UTC)
CEST = timezone(timedelta(hours=2))


def dialog_for(qtbot, known_workouts=None, descriptions=None, captured=None, described=None):
    widget = WorkoutLogDialog(
        on_submit=(captured if captured is not None else []).append,
        on_describe_workout=(described if described is not None else []).append,
        known_workouts=known_workouts or [],
        descriptions=descriptions or {},
        habit="workout",
        now=NOW,
        today=date(2026, 8, 17),
    )
    qtbot.addWidget(widget)
    return widget


def row(dialog, index: int):
    item = dialog.picker.tree.topLevelItem(index)
    assert item is not None
    return item


def check(dialog, index: int) -> None:
    row(dialog, index).setCheckState(0, Qt.CheckState.Checked)


def test_the_date_defaults_from_today(qtbot):
    dialog = dialog_for(qtbot)
    qd = dialog._date.date()
    assert (qd.year(), qd.month(), qd.day()) == (2026, 8, 17)


def test_the_time_defaults_from_now_not_a_config_value(qtbot):
    """Unlike WakeUpDialog, there's no configured default — you're usually logging a
    workout you just finished, so "now" is the sensible default."""
    dialog = dialog_for(qtbot)
    assert (dialog._time.time().hour(), dialog._time.time().minute()) == (18, 30)


def test_the_date_cannot_be_set_to_the_future(qtbot):
    dialog = dialog_for(qtbot)
    assert dialog._date.maximumDate() == QDate(2026, 8, 17)


def test_the_picker_lists_every_known_workout(qtbot):
    dialog = dialog_for(qtbot, known_workouts=["running", "yoga"])

    assert row(dialog, 0).text(0) == "running"
    assert row(dialog, 1).text(0) == "yoga"
    assert dialog.picker.selected() == []


def test_submitting_with_nothing_checked_shows_an_error_and_does_not_submit(qtbot):
    captured: list[list[Event]] = []
    dialog = dialog_for(qtbot, known_workouts=["running"], captured=captured)

    dialog._submit()

    assert captured == []
    assert "at least one workout" in dialog._error.text()


def test_checking_one_workout_and_submitting_builds_a_workout_logged_event(qtbot):
    captured: list[list[Event]] = []
    dialog = dialog_for(qtbot, known_workouts=["running"], captured=captured)
    check(dialog, 0)

    dialog._submit()

    assert len(captured) == 1
    event = captured[0][0]
    assert isinstance(event, WorkoutLogged)
    assert event.workouts == ["running"]
    assert event.habit == "workout"
    assert not dialog.isVisible()


def test_checking_two_workouts_includes_both_in_one_event(qtbot):
    captured: list[list[Event]] = []
    dialog = dialog_for(qtbot, known_workouts=["running", "yoga"], captured=captured)
    check(dialog, 0)
    check(dialog, 1)

    dialog._submit()

    event = captured[0][0]
    assert isinstance(event, WorkoutLogged)
    assert set(event.workouts) == {"running", "yoga"}


def test_submitted_timestamp_reflects_the_picked_date_and_time(qtbot):
    captured: list[list[Event]] = []
    dialog = dialog_for(qtbot, known_workouts=["running"], captured=captured)
    dialog._time.setTime(QTime(7, 15))
    check(dialog, 0)

    dialog._submit()

    assert (dialog._when().hour, dialog._when().minute) == (7, 15)


def test_cancelling_submits_nothing(qtbot):
    captured: list[list[Event]] = []
    dialog = dialog_for(qtbot, known_workouts=["running"], captured=captured)
    check(dialog, 0)

    dialog.reject()

    assert captured == []


def test_creating_a_new_workout_inline_reaches_on_describe_workout(qtbot, monkeypatch):
    """The catalog write (WorkoutCreated) lands immediately through on_describe_workout,
    the same split SessionCompleteDialog makes for tags — not deferred to "Log & commit"."""

    def fake_exec(self: CatalogEditDialog) -> int:
        self._name.setText("push-ups")
        self._on_save()
        return self.result()

    monkeypatch.setattr(CatalogEditDialog, "exec", fake_exec)
    described: list[Event] = []
    dialog = dialog_for(qtbot, described=described)

    dialog.picker._on_new_item()

    assert len(described) == 1
    assert isinstance(described[0], WorkoutCreated)
    assert described[0].workout == "push-ups"
    # Not logged yet — that only happens once "Log & commit" is pressed.
    assert dialog.picker.selected() == ["push-ups"]


# --- editing an entry -----------------------------------------------------
# `replacing` only seeds the fields and renames the window; the void that makes it a
# correction is the manager's to add (see EntryManagerDialog), so what this dialog
# *writes* is the same single honest event either way.
def ok_button(dialog):
    """The dialog's primary button, out of its QDialogButtonBox."""
    box = dialog.findChild(QDialogButtonBox)
    assert box is not None
    button = box.button(QDialogButtonBox.StandardButton.Ok)
    assert button is not None
    return button


def logged_workout(workouts=("running",), hour=18):
    """A workout log on 2026-08-04, as it would come back out of the log."""
    return build_workout_logged_event(
        datetime(2026, 8, 4, hour, 0, tzinfo=CEST), list(workouts), habit="workout"
    )


def editing(qtbot, replacing, known_workouts=None, captured=None):
    widget = WorkoutLogDialog(
        on_submit=(captured if captured is not None else []).append,
        on_describe_workout=[].append,
        known_workouts=known_workouts or ["running", "yoga"],
        descriptions={},
        habit="workout",
        now=NOW,
        time_config=TimeConfig(timezone="Europe/Berlin"),
        today=date(2026, 8, 17),
        replacing=replacing,
    )
    qtbot.addWidget(widget)
    return widget


def test_editing_seeds_the_date_and_time_from_the_entry(qtbot):
    dialog = editing(qtbot, logged_workout(hour=18))

    picked = dialog._date.date()
    assert (picked.year(), picked.month(), picked.day()) == (2026, 8, 4)
    assert (dialog._time.time().hour(), dialog._time.time().minute()) == (18, 0)


def test_editing_starts_with_the_entrys_own_workouts_ticked(qtbot):
    """Unticking one is how you drop it — which is what makes "one entry, several
    workouts" correctable at all, despite the void being all-or-nothing."""
    dialog = editing(qtbot, logged_workout(workouts=("running", "yoga")))

    assert sorted(dialog.picker.selected()) == ["running", "yoga"]


def test_a_fresh_log_starts_with_nothing_ticked(qtbot):
    dialog = editing(qtbot, None)

    assert dialog.picker.selected() == []


def test_editing_renames_the_window_and_its_button(qtbot):
    dialog = editing(qtbot, logged_workout())

    assert dialog.windowTitle() == "Edit workout log"
    assert ok_button(dialog).text() == "Save && commit"


def test_logging_afresh_keeps_the_log_wording(qtbot):
    dialog = editing(qtbot, None)

    assert dialog.windowTitle() == "Log workout"
    assert ok_button(dialog).text() == "Log && commit"


def test_editing_still_submits_one_plain_workout_log(qtbot):
    captured: list[list[Event]] = []
    dialog = editing(qtbot, logged_workout(), captured=captured)

    dialog._submit()

    (batch,) = captured
    assert [type(e) for e in batch] == [WorkoutLogged]
