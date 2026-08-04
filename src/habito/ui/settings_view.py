"""The Settings tab: edit the Pomodoro format and add past sessions.

Kept off the main timer tab so the timer stays uncluttered. Saving validates through the
controller (which persists to settings.toml and applies to the engine) and reports back a
short confirmation or error.
"""

from __future__ import annotations

from typing import Protocol

import customtkinter as ctk

from habito.config.models import PomodoroConfig


class Controller(Protocol):
    def on_save_settings(self, work: int, brk: int, rounds: int) -> str | None: ...
    def on_open_backfill(self) -> None: ...


class SettingsView(ctk.CTkFrame):
    def __init__(self, master, controller: Controller, pomodoro: PomodoroConfig) -> None:
        super().__init__(master, fg_color="transparent")
        self._c = controller
        self.grid_columnconfigure(0, weight=1)
        self._build(pomodoro)

    def _build(self, pomodoro: PomodoroConfig) -> None:
        ctk.CTkLabel(
            self, text="Pomodoro format", font=ctk.CTkFont(size=15, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=20, pady=(18, 8))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.grid(row=1, column=0, sticky="ew", padx=20)
        form.grid_columnconfigure(0, weight=1)

        self._entries: dict[str, ctk.CTkEntry] = {}
        for i, (key, label, value) in enumerate(
            [
                ("work", "Work minutes", pomodoro.work_minutes),
                ("break", "Break minutes", pomodoro.break_minutes),
                ("rounds", "Rounds", pomodoro.rounds),
            ]
        ):
            ctk.CTkLabel(form, text=label).grid(row=i, column=0, sticky="w", pady=6)
            entry = ctk.CTkEntry(form, width=70, justify="center")
            entry.insert(0, str(value))
            entry.grid(row=i, column=1, sticky="e", pady=6)
            self._entries[key] = entry

        ctk.CTkButton(self, text="Save", width=120, command=self._save).grid(
            row=2, column=0, pady=(14, 4)
        )
        self._status = ctk.CTkLabel(self, text="", font=ctk.CTkFont(size=12))
        self._status.grid(row=3, column=0, pady=(0, 8))

        ctk.CTkFrame(self, height=1, fg_color="gray30").grid(
            row=4, column=0, sticky="ew", padx=20, pady=10
        )

        ctk.CTkLabel(
            self, text="Missed a session?", font=ctk.CTkFont(size=13)
        ).grid(row=5, column=0, pady=(0, 6))
        ctk.CTkButton(
            self, text="Add past session", width=160, command=self._c.on_open_backfill
        ).grid(row=6, column=0)

    def _save(self) -> None:
        try:
            work = int(self._entries["work"].get())
            brk = int(self._entries["break"].get())
            rounds = int(self._entries["rounds"].get())
        except ValueError:
            self._status.configure(text="Values must be whole numbers.", text_color="#d9534f")
            return

        error = self._c.on_save_settings(work, brk, rounds)
        if error:
            self._status.configure(text=error, text_color="#d9534f")
        else:
            self._status.configure(
                text="Saved ✓ — applies to your next session", text_color="#2fa572"
            )
