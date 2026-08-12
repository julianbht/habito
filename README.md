# Habito

A minimalist, keyboard-navigable cross-platform Pomodoro tracker for developers.

## Core Features

- **[All data on your Github repository](#tamper-evident-log)** — every event is appended
  to an immutable, machine-readable log and pushed to a separate GitHub repo the moment it happens.
  As a result, you have complete record of all study activity saved securely and completely under
  your control. Server-recorded push times also stand as third-party proof of when you actually
  studied.
- **[Fully keyboard-driven](#keyboard)** — Tab reaches every control, with shortcuts for
  start, stop and adjust.
- **[A calendar of your streak](#calendar)** — a month at a glance, green on every day you
  hit your goal.

## Requirements

Python 3.11+ • [uv](https://docs.astral.sh/uv/) • git

## Setup

Install dependencies:

```bash
uv sync
```

Create the separate data repo Habito commits to (makes `../habito-data` and `git init`s it):

```bash
uv run habito init-data
```

Create an empty repo on GitHub, then give the data repo that remote:

```bash
cd ../habito-data
git remote add origin https://github.com/<you>/habito-data.git
git push -u origin main
cd -
```

Verify everything is wired up — this should report `Evidence: READY`:

```bash
uv run habito doctor
```

Settings live in [`config/settings.json`](config/settings.json)

## Usage

Launch the timer UI:

```bash
uv run habito
```

Run against a throwaway log, without touching the data repo — see [Test mode](#test-mode):

```bash
uv run habito --test-mode
```

## Keyboard

The whole app is reachable without a mouse. Focus starts on the Play button, and every
control draws a visible focus ring.

| Key | Action |
|---|---|
| `Tab` / `Shift+Tab` | Move through duration → up → down → play/pause → stop → menu |
| `Space` / `Enter` | Press the focused button |
| `Space` | Start / pause / resume, from anywhere |
| `↑` / `↓` | Nudge the duration by a minute, while it has focus |
| `Ctrl+↑` / `Ctrl+↓` | Nudge by a minute from anywhere — the duration when idle, the live round when running |
| `Ctrl+.` | Stop the session |
| `Ctrl+,` | Open Settings |
| `Esc` | Close a dialog |

## Test mode

```bash
uv run habito --test-mode
```

For trying the UI out without polluting your real record. In this mode Habito:

- writes events to a **throwaway file in your temp directory** (the path is printed on
  startup) — the data repo is never touched;
- starts **no evidence worker**, so nothing is committed or pushed;
- leaves **`settings.json` unwritten** — format changes apply to the run only;
- paints the entire app **red**, so it can't be mistaken for a real session.

## Log

Every event, grouped by day, newest first — what started when, how long each round actually
ran, every pause and every `TimeAdjusted`. Backfilled entries are marked as such.

It is **strictly read-only**: no edit, no delete. That isn't an oversight. The log's value
comes from being append-only, and a view that could rewrite it would undercut the one claim
the app makes. If something in there is wrong, the right fix is to append a correction, not
to quietly remove the evidence.

## Layout

`src/` layout, one concern per package:

| Package | Responsibility |
|---|---|
| `habito.domain` | Pydantic event models (append-only log entries) |
| `habito.config` | TOML settings + validation |
| `habito.storage` | Append-only JSONL event store (Repository) |
| `habito.engine` | Pomodoro state machine (incl. the between-phase hold) + injectable Clock |
| `habito.projections` | Fold events → daily summaries (verified vs backfilled) |
| `habito.evidence` | git wrapper, background commit+push worker, Observer recorder |
| `habito.ui` | PySide6/Qt timer + calendar + log, dialogs (settings, backfill, phase prompt), window/controller, theme, progress background, notifications + sounds |
| `habito.backfill` | Synthesize events for a past session |

Only `habito.ui` knows about Qt. The views are purely presentational and talk to a
`Controller` protocol, so the engine, storage, projection and evidence layers are entirely
UI-agnostic.

## Tamper evident log

- **Git commit times are forgeable** (they come from your machine), so they prove nothing
  on their own. What *is* hard to forge is **GitHub's server-recorded push time**. Habito
  therefore commits **and pushes** after every event, immediately.
- The log is **append-only** (event sourcing): nothing is ever edited, only appended.
- Sessions you add later are stored with `origin = "backfilled"` and are reported
  separately from live, in-the-moment evidence — they never masquerade as verified.
- The log lives in a **separate git repo** that Habito owns exclusively, keeping the
  evidence history clean and free of collisions with your code commits.

## Tests

Run the suite — unit tests, UI tests, and a hermetic end-to-end evidence test:

```bash
uv run pytest
```

Lint:

```bash
uv run ruff check
```

Just the UI tests:

```bash
uv run pytest tests/test_ui_timer_view.py tests/test_ui_test_mode.py
```

The UI tests use [pytest-qt](https://pytest-qt.readthedocs.io/). Its `qtbot` fixture
delivers **real** mouse and key events through Qt's event loop, so focus, tab order and
shortcuts are genuinely exercised rather than faked by calling handlers directly. They run
headless — `conftest.py` sets `QT_QPA_PLATFORM=offscreen`, so no window ever appears and
nothing steals your focus.

The evidence integration test stands up a local *bare* git repo as a stand-in "remote"
and proves each event is committed and pushed in order, off the UI thread — no network
required. Real GitHub push-time behaviour is verified once, manually, after setup.
