---
schema: mastermind.mission_workspace_consumer_freeze.v1
operation_key: mastermind-os-mission-workspace-freeze-20260916-claude-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_operation: mastermind-os-rollout-contract-20260916-sol-001
parent_carrier: Mastermind#702
source_pin: bf843961cd6bbd3e5c4cbd68df43bbba2d05b98f
capability_state: SPEC_ONLY
production_effect: NONE
architecture_family: CONSUMER_CONTRACT_FREEZE
disposition: DRAFT / HOLD-FOR-SOL / NOT_IMPLEMENTED
---

# Mission workspace — consumer contract freeze (R2 first vertical)

**Date:** 2026-09-16
**Parent:** Mastermind #702 `[OS][DRAFT][HOLD-FOR-SOL] Integrated rollout contract and
offline mission-workspace reference` (candidate `091592da`, six additive paths).
**What this record adds to #702:** #702 §7 fixes *which questions* to close at each
existing owner and §15 names the next boundary as "obtain the incumbent producer
owner's exact mission-observation and authorized visible-content/history contract."
This record answers that: the producer contracts were recovered from source, every
field of the proposed workspace is classified against them, and the consumer contract
is frozen so one engineering worker can implement R2 without inventing a schema.

**What this record is not.** It creates no runtime, no route, no reducer, no store,
no lifecycle, no Job, no grant, no installation. It edits no existing producer. It
does not merge, reopen, retarget or take over #702, #523, #595, #600, #653, #677,
#684, #688, AD-RET2, CCTX-1, PF1 or DF1, and it does not modify Macro #7120/#7181.
Every line below is a reading of protected source at the pin, not an installed fact.

---

## 0. The correction this freeze had to make first

#702's reference workspace (`research/mastermind_os/reference_workspace.html`) has
**no mission data model**. Its two embedded collections are `sources[]` (seven
architecture/evidence links: `{id,title,owner,status,detail,ref,date,url}`) and
`nodeData[]` (six design-relationship nodes: `{id,kind,title,owner,needs,source}`).
Its workspace view renders prose timeline rows, a disabled **Send instruction**
button and the literal string `Conversation is not connected`.

That is honest, and it is also why the reference cannot be "wired up": there is no
field set to bind. The vertical therefore has to be specified from the producer side,
which is what §2–§4 do. The reference remains useful as interaction/copy evidence for
the empty, missing-source, effect-unknown and corrected states.

---

## 1. Entity binding — what a Program and a mission actually are

No new identity is minted. The two nouns bind to existing canonical identities:

| Product noun | Canonical identity | Owner | Producer key |
|---|---|---|---|
| **Program** | a workstream ref `WS:<KEY>` | Macro Agent OS (`agentos/workstreams/WS-<KEY>.md`) | `work[].work_ref` in `mastermind.chairman_control_room.v1`; `responsibility_ref` in `mastermind.autonomy_control_room.v1` |
| **mission** | an Executive Runtime **root** — a `Job` whose `root_job_id == job_id` | Executive OS (`control_plane/executive_runtime.py`) | `root_job_id`; rendered by `mastermind.fabric_job_view.v1` |
| **principal** | the responsibility's accountable seat + its current runtime evidence | Agent OS (seat) + Executive OS/RuntimeBinding (runtime) | `accountable_seat`, `current_worker`, `current_sol_target` on the autonomy card |
| **child** | a non-root `Job` under that root, with `orchestration_role` | Executive OS | `children[]` in `mastermind.fabric_job_view.v1` |

**The join key is the pair, always.** `control_plane/autonomy_control_room_projection.py`
Law 1 already fixes it: rows match a card on `responsibility_ref` **AND** `root_job_id`
together — "never title, provider label, newest timestamp, or recency"
(`autonomy_control_room_projection.py:2404`). The mission workspace inherits that key
verbatim. A Program with no resolved root is a Program the workspace can open and a
mission it cannot: see `runtime_root_state` in §4.

`orchestration_role` is a closed set enforced by a SQLite trigger:
`plan | work | review | repair | aggregation`
(`control_plane/executive_runtime.py:2062`; same set as `ROLES`,
`control_plane/executive_orchestration_result.py:25`). The workspace never invents a
sixth role and never renames these.

---

## 2. Current source/producer map

Each row is the producer that already owns the question, read at the pin. "Reachable"
answers the only question an implementer cares about: can a web consumer obtain this
today, and through what.

| # | Question | Canonical producer | Document / callable | Reachable by a browser today? |
|---|---|---|---|---|
| 1 | mission identity and hierarchy | Executive OS | `control_plane/fabric_job_view.py` → `mastermind.fabric_job_view.v1`; `read_fabric_view()`, `list_roots()`, `compose_fabric_view()` (pure) | **No.** Library + `scripts/fabric_job_view.py` CLI only. No HTTP route exists. |
| 2 | principal identity + current state | Agent OS (seat) + Executive Steward/RuntimeBinding | `mastermind.autonomy_control_room.v1` card fields `accountable_seat`, `current_worker`, `current_sol_target`, `runtime_root_state`, `root_job_candidates`, `root_job_ambiguous` | **Partly.** Present in the local `/api/state` document; **stripped** from remote X1 (§7). |
| 3 | child identity + current state | Executive OS | `children[]` job cards (`JOB_CARD_KEYS`, `fabric_job_view.py:127`) | **No** (same as row 1). Also see gap **G1**: job cards carry no worker identity. |
| 4 | assignment / pickup / START / return / CONTINUE / STOP | `project_dispatch_consumption` | `mastermind.autonomy_dispatch_consumption.v1`, 13-token `DISPATCH_STATES` (`autonomy_control_room_projection.py:2415`) | **Partly** — attached to `autonomy` in the local document. Gap **G2**: 2 of 13 tokens have no producer. |
| 5 | visible message/content history | OHF worker broker + `VisibleTurnProjection` | `ohf-observe-turn` on the broker socket; `control_plane/visible_turn_projection.py` | **No**, and only ever for a *live* turn. Gap **G3** — the central finding, §3.5. |
| 6 | permitted outputs / artifacts | Executive OS | `result{state,summary,artifacts,errors,next_actions}` on each job card (`fabric_job_view.py:518`) | **No** (row 1). Available in the document once row 1 is reachable. |
| 7 | review disposition | Executive OS | `review{required,reviews_job_id,verdict}`; verdict ∈ `approve \| reject \| NOT_YET` (`fabric_job_view.py:473`) | **No** (row 1). |
| 8 | result / parent consumption | W3C canonical terminal/Wake read | `CanonicalTerminalWakeRead` (`control_plane/executive_dialogue_observation.py:381`), consumed by `_classify_dispatch_row` | **Partly** — surfaces as `dispatch_state` + the `w3c` sub-object on the dispatch card. |
| 9 | capability / proof state | `fabric_job_view` capability + `armed` bits | `capability{state,installed,version,detail}`, states `PROVEN\|PARTIAL\|UNSUPPORTED\|NOT_INSTALLED`; `armed` = the five arm bits + `source` | **No** (row 1). |
| 10 | correction / retraction | Steward issue codes + `missingness[]` facts + `disagreements[]` | `MISSINGNESS_CLASSES` (`fabric_job_view.py:166`); `_AMBIGUOUS_ISSUE_FIELD`, `_RECONCILIATION_REQUIRED` | Partly, per row. |
| 11 | unavailable / null / unknown | same as row 10 + DF1 source/coverage vocabulary | `MISSING_PRODUCER \| NULL_BY_DESIGN \| EXCLUDED \| OMITTED \| DEGRADED`; DF1 `CURRENT\|PARTIAL\|HISTORICAL\|UNAVAILABLE\|CONFLICT\|NOT_PROJECTED\|NOT_APPLICABLE` | Frozen vocabulary, no gap. |
| 12 | ordering and pagination | Executive OS (jobs); `VisibleTurnProjection` (items) | jobs: deterministic `_job_sort_key`, bounded by `UNJOINED_JOB_ID_LIMIT`/`LIST_ROOTS_LIMIT` = 50. items: `publication_sequence` cursor + `RESYNC_REQUIRED` | jobs yes; items behind G3. |
| 13 | retention / revocation | `VisibleTurnProjection` (content); surface bindings (navigation) | `MAX_RETAINED_TURNS = 4`, `MAX_VIEWERS = 2`, in-memory; grants are "projection-scoped reader handles… not user or authentication tokens" (`visible_turn_projection.py:11`) | behind G3. |
| 14 | source provenance | CCR `sources{}` + Steward `SourceRef` + DF1 evidence-ref contract | `{owner,ref,field,source_revision,source_time,observed_at,freshness_state}`, nine closed owners (DF1 spec §11) | Yes — frozen vocabulary. |
| 15 | auth / grant boundaries | CCR local server; X1 remote; E1 Executive MCP | §7 below | Yes, and §7 is the load-bearing constraint on R2. |

### 2.1 The consumer side that already exists

- **`mastermind.chairman_control_room.v1`** (`control_plane/chairman_control_room.py:206`)
  — closed `OUTPUT_KEYS` `{schema, generated_at, sources, degraded, attention, work,
  unjoined_open_prs, unbound_surfaces, binding_conflicts, placement_selection,
  autonomy}`. Composed once at startup, served from a process-memory cache with
  single-flight background refresh; `composed_at`, `refresh_in_flight` and
  `state_refresh_error` travel in the envelope.
- **Local server routes** (`scripts/chairman_control_room.py:1103`, verified by
  reading the dispatcher): `GET /`, `GET /static/control_room.{js,css}`,
  `GET /favicon.ico`, `GET /api/state`†, `GET /api/discover`†, `POST /api/open`†,
  `POST /api/bind`†, `POST /api/unbind`†, `POST /api/refresh-builds`†
  († require `X-CCR-Token`). `/api/state` returns
  `{control_room, capabilities, live_builds_active, composed_at, refresh_in_flight,
  state_refresh_error, source_validity}`. **There is no per-mission route.**
- **A Program drilldown already ships, and R2 must not rebuild it.**
  `app/static/chairman_control/control_room.js` is a single scrolling page with five
  anchors (`#today #autonomy #work #surfaces #system`, `index.html:44`) plus a shared
  detail drawer. `openDetail(card, opener)` (`:1196`) sets `STATE.selectedWork` and
  `renderDetail(card)` (`:1084`) renders, keyed on `card.work_ref`, the recorded next
  action and three evidence rails — Agent OS, Executive (`jobs[].job_id` + status,
  `joined_by`) and GitHub PRs — plus attention, source drift and navigation surfaces.
  A sibling drawer `openAutonomyDetail` (`:2206`) / `renderAutonomyDetail` (`:2057`)
  renders the autonomy card with a **Dispatch proof** rail. `renderAutonomy` (`:2229`)
  renders `doc.autonomy`; `auDispatchChip` (`:1618`) renders `card.dispatch
  .dispatch_state` through the closed label maps `AU_DISPATCH` / `AU_DISPATCH_VARIANT`
  (`:1525`), and `AU_DISPATCH_UNSAFE` / `dispatchUnsafe` (`:1609`) already suppress
  owed-action controls for stale, unacknowledged, watch-unproven,
  binding-reconciliation and effect-unknown states while keeping detail reachable.
  **So the Program lens, the principal lens and the dispatch lens are already built.**
  The one lens with no web consumer at all is the *mission tree* — see the next bullet.
