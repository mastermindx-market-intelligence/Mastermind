# Executive Inbox — Executive OS Phase 1F-A / Phase 1F-B projection

A **read-only projection** of the durable Executive OS runtime into the small set of
things an executive seat must actually look at, and whose each one is.

The runtime (`control_plane/executive_runtime.py`) accumulates Job, Attempt, Worker,
and Event rows without bound. Almost all of them are routine: work that queued, ran,
and completed exactly as asked. Reading the ledger is not an executive act — deciding
what it *demands* is. The inbox compresses hundreds of rows into a handful of items,
each addressed to a seat, each carrying the canonical evidence it was derived from.

    durable Job/Attempt/Worker/Event rows  →  classify  →  N attention items + counts

Module: `control_plane/executive_inbox.py` · CLI: `scripts/executive_inbox.py` ·
tests: `tests/test_executive_inbox.py` (wired into the hermetic governance gate in
`.github/workflows/ci.yml`).

## Invocation

```bash
# Human-readable inbox (default)
python3 scripts/executive_inbox.py

# The mastermind.executive_inbox.v2 document
python3 scripts/executive_inbox.py --json

# Runtime only — skip boot-packet collection (no subprocess, no Agent OS read)
python3 scripts/executive_inbox.py --no-boot-packet

# Ground on a boot packet already on disk instead of collecting one
python3 scripts/ceo_boot_packet.py --json > /tmp/packet.json
python3 scripts/executive_inbox.py --boot-packet-file /tmp/packet.json

# Freeze the clock — reproducible output, byte-identical across runs
python3 scripts/executive_inbox.py --json --now 2026-08-14T00:00:00Z

# Project a different checkout (mainly tests)
python3 scripts/executive_inbox.py --root /path/to/checkout
```

`--no-boot-packet` and `--boot-packet-file` are mutually exclusive. The command
**always exits 0 once its arguments parse**.

## The boundary — a projection, not an authority

**The SQLite runtime remains the only lifecycle authority.** The inbox reads it and
says what deserves attention. It decides nothing, moves nothing, and remembers
nothing.

Specifically, this phase adds **no second control plane**: no new database, no new
table, no queue, no scheduler, no lease, no registry, no liveness store — and the
module writes **no file, ever**. Every fact it emits is derived from rows that already
exist, and it is recomputed from those rows on every call. A durable "inbox state"
would be exactly the `constraints.duplicate_control_planes` prohibition the strategic
state names.

Three neighbouring authorities are untouched:

- **The Improvement Agenda remains the company priority queue.** The inbox identifies
  *attention*; it never ranks the roadmap and never decides eligibility. An item
  appearing here says a durable row is in an exceptional state — not that the work is
  more important than anything on the agenda.
- **Agent OS remains a knowledge plane.** It is read (through the boot packet) and
  never written. A `claim:` there is an author's note, not liveness.
- **The runtime remains the execution plane.** Nothing here dispatches, claims,
  requeues, cancels, leases, schedules, or arms anything.

**Labels confer no privilege.** `target` is derived from the KIND of problem, never
from `department`, `priority`, a P0 id, an owner, an actor name, or an executive
title. `Sol` / `CEO` / `COO` are provenance labels with zero authority attached.

## Design laws

| Law | What it means here |
|---|---|
| **No second control plane** | No new store of any kind; the module writes no file. |
| **Read through the runtime's own registries** | `Runtime.at(root, create=False)` → `list_jobs` / `list_attempts` / `list_workers` / `list_events`. No raw SQL in the module. |
| **A reader never creates, migrates, or re-modes a database** | Existence is checked first, then the store is opened read-only (see below). |
| **Fail open, and name the gap** | Every unreadable input becomes a `degraded` string. Never a traceback, never a quiet success. The one exception is an unparseable `--now`, which is a usage error. |
| **No invented recommendations** | `reason` is assembled only from canonical fields; `existing_next_actions` is copied verbatim from the stored payload. |
| **Deterministic** | Same state + same `--now` ⇒ byte-identical `--json`. The clock is read at most once per build. |
| **Import-time stdlib only** | From `control_plane`, exactly `executive_runtime` and `ceo_boot_packet`; an AST test pins the set. |

### Why the read-only construction path exists

