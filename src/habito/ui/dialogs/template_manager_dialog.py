"""Manage session templates — the ☰ "Templates" entry.

The same three parts as every other manager (see `EntryManagerDialog`): the shared
`EntryList`, a primary button that opens the form (`TemplateDialog`), and a row menu —
double-click edits, right-click offers Edit… and Delete….

Its own class rather than another `EntryManagerDialog`, because what it manages is config,
not the log: an edit replaces the template in place instead of voiding and re-appending,
and a delete is gone rather than struck through. The part that is genuinely the same — the
list — is shared.

Every change goes out as the whole new list plus which one is active, so the rules about
the list as a whole are checked in one place (`ConfigEditor.apply_templates`), and the
manager re-reads the config afterwards rather than trusting its own copy.

Two templates with the same label are refused here, in the form, rather than by the config:
the timer only shows a label, so a second one reading the same would be indistinguishable —
but the config can't refuse it without also refusing the timer's work-length field on its
way *past* another template's value (stepping 25 → 30 while "4 × 30 · 5" exists).
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QDialog, QMenu, QVBoxLayout, QWidget

from habito.config.models import PomodoroConfig, SessionTemplate
from habito.ui.dialogs.template_delete_confirm_dialog import TemplateDeleteConfirmDialog
from habito.ui.dialogs.template_dialog import TemplateDialog
from habito.ui.svg_icons import icon
from habito.ui.widgets.controls import (
    BROWSE_DIALOG_HEIGHT,
    BROWSE_DIALOG_WIDTH,
    button,
    button_row,
    primary_button,
)
from habito.ui.widgets.entry_list import EntryList

ApplyCallback = Callable[[list[SessionTemplate], int], str | None]
"""The new template list and the active index; ``None`` when accepted, else why not."""


def describe_template(template: SessionTemplate, active: bool) -> str:
    details = (
        f"{template.rounds} × {template.work_minutes:g} min, {template.break_minutes} min break"
    )
    text = f"{template.name} — {details}" if template.name else details
    return f"{text}  · active" if active else text


class TemplateManagerDialog(QDialog):
    def __init__(
        self,
        *,
        reload: Callable[[], PomodoroConfig],
        on_apply: ApplyCallback,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._reload = reload
        self._on_apply = on_apply
        self._config = reload()
        self.setWindowTitle("Templates")
        self.setMinimumWidth(BROWSE_DIALOG_WIDTH)
        self.setMinimumHeight(BROWSE_DIALOG_HEIGHT)
        self.setModal(True)
        self._build()
        self._refresh()

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(10)

        self.list = EntryList(
            "Double-click a template to edit it, or right-click to delete it. "
            "Click the template name on the timer to switch.",
            empty_text="",  # never empty: the config always holds at least one
        )
        self.list.row_menu_requested.connect(self._on_row_menu)
        self.list.row_activated.connect(self._edit)
        root.addWidget(self.list, 1)

        close_btn = button("Close")
        close_btn.clicked.connect(self.accept)
        self.add_button = primary_button("New template")
        self.add_button.clicked.connect(self._add)
        root.addLayout(button_row(self, primary=self.add_button, dismiss=close_btn))

    def _refresh(self) -> None:
        self._config = self._reload()
        active = self._config.active_template
        self.list.set_rows(
            [describe_template(t, i == active) for i, t in enumerate(self._config.templates)]
        )

    def _apply(self, templates: list[SessionTemplate], active: int) -> str | None:
        error = self._on_apply(templates, active)
        self._refresh()
        return error

    def _submit(self, template: SessionTemplate, row: int | None) -> str | None:
        """Add ``template`` (``row`` is ``None``) or put it in place of the one at ``row``."""
        others = [t for i, t in enumerate(self._config.templates) if i != row]
        if any(t.label() == template.label() for t in others):
            return f"There's already a template called {template.label()!r}."
        templates = list(self._config.templates)
        if row is None:
            templates.append(template)
        else:
            templates[row] = template
        return self._apply(templates, self._config.active_template)

    def _add(self) -> None:
        TemplateDialog(on_submit=lambda t: self._submit(t, None), parent=self).exec()

    def _edit(self, row: int) -> None:
        if not 0 <= row < len(self._config.templates):
            return

        TemplateDialog(
            on_submit=lambda t: self._submit(t, row),
            replacing=self._config.templates[row],
            parent=self,
        ).exec()

    def _on_row_menu(self, row: int, pos: QPoint) -> None:
        if not 0 <= row < len(self._config.templates):
            return
        menu = QMenu(self)
        menu.addAction("Edit…", lambda: self._edit(row))
        delete = menu.addAction(icon("delete"), "Delete…", lambda: self._delete(row))
        # There is always a template to run, so the last one can't go.
        delete.setEnabled(len(self._config.templates) > 1)
        menu.exec(pos)

    def _delete(self, row: int) -> None:
        templates = list(self._config.templates)
        summary = describe_template(templates[row], active=False)
        if TemplateDeleteConfirmDialog(summary, parent=self).exec() != QDialog.DialogCode.Accepted:
            return
        del templates[row]
        active = self._config.active_template
        # Deleting the active one falls back to the first; deleting one above it shifts it.
        if row == active:
            active = 0
        elif row < active:
            active -= 1
        self._apply(templates, active)