- **`mastermind.fabric_job_view.v1` has no web consumer.** `grep -rn fabric_job_view`
  over the repo hits only its module, its CLI and its tests; zero `.js`/`.html`
  references. `control_room.js:2154` renders the bare string `"root job " +
  card.root_job_id` and `:2155` renders `root_job_ambiguous` with a candidate count —
  a single id, with no navigation into the tree. That dangling id is the exact seam
  R2 fills.
- **DF1** is the accepted *shape* for adding a new read surface: a pure reducer plus
  one token-gated JSON route plus local-only assets. Its design spec is merged
  (PR #521, `185dc742`); its plan is **open Draft PR #523** (`3c0a933b`); its
  implementation does **not exist** — `control_plane/chairman_brief.py` is absent and
  `app/static/chairman_control/` holds only `control_room.css`, `control_room.js`,
  `index.html`, `remote.html`. R2 must not assume DF1 has landed.

---

## 3. Field-by-field classification

Four classes, applied to every field the workspace proposes to show:
**A** = already available from a canonical owner · **D** = deterministically derivable
from A-class inputs · **M** = missing, requires producer work · **N** = deliberately
not projected in R2.

### 3.1 Mission header

| Field | Class | Source / derivation |
|---|---|---|
| `program.work_ref` | A | CCR `work[].work_ref` |
| `program.title`, `program.state`, `program.next_action` | A | `agent_os` entry on the work card (Macro `agent_os_state.v1`) |
| `mission.root_job_id` | A | autonomy card `root_job_id` (resolved only when exactly one candidate) |
| `mission.root_job_candidates`, `root_job_ambiguous`, `runtime_root_state` | A | autonomy card (`RESOLVED \| CONFLICT \| UNKNOWN`) |
| `mission.status`, `depth`, `orchestration_role`, `plan_step_id` | A | root job card |
| `mission.armed` (5 bits + `source`) | A | `fabric_job_view.armed`; `null` when `control.json` is absent, **never `false`** |
| `mission.capability` | A | `fabric_job_view.capability` |
| `mission.title` | **M** | Executive OS `Job` has no human title. Do **not** synthesize one from the Agent OS workstream title — that is a different object. Render the `root_job_id` until a producer supplies it. |

### 3.2 Principal and children

| Field | Class | Source / derivation |
|---|---|---|
| `principal.accountable_seat` | A | autonomy card; `chairman\|ceo\|coo\|worker` |
| `principal.current_worker`, `principal.current_sol_target` | A | autonomy card (Steward `RuntimeFact` projection) |
| `principal.owed_turn{seat,…}` | A | autonomy card |
| `children[].job_id`, `.status`, `.parent_job_id`, `.depth`, `.orchestration_role`, `.plan_step_id`, `.attempt_count`, `.attempt_limit`, `.current_attempt_id` | A | `fabric_job_view.children[]` |
| `children[].latest_attempt{attempt_id,attempt_number,status,started_at,finished_at,exit_code,has_result,error}` | A | `ATTEMPT_CARD_KEYS` (`fabric_job_view.py:146`) |
| `children[].worker_id` / who is executing this child | **M** | **Gap G1.** `grep -n worker control_plane/fabric_job_view.py` returns zero hits: neither `JOB_CARD_KEYS` nor `ATTEMPT_CARD_KEYS` carries a worker identity. `mastermind.execution_principal_snapshot/v1` (`executive_orchestration_principal.py:266`) has `worker_id`/`provider`/`account_label` per attempt, but it is Runtime-sealed evidence with no read projection — and it also carries `os_principal_uid` and `provider_home_identity`, which must never reach a browser. |
| `children[].is_ambiguous` | D | `len(root_job_candidates) > 1` on the parent |
| `unjoined_job_count`, `unjoined_job_ids` (≤50) | A | `fabric_job_view`; `len(children) + unjoined_job_count` = scope size, so the tree is never a silent subset |

### 3.3 Work state (assignment → consumption)

| Field | Class | Source / derivation |
|---|---|---|
| `dispatch.state` | A | `dispatch_state`, one of 13 `DISPATCH_STATES` |
| `dispatch.reason` | A | machine reason token, e.g. `attempt_in_progress:RUNNING`, `canonical_terminal_wake_acknowledged` |
| `dispatch.historical` | A | true when the contributing source is not `CURRENT` |
| `dispatch.actionable` | A | `state == "RETURNED" and not historical` — the **only** actionable combination |
| `dispatch.watch_proven`, `dispatch.carrier`, `dispatch.w3c{state,reason,terminal_state,wake_state,terminal_applied,source_receipt}` | A | dispatch card |
| `dispatch.state == CONTINUED` / `STOPPED` | **M** | **Gap G2.** Both are in the closed vocabulary (`:2417`) but `_classify_dispatch_row` can return only 11 tokens — enumerated over lines 2520–2660: `WAITING_CAPACITY, RECEIVER_SELECTED, DELIVERY_SENT, PICKUP_ACKNOWLEDGED, STARTED, RETURNED, DELIVERY_UNCONSUMED, WATCH_UNPROVEN, RUNTIME_BINDING_RECONCILIATION_REQUIRED, EFFECT_UNKNOWN, UNKNOWN`. `SOL CONTINUE` / `SOL STOP` are Slack-carrier edges under `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` §2.1/§2.2; no Executive producer emits them. R2 renders both as `NOT_PROJECTED`, never as an inferred `STOPPED`. |
| `blocked` vs `waiting` vs `effect-unknown` vs `complete` | D | the required four-way distinction is a **pure function of already-available fields** — see §4.3. No new state machine. |

### 3.4 Output, review, consumption

| Field | Class | Source / derivation |
|---|---|---|
| `result.state` | A | `NOT_STARTED \| IN_PROGRESS \| ACCEPTED \| CANCELLED \| FAILED \| LOST \| RATE_LIMITED`. Admitted-but-never-claimed is `NOT_STARTED`, never `RUNNING`, never `FAILED` (`fabric_job_view.py:423`) |
| `result.summary`, `.artifacts[]`, `.errors[]`, `.next_actions[]` | A | job card `result` block |
| `review.required`, `.reviews_job_id`, `.verdict` | A | `approve \| reject \| NOT_YET`; absent **and** empty verdict both read `NOT_YET` |
| "was it reviewed" | D | `review.verdict != "NOT_YET"` |
| "did the parent consume it" | A | `dispatch.state == RETURNED` with `w3c.terminal_applied` and `w3c.wake_state ∈ {TARGET_ACKNOWLEDGED, SOURCE_RESOLVED}` — the **only** evidence of consumption |
| "returned but not consumed" | A | `DELIVERY_UNCONSUMED` with reason `canonical_wake_unacknowledged` |
| `evidence.prs[]` | A | CCR `work[].github.prs` |
| `evidence.attention_ids[]` | A | CCR `work[].attention_ids` |
| `evidence.disagreements[]` | A | CCR `work[].disagreements` + autonomy `disagreements[]` |

### 3.5 Conversation / content history — the central gap

**Classification: M (Gap G3), and N for R2.**

There is exactly one producer of visible turn text, and it is not a history store:

- `control_plane/visible_turn_projection.py` is an **in-memory, process-local
  hot window**. Its own docstring is explicit: viewer grants "are internal,
  projection-scoped reader handles… not user or authentication tokens and confer no
  permission to send anything to the provider", and "when the last viewer for a turn
  is revoked, its bounded in-memory hot-window state is discarded; **it is not
  history**" (`:11`–`:14`).
- Bounds: `MAX_RETAINED_TURNS = 4`, `MAX_ITEMS_PER_TURN = 256`,
  `MAX_ITEM_BYTES = 16_384`, `MAX_VIEWERS = 2`, `MAX_READ_ITEMS = 64`.
- The only production callers are `control_plane/codex_operator_adapter.py`
  (which constructs one per adapter) and `control_plane/executive_worker_broker.py`,
  which exposes it as the broker operation **`ohf-observe-turn`** (`:1470`, handler
  `:2115`). That handler returns real `text`, plus `next_cursor`, `gaps[]`,
  `terminal`, `publication_epoch`, `retained_scope`, `resync_required` (`:2201`).
- Every read is fenced on the **live** generation: `attempt`, `epoch`,
  `generation`, `generation_number` and `worker_id` must all equal the currently
  active generation, or the call refuses `GENERATION_INVALID`; an unbound turn
  refuses `TURN_NOT_BOUND`; a revoked grant refuses `READER_REVOKED`.
- The transport is an AF_UNIX / mTLS broker socket, not HTTP. A browser cannot
  reach it. And `ohf-observe-turn` is **not** in
  `remote_worker_broker_client._READ_ONLY_OPERATIONS` (`:30`, which holds only
  `ohf-identity` and `ohf-materialization-status`), so remotely it is treated as a
  modifying operation with uncertainty handling.
- `control_plane/executive_dialogue_observation.py` is deliberately payload-free —
  `CanonicalTerminalWakeRead` is documented as a "public read-only terminal/Wake
  result with no provider or payload data" (`:381`) — so it is not an alternative.
  Its terminal projection validates `candidate.summary` and then *omits* it from the
  emitted wire, which is digests, ids and timestamps only (`:1071`).
- Peer authorization on the broker is kernel UID equality against the Executive
  control principal (`executive_worker_broker.py:1410`) — there is no bearer, session
  or user identity to map a browser viewer onto.

Three further properties make G3 worse than "not wired up yet", and each was
confirmed against source:

- **Capture is opt-in and prospective.** `publish()` returns immediately when the
  turn has no viewer: `if not self._viewers_by_turn.get(key): return`
  (`visible_turn_projection.py:353`). Content is retained only if a grant was minted
  **before** it flowed. There is no backfill path, and `mint_observer_grant`
  (`codex_operator_adapter.py:2122`) requires a live `_GenerationState`, so a grant
  for a finished attempt cannot be minted at all.
- **Eviction is silent.** Past `MAX_RETAINED_TURNS` the oldest record is dropped FIFO
  with no tombstone and no gap record (`:560`); a holder of its grant simply gets
  `TURN_NOT_BOUND`. Revoking the last viewer pops the record outright (`:405`).
- **`ohf-observe-turn` has no production consumer.** `grep -rn
  "ohf-observe-turn\|mint_observer_grant"` over the repo returns the two definition
  sites and tests only. It is a fully specified read model — cursors, epochs, gap
  records, refusal receipts — that nothing calls.

**Two traps recorded for whichever wave eventually closes G3.**

1. `ReadResult.resync_required` is `bool(gaps)` (`visible_turn_projection.py:498`,
   forwarded verbatim by the broker at `:2227`). It does **not** mean "reset your
   cursor" — the actual cursor reset is the `RESYNC_REQUIRED` *exception*, raised only
   on a publication-epoch change (`:447`). A consumer that treats the boolean as a
   reset signal will loop, because a retained gap keeps it true on every subsequent
   page.
2. `brain/advisor.py` has a real durable per-conversation chat store
   (`load_history`/`append_turn`, JSON under `data/brain/chat_history/`, last 200
   turns). It is the **portfolio-research advisor popup**, keyed by a `uuid4`
   conversation id with no Job/Attempt identity, no cursor, no grant and
   `except Exception: pass` on write. It is not a mission transcript and must never
   be pressed into service as one.

**Consequence, stated plainly:** for a *finished* mission — which is every mission a
Chairman opens after the fact — **no conversation history exists anywhere in this
repository.** The #702 reference's `Conversation is not connected` is not a
placeholder to be filled in R2; it is the accurate terminal state of the current
estate. R2 renders `conversation` as
`{state: "UNAVAILABLE", coverage: "NOT_PROJECTED", reason_codes:
["VISIBLE_CONTENT_HISTORY_NOT_PROJECTED"]}` and says so in copy. Building a durable
transcript store is forbidden here: `WS:CHAIRMAN-CONTROL-ROOM` `do_not_redo` bans
"a dialogue DB, Slack-owned lifecycle state, mutable thread cursor, second queue,
automatic retry ledger or another session identity plane", and ASD-A4 (the accepted
read-only dialogue-attention projection) is `status: todo` and gated behind
ASD-A3 **and** P0B.