`RuntimeStore` by default creates `data/control_plane/`, creates the SQLite file,
runs migrations, chmods the file and its directory, and sets `journal_mode=WAL`.
That is correct for the execution plane and wrong for a projector.

**Existence alone was not enough.** A 0-byte husk, a truncated restore, or a foreign
SQLite file all pass `is_file()` — and a default-constructed store would write the
*entire* Executive OS schema into that file and then report the result as a company
with nothing running. So the projector opens the runtime through the minimal
read-only accessor added for it:

```python
Runtime.at(root, create=False)
```

With `create=False` the store: performs no `mkdir` and no `chmod`; connects via
SQLite `mode=ro`, which structurally refuses both file creation and every write;
sets **no** `journal_mode` or `synchronous` pragma, because setting a journal mode is
itself a write; runs **no** migration; verifies `schema_migrations` is actually
present and raises `PersistenceError` naming the path when it is not; and refuses
`transaction()` outright with `StateConflict`, so no lifecycle call can reach the
database even by mistake. `create=True` remains the default and is byte-identical to
previous behaviour for every existing caller.

**The one disclosed residue.** Opening a **WAL** database — the mode this runtime
uses — lets SQLite build its wal-index, so `-wal` and `-shm` sidecars may appear even
under `mode=ro`. They carry no committed state: the tests assert the database file's
sha256 is unchanged, its full logical dump is unchanged, and any `-wal` present
afterwards is zero-length. On a `delete`-mode database the reader creates nothing at
all, and its journal mode is still `delete` afterwards — also asserted.

**Why registry reads and not raw SQL.** A projector with its own row decoder
disagrees with the authority the first time either one moves. The cost of delegating
is visible and deliberate: one undecodable row raises out of its registry and hides
that registry's whole surface. That lands as a named `degraded` entry — a *visible*
degradation — rather than as a quietly shorter list. That trade was made on purpose;
the alternative was rejected.

## JSON schema — `mastermind.executive_inbox.v2`

| Key | Type | Meaning |
|---|---|---|
| `schema` | `str` | Always `mastermind.executive_inbox.v2`. A bump means a migration. |
| `generated_at` | `str` | ISO-8601 Z. `--now` when given, else current UTC. The only clock read. |
| `grounding` | `dict` | What this projection was computed against (below). |
| `attention` | `list` | The items, sorted (below). May be empty; empty is a claim, not an absence of data. |
| `runtime_counts` | `dict \| null` | Totals and per-status maps for jobs/attempts/workers. `null` when the database is missing or could not be opened. |
| `suppressed` | `dict \| null` | Counts of the routine jobs that were deliberately not listed. `null` when jobs could not be read. |
| `degraded` | `list[str]` | Everything that could not be read, named. Never suppressed anywhere. |

### `grounding`

| Key | Type | Meaning |
|---|---|---|
| `mastermind` | `dict` | `{root, sha, branch}` for this checkout. `sha`/`branch` are `null` when git cannot answer. |
| `macro` | `dict` | `{root, sha}` carried from the boot packet. Both `null` when no packet was read. |
| `boot_packet_schema` | `str \| null` | `mastermind.ceo_boot_packet.v1` when a packet on that schema grounded this run; `null` otherwise (including when the packet was on an unknown schema — see Degraded). |
| `runtime_db` | `dict` | `{path, present}` for the durable database. |

### `runtime_counts`

```json
{"jobs":     {"total": 20, "by_status": {"QUEUED": 3, "RUNNING": 1, ...}},
 "attempts": {"total": 16, "by_status": {"CLAIMED": 0, ...}},
 "workers":  {"total": 3,  "by_status": {"AVAILABLE": 2, ...}}}
```

Every `by_status` map carries **every** enum member, zeros included. A status that
disappeared from the map would be indistinguishable from a status that dropped to
zero, and an executive surface must never make "none of these right now" look like
"this state no longer exists". Any one of the three sub-sections is `null` on its own
when that registry could not be read; the others keep answering.

### `attention[]`

