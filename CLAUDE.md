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

`domain` ← `storage`, `projections`, `engine`, `actions` ← `evidence`, `ui`

`habito.actions` (`tagging`, `backfill`, `retraction`, `voiding`, `wakeup`, `workout`) holds
the event-builder modules — one per correction/annotation kind, each turning a user action into
an event via `stamp()` in `domain.events` rather than recomputing the timestamp arithmetic
itself.

Only `habito.ui` imports Qt. Views are presentational and talk to a `Controller`
protocol, so engine/storage/projections/evidence stay UI-agnostic. `habito.app` is the
composition root and the only place that wires them together. Inside `ui`: `pages/` holds
the three `QStackedWidget` pages (see § Pages), `dialogs/` the modal `QDialog`s (named
`*_dialog.py` for what they are, not what opens them), and `widgets/` the reusable pieces
embedded in either. `app.py`, `theme.py`, `svg_icons.py`, `sounds.py` and `notifier.py`
stay at the package root as the window's own shared infrastructure, alongside `icons/`.

## Events

Everything in the log is one of the nineteen types below (`habito.domain.events.Event`,
the discriminated union pyright and Pydantic both check against). Grouped by what they're
about, not declaration order:

**Session lifecycle** — one `session_id` shared by every event from `SessionStarted` to
`SessionEnded`, minted once per `PomodoroEngine` session (or per backfill write) and never
reused. *Which* id a producer shares across a session is a convention each producer has a
test for, not something the type system enforces — but *whether an event has one at all* is
type-enforced, via `SessionEvent` (see § Session identity).