---

## 4. The consumer contract — `mastermind.mission_workspace.v1`

### 4.1 Shape

One **pure reducer**, mirroring `compose_chairman_brief` in the DF1 plan §6:

```python
def compose_mission_workspace(
    *,
    control_room: Mapping[str, Any] | None,     # mastermind.chairman_control_room.v1
    fabric_view: Mapping[str, Any] | None,      # mastermind.fabric_job_view.v1
    work_ref: str,
    root_job_id: str | None,
    source_validity: Mapping[str, Any] | None,
    cache_currentness: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure deterministic read-only mission workspace projection."""
```

No I/O, no environment, no clock, no randomness, no mutation, no provider inspection,
no second join. Same argument + same inputs ⇒ byte-identical
`json.dumps(doc, sort_keys=True)`. Enforced by an AST anti-authority test, as
`tests/test_fabric_job_view.py` D6 and the DF1 plan both already do.

Closed top-level key set:

```json
{
  "schema": "mastermind.mission_workspace.v1",
  "generated_at": "…Z",
  "source": {
    "control_room_schema": "mastermind.chairman_control_room.v1",
    "control_room_generated_at": "…Z",
    "fabric_view_schema": "mastermind.fabric_job_view.v1",
    "fabric_view_generated_at": "…Z",
    "source_coverage": []
  },
  "read_state": {"state": "CURRENT", "reason_codes": [], "usable_sections": []},
  "program":      {"work_ref": "WS:…", "title": null, "state": null, "next_action": null,
                   "evidence": []},
  "mission":      {"root_job_id": null, "root_job_candidates": [], "root_job_ambiguous": false,
                   "runtime_root_state": "UNKNOWN", "status": null, "orchestration_role": null,
                   "plan_step_id": null, "depth": null, "title": null,
                   "armed": {}, "capability": {}, "evidence": []},
  "principal":    {"accountable_seat": null, "current_worker": null, "current_sol_target": null,
                   "owed_turn": null, "evidence": []},
  "children":     {"state": "…", "coverage": "…", "reason_codes": [], "total_count": null,
                   "items": [], "overflow_count": null},
  "work_state":   {"dispatch_state": "UNKNOWN", "reason": null, "actionable": false,
                   "historical": true, "watch_proven": null, "carrier": null, "w3c": null,
                   "posture": "EFFECT_UNKNOWN", "evidence": []},
  "output":       {"state": "…", "coverage": "…", "reason_codes": [], "total_count": null,
                   "items": [], "overflow_count": null},
  "review":       {"required": null, "reviews_job_id": null, "verdict": "NOT_YET",
                   "evidence": []},
  "consumption":  {"state": "UNKNOWN", "reason": null, "evidence": []},
  "conversation": {"state": "UNAVAILABLE", "coverage": "NOT_PROJECTED",
                   "reason_codes": ["VISIBLE_CONTENT_HISTORY_NOT_PROJECTED"],
                   "total_count": null, "items": [], "overflow_count": null},
  "missingness":  [],
  "degraded":     [],
  "feature_gates": {"conversation": "UNAVAILABLE", "actions": "READ_ONLY",
                    "advanced": "AVAILABLE"}
}
```