| Key | Type | Meaning |
|---|---|---|
| `attention_id` | `str` | `eia-` + first 12 hex of `sha256(schema\|target\|kind\|source\|job_id\|workstream\|reason)`. Content-addressed: no counter, uuid, or clock. A changed `reason` is a changed claim, so it changes the id. Agent OS items append their source row ordinal (below). |
| `target` | `str` | `chairman` \| `ceo` \| `coo` — which seat this belongs to. |
| `kind` | `str` | The classification (table below). |
| `source` | `str` | `runtime` (the durable database) or `agent_os` (via the boot packet). |
| `job_id` | `str \| null` | `JOB-…` for runtime items. |
| `workstream` | `str \| null` | From the Agent OS row, or from a job's CEO-intent provenance. |
| `status` | `str \| null` | The `JobStatus` value for runtime items. |
| `reason` | `str` | One sentence, assembled only from canonical fields. |
| `evidence` | `list` | `{ref, field, value}` triples naming exactly where each claim came from — e.g. `{"ref":"job:JOB-009","field":"status","value":"FAILED"}`. |
| `existing_next_actions` | `list[str]` | Copied **verbatim** from the job's stored `result.next_actions`, else its `checkpoint.next_actions`. `[]` when none. Never authored here. |
| `parent_job_id` | `str \| null` | Durable parent/container job, when this is a child. |
| `root_job_id` | `str` | Immutable root of the parent/child tree. |
| `depth` | `int` | Durable bounded hierarchy depth; root is zero. |
| `owner_seat` | `str` | Recorded seat (`coo`, `ceo`, or `chairman`); labels do not grant authority. |
| `escalation_target` | `str` | Shrink-only escalation target. |
| `business_impact` | `str` | `routine`, `material`, or `critical`; display/audit metadata, not a priority key. |
| `review_required` | `bool` | Whether the job needs an independent sibling approval before its parent can aggregate. |
| `reviews_job_id` | `str \| null` | Review job's sibling target, when this is a review job. |

**Sort order:** `(target rank chairman=0/ceo=1/coo=2, source, job_id or workstream or
"", kind)`. `--json` is emitted with `json.dumps(..., indent=2, sort_keys=True)`.

**Why Agent OS items carry an ordinal in their hash.** Runtime items are already
unique by `job_id`. Two `needs_ceo` rows can be byte-identical, and two identical
pending rulings are two rulings — without the source row index their
content-addressed ids would collide and the second would silently disappear from the
CEO's lane. The ordinal is appended only for `source: agent_os`, so runtime ids
remain exactly the documented six-part join.

## Classification

One pass over the jobs. **First match wins, and a job yields at most one item** — an
inbox that listed the same job three times would be a worse instrument than the ledger
it projects. Every runtime item is `target: coo`.

| # | Condition | `kind` | Why it is attention |
|---|---|---|---|
| 1 | status `FAILED` | `job_failed` | The work did not happen and nothing will retry it on its own. |
| 2 | status `LOST` | `job_lost` | The invocation was recorded as gone. |
| 3 | status `RATE_LIMITED` | `job_rate_limited` | Capacity, not the job, stopped it. |
| 4 | status `CANCEL_REQUESTED` | `cancel_requested` | A cancel was issued and the attempt has not acknowledged it. |
| 5 | queued/running/checkpointed parent with living children, or a review-required child without an independent completed approval | `aggregation_blocked` | Parent aggregation is a durable refusal, not an automatic cycle. |
| 6 | completed review whose worker also completed the reviewed job | `review_not_independent` | Same-worker review is void evidence, never an approval. |
| 7 | `QUEUED` and `attempt_count >= attempt_limit` | `attempts_exhausted` | A wedge, not a queue position — see below. |
| 8 | `COMPLETED` with no `result`; **or** a stored `result` the runtime's validator rejects; **or** a stored `checkpoint` it rejects (any status) | `malformed_result_evidence` | The evidence contradicts itself; no downstream reading of this row is trustworthy. |
| 9 | `COMPLETED` and `result.errors` non-empty | `completed_with_errors` | It finished, and it says something went wrong. |
| 10 | `COMPLETED` and `result.next_actions` non-empty | `unresolved_next_actions` | It finished and handed work onward; nothing else picks that up. |
| 11 | `RUNNING`/`CHECKPOINTED` whose **current** attempt's `lease_expires_at` < `now` | `stale_lease` | The supervisor-death signature — see below. |
| 12 | anything else | *(suppressed)* | Routine — counted, not listed. |

