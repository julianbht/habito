"""The application window — also the small controller the views call into.

Owns the tick loop that drives the engine and repaints the view. Evidence status arrives
from the worker thread as a Qt signal, which Qt queues onto the UI thread automatically —
the safe cross-thread pattern here, and the reason no explicit status queue is needed.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QActionGroup, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from habito.config.editor import ConfigEditor
from habito.config.models import Config
from habito.domain.events import Event, Origin, SessionTagged, logical_day
from habito.engine.pomodoro import EngineState, PomodoroEngine, State
from habito.evidence.worker import EvidenceStatus, EvidenceWorker
from habito.projections.daily import summarize_by_day, summary_for
from habito.projections.resume import ResumePhase, find_resumable
from habito.projections.sessions import summarize_sessions
from habito.projections.tags import known_tags
from habito.storage.event_store import EventStore
from habito.ui import theme
from habito.ui.backfill_view import BackfillDialog
from habito.ui.calendar_view import CalendarView
from habito.ui.log_view import LogView
from habito.ui.notifier import (
    DesktopNotifier,
    Notification,
    Sink,
    break_over_reminder,
    notification_for,
)
from habito.ui.phase_dialog import PhaseDialog
from habito.ui.progress_background import ProgressBackground
from habito.ui.resume_dialog import ResumePromptDialog
from habito.ui.retract_view import RetractDialog
from habito.ui.session_complete_dialog import SessionCompleteDialog
from habito.ui.settings_view import SettingsDialog, SettingsValues
from habito.ui.shortcuts_view import SHORTCUTS, ShortcutsDialog
from habito.ui.sounds import SoundPlayer
from habito.ui.svg_icons import icon
from habito.ui.timer_view import TimerView, progress_for
from habito.ui.widgets import button

_TICK_MS = 250

# Page *identities*, not stack indices — the calendar and the log are only added to the
# stack once they're first opened, so a page's position there depends on what you've
# visited. `_page` tracks which of these is showing.
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
        # Validates and persists every settings change; mutates the same `config` object,
        # so reads of `self._config` below always see the current values.
        self._config_editor = ConfigEditor(config, test_mode)
        self._engine = engine
        self._store = store
        # Borrowed rather than built: one clock means a timezone change from Settings
        # reaches the events the engine stamps, not just the views.
        self._clock = engine.clock
        self._test_mode = test_mode
        self._theme = theme.Theme.resolve(config.ui.theme, test_mode)
        self._worker: EvidenceWorker | None = None
        self._settings_dialog: SettingsDialog | None = None
        # Built on first open; see `_calendar_view` / `_log_view`.
        self._calendar: CalendarView | None = None
        self._log: LogView | None = None
        self._page = _TIMER_PAGE
        self._last_state = engine.state
        self._ending_by_hand = False
        self._phase_dialog: PhaseDialog | SessionCompleteDialog | None = None
        # When "awaiting, break just ended" started (monotonic), and whether the
        # follow-up nudge has already fired for this particular wait — see
        # _maybe_remind. Reset the moment that state isn't current any more.
        self._awaiting_break_over_since: float | None = None
        self._break_reminded = False

        self.setWindowTitle("Habito — TEST MODE" if test_mode else "Habito")
        self._page_sizes = dict(_PAGE_SIZES)
        self.setMinimumSize(_PAGE_MINIMUMS[_TIMER_PAGE])
        self.resize(_PAGE_SIZES[_TIMER_PAGE])
        if config.ui.always_on_top:
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

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

        # The menu sits in its own top row rather than floating over the timer.
        top = QHBoxLayout()
        top.setContentsMargins(8, 6, 8, 0)
        top.addStretch(1)
        self._menu_btn = button("", "gear")
        self._menu_btn.setFixedSize(30, 28)
        self._menu_btn.setIcon(icon("menu"))
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
        self._pages = QStackedWidget()
        self._pages.addWidget(self._view)
        root.addWidget(self._pages)
        self.setCentralWidget(self._background)

        # Tab continues from the timer's last control into the menu, then wraps.
        self.setTabOrder(self._view.stop_button(), self._menu_btn)

    # --- views -----------------------------------------------------------
    # The calendar and the log are built the first time they're opened, not at startup.
    # Between them they were roughly a third of the window's construction cost — a
    # QCalendarWidget and a table — paid before the timer, the page you actually land on,
    # could paint. Neither has anything to catch up on when built late: each reads the
    # store on the way in and is constructed from the *current* config, which is what lets
    # the apply-a-setting paths below skip a view that doesn't exist yet.
    def _calendar_view(self) -> CalendarView:
        if self._calendar is None:
            self._calendar = CalendarView(
                self._theme,
                self._config.goals.threshold_seconds(),
                self._config.goals.stretch_seconds(),
            )
            self._pages.addWidget(self._calendar)
        return self._calendar

    def _log_view(self) -> LogView:
        if self._log is None:
            self._log = LogView(self._theme, self._config.time.rollover_hour)
            self._pages.addWidget(self._log)
        return self._log

    def _open_menu(self) -> None:
        menu = self.build_menu()
        menu.exec(self._menu_btn.mapToGlobal(self._menu_btn.rect().bottomLeft()))

    def build_menu(self) -> QMenu:
        """Assemble the ☰ menu. Separate from showing it, so its contents are testable."""
        menu = QMenu(self)
        group = QActionGroup(menu)
        group.setExclusive(True)
        for index, name, glyph in (
            (_TIMER_PAGE, "Timer", "timer"),
            (_CALENDAR_PAGE, "Calendar", "calendar_month"),
            (_LOG_PAGE, "Log", "format_list_bulleted"),
        ):
            action = menu.addAction(icon(glyph), name)
            action.setCheckable(True)
            action.setChecked(self._page == index)
            action.triggered.connect(lambda _c=False, i=index: self.show_page(i))
            group.addAction(action)

        menu.addSeparator()
        menu.addAction(icon("calendar_add_on"), "Backfill…", self.on_open_backfill)
        menu.addAction(icon("undo"), "Retract session…", self.on_open_retract)
        menu.addAction(icon("keyboard"), "Shortcuts…", self.on_open_shortcuts)
        menu.addAction(icon("settings"), "Settings…", self._open_settings)
        return menu

    def show_page(self, page: int) -> None:
        # Both derived views are folded from the log on the way in, so they're never
        # showing a stale picture of a session that finished while they were hidden.
        widget: QWidget
        focus: QWidget | None = None  # None means "the page decides", i.e. the timer
        if page == _CALENDAR_PAGE:
            calendar = self._calendar_view()
            self._refresh_calendar()
            widget, focus = calendar, calendar.calendar
        elif page == _LOG_PAGE:
            log = self._log_view()
            # The one view showing retractions, so it reads the stream unfiltered.
            log.set_events(self._store.read_all(include_retracted=True))
            widget, focus = log, log.tree
        else:
            widget = self._view

        self._resize_for(page)
        self._pages.setCurrentWidget(widget)
        self._page = page
        if focus is None:
            self._view.focus_first()
        else:
            focus.setFocus(Qt.FocusReason.OtherFocusReason)

    def _resize_for(self, page: int) -> None:
        """Give each view the room it needs, keeping whatever size you last chose for it."""
        if self._page == page:
            return
        self._page_sizes[self._page] = self.size()
        self.setMinimumSize(_PAGE_MINIMUMS[page])
        if not self.isMaximized() and not self.isFullScreen():
            self.resize(self._page_sizes[page])

    def _refresh_calendar(self) -> None:
        """Skipped when the calendar was never opened — it folds the log on the way in."""
        if self._calendar is not None:
            self._calendar.set_summaries(
                summarize_by_day(self._store.read_all(), self._config.time.rollover_hour)
            )

    def _install_shortcuts(self) -> None:
        """Keyboard equivalents for the transport controls.

        Bound off SHORTCUTS (see shortcuts_view.py for why each one is or isn't
        Ctrl-prefixed) — zipped against the slots below in that same order, so a
        mismatched length fails loudly here rather than silently binding the wrong slot
        to the wrong key.
        """
        slots = (
            self.on_pause_resume_or_start,
            self.on_stop,
            self._open_settings,
            self._view.nudge_up,
            self._view.nudge_down,
        )
        for (key, _description), slot in zip(SHORTCUTS, slots, strict=True):
            QShortcut(QKeySequence(key), self).activated.connect(slot)

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
            break_reminder_minutes=self._config.ui.break_reminder_minutes,
            time_config=self._config.time,
            parent=self,
        )
        self._settings_dialog.show()

    # --- resume ------------------------------------------------------------
    def offer_resume(self) -> None:
        """Called once by ``run_gui``, right after ``show()``: ask before continuing a
        session closed mid-round.

        Deliberately an explicit call from the composition root rather than a
        self-scheduled ``QTimer.singleShot`` — a zero-delay timer fires on whatever the
        *next* spin of the event loop happens to be, which in tests that construct a
        window without entering the loop is some later, unrelated test's spin (and its
        real, unmocked dialog). A plain call has no such lifetime beyond this one
        invocation, and the engine-idle guard below is what makes it safe for direct
        tests to call it whenever they like rather than only right after construction.
        """
        if self._engine.state not in (State.idle, State.done):
            return
        resumable = find_resumable(
            self._store.read_all(), self._config.habit, self._config.pomodoro.rounds
        )
        if resumable is None:
            return
        window = self._config.pomodoro.resume_window_minutes * 60
        elapsed = (self._clock.now() - resumable.interrupted_at).total_seconds()
        if elapsed > window:
            return
        if ResumePromptDialog(resumable, parent=self).exec() == QDialog.DialogCode.Accepted:
            self._today_baseline = self._compute_today_baseline()
            phase = State.work if resumable.phase is ResumePhase.work else State.break_
            self._engine.resume_session(
                resumable.round_index, phase, resumable.remaining_seconds, resumable.session_id
            )
            self._repaint()

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

    # The ConfigEditor validates, applies and writes; what's left here is the part that
    # needs widgets. A rejected change left the config untouched, so its side effects are
    # skipped — but an accepted-yet-unwritten one is still in force, so those still run.
    def on_set_work_minutes(self, minutes: float) -> str | None:
        """Set the work length from the timer's duration field.

        Fractional: the view sends ``seconds / 60``, and ``PomodoroConfig.work_minutes`` is
        a float so a sub-minute round survives the trip.
        """
        outcome = self._config_editor.apply_work_minutes(minutes)
        if outcome.ok:
            self._engine.update_config(self._config.pomodoro)
        return outcome.message

    def on_save_settings(self, values: SettingsValues) -> str | None:
        """Apply everything the Settings dialog can change, all of it or none of it."""
        outcome = self._config_editor.apply_settings(
            break_minutes=values.break_minutes,
            rounds=values.rounds,
            resume_window_minutes=values.resume_window_minutes,
            daily_minutes=values.daily_minutes,
            buffer_minutes=values.buffer_minutes,
            stretch_minutes=values.stretch_minutes,
            stretch_buffer_minutes=values.stretch_buffer_minutes,
            break_reminder_minutes=values.break_reminder_minutes,
            sound=values.sound,
            timezone=values.timezone,
            rollover_hour=values.rollover_hour,
        )
        if outcome.ok:
            self._engine.update_config(self._config.pomodoro)
            self._retune_goals()
            self._retune_sound()
            self._retune_clock()
        return outcome.message

    def _retune_clock(self) -> None:
        """Point the shared clock at the configured zone; new events carry its offset."""
        time_config = self._config.time
        self._clock.set_zone(time_config.zone())
        if self._log is not None:
            self._log.set_rollover_hour(time_config.rollover_hour)
        self._store.set_rollover_hour(time_config.rollover_hour)
        # "Today" may well have moved, so anything counting from it is now stale.
        self._today_baseline = self._compute_today_baseline()
        self._refresh_calendar()

    def _retune_goals(self) -> None:
        if self._calendar is not None:
            goals = self._config.goals
            self._calendar.set_goals(goals.threshold_seconds(), goals.stretch_seconds())

    def _retune_sound(self) -> None:
        self._notifier.set_sound(self._config.ui.sound)
        self._sounds.preload(self._config.ui.sound)

    def on_preview_sound(self, sound: str) -> None:
        """Play a sound without committing to it, so it can be auditioned."""
        self._sounds.play(sound)

    def on_open_backfill(self) -> None:
        BackfillDialog(
            on_submit=self._append_all,
            # Backfilled sessions are described in whole minutes; a sub-minute test round
            # isn't a sensible default for one.
            default_work=max(1, round(self._config.pomodoro.work_minutes)),
            default_break=self._config.pomodoro.break_minutes,
            default_rounds=self._config.pomodoro.rounds,
            habit=self._config.habit,
            time_config=self._config.time,
            today=self._today(),
            parent=self._settings_dialog or self,
        ).exec()

    def on_open_retract(self) -> None:
        RetractDialog(
            # The raw stream, so a session already retracted can be recognised as such
            # and left off the list.
            sessions=summarize_sessions(
                self._store.read_all(include_retracted=True),
                self._config.time.rollover_hour,
            ),
            on_submit=self._append_all,
            habit=self._config.habit,
            now=self._clock.local_now(),
            parent=self._settings_dialog or self,
        ).exec()

    def on_open_shortcuts(self) -> None:
        ShortcutsDialog(parent=self._settings_dialog or self).exec()

    # --- internals -------------------------------------------------------
    def _append_all(self, events: Iterable[Event]) -> None:
        """Land a hand-made correction — backfill or retraction — and re-derive from it.

        Both change what today and the calendar amount to, so both refresh the same two.
        """
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
        self._maybe_remind(snap)

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

    def _maybe_remind(self, snap: EngineState) -> None:
        """A second nudge if "Break over" goes unacknowledged for a while.

        Tracked here rather than the engine: it's a UX nicety with no domain meaning, not
        something worth a log event or a place in the engine's own tested invariants.
        Monotonic, like the engine's own phase timing, so it can't be fooled by the wall
        clock changing underneath it.
        """
        if snap.state is not State.awaiting or snap.pending is not State.work:
            self._awaiting_break_over_since = None
            self._break_reminded = False
            return
        if self._awaiting_break_over_since is None:
            self._awaiting_break_over_since = self._clock.monotonic()
            self._break_reminded = False
            return
        if self._break_reminded:
            return
        elapsed = self._clock.monotonic() - self._awaiting_break_over_since
        if elapsed < self._config.ui.break_reminder_minutes * 60:
            return
        self._break_reminded = True
        note = break_over_reminder(snap)
        if note is not None:
            self._notifier.send(note)
            self._prompt(note)

    def _prompt(self, note: Notification) -> None:
        """Put the phase prompt in front of whatever the user is doing."""
        self._close_prompt()
        if self._engine.state is State.done:
            self._phase_dialog = SessionCompleteDialog(
                note.title,
                note.body,
                note.action,
                known_tags(self._store.read_all(), self._config.habit),
                on_accept=self._on_session_complete_accepted,
                parent=self,
            )
        else:
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

    def _on_session_complete_accepted(self, tag: str | None) -> None:
        """Record the optional tag, if one was picked, and bring the timer back to front.

        Skipping (blank tag, Esc, the close button) is just as valid an answer as
        picking one — nothing here is required, so nothing here is enforced.
        """
        self._phase_dialog = None
        session_id = self._engine.session_id
        if tag and session_id is not None:
            self._append_all(
                [
                    SessionTagged(
                        timestamp=self._clock.now(),
                        tz_offset_minutes=self._clock.utc_offset_minutes(),
                        origin=Origin.live,
                        habit=self._config.habit,
                        session_id=session_id,
                        tag=tag,
                    )
                ]
            )
        self.show()
        self.raise_()
        self.activateWindow()
        self._view.focus_first()
        self._repaint()

    def _dismiss_stale_prompt(self, snap: EngineState) -> None:
        """Take the prompt down if the session moved on without it being answered."""
        dialog = self._phase_dialog
        if dialog is not None and dialog.gates_phase and snap.state is not State.awaiting:
            self._close_prompt()

    def _close_prompt(self) -> None:
        if self._phase_dialog is not None:
            self._phase_dialog.close()
            self._phase_dialog = None

    def _render_status(self, status: EvidenceStatus) -> None:
        if status.unpushed_count > 0:
            # Saved locally; only the push to GitHub (the third-party proof) is behind.
            self._view.set_status(f"status: offline · {status.unpushed_count} to sync", theme.WARN)
        elif status.pushed:
            self._view.set_status("status: synced", theme.OK)
        elif status.committed:
            self._view.set_status("status: saved locally", "gray")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt override)
        self._timer.stop()
        self._close_prompt()
        # Finalise an in-flight round/session honestly, same as hitting Stop, so quitting
        # mid-round doesn't drop the work — a no-op when idle/done. Must run before the
        # worker is stopped below: it's what queues the closing event for that final flush.
        self.on_stop()
        if isinstance(self._notifier, DesktopNotifier):
            self._notifier.close()
        if self._worker is not None:
            self._worker.stop()
        super().closeEvent(event)
