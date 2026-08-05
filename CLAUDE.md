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

Append-only JSONL, partitioned one file per day:

```
logs/2026/2026-08-04.jsonl
logs/2026/2026-08-05.jsonl
logs/2027/2027-01-01.jsonl
```

**Why per-day and not one file.** Every event is committed *and pushed* the moment it
happens. Git stores a whole new blob of the changed file per commit, so a single growing
log would make each commit cost more than the last one, forever — at ~40 events/day, a
year-three file would churn GBs of loose objects between garbage collections. A day file
stops growing when the day ends, so commit cost is O(1) in log age rather than O(n). It
also keeps every file under GitHub's 1 MB render limit, and means an old day's file is
never touched again — so a change to one stands out in the history.

**Rules that must hold:**

- **A filename is a partition key, never a fact.** Nothing may derive a date by parsing a
  path. Truth is `timestamp` + `tz_offset_minutes` on the event itself. This is what makes
  timezone changes, DST and rollover changes unable to corrupt anything.
- **The partition is a pure function of the event** — `logical_date(event, rollover_hour)`,
  no clock, no session lookup. Routing by session *start* would need state that a crash or
  restart mid-session loses, producing exactly the split it was trying to avoid.
- **Nothing is ever rewritten.** No migrations, no compaction, no edits. A session crossing
  the rollover simply spans two files; `read_all()` concatenates them back into one ordered
  stream and session identity travels in `session_id`.
- ISO names mean sorting paths as text *is* sorting by date, including across a year end.

`init_data` writes `logs/.gitkeep`, because git tracks files and not directories and the
initial commit would otherwise be empty.

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
- removing, renaming, or repurposing an existing field — forbidden

There is deliberately **no `schema_version` field**. The absence of one *is* version 1, so
it can be introduced on the day something first breaks and old lines still read correctly —
adding it now would put a meaningless `"schema_version":1` on every line of an evidence log
forever. When a break does come, add the field to *that event type only*, and upcast on
read (raw dict → current shape, at the deserialization boundary in `read_all`) rather than
teaching every consumer about old shapes. If a change can't be upcast honestly, introduce a
new event type instead of inventing data.

## Evidence

- Commit **and push** after every event — GitHub's server-recorded push time is the part
  that's hard to forge; local commit times are not.
- `GitRepo.add/commit/has_staged_changes` take a pathspec, so the worker stages the whole
  `logs/` tree and picks up whichever day file the event landed in.
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