**`kind` is an open, documented vocabulary.** Later phases add kinds (see the
orchestration contract's §5). A consumer that meets an unrecognised `kind` must treat
it as **attention**, never as routine — the whole point of the surface is that
something unfamiliar is exactly what a seat should look at. Additive kinds keep the
schema at `v2`; adding or removing a *field* on an item requires another schema
migration.

For kinds 1–3 at the attempt limit the reason gains
`; attempts exhausted (N/M) — requeue is refused`, because `requeue_job` refuses at
the limit: those jobs cannot be retried without an operator.

**Rule 5 is a wedge, not a queue position.** `claim_job` refuses when
`attempt_count >= attempt_limit`, and so does `requeue_job`. A QUEUED job at its limit
is therefore permanently unclaimable — it would otherwise sit in the QUEUED bucket
looking like ordinary pending work forever. (No sequence of runtime calls reaches this
state today: `requeue_job` refuses at the limit, so the row can only arrive by
operator edit, a restore, or a future requeue path. The projector still names it,
because the durable row is the authority.)

**Rule 9 is the one classification that reads a clock — and it is arithmetic, not
inference.** Nothing in the runtime moves a job out of `RUNNING` on its own:
`reconcile_expired` has to be *run*. So when a supervisor dies, its job keeps a
`RUNNING` row with an active attempt whose lease quietly ran out, and it sits in the
`running` suppression bucket looking like healthy work indefinitely. Rule 9 compares
two canonical timestamps — the attempt's own `lease_expires_at` against `now` — and
both are carried in `evidence` alongside `heartbeat_at`. It asserts nothing about
whether a process is alive; it says the lease this runtime itself wrote has expired
and nothing has swept it. Because it depends on `now`, an unparseable `--now` is a
**usage error** rather than a degraded read: a frozen clock that silently became the
wall clock would date the document one way and compare leases another. Rule 9 sits
last, so a row whose stored evidence is already self-contradictory (rule 6) reports
that first — the job still appears, under the more fundamental problem.

**Rule 2 (`job_lost`) distinguishes its two causes.** `mark_lost` records
`verified_process_absent` after a supervisor *proved* the invocation gone;
`reconcile_expired` records `reason: lease_expired` when a lease ran out with nobody
heart-beating. The first says a worker died, the second says nobody was watching, and
they need different repairs — so the reason names which one, read off the attempt's
own error record, with a neutral "the runtime marked it LOST" when neither marker is
present. Nothing is inferred when the record is silent.

**Rule 6 validates with the runtime's own validator.** `JobPayload.from_value` is run
against exactly what the runtime persisted — `checkpoint_job`, `complete_job`,
`fail_job`, and `checkpoint_attempt` all store `JobPayload.from_value(payload)
.to_dict()` with no wrapping envelope, so the stored object *is* the payload. A
second, local notion of "well-formed" here would let the inbox call healthy state
malformed.

### CEO-intent provenance

A CEO-submitted job is recognizable **only** by its `JOB_CREATED` event carrying
`payload.provenance.schema == "mastermind.ceo_intent.v1"`. The `ceo-intent:`
command-id prefix is a namespace any caller could type, not proof of origin, and the
job row itself carries nothing. When the record is present, the item gains evidence
refs for `provenance.actor` and `provenance.intent_id` and takes its `workstream` from
`provenance.workstream`.

Events are fetched **only for jobs already selected as attention**, so the read stays
bounded by the attention list rather than by the ledger.

Provenance never changes the target. A failed CEO-submitted job is a COO operational
exception exactly like any other.

A provenance record on a **versioned sibling** of that schema (`…ceo_intent.v2`) is
named in `degraded` rather than ignored. After a `ceo_intent` schema bump, silently
dropping the evidence would turn every CEO-submitted job anonymous without a sound.
A test pins `CEO_INTENT_PROVENANCE_SCHEMA` equal to `ceo_intent.INTENT_SCHEMA`.

### What creates CEO attention

Exactly one source in 1F-A: the collected boot packet's `brief.needs_ceo[]`. Each row
becomes one item — `target: ceo`, `kind: ceo_decision_pending`, `source: agent_os` —
whose `reason` is the row's `question` **verbatim** (`question not recorded` when
absent). A pending ruling is the organization's own words in the Agent OS record;
re-phrasing it here would put an unreviewed sentence in front of a decision. A row's
`recommendation`, if present, is deliberately **not** copied into
`existing_next_actions`: that field is the runtime's own stored next-actions, and
re-rendering an Agent OS recommendation as an executive action would be the inbox
authoring advice. A malformed (non-object) `needs_ceo` row becomes a `degraded` entry
naming its index — an unreadable pending ruling must never simply vanish.

