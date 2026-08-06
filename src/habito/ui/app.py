"""The application window — also the small controller the views call into.

Owns the tick loop that drives the engine and repaints the view. Evidence status arrives
from the worker thread as a Qt signal, which Qt queues onto the UI thread automatically —
the safe cross-thread pattern here, and the reason no explicit status queue is needed.
"""

from __future__ import annotations

from datetime import date

import qtawesome as qta
from pydantic import ValidationError
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
)

from habito.config.models import (
    Config,
    GoalsConfig,
    PomodoroConfig,
    TimeConfig,
    UIConfig,
)
from habito.config.writer import save_goals, save_pomodoro, save_time, save_ui
from habito.domain.events import logical_day
from habito.engine.pomodoro import EngineState, PomodoroEngine, State
from habito.evidence.worker import EvidenceStatus, EvidenceWorker
from habito.projections.daily import summarize_by_day, summary_for
from habito.storage.event_store import EventStore
from habito.ui import theme
from habito.ui.backfill_view import BackfillDialog
from habito.ui.calendar_view import CalendarView
from habito.ui.log_view import LogView
from habito.ui.notifier import DesktopNotifier, Notification, Sink, notification_for
from habito.ui.phase_dialog import PhaseDialog
from habito.ui.progress_background import ProgressBackground
from habito.ui.settings_view import SettingsDialog, SettingsValues
from habito.ui.sounds import SoundPlayer
from habito.ui.timer_view import TimerView, progress_for
from habito.ui.widgets import button

_TICK_MS = 250

_TIMER_PAGE = 0
_CALENDAR_PAGE = 1
_LOG_PAGE = 2

