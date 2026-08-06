# CLAUDE.md

Technical notes and design rules for working in this repo. The README is the public,
user-facing page — keep setup/usage there and keep it short; detail belongs here.

## Commands

```bash
uv run pytest          # full suite (unit + Qt UI + hermetic git evidence test)
uv run ruff check      # lint
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

**Why per-day and not one file.** Every event is committed *and pushed* the moment it
happens. Git stores a whole new blob of the changed file per commit, so a single growing
log would make each commit cost more than the last one, forever — at ~40 events/day, a
year-three file would churn GBs of loose objects between garbage collections. A day file
stops growing when the day ends, so commit cost is O(1) in log age rather than O(n). It
also keeps every file under GitHub's 1 MB render limit, and means an old day's file is
never touched again — so a change to one stands out in the history.

**Why the month level.** Browsing only. A year directory reaches 365 entries, which no
file listing shows usefully. The file keeps its full ISO name rather than shrinking to
`05.jsonl`, so it still identifies itself once opened or downloaded away from its
directory. Both levels are zero-padded, so `08` still sorts before `10`.

**Why habit at the top and not `logs/`.** Everything in the data repo is a log, so `logs/`
named nothing; the repo root now browses as a list of habits. Each habit's tree is also its
own git pathspec, so a commit stages exactly one habit.

**Rules that must hold:**

- **A path segment is a partition key, never a fact.** Nothing may derive a date or a habit
  by parsing a path. Truth is `timestamp` + `tz_offset_minutes` + `habit` on the event
  itself. This is what makes timezone changes, DST and rollover changes unable to corrupt
  anything.
- **The partition is a pure function of the event** — `event.habit` and
  `logical_date(event, rollover_hour)`, no clock, no session lookup, and no reference to
  how the store happens to be configured. Routing by session *start* would need state that
  a crash or restart mid-session loses, producing exactly the split it was trying to avoid.
- **Nothing is ever rewritten.** No migrations, no compaction, no edits. A session crossing
  the rollover simply spans two files; `read_all()` concatenates them back into one ordered
  stream and session identity travels in `session_id`.
- ISO names mean sorting paths as text *is* sorting by date, including across a year end.

`init_data` writes `<habit>/.gitkeep`, because git tracks files and not directories and the
initial commit would otherwise be empty.

## Habits

`habit` is a **required** field on every event, with no default — deliberately, even though
there is exactly one habit today and it puts a constant on every line for now. The parallel
to `schema_version` (§ Schema evolution) doesn't hold: absence-is-v1 stays unambiguous
forever, but a study-only log *will* eventually sit beside a reading one, and then "no field
means study" is a rule a human reading the file has to be told. That's a fact asserted by
omission — the thing the `timestamp`/`tz_offset_minutes` design exists to prevent. It was
added while the data repo was still disposable, which is the only free window for it.

Required all the way up, too: `PomodoroEngine` and `build_backfill_events` take `habit` as a
required keyword. A default at either would put the hole straight back into the layer that
actually builds the events.

One value, one meaning: config's top-level `habit` is stamped on the events *and* is the
directory they land in, rather than a config path and an event field that could drift.
`HABIT_PATTERN` (`^[a-z0-9][a-z0-9_-]*$`) is a path-safety rule as much as a style one — a
name with `/` or `..` would quietly nest or escape the tree. Lowercase specifically because
Windows filesystems are case-insensitive: `Study` and `study` would be two distinct strings
on the events but one single directory on disk.

An `EventStore` is *scoped* to one habit for reading — it writes wherever the event says,
but `read_all()` only replays its own subtree, so a second habit can't leak into this one's
calendar. The app is still single-habit end to end: one config value, one store, one engine.
Running a second habit today means a second config.

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
- adding a field **without** one — breaks every existing line, so only while the data repo
  is still disposable. `habit` was added exactly there (§ Habits); assume that window is
  closed now.
- removing, renaming, or repurposing an existing field — forbidden

There is deliberately **no `schema_version` field**. The absence of one *is* version 1, so
it can be introduced on the day something first breaks and old lines still read correctly —
adding it now would put a meaningless `"schema_version":1` on every line of an evidence log
forever. When a break does come, add the field to *that event type only*, and upcast on
read (raw dict → current shape, at the deserialization boundary in `read_all`) rather than
teaching every consumer about old shapes. If a change can't be upcast honestly, introduce a
new event type instead of inventing data.

## Goals and the calendar

Two goals, deliberately different in kind. `daily_minutes` is the one you mean to hit every
day and colours the cell green; `stretch_minutes` is the great-day mark and adds a star.
`buffer_minutes` applies to **both** — if 95 counts as 100, then 145 has to count as 150.
The stretch goal is off by default (`None`; the TOML and the Settings spin both spell that
`0`, since TOML has no null).

Two thresholds rather than a colour gradient on purpose: "met" and "well past it" are
categories, and a ramp encodes a continuum nobody can read back off a 40px cell without a
legend. Shape is also a channel that survives colour blindness, where a green→gold ramp is
exactly the axis that collapses.

The calendar keeps **one meaning per channel**: fill = met, star = stretch. That's why the
today ring and the backfilled/verified outline were both removed — three encodings in one
small cell cost more than they told you. Anything needing more nuance belongs in the log.

`Palette.star` is per-theme because the light background's green fill is bright enough that
a mid amber nearly matches its luminance; light gets a deeper one. Still one colour per
theme, not a ramp.

## Evidence

- Commit **and push** after every event — GitHub's server-recorded push time is the part
  that's hard to forge; local commit times are not.
- `GitRepo.add/commit/has_staged_changes` take a pathspec, so the worker stages the whole
  `<habit>/` tree and picks up whichever day file the event landed in — scoped to one habit,
  so a commit never sweeps up another's events.
- Backfilled events carry `origin = "backfilled"`, and the log view and `DailySummary` keep
  them separate from live evidence. The calendar deliberately does *not* — one cell per day
  has room for one question ("did this day count"), and a second encoding there was noise.
- The log view is read-only by construction, not just by omission.

## Testing

- UI tests use pytest-qt's `qtbot` with real events through Qt's event loop; `conftest.py`
  forces `QT_QPA_PLATFORM=offscreen`.
- The evidence test stands up a local *bare* repo as a stand-in remote — no network.
- **Piping `pytest` truncates output on a crash.** Python block-buffers stdout to a pipe, so
  a hard Qt abort loses buffered progress and the dot count lies about where it died. Use
  `PYTHONUNBUFFERED=1` and grep for `Fatal|access violation` rather than reading dots.
- Large editable `QComboBox`es have caused hard Qt aborts in the suite. Prefer plain
  non-editable combos with a curated list.