**Runtime state never produces CEO attention in 1F-A.** Runtime results carry no
structured escalation field, so there is nothing in a Job row that says "this needs the
CEO". A job with unresolved next actions is COO attention, and the COO decides whether
to escalate it. That is a deliberate gap, not an oversight: the structured escalation
field is 1F-B's job.

### What creates chairman attention

**Nothing.** The `chairman` value is reserved in the schema and in the render's counts
line so the vocabulary exists and the count is visibly zero, but no 1F-A source maps
to it and no code path produces one.

Nothing infers a seat from difficulty, priority, department, cost, title, or actor
name. If a future phase adds chairman attention it must come from an explicit,
canonical, reviewable source — the same way `needs_ceo` does — never from a heuristic
over a job's fields.

## Suppression and auditability

Routine jobs are counted, never dropped:

| Bucket | What lands there |
|---|---|
| `clean_completed` | `COMPLETED` with no errors and no unresolved next actions |
| `queued` | `QUEUED` below the attempt limit |
| `running` | `RUNNING` with a live lease |
| `checkpointed` | `CHECKPOINTED` with a live lease |
| `cancelled` | `CANCELLED` |

`RUNNING` and `CHECKPOINTED` jobs at the attempt limit stay suppressed on purpose:
the final attempt is legitimately in flight, and flagging it would turn normal
last-attempt work into an alarm. An **expired** lease is the opposite case and
becomes `stale_lease` attention (rule 9).

**The arithmetic is checked in-module.** When jobs are readable:

    sum(suppressed.values()) + count(attention where source == "runtime")
        == runtime_counts.jobs.total

A mismatch appends an `internal reconciliation mismatch: …` entry to `degraded`. It is
never raised — a projection that crashed on its own audit would take the whole surface
down — but it is never hidden either. This is what makes suppression safe to trust: a
job cannot be quietly lost between "not listed" and "not counted".

## Degraded semantics

**The command always exits 0 once its arguments parse.** A missing runtime, an
unreadable registry, or an uncollectable boot packet is an orientation gap, not a
control-plane fault. This is the deliberate inverse of `control_plane/
strategic_state.py`, which fails loud, and the same contract
`control_plane/ceo_boot_packet.py` holds.

Everything that could not be read lands as a string in `degraded`:

**Runtime**

- `executive runtime database missing at <path>; runtime not projected` —
  `runtime_counts` and `suppressed` are `null` and no runtime attention is produced.
- `executive runtime database at <path> carries no Executive OS schema: <err>;
  runtime not projected` — a 0-byte husk, a truncated restore, or a foreign SQLite
  file. It is named, **not** given a schema.
- `executive runtime database at <path> is not an Executive OS database: <err>;
  runtime not projected` — the file is not SQLite at all.
- `executive runtime database at <path> could not be read: <err>; runtime not
  projected` — anything else the open raised, including a hot WAL that needs
  recovery (a read-only connection cannot recover one) and permission failures.
- `executive runtime database at <path> is unavailable: <err>; runtime not projected`
  — the connection itself failed.
- `runtime jobs|attempts|workers unreadable: <err>` — one registry raised; its section
  is `null` and the others keep answering.
- `runtime events unreadable: <err>; CEO-intent provenance not projected`.
- `<JOB-nnn> provenance schema <found> unrecognized (this build reads
  mastermind.ceo_intent.v1); intent evidence not attached`.
- `internal reconciliation mismatch: …` (above).

**Boot packet**

- `boot packet not collected (--no-boot-packet); CEO/Agent OS attention not projected`.
- `boot packet collection failed: <type>: <err>` — the collector raised despite its
  own fail-open contract.
- `boot packet file unreadable at <path>: <err>` / `boot packet file at <path> is not
  JSON: <err>` / `boot packet file at <path> is a <type>, not an object` — the run
  continues without a packet.