| Event | Fires when | Fields beyond the base five |
|---|---|---|
| `SessionStarted` | a session begins | `work_minutes`, `break_minutes`, `planned_rounds`, `resumed_from` (the interrupted session's id, only when continuing one — see `projections.resume`) |
| `RoundStarted` | a work round begins | `round_index` |
| `RoundEnded` | a work round ends, full-length or cut short | `round_index`, `work_seconds` (exact elapsed, so a resume never has to estimate) |
| `BreakStarted` | a break begins | `round_index` |
| `BreakEnded` | a break ends, full-length or cut short | `round_index`, `break_seconds` |
| `SessionPaused` | the timer is paused mid-phase | — |
| `SessionResumed` | the timer resumes from a pause | — |
| `TimeAdjusted` | a manual +N-minute nudge to the phase in flight | `round_index`, `delta_seconds` |
| `SessionEnded` | the session closes gracefully (never written on a crash — see `projections.resume`) | `total_work_seconds` |

**Corrections** (see § Corrections for the full rationale):

| Event | Fires when | Fields beyond the base five |
|---|---|---|
| `SessionRetracted` | a whole session is withdrawn, by session id | `target_date` (the day it corrects, not the day it was written), `reason` |
| `EventVoided` | one standalone entry — a wake-up, a workout log — is withdrawn, by event id | `target_event_id`, `target_date`, `reason` |

**Tags** (see § Tags for the full rationale; `SessionTagged`/`SessionUntagged` get
`session_id`, `TagCreated`/`TagDescribed` don't — see § Session identity):

| Event | Fires when | Fields beyond the base |
|---|---|---|
| `SessionTagged` | a session is labelled after the fact, at the session-end prompt or in the ☰ sessions dialog | `tag` |
| `SessionUntagged` | a tag is removed from a session, in the ☰ sessions dialog | `tag` |
| `TagCreated` | a tag is first named, in the tag editor | `tag` |
| `TagDescribed` | a tag's description is set or changed, in the tag editor | `tag`, `description` |

**Extras** (see § Extras for the full rationale; no `session_id` — see § Session identity):

| Event | Fires when | Fields beyond the base |
|---|---|---|
| `WakeUpLogged` | a wake-up is logged, later at the PC | `bedtime` (roughly when you went to bed — `timestamp` is the wake instant itself) |
| `WorkoutCreated` | a workout type is first named, in `WorkoutLogDialog`'s "+ New workout" | `workout` |
| `WorkoutDescribed` | a workout type's description is set or changed | `workout`, `description` |
| `WorkoutLogged` | one or more workouts are logged, later at the PC | `workouts` (a list — one log entry can cover more than one done in the same sitting) |

**Conventions that hold for every event, not just one family:**

- `timestamp`, `tz_offset_minutes`, `origin` and `habit` are on every event and every one
  is required — no defaults, so nothing stamps them on for you and each construction site
  spells them out in full (see § Schema evolution). `event_id` is the one exception,
  defaulted via `default_factory=uuid4` — nothing meaningful is lost by not spelling out a
  fresh id. `SessionEvent` adds a fifth required field, `session_id` — not on every event;
  see § Session identity for which events get it and why.
- Evolution is additive-only: a new event type or a new field with a default is fine;
  removing, renaming, or repurposing a field is not (see § Schema evolution).
- Nothing is ever rewritten. A correction, a retraction, a changed description — all of
  these are a later event appended, never an edit to one already written.

## Session identity

`session_id` lives on `SessionEvent` (`domain.events.SessionEvent`), not on `BaseEvent`
itself. Every event genuinely about one Pomodoro session extends `SessionEvent`:
`SessionStarted` through `SessionEnded`, `SessionRetracted`, `SessionTagged`,
`SessionUntagged`. An event that isn't about any particular session — `TagCreated`,
`TagDescribed`, `WakeUpLogged`, the `Workout*` family, `EventVoided` — extends `BaseEvent`
directly, with no `session_id` field at all. `EventVoided` is the load-bearing case: it
targets one event by its `event_id`, so a `session_id` there would claim a correlation it
does not have *and* make it look like something `SessionRetracted` ought to be able to
reach.

**The rule, for any new event type:** decide whether it belongs to one specific session
before writing it. If yes, extend `SessionEvent`. If no, extend `BaseEvent` directly. Never
mint a throwaway `session_id` to satisfy a field that isn't meaningful for it — the field's
presence is a **claim** that this event correlates with others sharing that id, and a
random one falsely stakes that claim.

**Why this replaced "every event gets one":** originally every event, session-scoped or
not, carried `session_id`, with a freshly-minted, unused one for `TagCreated`/
`TagDescribed` (and, briefly, `WakeUpLogged`). That looked harmless — nothing read it for
meaning — until `projections.sessions.summarize_sessions`, which groups *by* `session_id`,
treated each throwaway one as defining its own session. Creating a tag while tagging a real
session could turn one session into three rows in "Manage sessions…". Splitting the base
class turns that class of bug into a build-time one: reading `.session_id` off a bare
`Event` without first narrowing to `SessionEvent` is now a pyright error, not a silent
runtime artifact — see the `isinstance(_, SessionEvent)` narrowing this forced in
`projections.sessions`, `projections.tags.session_tags`, `projections.resume`,
`domain.events.drop_corrected`, `ui.app._compute_today_baseline` and `ui.pages.log_view`.

**Doesn't touch history.** Historical `TagCreated`/`TagDescribed` lines already written to
the data repo still hold a `session_id` key from before this split — left exactly alone,
never rewritten (see § The log's "nothing is ever rewritten"). Pydantic's default
`extra="ignore"` behaviour drops an unrecognised field silently on load, so those old lines
keep parsing exactly like new ones without it. No migration needed, none attempted.

**Flag it, don't work around it.** If a future feature turns out to want its own events
genuinely correlated to each other — a multi-event "workout session," say — that's a
decision for whoever's building it to raise explicitly: extend `SessionEvent` (if it's
honestly a Pomodoro-shaped session) or introduce its own, differently-named correlation id
(if `session_id`'s Pomodoro-specific meaning doesn't fit). Don't quietly reuse `session_id`
for something it was never meant to mean, and don't add a second ad-hoc id field to route
around this. If either is starting to feel necessary, that's the point to stop and
reconsider the split itself instead.

**This actually came up, and the answer was "don't."** `WorkoutLogged` could have gone the
correlated-events route — one event per workout in a log entry, sharing a fresh `log_id` —
to get `SessionTagged`/`SessionUntagged`-style per-item correction later. Instead
`workouts` is a plain `list[str]` on one event: nothing about logging several workouts at
once is actually correlated the way a session's rounds are, so minting an id for it would
have been exactly the "throwaway, nothing reads it for meaning" mistake this section warns
about. The accepted cost is coarser correction — a future undo mechanism (see §
Corrections) could only void a whole `WorkoutLogged` entry, never surgically remove one
wrong workout out of three — which was a deliberate trade, not an oversight.

## Origin

`origin` (`domain.events.Origin`) answers one precise question: **is `timestamp` the
moment this event was actually recorded, or a claimed moment typed in some time after?**
`live` for the former, `backfilled` for the latter. Everything else it might look like it's
answering — how old the thing the event is *about* is, how much you trust it, whether it
counts as "real work" — is a consequence of that one question, not a separate judgement
call to make per event type.

**It is not a judgement about the age of what's being described.** A tag attached to a
session from three days ago, via a row's "Manage tags…" in the sessions manager, is still
`live`: attaching a tag is
an act that happens the instant you do it, so `timestamp` genuinely *is* "now" when
`actions.tagging.build_session_tagged_event` builds it — not some earlier instant you
typed in. `TagCreated`/`TagDescribed` are `live` for the identical reason; so are
`SessionRetracted` and `EventVoided` — withdrawing something is an act that happens the
instant you do it, whatever the age of what it withdraws — and so are
`WorkoutCreated`/`WorkoutDescribed` — naming or describing a workout type, in
`WorkoutLogDialog`'s "+ New workout"/double-click, is exactly as much an in-the-moment act
as naming a tag. Contrast a backfilled Pomodoro session (`actions.backfill`), a wake-up
(`actions.wakeup`), or a logged workout (`actions.workout`): there, `timestamp` is a
*claimed* instant — the round you say you worked, the moment you say you woke, when you say
you did the workout — that provably differs from when the event was actually written,
because you're describing something that already happened by the time you open the dialog.

**`WakeUpLogged` and `WorkoutLogged` are always `backfilled`, and that's correct, not merely
constant.** There's no possible "live" wake-up or workout log short of a future sensor
pinging the app the instant it happens — the entire workflow is "write down, later, what
already happened." A field being the same value on every instance of an event type isn't a
code smell by itself (unlike `session_id` minting a fresh, meaningless value per event —
see § Session identity); it's only worth revisiting if some consumer reads it for
information it doesn't actually carry, which isn't the case here.

**For any new event type:** ask whether `timestamp` will be "now" at the moment you
construct it, or a moment you're reconstructing/claiming. That answer is `origin` — it
isn't a free choice made per instance the way `habit` or a tag name is.

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

**Two mechanisms, and which one applies is settled by the event's own shape, not by a
judgement call.** A whole Pomodoro session is withdrawn by `SessionRetracted`, keyed by the
`session_id` every one of its events carries. One standalone entry — a wake-up, a workout
log — is withdrawn by `EventVoided`, keyed by that single event's `event_id`. Neither can
reach the other's targets: `EventVoided` structurally cannot name a session (it has no
`session_id` to filter on), and `actions.voiding.build_void_event` refuses a `SessionEvent`
outright rather than letting a caller try. A second, overlapping way to void the same
events would be two undo systems fighting over one job.

**A correction files under the day it corrects**, not the day it was written: `target_date`
is copied onto the event, and `partition_date` returns it in place of `logical_date`. So
the partition stays a pure function of the event, opening the day the mistake landed on
shows the correction beside it, and a later `rollover_hour` change can't move a correction
away from its file. A session spanning the rollover takes one `SessionRetracted` per day it
touched, so no day file is left asserting time the log as a whole no longer claims; an
`EventVoided` targets one event, which has exactly one day, so one is always enough.

**`build_void_event` takes the target event, not its id.** `habit` and `target_date` are
then read off what's being voided rather than recomputed by each caller — a void written
under the wrong habit lands in a store that never reads it (`read_all` filters per habit),
and one under the wrong day files away from what it corrects. Both were reachable when the
builder took a bare `UUID`.

**`read_all()` drops everything a correction withdrew**, at the deserialization boundary —
the same place schema upcasting belongs — so projections and views need no knowledge of any
of this. `domain.events.drop_corrected` applies both rules in one pass, collecting each set
first because a correction files under the day it corrects and so can appear *ahead* of
what it withdraws in the concatenated stream. The two callers that want the stream exactly
as written pass `read_all(raw=True)`: the log view, which shows corrected rows struck
through with the correction beneath them, and `ManageSessionsDialog`, which needs to
recognise an already-retracted session so it can leave it off the list.

**Editing an entry is a void plus a fresh entry, submitted together.** Nothing is ever
rewritten, so "I logged the wrong time" is the old entry withdrawn and the corrected one
appended, in one `on_submit` batch (see `EntryManagerDialog._edit`). Two consequences worth
knowing: the void is built *inside* the form's submit callback, so backing out of the form
writes nothing at all; and this is what makes `WorkoutLogged`'s all-or-nothing granularity
survivable — one entry covering three workouts can't be voided one workout at a time (see §
Session identity), but unticking the wrong one and saving reaches the same place.