Every list section uses the **DF1 §8.3 envelope verbatim** —
`{state, coverage, reason_codes, total_count, items, overflow_count}` — with DF1's own
rules: `COMPLETE` permits exact integers; `INCOMPLETE` requires
`total_count = null` **and** `overflow_count = null` while known items stay visible;
`NOT_PROJECTED` is never a zero; `EMPTY` is legal only when coverage is complete and
the exact total is zero. Section states are DF1's five
(`AVAILABLE|EMPTY|PARTIAL|HISTORICAL|UNAVAILABLE`); read states DF1's four
(`CURRENT|PARTIAL|HISTORICAL|UNAVAILABLE`). **Do not mint a parallel vocabulary.**

`missingness[]` uses the `fabric_job_view` fact shape verbatim:
`{missingness_class, target_field, producer_owner, reason}` with
`missingness_class ∈ {MISSING_PRODUCER, NULL_BY_DESIGN, EXCLUDED, OMITTED, DEGRADED}`.

Every `evidence[]` entry uses the DF1 §11 tuple verbatim —
`{owner, ref, field, source_revision, source_time, observed_at, freshness_state}` —
with DF1's nine closed owners, 0–32 refs per item, no arbitrary URL or filesystem
path, `source_revision` null rather than fabricated, and dedupe by the complete tuple.

