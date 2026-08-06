"""The window background doubles as the progress indicator.

There is no progress bar widget to assert on, so these read the painted pixels back — the
only way to prove the fill actually reaches where it should.
"""

from __future__ import annotations

import pytest

from habito.engine.pomodoro import EngineState, State
from habito.ui import theme
from habito.ui.progress_background import ProgressBackground
from habito.ui.timer_view import progress_for

DARK = theme.Theme(accent=theme.ACCENT_LIVE, palette=theme.DARK)


def snapshot(state: State, remaining: int = 0, target: int = 0) -> EngineState:
    return EngineState(
        state=state,
        round_index=1,
        total_rounds=4,
        remaining_seconds=remaining,
        phase_target_seconds=target,
        accumulated_work_seconds=0,
        session_work_seconds=0,
        paused_from=None,
    )


@pytest.fixture
def background(qtbot):
    widget = ProgressBackground(DARK)
    qtbot.addWidget(widget)
    widget.resize(400, 300)
    widget.show()
    qtbot.waitExposed(widget)
    return widget


def sample(widget, across: float, down: float = 0.5):
    image = widget.grab().toImage()
    return image.pixelColor(int(image.width() * across), int(image.height() * down))


# --- what fraction to fill ------------------------------------------------
@pytest.mark.parametrize(
    ("snap", "expected"),
    [
        (snapshot(State.idle), 0.0),
        (snapshot(State.done), 0.0),
        (snapshot(State.work, remaining=1500, target=1500), 0.0),
        (snapshot(State.work, remaining=750, target=1500), 0.5),
        (snapshot(State.work, remaining=0, target=1500), 1.0),
    ],
)
def test_progress_for_reads_the_phase(snap, expected):
    assert progress_for(snap)[0] == pytest.approx(expected)


@pytest.mark.parametrize(
    ("state", "color"),
    [
        (State.work, theme.OK),
        (State.break_, theme.BREAK),
        (State.paused, theme.WARN),
    ],
)
def test_progress_for_picks_the_phase_colour(state, color):
    assert progress_for(snapshot(state, remaining=1, target=2))[1] == color


def test_progress_is_clamped_to_the_window(background):
    # add_time pushes remaining past the target; an overrun drives it the other way.
    background.set_progress(-0.5, theme.OK)
    assert background.fraction == 0.0

    background.set_progress(1.7, theme.OK)
    assert background.fraction == 1.0


# --- what actually gets painted -------------------------------------------
def test_nothing_is_filled_at_zero(background):
    background.set_progress(0.0, theme.OK)
    assert sample(background, 0.1) == DARK.background()
    assert sample(background, 0.9) == DARK.background()


def test_fill_grows_from_the_left(background):
    background.set_progress(0.5, theme.OK)
    assert sample(background, 0.1) == DARK.progress_fill(theme.OK)  # elapsed
    assert sample(background, 0.9) == DARK.background()  # still to come


def test_fill_spans_the_full_height(background):
    """It's the whole window's background, not a band — top and bottom must both fill."""
    background.set_progress(0.5, theme.OK)
    for down in (0.02, 0.5, 0.98):
        assert sample(background, 0.1, down) == DARK.progress_fill(theme.OK)


def test_fill_is_tinted_by_the_phase(background):
    background.set_progress(0.5, theme.OK)
    work = sample(background, 0.1)

    background.set_progress(0.5, theme.BREAK)
    assert sample(background, 0.1) == DARK.progress_fill(theme.BREAK)
    assert sample(background, 0.1) != work


def test_fill_is_subtle_enough_to_read_text_over():
    base, fill = DARK.background(), DARK.progress_fill(theme.OK)
    delta = sum(abs(getattr(fill, c)() - getattr(base, c)()) for c in ("red", "green", "blue"))
    assert 8 < delta < 90  # a visible shift, nowhere near the phase colour itself


def test_sub_pixel_changes_are_ignored(background):
    """A 250ms tick on a 400px window usually can't move the edge a whole pixel.

    Such updates are dropped rather than repainting the window four times a second for no
    visible change; the state only advances once the edge would actually land elsewhere.
    """
    background.set_progress(0.5, theme.OK)
    background.set_progress(0.5 + 0.4 / background.width(), theme.OK)
    assert background.fraction == 0.5  # under half a pixel — not worth a repaint

    background.set_progress(0.75, theme.OK)
    assert background.fraction == 0.75


def test_a_phase_change_repaints_even_at_the_same_fraction(background):
    """Work → break at the same fill must still change colour."""
    background.set_progress(0.5, theme.OK)
    background.set_progress(0.5, theme.BREAK)
    assert sample(background, 0.1) == DARK.progress_fill(theme.BREAK)