**Reinstating** is the same move in reverse: a retracted session is backfilled again, a
voided entry logged again.

## Managing

**One ☰ entry per stream of things you log, each opening that stream's manager.** The menu
is `Sessions… / Sleep… / Workouts…` (the last two only when extras are on), and a manager is
always the same three parts: the list of what's there, a primary button that opens that
stream's own logging form, and a right-click menu per row. Backfill and the tag catalog have
no menu entries of their own — adding a session and correcting one belong in the same
window, and a tag only ever means something on a session.

| Manager | Adds with | Row actions | Unit |
|---|---|---|---|
| `ManageSessionsDialog` | `BackfillDialog` | Manage tags…, Retract session… | a whole session, by `session_id` |
| `EntryManagerDialog` (Sleep) | `WakeUpDialog` | Edit…, Void… | one `WakeUpLogged` |
| `EntryManagerDialog` (Workouts) | `WorkoutLogDialog` | Edit…, Void… | one `WorkoutLogged` |

**Sleep and workouts share one class; sessions don't.** A wake-up and a workout log differ
only in what a row says and which form adds one, so `EntryManagerDialog` takes those as data
(`reload`, `open_form`) rather than being copied. A session is many events voided as one and
its row menu offers tagging rather than editing, so `ManageSessionsDialog` stays its own
class. What both genuinely share is the list, `ui.widgets.entry_list.EntryList` — extracted
once there were two real embedders wanting the identical widget, the same bar `CatalogPicker`
was generalized at, not a hypothetical third.

