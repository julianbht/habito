"""button_row: the one shape every dialog's bottom row takes.

Tested here rather than at each dialog, per the "a shared thing is tested once, where it
lives" rule — a dialog's own test asserts which buttons it has, not where they land.

The last test walks every dialog in the app, and is the deliberate exception: "the primary
is rightmost" is only a property of the app if nothing quietly lays out its own row. That
is the thing that would regress, and no per-dialog assertion would catch it.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pytest
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLayout, QWidget, QWidgetItem

from habito.actions.backfill import build_backfill_events
from habito.actions.tagging import build_tag_created_event, build_tag_described_event
from habito.actions.wakeup import build_wakeup_event
from habito.config.models import PomodoroConfig
from habito.projections.resume import ResumableSession, ResumePhase
from habito.projections.sessions import summarize_sessions
from habito.ui.dialogs.backfill_dialog import BackfillDialog
from habito.ui.dialogs.catalog_edit_dialog import CatalogEditDialog
from habito.ui.dialogs.entry_manager_dialog import EntryManagerDialog
from habito.ui.dialogs.manage_sessions_dialog import ManageSessionsDialog, SessionsSnapshot
from habito.ui.dialogs.resume_dialog import ResumePromptDialog
from habito.ui.dialogs.retract_confirm_dialog import RetractConfirmDialog
from habito.ui.dialogs.session_tag_dialog import SessionTagDialog
from habito.ui.dialogs.settings_dialog import SettingsDialog
from habito.ui.dialogs.shortcuts_dialog import ShortcutsDialog
from habito.ui.dialogs.void_confirm_dialog import VoidConfirmDialog
from habito.ui.dialogs.wakeup_dialog import WakeUpDialog
from habito.ui.dialogs.workout_log_dialog import WorkoutLogDialog
from habito.ui.widgets.controls import Button, button, button_row, primary_button

CEST = timezone(timedelta(hours=2))
NOW = datetime(2026, 8, 7, 14, 23, tzinfo=CEST)


def contents(row: QHBoxLayout) -> list[str]:
    """The row read left to right, with the stretch marked."""
    out: list[str] = []
    for i in range(row.count()):
        item = row.itemAt(i)
        widget = item.widget() if isinstance(item, QWidgetItem) else None
        out.append(widget.text() if isinstance(widget, Button) else "<stretch>")
    return out


@pytest.fixture
def host(qtbot):
    """Something for the row to belong to — `button_row` needs a parent to fix tab order."""
    widget = QDialog()
    qtbot.addWidget(widget)
    return widget


def test_the_primary_is_rightmost(host):
    row = button_row(host, primary=primary_button("Save"), dismiss=button("Cancel"))

    assert contents(row) == ["<stretch>", "Cancel", "Save"]


def test_auxiliary_buttons_sit_left_of_the_stretch(host):
    """Separated from the pair that ends the dialog, so a side trip doesn't read as a way
    to finish."""
    row = button_row(
        host,
        primary=primary_button("Log && commit"),
        dismiss=button("Cancel"),
        auxiliary=(button("+ New workout"),),
    )

    assert contents(row) == ["+ New workout", "<stretch>", "Cancel", "Log && commit"]


def test_a_row_can_be_dismiss_only(host):
    assert contents(button_row(host, dismiss=button("Close"))) == ["<stretch>", "Close"]


def test_a_row_can_be_primary_only(host):
    assert contents(button_row(host, primary=primary_button("Save"))) == ["<stretch>", "Save"]


def test_tab_order_follows_the_row_left_to_right(qtbot, host):
    """Qt derives tab order from *construction* order, which has nothing to do with where a
    button ends up — so the helper sets it, and a row built in any order still tabs the way
    it reads."""
    primary = primary_button("Save")  # constructed first, laid out last
    dismiss = button("Cancel")
    aux = button("+ New tag")
    host.setLayout(button_row(host, primary=primary, dismiss=dismiss, auxiliary=(aux,)))
    host.show()
    qtbot.waitExposed(host)

    aux.setFocus()
    seen = []
    for _ in range(2):
        host.focusNextChild()
        seen.append(host.focusWidget().text())

    assert seen == ["Cancel", "Save"]


# --- the rule, across every dialog in the app -------------------------------
def _session():
    events = build_backfill_events(
        datetime(2026, 8, 4, 6, 0, tzinfo=CEST),
        work_minutes=50,
        break_minutes=10,
        rounds=1,
        habit="study",
    )
    return summarize_sessions(events)[0]


def _wakeup():
    return build_wakeup_event(
        datetime(2026, 8, 4, 7, 30, tzinfo=CEST),
        datetime(2026, 8, 3, 23, 15, tzinfo=CEST),
        habit="sleep",
    )


class _StubSettingsController:
    """The two methods SettingsDialog's Controller protocol needs; it is built here only
    to be looked at, never driven — test_ui_settings_dialog.py exercises it properly."""

    def on_save_settings(self, values) -> str | None:
        return None

    def on_preview_sound(self, sound: str) -> None:
        pass


def _tag_created(name: str):
    return build_tag_created_event(name, habit="study", now=NOW)


def _tag_described(name: str, description: str):
    return build_tag_described_event(name, description, habit="study", now=NOW)


def _dialog_factories():
    """One factory per dialog, with the least scaffolding that makes it real.

    Factories, not dialogs: parametrizing over constructed widgets would build them at
    collection time, before a QApplication exists, which aborts Qt outright.
    """
    noop = lambda *args, **kwargs: None  # noqa: E731
    return {
        "BackfillDialog": lambda: BackfillDialog(
            on_submit=noop,
            default_work=25,
            default_break=5,
            default_rounds=4,
            habit="study",
            today=date(2026, 8, 17),
        ),
        "CatalogEditDialog": lambda: CatalogEditDialog(
            "tag",
            "topology",
            "",
            noop,
            lambda name: _tag_created(name),
            lambda name, description: _tag_described(name, description),
        ),
        "EntryManagerDialog": lambda: EntryManagerDialog(
            title="Sleep",
            hint="h",
            empty_text="none",
            add_text="Log wake-up…",
            reload=list,
            open_form=noop,
            on_submit=noop,
            rollover_hour=3,
            now=lambda: NOW,
        ),
        "ManageSessionsDialog": lambda: ManageSessionsDialog(
            reload=lambda: SessionsSnapshot((), {}, [], {}),
            on_submit=noop,
            habit="study",
            now=lambda: NOW,
            open_backfill=noop,
        ),
        "ResumePromptDialog": lambda: ResumePromptDialog(
            ResumableSession(
                session_id=_session().session_id,
                round_index=2,
                planned_rounds=4,
                phase=ResumePhase.work,
                remaining_seconds=600,
                interrupted_at=NOW,
            )
        ),
        "RetractConfirmDialog": lambda: RetractConfirmDialog(_session(), noop, "study", NOW),
        "SessionTagDialog": lambda: SessionTagDialog(
            _session().session_id, set(), ["topology"], {}, noop, "study", NOW
        ),
        "SettingsDialog": lambda: SettingsDialog(
            controller=_StubSettingsController(), pomodoro=PomodoroConfig()
        ),
        "ShortcutsDialog": ShortcutsDialog,
        "VoidConfirmDialog": lambda: VoidConfirmDialog(_wakeup(), "a wake-up", noop, 3, NOW),
        "WakeUpDialog": lambda: WakeUpDialog(
            on_submit=noop,
            default_wake_time=time(7, 0),
            default_bedtime=time(23, 0),
            habit="sleep",
            today=date(2026, 8, 17),
        ),
        "WorkoutLogDialog": lambda: WorkoutLogDialog(
            on_submit=noop,
            on_describe_workout=noop,
            known_workouts=["running"],
            descriptions={},
            habit="workout",
            now=NOW,
            today=date(2026, 8, 17),
        ),
    }


def _row_containing(layout: QLayout, widget: QWidget) -> QHBoxLayout | None:
    """The horizontal row `widget` sits directly in, anywhere under `layout`."""
    for i in range(layout.count()):
        item = layout.itemAt(i)
        if item is None:
            continue
        if isinstance(item, QWidgetItem) and item.widget() is widget:
            return layout if isinstance(layout, QHBoxLayout) else None
        child = item.layout()
        if child is not None:
            found = _row_containing(child, widget)
            if found is not None:
                return found
    return None


@pytest.mark.parametrize("name", sorted(_dialog_factories()))
def test_every_dialogs_accent_button_ends_its_row(qtbot, name):
    dialog = _dialog_factories()[name]()
    qtbot.addWidget(dialog)

    accented = [b for b in dialog.findChildren(Button) if b.objectName() == "primary"]
    if not accented:
        pytest.skip(f"{name} has no accent button")
    primary = accented[0]
    root = dialog.layout()
    assert root is not None
    row = _row_containing(root, primary)

    assert row is not None, f"{name}: its primary is not in a horizontal button row"
    assert contents(row)[-1] == primary.text(), f"{name}: {contents(row)}"
