"""Dialog to retroactively add a study session you did away from the app.

Produces backfilled events (``origin=backfilled``) via :func:`habito.backfill.build_backfill_events`
and hands them to the ``on_submit`` callback, which appends them to the store (each is then
committed+pushed, tagged ``[backfilled]``).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import customtkinter as ctk

from habito.backfill import build_backfill_events
from habito.domain.events import Event

SubmitCallback = Callable[[list[Event]], None]


class BackfillDialog(ctk.CTkToplevel):
    def __init__(
        self,
        master,
        on_submit: SubmitCallback,
        default_work: int,
        default_break: int,
        default_rounds: int,
        today_str: str,
    ) -> None:
        super().__init__(master)
        self._on_submit = on_submit
        self.title("Add past session")
        self.geometry("320x300")
        self.resizable(False, False)
        self.grab_set()  # modal

        self.grid_columnconfigure(1, weight=1)
        self._entries: dict[str, ctk.CTkEntry] = {}
        rows = [
            ("date", "Date (YYYY-MM-DD)", today_str),
            ("time", "Start time (HH:MM)", "06:00"),
            ("work", "Work minutes", str(default_work)),
            ("break", "Break minutes", str(default_break)),
            ("rounds", "Rounds", str(default_rounds)),
        ]
        for i, (key, label, default) in enumerate(rows):
            ctk.CTkLabel(self, text=label).grid(row=i, column=0, sticky="w", padx=12, pady=6)
            entry = ctk.CTkEntry(self, width=120)
            entry.insert(0, default)
            entry.grid(row=i, column=1, sticky="e", padx=12, pady=6)
            self._entries[key] = entry

        self._error = ctk.CTkLabel(self, text="", text_color="#d9534f", wraplength=280)
        self._error.grid(row=len(rows), column=0, columnspan=2, padx=12)

        ctk.CTkButton(self, text="Add & commit", command=self._submit).grid(
            row=len(rows) + 1, column=0, columnspan=2, pady=12
        )

    def _submit(self) -> None:
        try:
            start = self._parse_start()
            work = int(self._entries["work"].get())
            brk = int(self._entries["break"].get())
            rounds = int(self._entries["rounds"].get())
            events = build_backfill_events(start, work, brk, rounds)
        except ValueError as exc:
            self._error.configure(text=str(exc))
            return
        self._on_submit(events)
        self.destroy()

    def _parse_start(self) -> datetime:
        date_raw = self._entries["date"].get().strip()
        time_raw = self._entries["time"].get().strip()
        try:
            naive = datetime.strptime(f"{date_raw} {time_raw}", "%Y-%m-%d %H:%M")
        except ValueError as exc:
            raise ValueError("Use date YYYY-MM-DD and time HH:MM") from exc
        # Attach the system local timezone so the offset is recorded correctly.
        return naive.astimezone()