### 4.2 Field semantics that are not obvious

- **`armed.*` is tri-state.** Absent or unreadable `control.json` ⇒ every bit `null`
  and `armed.source == "absent"` — **never `false`**. A `false` bit is a positive
  fact that the host asserted; `null` is ignorance. When `ceo_submit_armed is False`
  the workspace must show the degraded entry "no Chairman-authenticated admitted job
  can exist yet" rather than an empty mission.
- **`runtime_root_state`** separates three cases that all leave `root_job_id` null:
  `RESOLVED` (exactly one candidate), `CONFLICT` (2+ — reconciliation required, never
  a pick), `UNKNOWN` (no runtime evidence at all).
- **`children` coverage is `INCOMPLETE` whenever `unjoined_job_count > 0`.** Those
  jobs exist under the root but carry no CEO-intent workstream provenance; they are
  counted and listed (first 50), never dropped, and their presence forbids an exact
  total.
- **`consumption`** is read only from the dispatch card's W3C branch. A terminal
  Attempt, a watcher receipt, a raw `APPLIED` marker and a Slack delivery are each
  explicitly *not* a return: the classifier emits `WATCH_UNPROVEN` with reason
  `canonical_w3c_evidence_required` in exactly that case.
- **`work_state.actionable`** is `dispatch_state == "RETURNED" and not historical`,
  copied, not recomputed.

### 4.3 The required four-way posture — derived, not invented

The brief requires the Chairman to distinguish blocked / waiting / effect-unknown /
complete. This is a pure total function over `dispatch_state` and `result.state`,
evaluated in order; nothing new is produced:

| `posture` | Condition |
|---|---|
| `EFFECT_UNKNOWN` | `dispatch_state ∈ {EFFECT_UNKNOWN, RUNTIME_BINDING_RECONCILIATION_REQUIRED}` — checked first, before every other signal, mirroring Law 8's "EFFECT_UNKNOWN outranks optimistic progress" |
| `BLOCKED` | a Steward `blocker` or an Agent-OS `declared_blocker` is present, or `dispatch_state == DELIVERY_UNCONSUMED` |
| `WAITING` | `dispatch_state ∈ {WAITING_CAPACITY, RECEIVER_SELECTED, DELIVERY_SENT, PICKUP_ACKNOWLEDGED}` |
| `RUNNING` | `dispatch_state == STARTED` |
| `RETURNED_UNCONSUMED` | `dispatch_state == WATCH_UNPROVEN`, or `RETURNED` with `historical` true |
| `COMPLETE` | `dispatch_state == RETURNED`, `historical` false, and `result.state == ACCEPTED` |
| `UNKNOWN` | everything else, including `dispatch_state == UNKNOWN` |

`COMPLETE` requires **both** the canonical consumption evidence and an accepted
result. A `COMPLETED` Job with no result payload already carries a `DEGRADED`
missingness fact on `result.summary`; the workspace shows `RETURNED_UNCONSUMED` plus
that fact, never `COMPLETE`.

---

## 5. Null, missing and correction rules

1. **Null is not zero.** `NOT_PROJECTED` (no producer in this generation),
   `UNAVAILABLE` (producer exists, this read failed), and `EMPTY` (complete coverage,
   exact total zero) are three different states and never collapse.
2. **Absence is never completion.** An item that disappears between two generations
   does not imply it finished or was cancelled. The workspace states the gap.
3. **Known subset is not the queue.** Under `INCOMPLETE`, items may render but totals
   and overflow are `null`, and the copy says the list is known-subset evidence.
4. **A correction preserves identity.** A field whose earlier claim is no longer
   supported keeps its identity and gains a `DEGRADED` missingness fact naming the
   producer; it is never silently rewritten and never silently dropped.
5. **Freshness never renews itself.** `observed_at` comes from the producer;
   rendering does not refresh it. `generated_at` is injected into the reducer, never
   sampled — this is what makes staleness visible instead of cosmetic.
6. **Source time and observation time stay distinct**, and `source_revision` is
   `null` when unavailable rather than invented.
