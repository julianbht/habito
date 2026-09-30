<p align="center">
  <img src="branding/logo.svg" alt="Habito logo" width="128">
</p>

<p align="center">
  <em>"No man is free who is not master of himself."</em><br>
  — Epictetus
</p>

# Habito

A minimalist, keyboard-navigable cross-platform Pomodoro tracker for developers.

## Core Features

- **[All data on your Github repository](#tamper-evident-log)** — every event is appended
  to a machine-readable log and pushed to YOUR GitHub repo the moment it happens.
  You and only you have complete record of all activity entirely under your control.
- **[Fully keyboard-driven](#keyboard)** — Tab reaches every control, with shortcuts for
  start, stop and adjust.
- **[A calendar of your streak](#calendar)** — a month at a glance, green on every day you
  hit your goal.
- **[Goal Tracking](#calendar)** — low, middle and high goal each with indicators on the
  calendar if they have been hit
- **[Timer Templates](#calendar)** — you can setup several pomodoro templates with different
  study and break timers
- **[Backfilling](#calendar)** — you can backfill sessions and they get marked as such.
  Useful if you forgot to track a session or want to migrate.

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

- Every event, grouped by day, newest first — what started when, how long each round actually
  ran, every pause and every `TimeAdjusted`.
- The log lives in a separate git repo that Habito owns exclusively, keeping the
  evidence history clean and free of collisions with your code commits. Server-recorded push
  times also stand as third-party proof of when you actually studied.
- Server-recorded push times also stand as third-party proof of when you actually
  studied.

## Layout

`src/` layout, one concern per package, dependencies pointing inward toward `domain`:

```
src/habito/
├── domain/        Pydantic event models — the append-only log's entries
├── config/        settings.json loading + validation
├── storage/       append-only JSONL event store
├── engine/        Pomodoro state machine + injectable Clock
├── projections/   fold events → daily summaries, resumability, known tags
├── actions/       event-builders for corrections/annotations: tagging, backfill, retraction
├── evidence/      git wrapper + background commit/push worker
├── ui/            PySide6/Qt — the only package that imports Qt
│   ├── pages/     the 3 QStackedWidget pages: timer, calendar, log
│   ├── dialogs/   modal QDialogs: settings, backfill, retract, tag manager, ...
│   ├── widgets/   reusable pieces: buttons/steppers, tag picker, progress background
│   └── app.py     the main window, and the controller the views talk to
└── app.py         composition root — wires the above together; CLI entry point
```

Only `habito.ui` knows about Qt. The views are purely presentational and talk to a
`Controller` protocol, so the engine, storage, projection and evidence layers are entirely
UI-agnostic.

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
