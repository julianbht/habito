# Habito

A minimalist, keyboard-navigable cross-platform Pomodoro tracker for developers with logs stored on Github.

## Requirements

- Python **3.11+**
- [uv](https://docs.astral.sh/uv/)
- git (with push access to a GitHub repo you create for the data)

## Setup

```bash
uv sync                      # create the venv and install deps

# 1. Create the separate data repo Habito will commit to:
uv run habito init-data      # creates ../habito-data and `git init`s it

# 2. Give it a GitHub remote (create an empty repo on GitHub first), e.g.:
cd ../habito-data
git remote add origin https://github.com/<you>/habito-data.git
git push -u origin main
cd -

# 3. Verify everything is wired up:
uv run habito doctor         # should report "Evidence: READY"
```

Settings live in [`config/settings.toml`](config/settings.toml) — Pomodoro format
(default 25 + 5, 4 rounds), quick-add increments, theme, and the data-repo path.

## Usage

```bash
uv run habito                # launch the timer UI
uv run habito doctor         # check config + evidence readiness
uv run habito init-data      # (re)create the data repo
```

The main window is a clean timer with icon controls — **▶ play / ⏸ pause** (the primary
button toggles: ▶ to start or resume, ⏸ to pause when you step away) and **⏹ stop** — plus a
live **status** line (`synced ✓` when your log has reached GitHub, `offline · N to sync`
when a push is behind).

The **big time is also the work-length control**:

- **Before you start** (or after a session ends) it's an editable field — click in and type
  `30` (or `30:00`), or nudge it with the stepper below. This sets the work length for your
  next session.
- **While running** it locks to the live countdown, and the stepper adjusts the current
  round on the fly.

The **stepper** — `Adjust: [ − ] [ step ▾ ] [ + ]` — picks a step from the dropdown (values
from `quick_add_minutes`, plus a **Custom…** entry for any amount) and nudges by that many
minutes. Live adjustments are recorded transparently in the log as `TimeAdjusted` events.

The **⚙ gear** opens Settings for **break length** and **round count** (work length lives on
the timer now), plus **Add past session** to backfill. Everything is saved back to
`settings.toml` with your comments preserved, applied to your next session.

## Layout

`src/` layout, one concern per package:

| Package | Responsibility |
|---|---|
| `habito.domain` | Pydantic event models (append-only log entries) |
| `habito.config` | TOML settings + validation |
| `habito.storage` | Append-only JSONL event store (Repository) |
| `habito.engine` | Pomodoro state machine + injectable Clock |
| `habito.projections` | Fold events → daily summaries (verified vs backfilled) |
| `habito.evidence` | git wrapper, background commit+push worker, Observer recorder |
| `habito.ui` | CustomTkinter timer + backfill views, window/controller |
| `habito.backfill` | Synthesize events for a past session |

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

```bash
uv run pytest        # unit + a hermetic end-to-end evidence test (local bare remote)
uv run ruff check    # lint
```

The evidence integration test stands up a local *bare* git repo as a stand-in "remote"
and proves each event is committed and pushed in order, off the UI thread — no network
required. Real GitHub push-time behaviour is verified once, manually, after setup.
