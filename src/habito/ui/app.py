"""The application window — also the small controller the views call into.

Owns the tick loop that drives the engine and repaints the view. Evidence status
arrives from the worker thread via a queue and is drained here on the UI thread (the
safe cross-thread pattern for Tkinter).
"""

from __future__ import annotations

import queue
from datetime import date

import customtkinter as ctk

from habito.config.models import Config
from habito.engine.pomodoro import PomodoroEngine, State
from habito.evidence.worker import EvidenceStatus, EvidenceWorker
from habito.projections.daily import summary_for
from habito.storage.event_store import EventStore
from habito.ui.backfill_view import BackfillDialog
from habito.ui.timer_view import TimerView

_TICK_MS = 250


class HabitoApp(ctk.CTk):
    def __init__(self, config: Config, engine: PomodoroEngine, store: EventStore) -> None:
        super().__init__()
        self._config = config
        self._engine = engine
        self._store = store
        self._worker: EvidenceWorker | None = None
        self._status_queue: queue.Queue[EvidenceStatus] = queue.Queue()
        self._evidence_enabled = False

        self.title("Habito")
        self.geometry("360x470")
        self.minsize(340, 460)
        if config.ui.always_on_top:
            self.attributes("-topmost", True)

        self._view = TimerView(self, controller=self, quick_add_minutes=config.pomodoro.quick_add_minutes)
        self._view.pack(fill="both", expand=True)

        self._today_baseline = self._compute_today_baseline()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(_TICK_MS, self._tick)

    # --- wiring from the composition root --------------------------------
    def attach_worker(self, worker: EvidenceWorker) -> None:
        self._worker = worker
        self._evidence_enabled = True

    def on_evidence_status(self, status: EvidenceStatus) -> None:
        """Called from the worker thread; just hand off to the UI thread via the queue."""
        self._status_queue.put(status)

    def set_evidence_mode(self, text: str, color: str = "gray60") -> None:
        self._view.set_evidence(text, color)

    # --- controller callbacks (from the view) ----------------------------
    def on_start(self) -> None:
        self._today_baseline = self._compute_today_baseline()
        self._engine.start()

    def on_pause_resume(self) -> None:
        if self._engine.state is State.paused:
            self._engine.resume()
        else:
            self._engine.pause()

    def on_skip(self) -> None:
        self._engine.skip()

    def on_stop(self) -> None:
        self._engine.stop()

    def on_add_time(self, minutes: float) -> None:
        self._engine.add_time(minutes)

    def on_open_backfill(self) -> None:
        BackfillDialog(
            self,
            on_submit=self._apply_backfill,
            default_work=self._config.pomodoro.work_minutes,
            default_break=self._config.pomodoro.break_minutes,
            default_rounds=self._config.pomodoro.rounds,
            today_str=date.today().isoformat(),
        )

    # --- internals -------------------------------------------------------
    def _apply_backfill(self, events) -> None:
        for event in events:
            self._store.append(event)
        self._today_baseline = self._compute_today_baseline()

    def _compute_today_baseline(self) -> int:
        summary = summary_for(self._store.read_all(), date.today())
        return summary.total_work_seconds

    def _tick(self) -> None:
        self._engine.tick()
        self._drain_status()
        snap = self._engine.snapshot()
        self._view.render(snap, self._today_baseline + snap.session_work_seconds)
        self.after(_TICK_MS, self._tick)

    def _drain_status(self) -> None:
        if not self._evidence_enabled:
            return
        latest: EvidenceStatus | None = None
        try:
            while True:
                latest = self._status_queue.get_nowait()
        except queue.Empty:
            pass
        if latest is not None:
            self._render_status(latest)

    def _render_status(self, status: EvidenceStatus) -> None:
        if status.error:
            self._view.set_evidence("evidence: ⚠ push deferred", "#d9863b")
        elif status.unpushed_count > 0:
            self._view.set_evidence(f"evidence: {status.unpushed_count} unpushed", "#d9863b")
        elif status.pushed:
            self._view.set_evidence("evidence: pushed ✓", "#2fa572")
        elif status.committed:
            self._view.set_evidence("evidence: committed", "gray70")

    def _on_close(self) -> None:
        if self._worker is not None:
            self._worker.stop()
        self.destroy()

    def run(self) -> None:
        self.mainloop()