**Rows are handed over already rendered.** `EntryManagerDialog` takes `ManagedEntry(summary,
event)` rather than a `describe` callback, so it never has to name a concrete event type —
which is what lets it be one non-generic class serving two streams. The rendering lives in
`ui.dialogs.entry_summaries`, the counterpart to `describe_session`.

**A manager is handed a `reload`, never a snapshot.** Anything written from inside it — a
backfilled session, an edited wake-up, a tag attached through a row's dialog — has to appear
in the list behind the form that wrote it, and re-folding the log is the only way that can't
drift from what the store actually holds. `now` is a callable for the same reason: a manager
can sit open for hours, and a correction records when it was made.

**Double-click a row to edit it**, matching the gesture that edits a catalog entry one
dialog further in (see § Tags). The right-click menu keeps the action discoverable and adds
the destructive one beside it. `EntryList` emits `row_activated` either way;
`ManageSessionsDialog` leaves it unconnected, because a session has no "edit" and guessing
at one would be worse than nothing happening.

**Nesting stops here.** Workouts already reach three modals deep (manager → log form →
catalog editor). The size tiers still line up (Browse → Browse → Compact), but a fourth
level means the shape needs rethinking, not another dialog.

## Tags

A session may be labelled with a free-form tag — what you were studying, not a setting —
via `SessionTagged`, offered once at session end and always optional. Tags can also be
added or removed well after the fact — retroactive tagging needs `SessionUntagged` as much
as `SessionTagged`, since undoing an accidental or outdated tag is an append too, never an
edit to the original.