7. **A refusal is a rendered state.** `query_status ∈ {ok, degraded, unknown,
   refused}` and `capability.state ∈ {PROVEN, PARTIAL, UNSUPPORTED, NOT_INSTALLED}`
   both render. An absent runtime is a typed refusal with `root: null` and
   `children: []`; it must never read as "no work".
8. **Revocation invalidates the read.** A cached page must not keep serving content
   whose grant was revoked. In R2 this is trivially satisfied: there is no content.

---

## 6. Deterministic vs model-generated

**Deterministic (the whole of `mastermind.mission_workspace.v1`):** identity
resolution and joins; every state, coverage and posture value; ordering; totals and
overflow; evidence binding; missingness facts; redaction and size limits; all
copy keyed off a closed vocabulary.

**Model-generated: nothing in R2.** No summary, no narrative, no "what changed".
DF1 §17 already binds this and is inherited verbatim: model output "cannot populate
authoritative options/recommendation, admit/suppress an item, decide currentness,
enable action, or close anything." If a later wave adds narration it renders in a
separately labelled region, cites structured refs, and carries zero authority.

---

## 7. Auth boundaries

| Surface | Boundary | R2 disposition |
|---|---|---|
| **Local P0A** (`scripts/chairman_control_room.py`) | loopback-only bind, Host allowlist, CSP + nosniff, `X-CCR-Token`. The token is a **per-process browser-origin/CSRF capability nonce, not authentication**: `GET /` is unauthenticated and is what delivers it, so any same-user local process can read it — that adversary is explicitly outside the threat boundary. | **R2 ships here, and only here.** |
| **Remote X1** (`chairman_control_room_remote.v1`) | a closed-allowlist re-projection that keeps only `{schema, observed_at, code_identity, source_freshness, degraded, attention, work, unjoined_open_prs}` and **drops `sources`, `unbound_surfaces`, `binding_conflicts`, `placement_selection` and `autonomy`**; served on a UNIX socket under systemd with group `caddy` — authentication belongs to the fronting proxy, not to this code. Its own read routes are statics + `/healthz` + `/api/state`, no POST and no token, and `remote.html` ships a 3-anchor nav (`#today #work #system`) with Autonomy and Surfaces structurally absent. | **Excluded.** DF1 §23.3 already holds remote X1 from decision-first changes without a separate redaction/route/package/install/production-proof operation. R2 inherits that hold. Note the sharper reason: X1 strips `autonomy`, so most of §4's work-state fields are structurally absent there. |
| **E1 / Executive MCP** | four static readers (`executive_state`, `executive_inbox`, `executive_job`, `ceo_intent_status`) over authenticated `POST /mcp`; envelope `mastermind.executive_mcp_result.v1`; 64 KiB request / 256 KiB response ceilings; typed errors; no submit route. | **Not used by R2.** It is a CEO-seat tool surface, not a browser surface, and `executive_job` takes a single `job_id` with no tree. |
| **Worker broker** (`ohf-*`) | AF_UNIX / mTLS, generation-fenced, reader grants. | **Not used by R2** (§3.5). Proxying it into a web route would be new producer *and* new security work. |
| **BSC-E1 public edge** | `IDENTITY_PROVIDER_SELECTION_REQUIRED`: no production policy, no IdP owner, no OpenAI-reachable public edge on the Studio. | **Blocks any "authenticated remote" reading of R2.** "Authenticated" in the acceptance target below means the local P0A token-gated path, and the record says so rather than implying an IdP exists. |

**Invariants.** Reads never start/resume a provider, drain notifications, acknowledge
an obligation, claim work, renew a lease, or keep a worker alive. A thousand viewers
create zero schedulers. No browser input ever becomes a path, host, endpoint, argv or
profile. All source-derived strings pass one sanitizer and are placed by safe DOM
construction, never HTML interpolation.

---

## 8. No-rebuild boundaries

Do not create: a second Job/Attempt/Worker lifecycle or store; a conversation or
transcript database; a provider-session registry; an evidence store; an auth plane; a
graph authority; a second freshness clock, cursor DB, queue, retry ledger or
scheduler; a universal `/api/mission` invoke endpoint; a second sanitizer or
redaction owner; a parallel state/coverage vocabulary.

Do not edit: `index.html`, `control_room.js`, `control_room.css` (DF1 plan §4 already
fences these); any producer module in §2; any X1 route, static asset, package or
install closure; `.github/workflows/`; any Figma file (the existing pause stands).

Do not take over: #702's six paths, #523's DF1 plan, #595, #600, #653, #677, #684,
#688, AD-RET2, CCTX-1, PF1, DF1, Macro #7120 or #7181.

---

## 9. One implementation path list

Create:

1. `control_plane/mission_workspace.py` — the pure reducer of §4.
2. `app/static/chairman_control/mission.html`
3. `app/static/chairman_control/mission.js`
4. `app/static/chairman_control/mission.css`
5. `tests/test_mission_workspace.py` — reducer + AST anti-authority test.
6. `tests/test_chairman_control_room_mission_server.py` — route/auth/size tests.
7. `tests/test_chairman_control_room_mission_ui.py` — browser tests.
8. `docs/superpowers/plans/<date>-mastermind-os-r2-mission-workspace.md` — the plan.

Modify:

9. `scripts/chairman_control_room.py` — add exactly four routes.
10. `docs/CHAIRMAN_CONTROL_ROOM.md` — document them.

An eleventh path is `DECISION_REQUEST PATH_BOUNDARY_REQUIRED`.

Routes, following DF1 §5 exactly:

```text
GET /mission?work_ref=<ref>&root_job_id=<id>     token-injected mission.html, same CSP as /
GET /api/mission?work_ref=<ref>&root_job_id=<id> token + Host + Origin + no-store gated JSON
GET /static/mission.js
GET /static/mission.css
```

Rules: `/api/mission` reads the one cached CCR snapshot (no synchronous composition)
and performs **one** bounded `read_fabric_view(runtime_root, root_job_id,
control_config_path=…)` call; canonical-encoded; maximum successful body exactly
262144 bytes; larger returns HTTP 503 with
`{"schema":"mastermind.mission_workspace_error.v1","error":"MISSION_WORKSPACE_RESPONSE_TOO_LARGE"}`;
no partial success bytes; no new POST; `/` remains Advanced.

