# CLAUDE.md

Technical notes and design rules for working in this repo. The README is the public,
user-facing page — keep setup/usage there and keep it short; detail belongs here.

## Commands

```bash
uv run pytest          # full suite (unit + Qt UI + hermetic git evidence test)
uv run ruff check      # lint
uv run ruff format     # format (--check to only report)
uv run pyright         # types: strict on src/, standard on tests/
uv run habito          # launch the UI
uv run habito doctor   # config + data-repo readiness
```

## Layers

One concern per package, dependencies point inward toward `habito.domain`:

`domain` ← `storage`, `projections`, `engine`, `backfill` ← `evidence`, `ui`

Only `habito.ui` imports Qt. Views are presentational and talk to a `Controller`
protocol, so engine/storage/projections/evidence stay UI-agnostic. `habito.app` is the
composition root and the only place that wires them together.

## The log

Append-only JSONL, partitioned by habit, then year, then month, one file per day:

```
study/2026/08/2026-08-04.jsonl
study/2026/08/2026-08-05.jsonl
study/2027/01/2027-01-01.jsonl
reading/2027/01/2027-01-01.jsonl
```

**Rules that must hold:**

- **A path segment is a partition key, never a fact.** Nothing may derive a date or a habit
  by parsing a path. Truth is `timestamp` + `tz_offset_minutes` + `habit` on the event
  itself. This is what makes timezone changes, DST and rollover changes unable to corrupt
  anything.
- **The partition is a pure function of the event** — `partition_date(event, rollover_hour)`
  and `event.habit`, no clock, no session lookup, no store config. Routing by session
  *start* would need state that a crash or restart mid-session loses, producing exactly the
  split it was trying to avoid.
- **Nothing is ever rewritten.** No migrations, no compaction, no edits. A session crossing
  the rollover simply spans two files; `read_all()` concatenates them back into one ordered
  stream and session identity travels in `session_id`.
- ISO names mean sorting paths as text *is* sorting by date, including across a year end.

`init_data` writes `<habit>/.gitkeep`, because git tracks files and not directories and the
initial commit would otherwise be empty.

## Corrections

A mistake is corrected by appending `SessionRetracted`, so the record shows both what was
claimed and that it was withdrawn.

**It files under the day it corrects**, not the day it was written: `target_date` is copied
onto the event, and `partition_date` returns it in place of `logical_date`. So the partition
stays a pure function of the event, opening the day the mistake landed on shows the
correction beside it, and a later `rollover_hour` change can't move a retraction away from
its file. A session spanning the rollover takes one retraction per day it touched, so no day
file is left asserting time the log as a whole no longer claims.

**`read_all()` drops retracted sessions**, at the deserialization boundary — the same place
schema upcasting belongs — so projections and views need no knowledge of any of this. The
two callers that want the raw stream pass `include_retracted=True`: the log view, which
shows retracted rows struck through with the retraction beneath them, and the retract
dialog, which lists sessions to pick from.

## Tags

A session may be labelled with a free-form tag — what you were studying, not a setting —
via `SessionTagged`, offered once at session end and always optional.

**Its own event, not a field on `SessionStarted`**: the tag is only known once the session
is over, and `SessionStarted` is long since written (and probably already committed) by
then. Nothing is ever rewritten to add it — `SessionTagged` carries the session's
`session_id` the same way `SessionRetracted` does, an annotation appended after the fact
rather than an edit to what already stands. Filed under today like anything else;
`target_date` doesn't apply here, since this describes the session rather than correcting
an earlier day.

**No tag list to maintain.** `projections.tags.known_tags` derives every tag on offer by
folding `SessionTagged` out of the log itself, the same shape as `find_resumable` and
`summarize_sessions` — so the picker can't drift from what the log actually says, and
skipping the prompt (the expected common case) leaves no trace at all rather than an empty
tag.

**The picker is a plain, non-editable combo**, not an editable one: large editable
`QComboBox`es have caused hard Qt aborts elsewhere in this app (see Testing). A "New tag…"
entry opens a one-line `QInputDialog` instead, the same shape Settings already uses for
"choose a custom sound file."

## Time

Three distinct things, easy to conflate:

| Concept | Where | Meaning |
|---|---|---|
| `timestamp` | on the event | the UTC instant, never adjusted |
| `tz_offset_minutes` | on the event | the offset in force *when it was written* |
| `rollover_hour` | config | where a habit-day breaks |