- `boot packet schema is <found>, expected mastermind.ceo_boot_packet.v1 — not read;
  CEO/Agent OS attention not projected`. An unknown contract is **never silently
  mapped**: `grounding.boot_packet_schema` and `grounding.macro` stay `null`.
- `boot packet degraded field is a <type>, not a list; its warnings were not bubbled`.
- `boot packet carries no Agent OS brief; CEO attention not projected` — `build_packet`
  emits `brief: null` whenever the Macro checkout does not resolve or the Agent OS
  brief fails. Without this entry the CEO lane would render a healthy-looking
  "0 CEO" out of a read that never happened.
- `boot packet brief is a <type>, not an object; CEO attention not projected`.
- `boot packet brief schema is <found>, expected ceo_brief.v1 — not read; CEO
  attention not projected` — Agent OS owns that contract, and a foreign brief may
  put `needs_ceo` to a different use entirely.
- `boot packet needs_ceo is a <type>, not a list; CEO attention not projected`.
- `boot packet needs_ceo[<i>] is not an object (<type>); no CEO attention projected
  from it`.
- `boot_packet: <entry>` — the packet's own `degraded` entries, bubbled with a prefix
  so a boot-packet problem is never mistaken for an inbox problem, and never hidden.

The text renderer never suppresses the DEGRADED block, and the counts lines are always
present — reading `runtime: not projected` and `suppressed: runtime not projected`
when there is no database.

## The default text surface

```
EXECUTIVE INBOX — 2026-08-14T00:00:00Z
mastermind eeeeeeeeeeee (master) · macro 999999999999 · runtime db present
schema mastermind.executive_inbox.v2
0 chairman · 2 CEO · 13 COO
runtime: 22 jobs · 18 attempts · 4 workers (2 AVAILABLE · 1 OFFLINE · 1 ERROR)
suppressed: 4 clean completions · 2 queued · 2 running/checkpointed · 1 cancelled
```

The **worker roll-call is on the default surface on purpose**: a fleet that is
entirely `ERROR` or `OFFLINE` produces no failed jobs — nothing can fail if nothing
can be claimed — so a dead fleet is invisible in the attention list and would
otherwise read as a quiet, healthy company. Only non-zero statuses are listed, in
enum-declaration order.

The seat counts iterate the declared vocabulary **union** whatever targets are
actually present, so a target a future phase adds can never be counted-but-unprinted.

## Deliberate non-goals

None of these are in 1F-A, and none of them are oversights:

- **No polling and no daemon.** The inbox is computed when asked. There is no watcher,
  no interval, no persistent Sol or Fable process.
- **No dispatch.** Nothing here claims, requeues, cancels, leases, or launches.
- **No notification transport.** No Slack, no email, no webhook, no socket. The output
  is stdout.
- **No automatic escalation.** Nothing promotes an item from COO to CEO or Chairman.
- **No strategic-state writes.** `config/strategic_state.yml` is not touched.
- **No Agent OS writes.** The `agentos/` store is read through the boot packet's
  existing one-way bridge and never written.
- **No persistence.** No inbox table, no "read/unread" flag, no snooze, no history. A
  durable acknowledgement state is a control plane; if a later phase needs one it must
  live in the existing runtime's event log, not in a new store.
- **No ranking.** Items are sorted for determinism, not scored for importance.

## Phase 1F-C remains separate

The orchestration contract that governs what may be built on top of this projection is
`research/EXECUTIVE_OS_PHASE1F_ORCHESTRATION_CONTRACT.md`. Read it before extending
anything below.

Phase 1F-B now provides the durable substrate and explicit refusals. The
run-once COO cycle remains a separate reviewed phase and is intentionally not
present here. The remaining gaps are:

1. **Explicit cycle (1F-C).** No daemon, polling loop, automatic parent completion,
   or model call was added. A future run-once COO cycle must consume these durable
   rows and remain subtree-scoped.
2. **Chairman attention.** The vocabulary is reserved and unused. It must be fed by an
   explicit canonical source, never inferred.

Whatever comes next, the boundary in this document is the constraint: the runtime stays
the only lifecycle authority, the Improvement Agenda stays the priority queue, Agent OS
stays a knowledge plane, and an executive surface that cannot read something says so.