**No tag list to maintain.** `projections.tags.known_tags` derives every tag on offer by
folding `TagCreated` / `TagDescribed` / `SessionTagged` out of the log itself, the same
shape as `find_resumable` and `summarize_sessions`. `projections.tags.session_tags` folds
the same way for one session's *current* tags — `SessionTagged` adds, a later
`SessionUntagged` for the same tag removes it, "later wins" the same shape as
`tag_descriptions`.

**Four tag events, one job each — never one event wearing two meanings.**
`TagCreated` marks that a tag exists; `TagDescribed` sets or changes its description;
`SessionTagged` puts one on a session; `SessionUntagged` takes it back off — a later,
appended fact, never an edit to the `SessionTagged` it reverses.

**One picker and one editor, shared with workouts — and the picker *is* the catalog
manager.** `ui.widgets.catalog_picker.CatalogPicker` is the checkable `Name | Description`
tree used by the session-end "+ Attach tag" prompt, `SessionTagDialog` (tag or untag one
session after the fact), and `WorkoutLogDialog`'s workout picker.
`ui.dialogs.catalog_edit_dialog.CatalogEditDialog` is the editor all three open, by
double-click on a row or by "+ New …". These were originally `TagPicker`/`TagEditDialog` —
generalized once workouts needed the identical name-and-description-tree shape, rather than
duplicated as `WorkoutPicker`/etc.: two real call sites wanting the exact same widget, not a
hypothetical future one, is the point past which sharing beats duplicating. `noun` (`"tag"`
/ `"workout"`) is the only thing that varies in the label text; `build_created`/
`build_described` are the two event-builders a call site binds to its own `habit`/`now` (via
a `lambda`, matching the rest of the codebase's callback-adapting convention — not
`functools.partial`, which has no other precedent here) before handing them in, so the
shared widgets never need to know which domain they're serving.

**There is no separate catalog-manager dialog, and adding one back would be a mistake.**
There used to be a `CatalogManagerDialog` — a ☰ "Manage tags…" entry, and briefly a
"Workout types…" button beside "Log workout…". It was `CatalogPicker` with `checkable=False`
and nothing of its own: every call site already passes the *whole* catalog
(`known_tags`/`known_workouts`), so a picker already shows everything a manager would, and
creating and describing entries already happen through it. Deleting it took the `checkable`
flag with it — the picker is now always checkable — and the two buttons that opened it.
Two things make that safe, and both must keep holding: `CatalogEditDialog` writes its
`TagCreated`/`TagDescribed` on Save, *before* returning, so a description fixed inside a
picker stands even if the embedding dialog is then cancelled; and `CatalogPicker` appends
"Double-click a … to change its description." to whatever `hint` a call site passes, rather
than trusting each to say it, because double-click is now the only route to the editor and
one call site forgetting would hide the catalog entirely.

The accepted cost: with no session in the log there is no door to the tag catalog at all
(both are reached from a session-tagging flow). A tag with nothing to label does nothing, so
this is a real loss rather than a wash, but not one worth a dialog.