# Each view wants a different amount of room — the timer is a widget, the log is a table.
# Whatever you resize a view to is remembered and restored when you come back to it.
_PAGE_SIZES = {
    _TIMER_PAGE: QSize(380, 500),
    _CALENDAR_PAGE: QSize(460, 580),
    _LOG_PAGE: QSize(820, 660),
}
_PAGE_MINIMUMS = {
    _TIMER_PAGE: QSize(340, 470),
    _CALENDAR_PAGE: QSize(340, 470),
    _LOG_PAGE: QSize(520, 380),
}


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
        # Borrowed rather than built: one clock means a timezone change from Settings
        # reaches the events the engine stamps, not just the views.
        self._clock = engine.clock
        self._test_mode = test_mode
        self._theme = theme.Theme.resolve(config.ui.theme, test_mode)
        self._worker: EvidenceWorker | None = None
        self._settings_dialog: SettingsDialog | None = None
        self._last_state = engine.state
        self._ending_by_hand = False
        self._phase_dialog: PhaseDialog | None = None

        self.setWindowTitle("Habito — TEST MODE" if test_mode else "Habito")
        self._page_sizes = dict(_PAGE_SIZES)
        self.setMinimumSize(_PAGE_MINIMUMS[_TIMER_PAGE])
        self.resize(_PAGE_SIZES[_TIMER_PAGE])
        if config.ui.always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTop, True)

        self._build()
        self._install_shortcuts()
        self._sounds = SoundPlayer()
        self._sounds.preload(config.ui.sound)
        self._notifier: Sink = DesktopNotifier(
            self, self._sounds, config.ui.sound, enabled=config.ui.notifications
        )

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

        # The menu sits in its own top row rather than floating over the timer.
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 0)
        top.addStretch(1)
        self._menu_btn = button("", "gear")
        self._menu_btn.setFixedSize(30, 28)
        self._menu_btn.setIcon(qta.icon("mdi6.menu", color=self._theme.palette.text))
        self._menu_btn.setIconSize(QSize(18, 18))
        self._menu_btn.setToolTip("Menu — switch view, settings")
        self._menu_btn.clicked.connect(self._open_menu)
        top.addWidget(self._menu_btn)
        root.addLayout(top)

        self._view = TimerView(
            controller=self,
            work_minutes=self._config.pomodoro.work_minutes,
            ui_theme=self._theme,
        )
        self._calendar = CalendarView(
            self._theme,
            self._config.goals.threshold_seconds(),
            self._config.goals.stretch_seconds(),
        )
        self._log = LogView(self._theme, self._config.time.rollover_hour)

        self._pages = QStackedWidget()
        self._pages.addWidget(self._view)
        self._pages.addWidget(self._calendar)
        self._pages.addWidget(self._log)
        root.addWidget(self._pages)
        self.setCentralWidget(self._background)

        # Tab continues from the timer's last control into the menu, then wraps.
        self.setTabOrder(self._view.stop_button(), self._menu_btn)

    # --- views -----------------------------------------------------------
    def _open_menu(self) -> None:
        menu = self.build_menu()
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def build_menu(self) -> QMenu:
        """Assemble the ☰ menu. Separate from showing it, so its contents are testable."""
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        tint = self._theme.palette.text
        for index, name, glyph in (
            (_TIMER_PAGE, "Timer", "mdi6.timer-outline"),
            (_CALENDAR_PAGE, "Calendar", "mdi6.calendar-month-outline"),
            (_LOG_PAGE, "Log", "mdi6.format-list-bulleted"),
        ):
            action = menu.addAction(qta.icon(glyph, color=tint), name)
            action.setCheckable(True)
            action.setChecked(self._pages.currentIndex() == index)
            action.triggered.connect(lambda _c=False, i=index: self.show_page(i))
            group.addAction(action)

        menu.addSeparator()
        menu.addAction(
            qta.icon("mdi6.calendar-plus", color=tint),
            "Backfill…",
            self.on_open_backfill,
        )
        menu.addAction(
            qta.icon("mdi6.cog-outline", color=tint), "Settings…", self._open_settings
        )
        return menu

    def show_page(self, index: int) -> None:
        # Both derived views are folded from the log on the way in, so they're never
        # showing a stale picture of a session that finished while they were hidden.
        if index == _CALENDAR_PAGE:
            self._refresh_calendar()
        elif index == _LOG_PAGE:
            self._log.set_events(self._store.read_all())

        self._resize_for(index)
        self._pages.setCurrentIndex(index)
        if index == _TIMER_PAGE:
            self._view.focus_first()
        elif index == _CALENDAR_PAGE:
            self._calendar.calendar.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            self._log.tree.setFocus(Qt.FocusReason.OtherFocusReason)

    def _resize_for(self, index: int) -> None:
        """Give each view the room it needs, keeping whatever size you last chose for it."""
        current = self._pages.currentIndex()
        if current == index:
            return
        self._page_sizes[current] = self.size()
        self.setMinimumSize(_PAGE_MINIMUMS[index])
        if not self.isMaximized() and not self.isFullScreen():
            self.resize(self._page_sizes[index])

    def _refresh_calendar(self) -> None:
        self._calendar.set_summaries(
            summarize_by_day(self._store.read_all(), self._config.time.rollover_hour)
        )

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
            controller=self,
            pomodoro=self._config.pomodoro,
            goals=self._config.goals,
            sound=self._config.ui.sound,
            time_config=self._config.time,
            parent=self,
        )
        self._settings_dialog.show()

    # --- controller callbacks (from the views) ---------------------------
    def on_start(self) -> None:
        self._today_baseline = self._compute_today_baseline()
        self._engine.start()
        self._repaint()

    def on_pause_resume(self) -> None:
        if self._engine.state is State.awaiting:
            # ▶ on a finished phase means "get on with it", same as the prompt's button.
            self._on_prompt_accepted()
            return
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
        self._ending_by_hand = True  # you know you just stopped it; no need to be told
        self._engine.stop()
        self._repaint()

    def on_add_time(self, minutes: float) -> None:
        self._engine.add_time(minutes)
        self._repaint()

    def _apply_pomodoro(
        self,
        *,
        work: int | None = None,
        brk: int | None = None,
        rounds: int | None = None,
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

    def on_save_settings(self, values: SettingsValues) -> str | None:
        """Apply everything the Settings dialog can change, stopping at the first error."""
        return (
            self._apply_pomodoro(brk=values.break_minutes, rounds=values.rounds)
            or self._apply_goals(
                values.daily_minutes, values.buffer_minutes, values.stretch_minutes
            )
            or self._apply_sound(values.sound)
            or self._apply_time(values.timezone, values.rollover_hour)
        )

    def _apply_time(self, timezone: str, rollover_hour: int) -> str | None:
        """Point the shared clock at a new zone; events from here on carry its offset."""
        try:
            updated = TimeConfig(timezone=timezone, rollover_hour=rollover_hour)
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first["loc"][0] if first["loc"] else "timezone"
            return f"{field}: {first['msg']}"

        self._config.time = updated
        self._clock.set_zone(updated.zone())
        self._log.set_rollover_hour(updated.rollover_hour)
        self._store.set_rollover_hour(updated.rollover_hour)
        # "Today" may well have moved, so anything counting from it is now stale.
        self._today_baseline = self._compute_today_baseline()
        self._refresh_calendar()
        if self._test_mode:
            return None  # a test run must not rewrite your real settings.toml
        try:
            save_time(self._config, updated)
        except OSError as exc:
            return f"Applied, but couldn't write settings.toml: {exc}"
        return None

    def _apply_goals(
        self, daily_minutes: int, buffer_minutes: int, stretch_minutes: int = 0
    ) -> str | None:
        try:
            updated = GoalsConfig(
                daily_minutes=daily_minutes,
                buffer_minutes=buffer_minutes,
                # The spin's "Off" is 0; the config says "no stretch goal" with None.
                stretch_minutes=stretch_minutes or None,
            )
        except ValidationError as exc:
            first = exc.errors()[0]
            field = first["loc"][0] if first["loc"] else "goal"
            return f"{field}: {first['msg']}"

        self._config.goals = updated
        self._calendar.set_goals(updated.threshold_seconds(), updated.stretch_seconds())
        if self._test_mode:
            return None  # a test run must not rewrite your real settings.toml
        try:
            save_goals(self._config, updated)
        except OSError as exc:
            return f"Applied, but couldn't write settings.toml: {exc}"
        return None

    def on_preview_sound(self, sound: str) -> None:
        """Play a sound without committing to it, so it can be auditioned."""
        self._sounds.play(sound)

    def _apply_sound(self, sound: str) -> str | None:
        try:
            updated = self._config.ui.model_copy(update={"sound": sound})
            UIConfig.model_validate(updated.model_dump())
        except ValidationError as exc:
            return f"sound: {exc.errors()[0]['msg']}"

        self._config.ui = updated
        self._notifier.set_sound(sound)
        self._sounds.preload(sound)
        if self._test_mode:
            return None  # a test run must not rewrite your real settings.toml
        try:
            save_ui(self._config, updated)
        except OSError as exc:
            return f"Applied, but couldn't write settings.toml: {exc}"
        return None

    def on_open_backfill(self) -> None:
        BackfillDialog(
            on_submit=self._apply_backfill,
            # Backfilled sessions are described in whole minutes; a sub-minute test round
            # isn't a sensible default for one.
            default_work=max(1, round(self._config.pomodoro.work_minutes)),
            default_break=self._config.pomodoro.break_minutes,
            default_rounds=self._config.pomodoro.rounds,
            time_config=self._config.time,
            today=self._today(),
            parent=self._settings_dialog or self,
        ).exec()

    # --- internals -------------------------------------------------------
    def _apply_backfill(self, events) -> None:
        for event in events:
            self._store.append(event)
        self._today_baseline = self._compute_today_baseline()
        self._refresh_calendar()

    def _today(self) -> date:
        """The habit-day in progress — which before the rollover hour is still yesterday."""
        return logical_day(self._clock.local_now(), self._config.time.rollover_hour)

    def _compute_today_baseline(self) -> int:
        summary = summary_for(
            self._store.read_all(), self._today(), self._config.time.rollover_hour
        )
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
        self._announce(snap)

    def _announce(self, snap: EngineState) -> None:
        """Prompt and notify on phase changes the engine made on its own.

        Transitions are read off consecutive snapshots rather than the event stream, which
        keeps backfilled sessions — appended straight to the store — from announcing
        themselves hours after the fact.
        """
        previous, self._last_state = self._last_state, snap.state
        self._dismiss_stale_prompt(snap)
        if self._ending_by_hand:
            self._ending_by_hand = False
            return
        note = notification_for(previous, snap)
        if note is None:
            return
        self._notifier.send(note)
        self._prompt(note)

    def _prompt(self, note: Notification) -> None:
        """Put the phase prompt in front of whatever the user is doing."""
        self._close_prompt()
        self._phase_dialog = PhaseDialog(
            note.title,
            note.body,
            note.action,
            on_accept=self._on_prompt_accepted,
            gates_phase=self._engine.state is State.awaiting,
            parent=self,
        )
        self._phase_dialog.present()

    def _on_prompt_accepted(self) -> None:
        """Start the waiting phase and bring the timer back to the front."""
        self._phase_dialog = None
        self._engine.acknowledge()
        self._last_state = self._engine.state  # already handled; don't re-announce it
        self.show()
        self.raise_()
        self.activateWindow()
        self._view.focus_first()
        self._repaint()

    def _dismiss_stale_prompt(self, snap: EngineState) -> None:
        """Take the prompt down if the session moved on without it being answered."""
        dialog = self._phase_dialog
        if (
            dialog is not None
            and dialog.gates_phase
            and snap.state is not State.awaiting
        ):
            self._close_prompt()

    def _close_prompt(self) -> None:
        if self._phase_dialog is not None:
            self._phase_dialog.close()
            self._phase_dialog = None

    def _render_status(self, status: EvidenceStatus) -> None:
        if status.unpushed_count > 0:
            # Saved locally; only the push to GitHub (the third-party proof) is behind.
            self._view.set_status(
                f"status: offline · {status.unpushed_count} to sync", theme.WARN
            )
        elif status.pushed:
            self._view.set_status("status: synced", theme.OK)
        elif status.committed:
            self._view.set_status("status: saved locally", "gray")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt override)
        self._timer.stop()
        self._close_prompt()
        if isinstance(self._notifier, DesktopNotifier):
            self._notifier.close()
        if self._worker is not None:
            self._worker.stop()
        super().closeEvent(event)
