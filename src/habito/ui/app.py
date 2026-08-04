"""The application window — also the small controller the views call into.

Owns the tick loop that drives the engine and repaints the view. Evidence status arrives
from the worker thread as a Qt signal, which Qt queues onto the UI thread automatically —
the safe cross-thread pattern here, and the reason no explicit status queue is needed.
"""

from __future__ import annotations

from datetime import date

from pydantic import ValidationError
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QVBoxLayout

from habito.config.models import Config, PomodoroConfig
from habito.config.writer import save_pomodoro
from habito.engine.pomodoro import PomodoroEngine, State
from habito.evidence.worker import EvidenceStatus, EvidenceWorker
from habito.projections.daily import summary_for
from habito.storage.event_store import EventStore
from habito.ui import theme
from habito.ui.backfill_view import BackfillDialog
from habito.ui.progress_background import ProgressBackground
from habito.ui.settings_view import SettingsDialog
from habito.ui.timer_view import TimerView, progress_for
from habito.ui.widgets import button

_TICK_MS = 250


class HabitoApp(QMainWindow):
    # Emitted from the evidence worker thread; Qt delivers it on the UI thread.
    _status_arrived = Signal(object)

    def __init__(
        self,
        config: Config,
        engine: PomodoroEngine,
        store: EventStore,
        test_mode: bool = False,
    ) -> None:
        super().__init__()
        self._config = config
        self._engine = engine
        self._store = store
        self._test_mode = test_mode
        self._theme = theme.Theme.resolve(config.ui.theme, test_mode)
        self._worker: EvidenceWorker | None = None
        self._settings_dialog: SettingsDialog | None = None

        self.setWindowTitle("Habito — TEST MODE" if test_mode else "Habito")
        self.resize(380, 500)
        self.setMinimumSize(340, 470)
        if config.ui.always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTop, True)

        self._build()
        self._install_shortcuts()

        self._status_arrived.connect(self._render_status)
        self._today_baseline = self._compute_today_baseline()

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(_TICK_MS)
        self._view.focus_first()

    # --- layout ----------------------------------------------------------
    def _build(self) -> None:
        # The progress fill is painted by the outermost content widget, so it reaches every
        # corner — including the gear's row — instead of stopping at the timer's edge.
        self._background = ProgressBackground(self._theme)
        root = QVBoxLayout(self._background)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if self._test_mode:
            banner = QLabel("TEST MODE — nothing is recorded", objectName="banner")
            banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
            root.addWidget(banner)

        # Gear sits in its own top row rather than floating over the timer.
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 0)
        top.addStretch(1)
        self._gear = button("⚙", "gear")
        self._gear.setFixedSize(30, 28)
        self._gear.setToolTip("Settings  (Ctrl+,)")
        self._gear.clicked.connect(self._open_settings)
        top.addWidget(self._gear)
        root.addLayout(top)

        self._view = TimerView(
            controller=self,
            work_minutes=self._config.pomodoro.work_minutes,
        )
        root.addWidget(self._view)
        self.setCentralWidget(self._background)

        # Tab continues from the timer's last control into the gear, then wraps.
        self.setTabOrder(self._view.stop_button(), self._gear)

    def _install_shortcuts(self) -> None:
        """Keyboard equivalents for the transport controls.

        Deliberately Ctrl-prefixed: a bare Space or Enter has to keep meaning "press the
        focused button", or Tab navigation stops making sense.
        """
        for keys, slot in (
            ("Ctrl+Space", self.on_pause_resume_or_start),
            ("Ctrl+.", self.on_stop),
            ("Ctrl+,", self._open_settings),
            ("Ctrl+Up", self._view.nudge_up),
            ("Ctrl+Down", self._view.nudge_down),
        ):
            QShortcut(QKeySequence(keys), self, activated=slot)

    # --- wiring from the composition root --------------------------------
    @property
    def ui_theme(self) -> theme.Theme:
        """The resolved look for this run, so the composition root can style the app."""
        return self._theme

    def attach_worker(self, worker: EvidenceWorker) -> None:
        self._worker = worker

    def on_evidence_status(self, status: EvidenceStatus) -> None:
        """Called from the worker thread; the signal hops it to the UI thread."""
        self._status_arrived.emit(status)

    def set_status_mode(self, text: str, color: str = theme.MUTED) -> None:
        self._view.set_status(text, color)

    def _open_settings(self) -> None:
        if self._settings_dialog is not None and self._settings_dialog.isVisible():
            self._settings_dialog.raise_()
            self._settings_dialog.activateWindow()
            return
        self._settings_dialog = SettingsDialog(
            controller=self, pomodoro=self._config.pomodoro, parent=self
        )
        self._settings_dialog.show()

    # --- controller callbacks (from the views) ---------------------------
    def on_start(self) -> None:
        self._today_baseline = self._compute_today_baseline()
        self._engine.start()
        self._repaint()

    def on_pause_resume(self) -> None:
        if self._engine.state is State.paused:
            self._engine.resume()
        else:
            self._engine.pause()
        self._repaint()

    def on_pause_resume_or_start(self) -> None:
        """What the primary button does, for the keyboard shortcut."""
        if self._engine.state in (State.idle, State.done):
            self._view.commit_planned()
            self.on_start()
        else:
            self.on_pause_resume()

    def on_stop(self) -> None:
        self._engine.stop()
        self._repaint()

    def on_add_time(self, minutes: float) -> None:
        self._engine.add_time(minutes)
        self._repaint()

    def _apply_pomodoro(
        self, *, work: int | None = None, brk: int | None = None, rounds: int | None = None
    ) -> str | None:
        """Merge overrides into the Pomodoro config, validate, apply, and persist."""
        cur = self._config.pomodoro
        try:
            updated = PomodoroConfig(
                work_minutes=cur.work_minutes if work is None else work,
                break_minutes=cur.break_minutes if brk is None else brk,
                rounds=cur.rounds if rounds is None else rounds,
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first["loc"][0] if first["loc"] else "value"
            return f"{field}: {first['msg']}"

        self._config.pomodoro = updated
        self._engine.update_config(updated)
        if self._test_mode:
            return None  # a test run must not rewrite your real settings.toml
        try:
            save_pomodoro(self._config, updated)
        except OSError as exc:
            return f"Applied, but couldn't write settings.toml: {exc}"
        return None

    def on_set_work_minutes(self, minutes: int) -> str | None:
        """Set the work length from the timer's duration field."""
        return self._apply_pomodoro(work=minutes)

    def on_save_settings(self, brk: int, rounds: int) -> str | None:
        """Save break length and round count from the Settings window."""
        return self._apply_pomodoro(brk=brk, rounds=rounds)

    def on_open_backfill(self) -> None:
        BackfillDialog(
            on_submit=self._apply_backfill,
            default_work=self._config.pomodoro.work_minutes,
            default_break=self._config.pomodoro.break_minutes,
            default_rounds=self._config.pomodoro.rounds,
            parent=self._settings_dialog or self,
        ).exec()

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
        self._repaint()

    def _repaint(self) -> None:
        """Push the current engine state at the view.

        Called after every command as well as on the timer: the view decides what its
        controls do from the last state it was handed, so leaving it stale for up to a
        tick would make a keypress right after "start" act on the wrong thing.
        """
        snap = self._engine.snapshot()
        self._view.render_state(snap, self._today_baseline + snap.session_work_seconds)
        self._background.set_progress(*progress_for(snap))

    def _render_status(self, status: EvidenceStatus) -> None:
        if status.unpushed_count > 0:
            # Saved locally; only the push to GitHub (the third-party proof) is behind.
            self._view.set_status(
                f"status: offline · {status.unpushed_count} to sync", theme.WARN
            )
        elif status.pushed:
            self._view.set_status("status: synced ✓", theme.OK)
        elif status.committed:
            self._view.set_status("status: saved locally", "gray")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._timer.stop()
        if self._worker is not None:
            self._worker.stop()
        super().closeEvent(event)