`checked` seeds which rows start ticked — empty for a session that just ended or a fresh
`WorkoutLogDialog` (nothing's picked yet), a session's current tags
(`projections.tags.session_tags`) for `SessionTagDialog`, where unchecking a pre-ticked row
is how you untag it, and a logged entry's own workouts when `WorkoutLogDialog` is editing
one. `SessionTagDialog` itself writes nothing per click — it diffs the tree's final checked
state against what it opened with into exactly the `SessionTagged`/`SessionUntagged` events
that changed, only on "Apply Tags" — a muted line above the buttons tracks that same diff
live ("No changes" / "N tags changed") so the click isn't a surprise.

`CatalogPicker` builds "+ New …" (so every call site opens the same editor) but doesn't lay
it into its own layout: what sits beside it is each embedding dialog's own choice — never a
big button stretched to the container's width, stacked above another. It stays a plain
button in every case, because some other button is always the embedding dialog's primary
action (Apply Tags, Log & commit).

## Extras

Personal, non-Pomodoro habits — logging when you woke up, logging a workout — live behind
`config.extras.enabled`, off by default, one flag for the whole group rather than one per
habit. The flag is **hand-edit-only** in `settings.json`, deliberately with no
Settings-dialog widget: it's a once-per-install "which build am I running" choice, like
`paths.data_repo`, not something you'd revisit (see § Settings for the general "default to
a widget" rule this is the documented exception to). When it's off, the whole feature is
invisible — no ☰ menu entries, no Settings section, no second or third `EventStore` even
gets constructed.

**Second and third habits, not a second app.** Wake-up and workout logging reuse every
piece of existing infrastructure rather than inventing a parallel one: the same `EventStore`
(already parameterized by habit name — nothing habit-specific to generalize), the same
JSONL/day-file layout, the same evidence mechanism. Each is filed under its own habit
directory (`config.extras.wakeup.habit` / `config.extras.workout.habit`, default `sleep` /
`workout`) alongside `study`, so `habito.app` builds a *second* and *third* `EventStore`
when extras are enabled and hands all three to `HabitoApp`.

**One `EvidenceWorker` still, not one per habit.** Three threads issuing git commands
against the same repo would race, so the composition root keeps a single worker whose
pathspec is `"."` — the whole data repo — rather than one habit's subtree. Safe because the
data repo holds nothing but habit directories and a `.gitignore`. The study store and (when
present) the wake-up and workout stores all `.subscribe()` the same `EvidenceRecorder`.

**`WakeUpLogged` is a single fact, not a session.** It doesn't fit the
`SessionStarted…SessionEnded` family — there are no rounds or breaks to a wake-up — so it's
its own event, following the same shape a backfilled event already uses: `timestamp` is the
actual wake instant (a real historical fact, not "when you clicked the button"), and
`bedtime` is the one thing worth recording alongside it — roughly when you went to bed the
evening before. Named `bedtime`, not "asleep at": you can attest to when you went to bed,
not the moment you actually fell asleep. `origin` is always `backfilled` — you're always at
the PC logging this after the fact, typically well after actually waking, so unlike a live
Pomodoro session there's no "in the moment" case to distinguish it from.

**`WakeUpDialog` is modeled on `BackfillDialog`**, right down to reusing
`TimeConfig.localize()` for both times you type — the wake instant and the bedtime — so a
machine set to the wrong zone still stamps events in *your* zone, never the machine's (see §
Time's documented gotcha). The dialog asks for exactly three things — date, wake time,
bedtime — and infers which calendar day the bedtime falls on: if the picked bedtime clock
value would land on or after the wake instant (the normal case — you went to bed the evening
before), it's dated the day before; a bedtime after midnight (asleep 01:00, woke 08:00 the
same day) needs no adjustment. `config.extras.wakeup.default_wake_time` /
`default_bedtime` seed the dialog's fields, so a normal day is one click.

Unlike the flag itself, **the wake/bedtime defaults do get a Settings-dialog section** —
shown only when extras are enabled — since those are values worth tweaking occasionally,
not a one-time install choice.

**`WorkoutLogDialog` is both "log an instance" and "manage the catalog"** — its embedded
`CatalogPicker` offers double-click-to-edit and "+ New workout" (see § Tags for why that is
the *only* catalog surface, for tags as much as workouts). Opening it just to fix a
workout's description and pressing Cancel afterwards is a normal use, not a workaround: the
description write already landed on Save. It's sized at `BROWSE_DIALOG_WIDTH`/`_HEIGHT` from
the start, unlike `SessionCompleteDialog`'s tag picker, which starts Compact and only grows
once revealed: there, attaching a tag is optional and skipping it is the common case; here,
picking at least one workout is the point of opening the dialog, so there's no collapsed
state worth having.

**Both forms take a `replacing` argument, and it only seeds the fields.** `WakeUpDialog` and
`WorkoutLogDialog` fill their date/time (and, for workouts, which rows start ticked) from an
existing entry and rename the window and its button — "Edit wake-up" / "Save & commit"
rather than "Log wake-up" / "Log & commit". What they *write* is unchanged: one honest event
either way. The void that turns that into a correction is `EntryManagerDialog`'s to add (see
§ Corrections), which is what keeps a form that produces exactly one event from growing a
second job.

