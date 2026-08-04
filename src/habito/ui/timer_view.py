"""The main timer screen (a CustomTkinter frame).

Purely presentational: it renders an :class:`EngineState` snapshot and forwards input to
the controller. It never talks to storage or git directly.

The big time doubles as the work-length control. While idle it is an editable field (type
a value, or nudge it with the −/+ stepper) that sets the next session's work length; once
running it locks to the live countdown and the stepper adjusts the round live.
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
_CUSTOM = "Custom…"

# Media-transport glyphs for the control buttons.
_PLAY = "▶"  # start / resume
_PAUSE = "⏸"  # pause (primary button toggles to this while running)
_STOP = "⏹"  # end session


def _fmt_step(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else f"{value:g}"


def _parse_minutes(text: str) -> int | None:
    """Parse ``"30"`` or ``"30:00"`` / ``"29:40"`` into whole minutes (rounded)."""
    text = text.strip()
    if not text:
        return None
    try:
        if ":" in text:
            mm, _, ss = text.partition(":")
            total = int(mm) * 60 + (int(ss) if ss else 0)
            return round(total / 60)
        return round(float(text))
    except ValueError:
        return None


class Controller(Protocol):
    def on_start(self) -> None: ...
    def on_pause_resume(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_add_time(self, minutes: float) -> None: ...
    def on_set_work_minutes(self, minutes: int) -> str | None: ...


class TimerView(ctk.CTkFrame):
    def __init__(
        self,
        master,
        controller: Controller,
        quick_add_minutes: list[int],
        work_minutes: int,
    ) -> None:
        super().__init__(master, fg_color="transparent")
        self._c = controller
        self._quick = quick_add_minutes or [1]
        self._is_idle = True
        self._showing_entry: bool | None = None
        self._planned_minutes = int(work_minutes)
        self._step = float(self._quick[0])
        self._build()

    # --- layout ----------------------------------------------------------
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)

        self._round_lbl = ctk.CTkLabel(self, text="Round – / –", font=ctk.CTkFont(size=14))
        self._round_lbl.grid(row=0, column=0, pady=(18, 0))

        self._state_lbl = ctk.CTkLabel(self, text="Ready", font=ctk.CTkFont(size=15, weight="bold"))
        self._state_lbl.grid(row=1, column=0, pady=(2, 0))

        big = ctk.CTkFont(size=56, weight="bold")
        self._time_lbl = ctk.CTkLabel(self, text="00:00", font=big)
        self._time_entry = ctk.CTkEntry(
            self, font=big, width=176, height=72, justify="center", border_width=2
        )
        self._time_entry.bind("<Return>", lambda _e: (self._commit_planned(), self.focus_set()))
        self._time_entry.bind("<FocusOut>", lambda _e: self._commit_planned())

        self._hint_lbl = ctk.CTkLabel(
            self, text="click to edit · or use −/+", font=ctk.CTkFont(size=10), text_color="gray50"
        )
        self._hint_lbl.grid(row=3, column=0, pady=(2, 4))

        self._progress = ctk.CTkProgressBar(self, width=280)
        self._progress.set(0)
        self._progress.grid(row=4, column=0, pady=(4, 14), padx=24, sticky="ew")

        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.grid(row=5, column=0, pady=(0, 8))
        sym = ctk.CTkFont(size=20)
        self._primary_btn = ctk.CTkButton(
            controls, text=_PLAY, width=76, height=40, font=sym, command=self._primary
        )
        self._primary_btn.grid(row=0, column=0, padx=4)
        self._stop_btn = ctk.CTkButton(
            controls, text=_STOP, width=58, height=40, font=sym, fg_color="gray30",
            command=self._c.on_stop,
        )
        self._stop_btn.grid(row=0, column=1, padx=4)

        # Stepper: Adjust:  [ − ]  [ step ▾ ]  [ + ]  min
        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.grid(row=6, column=0, pady=(6, 0))
        ctk.CTkLabel(add_row, text="Adjust:").grid(row=0, column=0, padx=(0, 8))
        self._minus_btn = ctk.CTkButton(
            add_row, text="−", width=38, fg_color="gray30", command=self._nudge_down
        )
        self._minus_btn.grid(row=0, column=1, padx=3)
        self._step_menu = ctk.CTkOptionMenu(
            add_row,
            width=86,
            values=[_fmt_step(m) for m in self._quick] + [_CUSTOM],
            command=self._on_step_change,
        )
        self._step_menu.set(_fmt_step(self._step))
        self._step_menu.grid(row=0, column=2, padx=3)
        self._plus_btn = ctk.CTkButton(
            add_row, text="+", width=38, fg_color="gray30", command=self._nudge_up
        )
        self._plus_btn.grid(row=0, column=3, padx=3)
        ctk.CTkLabel(add_row, text="min").grid(row=0, column=4, padx=(6, 0))

        self._today_lbl = ctk.CTkLabel(self, text="Today: 0m", font=ctk.CTkFont(size=13))
        self._today_lbl.grid(row=7, column=0, pady=(16, 2))

        self._status_lbl = ctk.CTkLabel(
            self, text="status: –", font=ctk.CTkFont(size=11), text_color="gray60"
        )
        self._status_lbl.grid(row=8, column=0, pady=(2, 12))

        # Start in idle mode so the editable field is visible before the first render tick.
        self._time_entry.grid(row=2, column=0, pady=(4, 0))
        self._refresh_entry()
        self._showing_entry = True

    # --- work-length editing (idle) --------------------------------------
    def _refresh_entry(self) -> None:
        self._time_entry.delete(0, "end")
        self._time_entry.insert(0, format_timer(self._planned_minutes * 60))

    def _set_planned(self, minutes: int) -> None:
        self._planned_minutes = max(1, minutes)
        self._refresh_entry()
        self._c.on_set_work_minutes(self._planned_minutes)

    def _commit_planned(self) -> None:
        minutes = _parse_minutes(self._time_entry.get())
        if minutes is not None and minutes >= 1:
            self._set_planned(minutes)
        else:
            self._refresh_entry()  # ignore invalid input, snap back

    # --- button glue -----------------------------------------------------
    def _primary(self) -> None:
        if self._is_idle:
            self._commit_planned()
            self._c.on_start()
        else:
            self._c.on_pause_resume()

    def _on_step_change(self, choice: str) -> None:
        if choice == _CUSTOM:
            self._prompt_custom_step()
            return
        self._step = float(choice)

    def _prompt_custom_step(self) -> None:
        dialog = ctk.CTkInputDialog(text="Step size in minutes:", title="Custom step")
        raw = dialog.get_input()
        value: float | None = None
        if raw:
            try:
                value = float(raw)
            except ValueError:
                value = None
        if value is not None and value > 0:
            self._step = value
        self._step_menu.set(_fmt_step(self._step))  # never leave "Custom…" showing

    def _nudge_up(self) -> None:
        self._nudge(self._step)

    def _nudge_down(self) -> None:
        self._nudge(-self._step)

    def _nudge(self, delta: float) -> None:
        if self._is_idle:
            self._set_planned(int(round(self._planned_minutes + delta)))
        else:
            self._c.on_add_time(delta)

    # --- rendering -------------------------------------------------------
    def render(self, snap: EngineState, today_seconds: int) -> None:
        self._is_idle = snap.state in (State.idle, State.done)

        self._round_lbl.configure(text=f"Round {snap.round_index} / {snap.total_rounds}")
        self._state_lbl.configure(
            text=_STATE_LABEL[snap.state], text_color=_ACCENT.get(snap.state, "gray70")
        )
        self._render_time(snap)

        running = snap.state in (State.work, State.break_)
        self._primary_btn.configure(text=_PAUSE if running else _PLAY)

        active = snap.state in (State.work, State.break_, State.paused)
        self._stop_btn.configure(state="normal" if active else "disabled")

        self._today_lbl.configure(text=f"Today: {format_duration(today_seconds)}")

    def _render_time(self, snap: EngineState) -> None:
        if self._is_idle:
            if self._showing_entry is not True:
                self._time_lbl.grid_remove()
                self._time_entry.grid(row=2, column=0, pady=(4, 0))
                self._hint_lbl.grid()
                self._refresh_entry()  # safe: just switched in, user isn't typing yet
                self._showing_entry = True
            self._progress.set(0)
        else:
            if self._showing_entry is not False:
                self._time_entry.grid_remove()
                self._hint_lbl.grid_remove()
                self._time_lbl.grid(row=2, column=0, pady=(4, 6))
                self._showing_entry = False
            self._time_lbl.configure(text=format_timer(snap.remaining_seconds))
            target = snap.phase_target_seconds or 1
            self._progress.set(max(0.0, min(1.0, (target - snap.remaining_seconds) / target)))
            self._progress.configure(progress_color=_ACCENT.get(snap.state, "#3b8ed0"))

    def set_status(self, text: str, color: str = "gray60") -> None:
        self._status_lbl.configure(text=text, text_color=color)
