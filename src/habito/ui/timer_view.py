"""The main timer screen.

Purely presentational: it renders an :class:`EngineState` snapshot and forwards input to
the controller. It never talks to storage or git directly.

The big time doubles as the work-length control. While idle it is a :class:`MinutesSpinBox`
— type a value or use its arrows — that sets the next session's work length; once running
it swaps to the live countdown with a compact ▲/▼ pair that adjusts the round on the fly.
"""

from __future__ import annotations

from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractSpinBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from habito.engine.pomodoro import EngineState, State
from habito.ui import theme
from habito.ui.widgets import DurationSpinBox, button, format_duration, format_timer, label

_STATE_LABEL = {
    State.idle: "Ready",
    State.work: "Focus",
    State.break_: "Break",
    State.paused: "Paused",
    State.done: "Done",
}
_STATE_COLOR = {
    State.work: theme.OK,
    State.break_: theme.BREAK,
    State.paused: theme.WARN,
    State.done: theme.OK,
    State.idle: theme.MUTED,
}
# One press of ▲/▼ is worth one minute — deliberately not configurable.
_STEP_SECONDS = 60

# Media-transport glyphs for the control buttons.
_PLAY = "▶"  # start / resume
_PAUSE = "⏸"  # pause (primary button toggles to this while running)
_STOP = "⏹"  # end session

_EDIT_PAGE = 0
_COUNTDOWN_PAGE = 1

# A work round longer than three hours isn't a Pomodoro. The floor is seconds rather than
# minutes so a round can be made short enough to watch it finish.
_MAX_WORK_SECONDS = 180 * 60
_MIN_WORK_SECONDS = 5
_TIME_WIDTH = 212


def progress_for(snap: EngineState) -> tuple[float, str]:
    """How far through the phase we are, and the colour that progress should read as.

    Lives here beside :data:`_STATE_COLOR` but is used by the window, which owns the
    background the fill is painted onto.
    """
    color = _STATE_COLOR.get(snap.state, theme.MUTED)
    if snap.state in (State.idle, State.done):
        return 0.0, color
    target = snap.phase_target_seconds or 1
    return (target - snap.remaining_seconds) / target, color


class Controller(Protocol):
    def on_start(self) -> None: ...
    def on_pause_resume(self) -> None: ...
    def on_stop(self) -> None: ...
    def on_add_time(self, minutes: float) -> None: ...
    def on_set_work_minutes(self, minutes: float) -> str | None: ...