**`WorkoutLogged.workouts` is a list, not one event per workout.** A single log entry (one
date, one time) can cover several workouts done in the same sitting; see § Session identity
("This actually came up, and the answer was 'don't'") for why that's a list field rather
than several events sharing a fresh correlation id, and § Corrections for the coarse-only
correction tradeoff that follows from it. `origin` is always `backfilled`, for the identical
reason `WakeUpLogged`'s is (see § Origin) — the workflow is always "write down, later, what
already happened," never "in the moment." Unlike wake-up, there's no `default_wake_time`-
style config for the log time: `WorkoutLogDialog` defaults it to *now* rather than a
configured value, since you're usually logging a workout you just finished.

**The log view merges all three streams**, unlike the calendar (which stays study-only —
neither `WakeUpLogged` nor `WorkoutLogged` has `RoundEnded`s for the goal math to count, so
there's nothing for it to show). `HabitoApp.show_page` reads all three stores with
`read_all(raw=True)` — raw for every one of them, since the log view is the one place a
correction is shown beside what it corrects — and hands `LogView` the combined list.
Day-grouping (`partition_date`) is already habit-agnostic, so nothing there needs to know
which stream a row came from; `describe()` carries a case per event type. The sessions
manager stays study-only on purpose: none of these are a session.

None of `WakeUpLogged`, `WorkoutCreated`, `WorkoutDescribed`, `WorkoutLogged`, `EventVoided`
mint a `session_id` at all — each extends `BaseEvent` directly, not `SessionEvent` (see § Session
identity for the full rationale, including the "Manage sessions…" bug that shape once
caused for `TagCreated`/`TagDescribed`, and why every event added here since was designed
that way from the start rather than needing the same fix).

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

`stamp(local)` is the other direction — a timezone-aware local instant in, `(timestamp,
tz_offset_minutes)` out, raising on a naive one. Every event-builder module (`tagging`,
`backfill`, `retraction`, `voiding`, `wakeup`, `workout`) calls this rather than each
computing `.utcoffset()` and
`.astimezone(UTC)` itself: that computation used to be copied three times over, once per
module, which is exactly the kind of duplication worth a shared helper rather than a
fourth copy the next time an event needs building. It does *not* auto-fill these fields on
`BaseEvent` itself, on purpose — see § Schema evolution on why nothing stamps the common
fields on for you; this only removes the copy-pasted arithmetic, not the requirement that
every construction site still spells out the result explicitly.

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

**Every field on `BaseEvent` is required, except `event_id`.** No defaults on `timestamp`,
`tz_offset_minutes`, `origin` or `habit` — `origin` most pointedly: a default there would
make an omission indistinguishable from a claim, and a backfilled event that forgot to say
so would pass itself off as verified evidence. Because they are all required, an event is
spelled out in full at each construction site and pyright rejects one that skips a field;
nothing stamps them on for you. `event_id` defaults via `default_factory=uuid4` — a fresh
id is always a fine answer for a field nothing correlates against, unlike the rest.
`SessionEvent.session_id` is required the same deliberate way (see § Session identity for
why it isn't on `BaseEvent` itself). The cost is that it *agreeing* across a session is a
convention rather than a guarantee, so each producer (`engine.pomodoro`, `backfill`) has a
test asserting one id and the right origin across a whole session.

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

**Default to a widget.** Most settings belong in the Settings dialog; hand-edit-only is the
exception, earned by a concrete reason (e.g. `paths.data_repo` and the git remote config are
set once per machine, and `extras.enabled` is a which-build-is-this choice — see § Extras).
When in doubt, wire it up.

Two entry points, because there are two ways to change a setting: `apply_work_minutes` for
the timer's duration field, and `apply_settings` for the whole dialog. The dialog's values
are validated **as one config and rejected as one** — applying section by section could
leave the goals saved and the timezone refused, with the file disagreeing with the dialog
still on screen. It also makes a Save one write instead of four.

## Controls

**Dialogs pick one of three sizes rather than their own numbers** (`ui.widgets`:
`COMPACT_DIALOG_WIDTH`, `BROWSE_DIALOG_WIDTH`/`_HEIGHT`, `LARGE_DIALOG_WIDTH`/`_HEIGHT`). A
size is about a dialog's *job*, not how much it could ever hold — unbounded content (a
growing tag list) scrolls rather than earning its dialog a bigger window:

| Tier | Width | Height | Job | Dialogs |
|---|---|---|---|---|
| Compact | 320 | content-driven | one ask, or a short form | `PhaseDialog`, `SessionCompleteDialog` (collapsed), `CatalogEditDialog`, `BackfillDialog`, `WakeUpDialog`, `ResumePromptDialog`, `RetractConfirmDialog`, `VoidConfirmDialog` |
| Browse | 440 | 360 | pick one thing from a list, or manage a small growing one | `ManageSessionsDialog`, `EntryManagerDialog`, `ShortcutsDialog`, `SessionTagDialog`, `WorkoutLogDialog`, `SessionCompleteDialog` (tag picker showing) |
| Large | 460 | 580 | everything at once | `SettingsDialog` only — reuses the size `HabitoApp` already gives the calendar/log pages (`_PAGE_SIZES`) rather than a fourth number, and scrolls its form internally (see its own module docstring) instead of growing past it |

Compact is the one tier that isn't a fixed box: nothing sets a minimum height, so it's the
same width every time but not the same pixel size — a longer message is a taller dialog,
not a scrollbar.

**Never use Qt's built-in spin arrows.** They are two ~14×13px targets stacked in one
corner: because they touch, the pointer that just pressed one is resting *inside* it, so a
small nudge toward the other still lands on the first and the control reads as "the up
button stopped working".

**Two button tiers, reused rather than rebuilt per view — same size either way, only the
colour differs.** `widgets.button(text, object_name)` with no object name is the plain,
unstyled case — Close, Cancel, "+ New tag" — anything that isn't the thing the dialog
exists to do. `object_name="primary"` is the accent colour, for whichever button *is* the
thing the dialog exists to do — Save, Retract & commit, Void & commit, Add & commit, Log &
commit, Apply Tags, Backfill…, Log wake-up…, Log workout…, Resume, Done, Start round N

**A dialog's primary button is always also its default button** (`setDefault(True)`, or
`widgets.primary_button(text)`, which bundles the two) — whether it was built with
`widgets.button()` or pulled out of a `QDialogButtonBox`.

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
`_PAGE_SIZES`/`_PAGE_MINIMUMS` give the log the calendar's own size rather than its own —
its rows are short enough that a wider window just left space empty.

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
- `GitRepo.add/commit/has_staged_changes` take a pathspec. The composition root passes `"."`
  (the whole data repo), not one habit's tree — the repo holds nothing but habit
  directories and a `.gitignore`, so this is what lets one `EvidenceWorker` (one thread, one
  git-command queue) serve every habit's store rather than needing one worker per habit
  (see § Extras).
- Backfilled events carry `origin = "backfilled"`, and the log view and `DailySummary` keep
  them separate from live evidence. The calendar deliberately does *not* — one cell per day
  has room for one question ("did this day count"), and a second encoding there was noise.
- The log view is read-only. Every correction is made from a manager (see § Managing);
  the log stays the place you read what happened, not a place you change it.

## Testing

**A shared thing is tested once, where it lives. A use site tests only its own choices.**

Two corollaries:

- **Don't assert a constant twice.** `singleStep() == 5` *and* a click proving it moves by
  5 are one fact. Assert the constant at the use site; the behaviour is already covered
  where the widget is tested.
- **Delete a test when its reason dies.** Removing a feature means removing its tests in
  the same commit, not leaving them to be worked around.
- **A dialog handed a `reload` gets tested through a real log.** `ManageSessionsDialog` and
  `EntryManagerDialog` take a callable that re-folds events, so their fixtures hold a
  mutable event list and stub sub-dialogs append genuine events to it. "The row disappeared"
  then has to be a consequence of the correction actually landing, not of the dialog
  patching its own state — which is the bug that shape exists to prevent.

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