**One cost the implementer must not discover in production.** `read_fabric_view` is
the only I/O in the request path and it is *not* free: `_gather_jobs` calls
`runtime.jobs.list_jobs()`, which takes no arguments and is a **full table scan**,
with the root filter applied in Python (`docs/FABRIC_JOB_VIEW.md`, implementation
notes). It must be opened with `Runtime.at(root, create=False)` — a bare
`Runtime.at(root)` defaults to `create=True` and would manufacture an empty database
and then report a quiet, job-free company. The route therefore: (a) calls it once per
request and never in a loop; (b) is measured against the largest real runtime
available before acceptance, with the number recorded in the receipt; (c) if that
measurement exceeds a request budget, the fix is a bounded cache in the *existing*
cache owner, never a new store and never a second gather. `compose_fabric_view` itself
is pure and accepts an injected `generated_at`, so the reducer stays deterministic.

**The one query-string deviation from DF1 must be stated, not smuggled.** DF1's
`/brief` and `/api/brief` reject every non-empty query string. `/api/mission` needs
two parameters. They are validated as a closed pair before any read: `work_ref`
against `chairman_control_room._WS_TOKEN_RE`, `root_job_id` against the Runtime job-ref
grammar, both required, no other key accepted, neither ever used to build a path.
Any other query shape is a 400. This narrowing needs Sol's ruling, not an
implementer's judgement.

Order of work: reducer + tests red-then-green → server route + tests → assets + UI
tests → browser acceptance → receipt. Return state `DRAFT / HOLD-FOR-SOL /
BUILT_NOT_PROVEN`.

### 9.1 What R2 must NOT re-render

Because the shipped inspector already has a work-ref drawer and an autonomy drawer
(§2.1), the mission page is **only the tree and its per-job evidence**:
mission header, principal summary, `children[]` with roles and attempts, output,
review, consumption posture, the `conversation` refusal, and the missingness list.

- It must **not** re-implement the Agent OS / GitHub / attention / source-drift /
  navigation rails — `renderDetail` already owns those; link back to `/#work` and
  `/#autonomy` instead.
- It must **not** re-implement dispatch chips or their label maps. The closed
  vocabulary and the unsafe-state suppression already live in `control_room.js:1525`
  and `:1609`. `mission.js` carries its own copy only because the DF1 path ceiling
  forbids editing `control_room.js`; that duplication is a **deliberate, recorded**
  cost of the fence, not an invitation to diverge. If the two label maps ever
  disagree, the shipped one wins and the mission copy is the bug.
- It must **not** introduce a second refusal rule for owed actions. R2 has no action
  controls at all (`feature_gates.actions: READ_ONLY`), so the question cannot arise;
  a later wave inherits `dispatchUnsafe`, it does not re-derive it.

---

## 10. Required producer gaps

Each is owned by an existing owner. **None may be closed by the R2 consumer.**

| Gap | What is missing | Owner | R2 behaviour until closed |
|---|---|---|---|
| **G1** | per-child worker identity in `mastermind.fabric_job_view.v1` | Executive OS / `fabric_job_view` owner | `children[].worker_id` renders `null` + one `MISSING_PRODUCER` fact on `children.worker_id`, producer `executive_runtime`. A safe closure adds `worker_id` only — never `os_principal_uid` or `provider_home_identity`. |
| **G2** | no producer for `CONTINUED` / `STOPPED` | dispatch-consumption owner + the Dialogue close-law owner | both render `NOT_PROJECTED`; never inferred from Slack text or watcher silence |
| **G3** | no durable authorized visible-content/history resource for a finished mission; the one hot-window producer is prospective-capture-only, 4-turn FIFO, `agentMessage`-only, and its `ohf-observe-turn` surface has no production consumer | OHF / Fabric owner; organizationally ASD-A4 under `WS:CHAIRMAN-CONTROL-ROOM` (`status: todo`, gated behind ASD-A3 **and** P0B) | `conversation` section is `UNAVAILABLE / NOT_PROJECTED` with the stated reason code |
| **G4** | no HTTP read path to `mastermind.fabric_job_view.v1` | this R2 consumer creates it as a route over the existing library — the *only* new surface R2 adds | n/a |
| **G5** | no human-readable mission title on an Executive Job | Executive OS | `mission.title` null + `MISSING_PRODUCER`; never synthesized from the workstream title |
| **G6** | `ceo_submit_armed` is `false` in the shipped control template, so no Chairman-authenticated admitted root exists on a production host | Chairman ceremony (host-owned), out of scope here | the acceptance run below uses a real Runtime with a real root, and the record states which host it was |

---

## 11. Browser acceptance scenario

Local P0A path, real browser, one real Runtime root. Screenshots are attachments,
never production captures.

1. Start the local Control Room against a checkout whose
   `data/control_plane/executive.sqlite3` contains at least one real root; obtain a
   root id with `python3 scripts/fabric_job_view.py --list-roots --runtime-root <abs>`.
2. Open `/` (Advanced). Confirm the token is delivered and the cached state loads.
3. Navigate to `/mission?work_ref=<WS:…>&root_job_id=<id>` for a Program whose
   autonomy card resolves exactly that root.
4. Assert on screen: the Program title and state; `root_job_id` with
   `runtime_root_state: RESOLVED`; the accountable seat and `current_worker`;
   the child list with each `orchestration_role` and `latest_attempt.status`;
   the posture chip; `review.verdict`; `result.state` with artifacts;
   the consumption line derived from `dispatch_state` + `w3c`;
   the `conversation` section reading *not projected*, with its reason;
   every `MISSING_PRODUCER` fact from §10 visible rather than hidden.
5. Cross-check every rendered value against the underlying evidence in the same
   session: `python3 scripts/fabric_job_view.py --runtime-root <abs> --root-job-id
   <id> --json` for the mission tree, and the `autonomy` block of `GET /api/state`
   for the principal/dispatch fields. **The page and the producers must agree
   field-for-field** — this, not a green suite, is the acceptance.
6. Prove at least one negative from §12 on the same page.
7. Prove read-only-ness: no POST is issued, no storage is written, and no
   provider/runtime mutation occurs during the whole run.
8. Desktop 1440, tablet 1024 and mobile 390 widths: no horizontal overflow, keyboard
   activation of every known target, focus restoration after any dialog, no
   colour-only state.

Not acceptance: a green test suite, a screenshot, a merged PR, or a rendered page
whose values were never compared to the producers.

---

## 12. Negative cases (each must render distinctly)

1. **Absent runtime** — `db_present: false`, `capability.state: NOT_INSTALLED`,
   `root: null`, `children: []`, typed refusal. No directory, file or journal is
   created by the read. Must not read as "no work".
