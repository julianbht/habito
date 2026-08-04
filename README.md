# Habito

A minimalist, cross-platform (Windows + macOS) Pomodoro habit tracker with a
**tamper-evident** study log. Every event is appended to an immutable log and — the moment
it happens — committed and pushed to a separate GitHub repo, so the **push timestamps
recorded by GitHub's servers** stand as third-party proof of when you actually studied.

## Why the design is like this

- **Git commit times are forgeable** (they come from your machine), so they prove nothing
  on their own. What *is* hard to forge is **GitHub's server-recorded push time**. Habito
  therefore commits **and pushes** after every event, immediately.
- The log is **append-only** (event sourcing): nothing is ever edited, only appended.
- Sessions you add later are stored with `origin = "backfilled"` and are reported
  separately from live, in-the-moment evidence — they never masquerade as verified.
- The log lives in a **separate git repo** that Habito owns exclusively, keeping the
  evidence history clean and free of collisions with your code commits.

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

The window has two tabs:

- **Timer** — Start / Pause / Skip / Stop, extend the current round with the
  `+1 / +3 / +5` (or custom) buttons, and see today's total plus the live evidence status.
- **Settings** — change the Pomodoro format (work / break / rounds; saved back to
  `settings.toml` with your comments preserved, applied to your next session), and
  **Add past session** to backfill a session you did away from the app.

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

## Tests

```bash
uv run pytest        # unit + a hermetic end-to-end evidence test (local bare remote)
uv run ruff check    # lint
```

The evidence integration test stands up a local *bare* git repo as a stand-in "remote"
and proves each event is committed and pushed in order, off the UI thread — no network
required. Real GitHub push-time behaviour is verified once, manually, after setup.
