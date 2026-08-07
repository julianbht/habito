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

Type-check strictness lives in `pyproject.toml`, not per-editor. Tests sit at `standard`
because strict wants an annotation on every parameter and a pytest fixture arrives as a
bare one — that alone was ~1700 findings that said nothing about whether the code works.

`uv run pre-commit install` once per clone wires ruff and the whitespace/TOML/YAML checks
into commits. CI runs all four checks on a clean machine.

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
also keeps every file under GitHub's 1 MB render limit, and means a finished day's file is
only ever appended to by a correction — so a touched old file stands out in the history.

**Month directories are for browsing** — a year holds 365 entries. Both levels are
zero-padded so `08` sorts before `10`, and the file keeps its full ISO name so it
identifies itself when opened away from its directory.

**Habit at the top** gives each habit its own git pathspec, so a commit stages exactly one.

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

**One event type, targeting a session.** There is no inverse per event type. A mistake is
made in whole sessions ("that hour went in under the wrong date"), so the retraction names
a `session_id` and every event carrying it stops counting. It applies to live sessions as
well as backfilled ones. To reinstate a retracted session, backfill it again.

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

The cost is one extra pass over a stream every consumer already replays in full, and the
set is collected before filtering so the result doesn't depend on stream order (a retraction
of a rollover-spanning session sits in the earlier day's file, ahead of events it voids in
the later one).

`RetractDialog` sits in the ☰ menu beside Backfill, the other correction made by hand. The
log view stays read-only: retracting appends to the log like everything else.

## Habits

`habit` is required on every event, with no default. A default would make "absence means
study" a rule you'd have to know to read the log — a fact asserted by omission. Required on
`PomodoroEngine` and `build_backfill_events` too, the layers that build events.

Config's top-level `habit` is both stamped on the events and the directory they land in, so
the two can't drift. `HABIT_PATTERN` (`^[a-z0-9][a-z0-9_-]*$`) keeps a name usable as a path
segment; lowercase because Windows filesystems are case-insensitive, so `Study` and `study`
would be two strings but one directory.

An `EventStore` is scoped to one habit for reading: it writes wherever the event says, but
`read_all()` replays only its own subtree. The app is single-habit end to end — a second
habit means a second config.

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

`widgets.StepSpinBox` snaps stepping onto multiples of the step size. Plain `QSpinBox` adds
the step to whatever is there, so an off-grid value stays off it forever (47 → 52 → 57);
snapping spends the first press rounding onto the grid, in the direction of travel so a
press never moves the value backwards.

**Step size follows how the value is used, not how big it is.** The goal moves in 5s
because it's a target you pick roughly; a break moves in 1s because it's tuned against how
long a break actually feels. Same widget, different `singleStep`.

## Evidence

- Commit **and push** after every event — GitHub's server-recorded push time is the part
  that's hard to forge; local commit times are not.
- `GitRepo.add/commit/has_staged_changes` take a pathspec, so the worker stages the whole
  `<habit>/` tree and picks up whichever day file the event landed in.
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