2. **Unreadable runtime** — `capability.state: UNSUPPORTED`, `degraded` names
   `jobs unreadable: <first line>`. Distinct from case 1.
3. **Unknown root** — `MISSING_PRODUCER` on `root` plus a degraded entry naming the
   id. Not a 404 blank page.
4. **Stale state** — the cached CCR snapshot is past TTL and the background refresh
   failed: `read_state: HISTORICAL`, `state_refresh_error` surfaced, dated. A
   retained stale empty section must **not** become a clear/complete zero.
5. **Ambiguous root** — 2+ candidates: `runtime_root_state: CONFLICT`,
   `root_job_ambiguous: true`, candidates listed, `root_job_id` stays `null`.
   Reconciliation required; never a pick by recency.
6. **Unjoined children** — `unjoined_job_count > 0`: coverage `INCOMPLETE`, totals
   `null`, ids listed, gap named. Never a silent subset.
7. **Effect unknown** — `EFFECT_UNKNOWN` outranks every optimistic signal; every
   actuator stays disabled; copy says *reconcile the original operation, do not
   resend*.
8. **Runtime generation conflict** — `runtime_generation_state: CONFLICT` ⇒
   `RUNTIME_BINDING_RECONCILIATION_REQUIRED`, `historical: true`, even when an
   earlier generation looked terminal.
9. **Unconsumed delivery** — `DELIVERY_UNCONSUMED` with
   `canonical_wake_unacknowledged`: delivered, never acknowledged. Must not render as
   active, started, executing or waiting-on-worker.
10. **Terminal Attempt without canonical return** — `WATCH_UNPROVEN` /
    `canonical_w3c_evidence_required`. A `COMPLETED` Attempt is historical context,
    never a return.
11. **Corrected evidence** — a `COMPLETED` job with no result payload:
    `result.state: ACCEPTED`, `summary: null`, plus the `DEGRADED` fact. Posture is
    `RETURNED_UNCONSUMED`, not `COMPLETE`.
12. **Undecided review** — absent and empty verdicts both read `NOT_YET` with a
    `MISSING_PRODUCER` fact; never `reject`, never `false`.
13. **Terminal STOP** — `CONTINUED`/`STOPPED` render `NOT_PROJECTED` with G2's
    reason. A terminal child wave never implies the parent Program is terminal, and a
    child STOP never disarms a sibling or aggregate lane.
14. **Missing source** — `control.json` absent: all five `armed` bits `null`,
    `armed.source: "absent"`, one degraded entry. Never `false`.
15. **Unarmed submit** — `ceo_submit_armed: false`: the degraded entry explains why
    no admitted job can exist, rather than showing an empty mission.
16. **Hostile text** — a job summary containing HTML, a Slack mention or a
    ` ` renders as inert text; no interpolation, no execution.
17. **Oversize** — a document past 262144 bytes returns the typed 503 before any
    partial bytes are written.
18. **Bad query** — a missing, extra or malformed parameter is a 400 before any read.

No negative may collapse to a spinner, a blank card, a false zero or a green badge.

---

## 13. Follow-on handoff

```text
HANDOFF 5 — Mastermind OS R2 mission-workspace implementation
PREFERRED_AVENUE: bounded engineering worker (Sonnet-class or equivalent);
  Opus/Fable not required — this freeze removed the open architecture questions.
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PARENT: mastermind-os-rollout-contract-20260916-sol-001 (Mastermind #702)
CONTRACT: docs/superpowers/specs/2026-09-16-mastermind-os-mission-workspace-consumer-freeze.md

Mission
  Implement mastermind.mission_workspace.v1 exactly as frozen in §4, on the local
  P0A path only, using the ten-path ceiling in §9.

Sequence
  1. Write the plan at docs/superpowers/plans/<date>-mastermind-os-r2-mission-workspace.md.
  2. Reducer + tests first: observe the intended RED, then green. AST anti-authority
     test proving no I/O, clock, environment, randomness or mutation.
  3. Server route + auth/size tests. Four routes, no POST.
  4. Assets + UI tests. Do not touch index.html / control_room.{js,css}.
  5. Browser acceptance per §11 against a real Runtime root, with the field-for-field
     producer cross-check. Record the host.
  6. Publish one Draft/HOLD PR with a receipt; do not merge, install or deploy.

Binding constraints
  - Consume producers; create none. §8 no-rebuild list is binding.
  - Reuse DF1's source-state, coverage, section-envelope and evidence-ref
    vocabularies verbatim. Do not mint a parallel vocabulary.
  - G1, G2, G3, G5 stay open and render as typed missingness. Closing any of them
    inside this consumer is out of scope and is a blocker to surface, not to fix.
  - Remote X1 unchanged (§7).

Blocker to return before coding
  §9's query-string narrowing of DF1's "reject every non-empty query string" rule
  needs an explicit Sol ruling. Return PATH_BOUNDARY_REQUIRED and wait if it is
  not granted.

Completion
  An implementation worker can build this without inventing a schema or an authority.
  Acceptance is §11 step 5 — the page agreeing field-for-field with the producers —
  plus at least one §12 negative. A green suite, a screenshot or a merged PR is not
  acceptance.
```

---

## Sources

Read at pin `bf843961cd6bbd3e5c4cbd68df43bbba2d05b98f`, this checkout:

- `control_plane/fabric_job_view.py`, `docs/FABRIC_JOB_VIEW.md`
- `control_plane/chairman_control_room.py`, `scripts/chairman_control_room.py`,
  `docs/CHAIRMAN_CONTROL_ROOM.md`
- `control_plane/autonomy_control_room_projection.py`
- `control_plane/executive_steward.py`
- `control_plane/chairman_control_room_remote.py`, `ops/control_room_remote/install.sh`
- `control_plane/visible_turn_projection.py`, `control_plane/executive_worker_broker.py`,
  `control_plane/remote_worker_broker_client.py`,
  `control_plane/executive_dialogue_observation.py`
- `control_plane/executive_orchestration_principal.py`,
  `control_plane/executive_orchestration_result.py`,
  `control_plane/executive_terminal_return.py`,
  `control_plane/runtime_binding_projection.py`
- `control_plane/executive_inbox.py`, `docs/EXECUTIVE_INBOX.md`, `docs/EXECUTIVE_MCP.md`
- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`, `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`
- `docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md`
  (merged, `185dc742`) and its H1A supersession addendum
- DF1 plan at `3c0a933b` (open Draft PR #523)
- Mastermind #702 at `091592da` (all six paths)
- Macro `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md` at `0f62daf54571`
