"""The main timer screen (a CustomTkinter frame).

Purely presentational: it renders an :class:`EngineState` snapshot and forwards button
presses to the controller. It never talks to storage or git directly.
"""

from __future__ import annotations

from typing import Protocol

import customtkinter as ctk

from habito.engine.pomodoro import EngineState, State
from habito.ui.widgets import format_duration, format_timer

_STATE_LABEL = {
    State.idle: "Ready",
    State.work: "Focus",
    State.break_: "Break",
    State.paused: "Paused",
    State.done: "Done",
}
_ACCENT = {
    State.work: "#2fa572",
    State.break_: "#3b8ed0",
    State.paused: "#b0862f",
    State.done: "#2fa572",
    State.idle: "#4a4a4a",
}


class Controller(Protocol):
    def on_start(self) -> None: ...
    def on_pause_resume(self) -> None: ...
    def on_skip(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_add_time(self, minutes: float) -> None: ...


class TimerView(ctk.CTkFrame):
    def __init__(
        self,
        master,
        controller: Controller,
        quick_add_minutes: list[int],
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._c = controller
        self._quick = quick_add_minutes
        self._is_idle = True
        self._build()

    # --- layout ----------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        self._round_lbl = ctk.CTkLabel(self, text="Round – / –", font=ctk.CTkFont(size=14))
        self._round_lbl.grid(row=0, column=0, pady=(18, 0))

        self._state_lbl = ctk.CTkLabel(
            self, text="Ready", font=ctk.CTkFont(size=15, weight="bold")
        )
        self._state_lbl.grid(row=1, column=0, pady=(2, 0))

        self._time_lbl = ctk.CTkLabel(self, text="00:00", font=ctk.CTkFont(size=64, weight="bold"))
        self._time_lbl.grid(row=2, column=0, pady=(4, 6))

        self._progress = ctk.CTkProgressBar(self, width=280)
        self._progress.set(0)
        self._progress.grid(row=3, column=0, pady=(0, 14), padx=24, sticky="ew")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=4, column=0, pady=(0, 8))
        self._primary_btn = ctk.CTkButton(controls, text="Start", width=110, command=self._primary)
        self._primary_btn.grid(row=0, column=0, padx=4)
        self._skip_btn = ctk.CTkButton(
            controls, text="Skip", width=70, fg_color="gray30", command=self._c.on_skip
        )
        self._skip_btn.grid(row=0, column=1, padx=4)
        self._stop_btn = ctk.CTkButton(
            controls, text="Stop", width=70, fg_color="gray30", command=self._c.on_stop
        )
        self._stop_btn.grid(row=0, column=2, padx=4)

        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.grid(row=5, column=0, pady=(4, 0))
        ctk.CTkLabel(add_row, text="Add:").grid(row=0, column=0, padx=(0, 6))
        self._add_btns: list[ctk.CTkButton] = []
        for i, m in enumerate(self._quick):
            b = ctk.CTkButton(
                add_row, text=f"+{m}", width=44, fg_color="gray25",
                command=lambda mm=m: self._c.on_add_time(mm),
            )
            b.grid(row=0, column=1 + i, padx=3)
            self._add_btns.append(b)
        self._custom_entry = ctk.CTkEntry(add_row, width=52, placeholder_text="min")
        self._custom_entry.grid(row=0, column=1 + len(self._quick), padx=(8, 3))
        self._custom_btn = ctk.CTkButton(
            add_row, text="+", width=30, fg_color="gray25", command=self._add_custom
        )
        self._custom_btn.grid(row=0, column=2 + len(self._quick), padx=3)

        self._today_lbl = ctk.CTkLabel(self, text="Today: 0m", font=ctk.CTkFont(size=13))
        self._today_lbl.grid(row=6, column=0, pady=(16, 2))

        self._status_lbl = ctk.CTkLabel(
            self, text="status: –", font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self._status_lbl.grid(row=7, column=0, pady=(2, 12))

    # --- button glue -----------------------------------------------------
    def _primary(self) -> None:
        self._c.on_start() if self._is_idle else self._c.on_pause_resume()

    def _add_custom(self) -> None:
        raw = self._custom_entry.get().strip()
        self._custom_entry.delete(0, "end")
        try:
            minutes = float(raw)
        except ValueError:
            return
        if minutes > 0:
            self._c.on_add_time(minutes)

    # --- rendering -------------------------------------------------------
    def render(self, snap: EngineState, today_seconds: int) -> None:
        self._is_idle = snap.state in (State.idle, State.done)

        self._round_lbl.configure(text=f"Round {snap.round_index} / {snap.total_rounds}")
        self._state_lbl.configure(
            text=_STATE_LABEL[snap.state], text_color=_ACCENT.get(snap.state, "gray70")
        )
        self._time_lbl.configure(text=format_timer(snap.remaining_seconds))

        target = snap.phase_target_seconds or 1
        elapsed = target - snap.remaining_seconds
        self._progress.set(max(0.0, min(1.0, elapsed / target)))
        self._progress.configure(progress_color=_ACCENT.get(snap.state, "#3b8ed0"))

        if snap.state in (State.idle, State.done):
            self._primary_btn.configure(text="Start")
        elif snap.state is State.paused:
            self._primary_btn.configure(text="Resume")
        else:
            self._primary_btn.configure(text="Pause")

        active = snap.state in (State.work, State.break_, State.paused)
        state_flag = "normal" if active else "disabled"
        for b in (self._skip_btn, self._stop_btn, self._custom_btn, *self._add_btns):
            b.configure(state=state_flag)

        self._today_lbl.configure(text=f"Today: {format_duration(today_seconds)}")

    def set_status(self, text: str, color: str = "gray60") -> None:
        self._status_lbl.configure(text=text, text_color=color)