`local_datetime(event)` reads the wall clock off the event's own recorded offset, so
changing the timezone setting never retroactively moves history — old entries keep the
offset they had, only new ones follow the new zone.

`logical_day(local, rollover_hour)` and `logical_date(event, rollover_hour)` decide which
day something counts toward. Default `rollover_hour = 3`: studying past midnight belongs to
the evening it started, not the morning after. Storage, calendar and log view all use the
same function, so a day file holds exactly the events the calendar attributes to that day.

**Gotcha:** to read a naive datetime the user typed as being *in* a zone, use
`TimeConfig.localize` (`naive.replace(tzinfo=zone)`), **not** `naive.astimezone(zone)` —
the latter reads it as machine-local and converts, which is wrong whenever the machine's
zone isn't the configured one. This was a real bug in the backfill dialog.

`tzdata` is a hard dependency: Windows ships no IANA database and `zoneinfo` finds nothing
without it.

## Schema evolution

Events are immutable and frozen. Evolve **additively only**:

- adding an event type — fine
- adding a field **with a default** — fine
- adding a field **without** one — breaks every existing line; only while the data repo is
  still disposable
- removing, renaming, or repurposing an existing field — forbidden

There is deliberately **no `schema_version` field**. The absence of one *is* version 1.

**Every field on `BaseEvent` is required.** No defaults, `origin` included — a default there
would make an omission indistinguishable from a claim, and a backfilled event that forgot
to say so would pass itself off as verified evidence. Because they are all required, an
event is spelled out in full at each construction site and pyright rejects one that skips a
field; nothing stamps the common five on for you. The cost is that `session_id` agreeing
across a session is now a convention rather than a guarantee, so each producer
(`engine.pomodoro`, `backfill`) has a test asserting one id and the right origin across a
whole session.

## Goals

Two goals, deliberately different in kind. `daily_minutes` is the one you mean to hit every
day; `stretch_minutes` is the great-day mark and adds a star.

Each has its **own** buffer — `buffer_minutes` for the daily goal, `stretch_buffer_minutes`
for the stretch one — rather than sharing one. A great day is a bigger ask, so it reasonably
gets more slack for the same reason the daily goal has a buffer at all; the two amounts have
no reason to move together. `GoalsConfig` still refuses a config where the *buffered* stretch
threshold would sit at or below the *buffered* daily one — a generous stretch buffer can't
let the star trigger before the day would even read as met.

## Settings

`config/settings.json`, read by `config.loader.load_config` and written whole by
`save_config`. **JSON, not TOML, and the file is not documentation** — the models are. Once
comments stop being worth preserving, TOML costs a third-party writer (`tomllib` is
read-only) to produce a file with no comments in it, while JSON is `json.loads` in and
`model_dump_json` out. Every key the file can hold is on `Config`, so writing the whole
thing round-trips the settings the UI can't reach as faithfully as the ones it can. The
trade: a hand-edit made *while the app is running* is lost at the next save.

Changing a setting is two jobs, split accordingly. `config.editor.ConfigEditor` validates
it, puts it on the live `Config` and writes the file — no Qt, so what counts as a valid
setting is testable without a window. `HabitoApp` keeps only what needs widgets, in
`_retune_clock` / `_retune_goals` / `_retune_sound`.

Two entry points, because there are two ways to change a setting: `apply_work_minutes` for
the timer's duration field, and `apply_settings` for the whole dialog. The dialog's values
are validated **as one config and rejected as one** — applying section by section could
leave the goals saved and the timezone refused, with the file disagreeing with the dialog
still on screen. It also makes a Save one write instead of four.

`Applied` distinguishes **rejected** from **applied-but-unsaved** because the two look the
same to the status line but must not behave the same: a rejection changed nothing, so the
side effects have to be skipped, while a failed write still leaves the change in force for
the session. Check `outcome.ok` before the side effects; return `outcome.message` either
way. `ConfigEditor` mutates the same `Config` object the window holds, so the side effects
read the new values straight off `self._config`.

## Controls