class TimerView(QWidget):
    def __init__(
        self,
        controller: Controller,
        work_minutes: float,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._c = controller
        self._is_idle = True
        self._build(round(work_minutes * 60))

    # --- layout ----------------------------------------------------------
    def _build(self, work_seconds: int) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 14, 20, 12)
        root.setSpacing(6)

        self._round_lbl = label("Round – / –", "round")
        self._round_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._round_lbl)

        self._state_lbl = label("Ready", "state")
        self._state_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._state_lbl)

        root.addLayout(self._build_time_row(work_seconds))
        root.addSpacing(14)
        root.addLayout(self._build_controls())

        root.addStretch(1)
        self._today_lbl = label("Today: 0m", "today")
        self._today_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._today_lbl)

        self._status_lbl = label("status: –", "muted")
        self._status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._status_lbl)

        self._apply_tab_order()

    def _build_time_row(self, work_seconds: int) -> QHBoxLayout:
        """The time — editable or counting down — with one ▲/▼ pair permanently beside it.

        The spin box's own arrows are switched off: styling ``::up-button`` makes Qt stop
        drawing the native indicators, and the replacements never look right. Owning the
        buttons ourselves means one visible, tab-reachable pair that works the same whether
        the timer is idle or running.
        """
        self._stack = QStackedWidget()
        self._stack.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._stack.setFixedWidth(_TIME_WIDTH)

        # Page 0 (idle): the spin box *is* the work-length control.
        self._spin = DurationSpinBox(
            minimum=_MIN_WORK_SECONDS, maximum=_MAX_WORK_SECONDS, object_name="time"
        )
        self._spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        self._spin.setValue(work_seconds)
        self._spin.setSingleStep(_STEP_SECONDS)
        self._spin.setToolTip(
            "Work length for the next session — type 30 for minutes, or 0:10 for seconds"
        )
        self._spin.valueChanged.connect(self._on_planned_changed)
        self._stack.addWidget(self._spin)

        # Page 1 (running): a live countdown can't be an editable field.
        self._time_lbl = label("00:00", "time")
        self._time_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._time_lbl)
        self._stack.setCurrentIndex(_EDIT_PAGE)

        self._up_btn = button("▲", "nudge")
        self._down_btn = button("▼", "nudge")
        for btn, slot, tip in (
            (self._up_btn, self.nudge_up, "Longer  (Ctrl+↑)"),
            (self._down_btn, self.nudge_down, "Shorter  (Ctrl+↓)"),
        ):
            btn.setFixedSize(34, 31)
            btn.setToolTip(tip)
            btn.clicked.connect(slot)

        nudge_col = QVBoxLayout()
        nudge_col.setSpacing(4)
        nudge_col.addWidget(self._up_btn)
        nudge_col.addWidget(self._down_btn)

        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self._stack)
        row.addSpacing(8)
        row.addLayout(nudge_col)
        row.addStretch(1)
        return row

    def _build_controls(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addStretch(1)
        self._primary_btn = button(_PLAY, "primary")
        self._primary_btn.setFixedSize(88, 42)
        self._primary_btn.setToolTip("Start / pause  (Ctrl+Space)")
        self._primary_btn.clicked.connect(self._primary)
        row.addWidget(self._primary_btn)

        self._stop_btn = button(_STOP, "transport")
        self._stop_btn.setFixedSize(66, 42)
        self._stop_btn.setToolTip("End the session  (Ctrl+.)")
        self._stop_btn.clicked.connect(self._c.on_stop)
        row.addWidget(self._stop_btn)
        row.addStretch(1)
        return row

    def _apply_tab_order(self) -> None:
        """Walk Tab through the controls in the order you'd actually use them."""
        chain = [
            self._spin,
            self._up_btn,
            self._down_btn,
            self._primary_btn,
            self._stop_btn,
        ]
        for earlier, later in zip(chain, chain[1:], strict=False):
            self.setTabOrder(earlier, later)

    def focus_first(self) -> None:
        """Put focus where a keyboard user starts: the duration field."""
        self._spin.setFocus(Qt.FocusReason.OtherFocusReason)

    def stop_button(self) -> QPushButton:
        """Last control in the view's tab chain, so the window can continue it."""
        return self._stop_btn

    # --- work-length editing (idle) --------------------------------------
    def _on_planned_changed(self, seconds: int) -> None:
        if self._is_idle:
            self._c.on_set_work_minutes(seconds / 60)

    def commit_planned(self) -> None:
        """Flush a half-typed duration before starting (spin box defers to focus-out)."""
        self._spin.interpretText()

    # --- button glue -----------------------------------------------------
    def _primary(self) -> None:
        if self._is_idle:
            self.commit_planned()
            self._c.on_start()
        else:
            self._c.on_pause_resume()

    def nudge_up(self) -> None:
        self._nudge(1)

    def nudge_down(self) -> None:
        self._nudge(-1)

    def _nudge(self, direction: int) -> None:
        """One minute in either direction.

        Idle, that means the planned work length; running, the current round. Same pair of
        controls either way, so the ▲/▼ buttons and the Ctrl+↑/↓ shortcuts don't need to
        care which mode the timer is in.
        """
        if self._is_idle:
            self._spin.setValue(self._spin.value() + direction * _STEP_SECONDS)
        else:
            self._c.on_add_time(direction * _STEP_SECONDS / 60)

    # --- rendering -------------------------------------------------------
    def render_state(self, snap: EngineState, today_seconds: int) -> None:
        self._is_idle = snap.state in (State.idle, State.done)

        self._round_lbl.setText(f"Round {snap.round_index} / {snap.total_rounds}")
        self._state_lbl.setText(_STATE_LABEL[snap.state])
        self._state_lbl.setStyleSheet(
            f"color: {_STATE_COLOR.get(snap.state, theme.MUTED)};"
        )
        self._render_time(snap)

        running = snap.state in (State.work, State.break_)
        self._primary_btn.setText(_PAUSE if running else _PLAY)

        active = snap.state in (State.work, State.break_, State.paused)
        self._stop_btn.setEnabled(active)

        self._today_lbl.setText(f"Today: {format_duration(today_seconds)}")

    def _render_time(self, snap: EngineState) -> None:
        if self._is_idle:
            self._show_page(_EDIT_PAGE)
            return

        self._show_page(_COUNTDOWN_PAGE)
        self._time_lbl.setText(format_timer(snap.remaining_seconds))

    def _show_page(self, page: int) -> None:
        """Swap the time display, keeping keyboard focus somewhere usable.

        The spin box is the only focusable widget inside the stack, so it's the only one
        that can be stranded: hiding it while focused would leave a keyboard user with
        nothing focused the moment a session starts. Hand focus on instead.
        """
        if self._stack.currentIndex() == page:
            return
        if page == _COUNTDOWN_PAGE and self._spin.hasFocus():
            self._primary_btn.setFocus(Qt.FocusReason.OtherFocusReason)
        self._stack.setCurrentIndex(page)

    def set_status(self, text: str, color: str = theme.MUTED) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"color: {color}; font-size: 11px;")