**Never use Qt's built-in spin arrows.** They are two ~14×13px targets stacked in one
corner: because they touch, the pointer that just pressed one is resting *inside* it, so a
small nudge toward the other still lands on the first and the control reads as "the up
button stopped working". Wrap the spin in `widgets.Stepper` instead — `NoButtons` on the
spin, and `−`/`+` at 30×28 **side by side** at the right-hand end, where the native arrows
were. Side by side rather than stacked because the pointer then travels along the axis they
are separated on, across targets wider than they are tall; and grouped rather than flanking
the field because one cluster per row reads as one control. `TimerView` owns its own pair
for the same reason, stacked because there it sits beside a 52px display.

The stepper's buttons take **no focus**, so the spin box stays the single tab stop and the
existing tab chains and Up/Down keys keep working — it wraps a control without becoming one.

## Icons

Vendored SVGs (`ui/icons/`), not a font or a CDN — `svg_icons.icon(name)` is just
`QIcon(icons/<name>.svg)`. Sourced from Google's [Material
Symbols](https://github.com/google/material-design-icons) (Outlined, Apache-2.0), fetched
**unmodified** except for a `fill` attribute added to the root `<svg>` — provenance and the
exact source path per file are in `icons/LICENSE.txt`, not repeated per-icon in code.

Colour is baked into the file rather than applied at paint time (unlike qtawesome, which
this replaced), so an icon doesn't yet follow the light/dark palette or turn red in test
mode. `#e6e6e6` for the menu/dialog icons, `#ffffff` for the primary button's (white on its
accent fill), `#9aa0a6` for the muted volume icon — match whichever of those the icon sits
against rather than introducing a fourth.

## Pages

The window is a `QStackedWidget` of three pages, but only the **timer** is built at
startup. `CalendarView` and `LogView` are built the first time they're opened
(`_calendar_view()` / `_log_view()`) — a `QCalendarWidget` and a table were ~130ms of
construction and first paint, spent before the one page you actually land on could show.

`_TIMER_PAGE` / `_CALENDAR_PAGE` / `_LOG_PAGE` are therefore **page identities, not stack
indices**: a page's position in the stack now depends on what you've visited. `self._page`
tracks what's showing; use `setCurrentWidget`, never `setCurrentIndex`.

This is only safe because **a view built late is born correct**. Each folds the store on
the way in, and each is constructed from the *current* config — so `_apply_goals`,
`_apply_time` and `_refresh_calendar` can skip a view that doesn't exist yet (`if
self._calendar is not None:`) rather than building one to update it. Anything new that
pushes state at a view must follow that pattern, or it defeats the laziness and starts
building the calendar every time Settings is saved.

## Evidence

- Commit **and push** after every event — GitHub's server-recorded push time is the part
  that's hard to forge; local commit times are not.
- `GitRepo.add/commit/has_staged_changes` take a pathspec, so the worker stages the whole
  `<habit>/` tree and picks up whichever day file the event landed in.
- Backfilled events carry `origin = "backfilled"`, and the log view and `DailySummary` keep
  them separate from live evidence. The calendar deliberately does *not* — one cell per day
  has room for one question ("did this day count"), and a second encoding there was noise.
- The log view is read-only

## Testing

**A shared thing is tested once, where it lives. A use site tests only its own choices.**

Two corollaries:

- **Don't assert a constant twice.** `singleStep() == 5` *and* a click proving it moves by
  5 are one fact. Assert the constant at the use site; the behaviour is already covered
  where the widget is tested.
- **Delete a test when its reason dies.** Removing a feature means removing its tests in
  the same commit, not leaving them to be worked around.

- UI tests use pytest-qt's `qtbot` with real events through Qt's event loop; `conftest.py`
  forces `QT_QPA_PLATFORM=offscreen`.
- The evidence test stands up a local *bare* repo as a stand-in remote — no network. That
  repo pair is **session-scoped and copied per test**: standing it up costs eight git
  subprocesses (~400ms on Windows, where spawning dominates) and it is scaffolding, not
  the thing under test — every assertion there is about what the worker does afterwards.
  Test-owned setup that no assertion is about is a candidate for exactly this treatment.
- **Piping `pytest` truncates output on a crash.** Python block-buffers stdout to a pipe, so
  a hard Qt abort loses buffered progress and the dot count lies about where it died. Use
  `PYTHONUNBUFFERED=1` and grep for `Fatal|access violation` rather than reading dots.
- Large editable `QComboBox`es have caused hard Qt aborts in the suite. Prefer plain
  non-editable combos with a curated list.
