---
schema: mastermind.mission_workspace_consumer_freeze.v3
operation_key: mastermind-os-mission-workspace-freeze-20260916-claude-001
workstream: WS:CHAIRMAN-CONTROL-ROOM
parent_operation: mastermind-os-rollout-contract-20260916-sol-001
parent_carrier: Mastermind#702
carrier: Mastermind#704
repairs_reviews: [5228415542, 5228672592]
inspected_commit: bf843961c0e1b5bd45fa481f0138c71f2a87d4e2
current_protected_commit: 5ee11ab1e993616f3568cfca4069cb21fa61fd8f
installed_generation: UNKNOWN
capability_state: SPEC_ONLY
production_effect: NONE
architecture_family: CONSUMER_CONTRACT_FREEZE
disposition: DRAFT / HOLD-FOR-SOL / NOT_IMPLEMENTED
slice: R2A (local mission tree) — NOT full R2; networked path HELD on producer gap G8
---

# Mission workspace — consumer contract freeze (R2A first sub-slice)

**Date:** 2026-09-16 · **v3, repaired** against exact-head reviews 5228415542 and
[5228672592](https://github.com/mastermindx-market-intelligence/Mastermind/pull/704#pullrequestreview-5228672592)
(REQUEST_CHANGES at `8b941411…` then `c09672fc…`).
**Parent:** Mastermind #702 (candidate `091592da`, six additive paths).

**What this record adds to #702.** #702 §7 fixes *which questions* to close at each
existing owner and §15 names the next boundary as "obtain the incumbent producer
owner's exact mission-observation and authorized visible-content/history contract."
This record answers that: producer contracts recovered from source, every proposed
field classified against them, and a consumer contract frozen so one engineering
worker can implement a bounded first sub-slice without inventing a schema.

**What this record is not.** It creates no runtime, route, reducer, store, lifecycle,
Job, grant or installation. It edits no producer. It does not merge, reopen, retarget
or take over #702, #523, #595, #600, #653, #677, #684, #688, #697, H3e, AD-RET2,
CCTX-1, PF1 or DF1, and does not modify Macro #7120/#7181. It claims no source-writer
release, worker, provider, credential, install or production acceptance.

---

## 0. Source reconciliation — three generations, kept apart

v1 of this record named a source pin that **does not exist**. `bf843961cd6bbd3e5c…`
returns 404; it was a fabricated 40-character expansion of the short SHA `bf843961`.
That is corrected here, and the correction is recorded rather than quietly rewritten,
because the whole document claims to be a reading of protected source.

| Generation | Value | Meaning |
|---|---|---|
| **Inspected commit** | `bf843961c0e1b5bd45fa481f0138c71f2a87d4e2` | the commit this checkout was at when every citation below was read |
| **Current protected** | `5ee11ab1e993616f3568cfca4069cb21fa61fd8f` | protected `master` at v3 repair time; the inspected commit is a verified ancestor. The intervening move from `e8803ba3` touched only CEO-ingress/boot-packet tests and did not alter any module cited here. |
| **Installed generation** | `UNKNOWN` | no installed-host evidence is held by this record. Source protection is not installation. |

Every cited module was compared blob-for-blob across those two commits. **All ten are byte-identical
at both `e8803ba3` and `5ee11ab1`**, so every line reference in this record is valid at
current protected head. Re-verified at the v3 repair.

| Module | blob (identical at both commits) |
|---|---|
| `control_plane/fabric_job_view.py` | `c69e44785e28ee191639b7af05d0fe5e22fbf24d` |
| `control_plane/chairman_control_room.py` | `cbe93fb6c3aa…` |
| `control_plane/autonomy_control_room_projection.py` | `1e716364cc75…` |
| `control_plane/visible_turn_projection.py` | `77a23ad9eeb5…` |
| `control_plane/executive_worker_broker.py` | `ce691178cabf…` |
| `control_plane/chairman_control_room_remote.py` | `dfd6b9a72f6c…` |
| `control_plane/executive_steward.py` | `90ecd34cdd79…` |
| `control_plane/executive_runtime.py` | `4502250cb5de…` |
| `scripts/chairman_control_room.py` | `9260d006c2bf…` |
| `app/static/chairman_control/control_room.js` | `c95f9befdc4c…` |
| DF1 plan (open Draft #523) | commit `bf9484a0` at v3 repair, not merged |
| #702 candidate | commit `091592da`, not merged |

The review's own receipts — module blob `c69e44785e28…` and source projection blob
`77a23ad9…` — equal the values above, so the two readings corroborate independently.

---

## 1. The correction the first pass had to make

#702's reference workspace (`research/mastermind_os/reference_workspace.html`) has
**no mission data model**. Its two embedded collections are `sources[]` (seven
architecture/evidence links) and `nodeData[]` (six design-relationship nodes). Its
workspace view renders prose timeline rows, a disabled **Send instruction** button and
the literal string `Conversation is not connected`.

That is honest, and it is why the reference cannot simply be "wired up": there is no
field set to bind. The vertical therefore had to be specified from the producer side.
The reference remains useful as interaction and copy evidence for empty, missing-source,
effect-unknown and corrected states.

---

## 2. Entity binding — what a Program and a mission actually are

No new identity is minted.

| Product noun | Canonical identity | Owner | Producer key |
|---|---|---|---|
| **Program** | a workstream ref `WS:<KEY>` | Macro Agent OS (`agentos/workstreams/WS-<KEY>.md`) | `work[].work_ref` in `mastermind.chairman_control_room.v1`; `responsibility_ref` in `mastermind.autonomy_control_room.v1` |
| **mission** | an Executive Runtime **root** — a `Job` whose `root_job_id == job_id` | Executive OS (`control_plane/executive_runtime.py`) | `root_job_id`; rendered by `mastermind.fabric_job_view.v1` |
| **principal** | the responsibility's accountable seat + its current runtime evidence | Agent OS (seat) + Executive OS / RuntimeBinding (runtime) | `accountable_seat`, `current_worker`, `current_sol_target` |
| **child** | a non-root `Job` under that root, with `orchestration_role` | Executive OS | `children[]` in `mastermind.fabric_job_view.v1` |

**The join key is the pair, always.** `autonomy_control_room_projection.py:2404` already
fixes it: rows match a card on `responsibility_ref` **AND** `root_job_id` together —
"never title, provider label, newest timestamp, or recency". This consumer inherits that
verbatim. Two individually valid identifiers are not a join and are not a permission:
the pair must be shown to exist, and the named Job must actually be a root
(`root_job_id == job_id`), before anything is rendered.

`orchestration_role` is a closed set enforced by a SQLite trigger —
`plan | work | review | repair | aggregation` (`executive_runtime.py:2062`; same set as
`ROLES`, `executive_orchestration_result.py:25`). No sixth role, no renaming.

---

## 3. Current source/producer map

| # | Question | Canonical producer | Document / callable | Reachable by a browser today? |
|---|---|---|---|---|
| 1 | mission identity and hierarchy | Executive OS | `fabric_job_view.py` → `mastermind.fabric_job_view.v1`; `read_fabric_view()`, `list_roots()`, pure `compose_fabric_view()` | **No.** Library + `scripts/fabric_job_view.py` CLI only. No HTTP route. |
| 2 | principal identity + current state | Agent OS (seat) + Steward / RuntimeBinding | autonomy card `accountable_seat`, `current_worker`, `current_sol_target`, `runtime_root_state`, `root_job_candidates`, `root_job_ambiguous` | **Partly.** In the local `/api/state` document; **stripped** from remote X1 (§8). |
| 3 | child identity + current state | Executive OS | `children[]` job cards (`JOB_CARD_KEYS`, `fabric_job_view.py:127`) | **No** (row 1). Gap **G1**: no worker identity on job cards. |
| 4 | assignment / pickup / START / return / CONTINUE / STOP | `project_dispatch_consumption` | `mastermind.autonomy_dispatch_consumption.v1`, 13-token `DISPATCH_STATES` (`:2415`) | **Partly** — attached to `autonomy` locally. Gap **G2**: 2 of 13 tokens have no producer. |
| 5 | visible message/content history | OHF worker broker + `VisibleTurnProjection` | `ohf-observe-turn`; `visible_turn_projection.py` | **No.** Live turn only, with a prospectively minted grant. Gap **G3**, §4.5. |
| 6 | permitted outputs / artifacts | Executive OS | `result{state,summary,artifacts,errors,next_actions}` (`fabric_job_view.py:518`) | **No** (row 1). |
| 7 | review disposition | Executive OS | `review{required,reviews_job_id,verdict}`; `approve \| reject \| NOT_YET` (`:473`) | **No** (row 1). |
| 8 | transport / obligation consumption | W3C canonical terminal/Wake read | `CanonicalTerminalWakeRead` (`executive_dialogue_observation.py:381`) via `_classify_dispatch_row` | **Partly** — `dispatch_state` + the `w3c` sub-object. |
| 9 | **product / artifact acceptance** | *no producer* | — | **No.** Gap **G7**, §5.3 — distinct from rows 7 and 8. |
| 10 | capability / proof state | `fabric_job_view` | `capability{state,installed,version,detail}`; `armed` five bits + `source` | **No** (row 1). |
| 11 | correction / retraction | Steward issue codes + `missingness[]` + `disagreements[]` | `MISSINGNESS_CLASSES` (`:166`); `_AMBIGUOUS_ISSUE_FIELD`; `_RECONCILIATION_REQUIRED` | Partly, per row. |
| 12 | unavailable / null / unknown | same, plus DF1 vocabulary | `MISSING_PRODUCER \| NULL_BY_DESIGN \| EXCLUDED \| OMITTED \| DEGRADED`; DF1 `CURRENT\|PARTIAL\|HISTORICAL\|UNAVAILABLE\|CONFLICT\|NOT_PROJECTED\|NOT_APPLICABLE` | Frozen vocabulary. |
| 13 | ordering and pagination | Executive OS (jobs); `VisibleTurnProjection` (items) | jobs: `_job_sort_key`, bounds 50. items: `publication_sequence` cursor + `RESYNC_REQUIRED` | jobs yes; items behind G3. |
| 14 | retention / revocation | `VisibleTurnProjection`; surface bindings | `MAX_RETAINED_TURNS = 4`, `MAX_VIEWERS = 2`, in-memory; grants "are not user or authentication tokens" (`:11`) | behind G3. |
| 15 | source provenance | CCR `sources{}` + Steward `SourceRef` + DF1 evidence-ref | `{owner,ref,field,source_revision,source_time,observed_at,freshness_state}` | Yes — frozen vocabulary. |
| 16 | auth / grant boundaries | CCR local; X1 remote; E1 Executive MCP | §8 | Yes — and §8 bounds the slice. |

### 3.1 The consumer side that already exists

- **`mastermind.chairman_control_room.v1`** (`chairman_control_room.py:206`) — closed
  `OUTPUT_KEYS` `{schema, generated_at, sources, degraded, attention, work,
  unjoined_open_prs, unbound_surfaces, binding_conflicts, placement_selection,
  autonomy}`. Composed once at startup, served from a process-memory cache with
  single-flight background refresh; `composed_at`, `refresh_in_flight` and
  `state_refresh_error` travel in the envelope.
- **Local routes** (`scripts/chairman_control_room.py:1103`, read from the dispatcher):
  `GET /`, `GET /static/control_room.{js,css}`, `GET /favicon.ico`, `GET /api/state`†,
  `GET /api/discover`†, `POST /api/open`†, `POST /api/bind`†, `POST /api/unbind`†,
  `POST /api/refresh-builds`† († require `X-CCR-Token`). `/api/state` returns
  `{control_room, capabilities, live_builds_active, composed_at, refresh_in_flight,
  state_refresh_error, source_validity}`. **There is no per-mission route.**
- **A Program drilldown already ships, and must not be rebuilt.** `control_room.js` is
  a single scrolling page with five anchors plus a shared drawer. `openDetail`
  (`:1196`) / `renderDetail` (`:1084`) render, keyed on `card.work_ref`, the recorded
  next action and three evidence rails — Agent OS, Executive (`jobs[].job_id` + status,
  `joined_by`), GitHub PRs — plus attention, source drift and navigation surfaces. A
  sibling drawer `openAutonomyDetail` (`:2206`) / `renderAutonomyDetail` (`:2057`)
  renders the autonomy card with a **Dispatch proof** rail. `renderAutonomy` (`:2229`)
  renders `doc.autonomy`; `auDispatchChip` (`:1618`) renders `card.dispatch
  .dispatch_state` through closed label maps `AU_DISPATCH` / `AU_DISPATCH_VARIANT`
  (`:1525`); `AU_DISPATCH_UNSAFE` / `dispatchUnsafe` (`:1609`) already suppress
  owed-action controls for stale, unacknowledged, watch-unproven,
  binding-reconciliation and effect-unknown states while keeping detail reachable.
  **The Program lens, the principal lens and the dispatch lens are already built.**
- **`mastermind.fabric_job_view.v1` has no web consumer.** `grep -rn fabric_job_view`
  hits only its module, CLI and tests; zero `.js`/`.html` references.
  `control_room.js:2154` renders the bare string `"root job " + card.root_job_id` and
  `:2155` renders `root_job_ambiguous` with a candidate count — a single id, with no
  navigation into the tree. That dangling id is the seam this sub-slice fills, and §10.1
  is where it must actually be closed for a real person.
- **DF1** is the accepted *shape* for a new read surface: a pure reducer, one
  token-gated JSON route, local-only assets. Its design spec is merged (PR #521,
  `185dc742`); its plan is **open Draft #523**, head `bf9484a01a76cb105c2b6a6dd62cb2d2378d262f` at this repair (it had moved beyond the `3c0a933b` cited in v1/v2 — re-read it before source admission); its implementation does
  **not exist** — `control_plane/chairman_brief.py` is absent and
  `app/static/chairman_control/` holds only `control_room.{css,js}`, `index.html`,
  `remote.html`. This record must not assume DF1 has landed.

---

## 4. Field-by-field classification

**A** = available from a canonical owner · **D** = deterministically derivable from
A-class inputs · **M** = missing, requires producer work · **N** = deliberately not
projected in this sub-slice.

### 4.1 Mission header

| Field | Class | Source / derivation |
|---|---|---|
| `program.work_ref` | A | CCR `work[].work_ref` |
| `program.title`, `.state`, `.next_action` | A | `agent_os` entry on the work card |
| `mission.root_job_id` | A | autonomy card (resolved only when exactly one candidate) |
| `mission.root_job_candidates`, `.root_job_ambiguous`, `.runtime_root_state` | A | autonomy card (`RESOLVED \| CONFLICT \| UNKNOWN`) |
| `mission.status`, `.depth`, `.orchestration_role`, `.plan_step_id` | A | root job card |
| `mission.submission_availability` | D | see §5.2 — replaces the false existential copy. `AVAILABLE` is **not** derivable from the arm bit and is unreachable in R2A. |
| `mission.armed` (5 bits + `source`) | A | `fabric_job_view.armed`; `null` when `control.json` is absent, **never `false`** |
| `mission.capability` | A | `fabric_job_view.capability` |
| `mission.title` | **M** | Executive OS `Job` has no human title. Do **not** synthesize one from the Agent OS workstream title — a different object. Render `root_job_id` until a producer supplies it (**G5**). |
| `mission.runtime_root` (the absolute path) | **N** | never emitted — see §8.2 |

### 4.2 Principal and children

| Field | Class | Source / derivation |
|---|---|---|
| `principal.accountable_seat` | A | autonomy card; `chairman\|ceo\|coo\|worker` |
| `principal.current_worker`, `.current_sol_target`, `.owed_turn` | A | autonomy card |
| `children[].job_id`, `.status`, `.parent_job_id`, `.depth`, `.orchestration_role`, `.plan_step_id`, `.attempt_count`, `.attempt_limit`, `.current_attempt_id` | A | `fabric_job_view.children[]` |
| `children[].latest_attempt{attempt_id,attempt_number,status,started_at,finished_at,exit_code,has_result}` | A | `ATTEMPT_CARD_KEYS` (`:146`) |
| `children[].latest_attempt.error` | **N→D** | the raw first-line error is **not** emitted (§8.2). A fixed `error_present: bool` plus an allowlisted classification is emitted instead. |
| `children[].worker_id` | **M** | **G1.** `grep -n worker control_plane/fabric_job_view.py` returns zero hits: neither `JOB_CARD_KEYS` nor `ATTEMPT_CARD_KEYS` carries a worker identity. `mastermind.execution_principal_snapshot/v1` (`executive_orchestration_principal.py:266`) has `worker_id`/`provider`/`account_label` per attempt, but it is Runtime-sealed with no read projection and also carries `os_principal_uid` and `provider_home_identity`, which must never reach a browser. |
| `unjoined_job_count`, `unjoined_job_ids` (≤50) | A | `len(children) + unjoined_job_count` = scope size, so the tree is never a silent subset |

### 4.3 Execution, transport and review — three separate facets

| Field | Class | Source / derivation |
|---|---|---|
| `execution.state` | A | `NOT_STARTED \| IN_PROGRESS \| ACCEPTED \| CANCELLED \| FAILED \| LOST \| RATE_LIMITED`. **Read `ACCEPTED` as "execution terminated COMPLETED", nothing more** — §5.3. Admitted-but-never-claimed is `NOT_STARTED`, never `RUNNING`, never `FAILED` (`:423`). |
| `execution.summary_present`, `.artifacts[]`, `.errors_present`, `.next_actions[]` | A/D | from the `result` block, allowlisted per §8.2 |
| `review.required`, `.reviews_job_id`, `.verdict` | A | `approve \| reject \| NOT_YET`; absent **and** empty verdict both read `NOT_YET` |
| `transport.dispatch_state` | A | one of 13 `DISPATCH_STATES` |
| `transport.reason`, `.historical`, `.actionable`, `.watch_proven`, `.carrier`, `.w3c{…}` | A | dispatch card. `actionable` is `state == "RETURNED" and not historical`, copied not recomputed. |
| `transport.dispatch_state == CONTINUED` / `STOPPED` | **M** | **G2.** Both are in the closed vocabulary (`:2417`) but `_classify_dispatch_row` can emit only 11 tokens, enumerated over lines 2520–2660: `WAITING_CAPACITY, RECEIVER_SELECTED, DELIVERY_SENT, PICKUP_ACKNOWLEDGED, STARTED, RETURNED, DELIVERY_UNCONSUMED, WATCH_UNPROVEN, RUNTIME_BINDING_RECONCILIATION_REQUIRED, EFFECT_UNKNOWN, UNKNOWN`. `SOL CONTINUE` / `SOL STOP` are Slack-carrier edges under `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` §2.1/§2.2. Both render `NOT_PROJECTED`; never inferred, and **no new token is minted**. |
| `acceptance.*` | **M** | **G7**, §5.3 |

### 4.4 Evidence

| Field | Class | Source |
|---|---|---|
| `evidence.prs[]` | A | CCR `work[].github.prs` |
| `evidence.attention_ids[]` | A | CCR `work[].attention_ids` |
| `evidence.disagreements[]` | A | CCR `work[].disagreements` + autonomy `disagreements[]` |

### 4.5 Conversation / content history — bounded, not permanently absent

**Classification: M (G3) for after-the-fact history; N for this sub-slice; the live
hot window remains the accepted first-release target under its incumbent owner.**

v1 of this record concluded that `conversation` is `NOT_PROJECTED` "throughout R2". That
over-generalised a verified narrow fact into a product definition, and it silently
equated *every Chairman mission* with *a finished mission*. The verified facts and the
corrected scope are separated below.

**Verified about the one producer of visible turn text:**

- `visible_turn_projection.py` is an **in-memory, process-local hot window**. Its
  docstring: viewer grants "are internal, projection-scoped reader handles… not user or
  authentication tokens and confer no permission to send anything to the provider", and
  when the last viewer is revoked the state "is discarded; **it is not history**"
  (`:11`–`:14`).
- Bounds: `MAX_RETAINED_TURNS = 4`, `MAX_ITEMS_PER_TURN = 256`,
  `MAX_ITEM_BYTES = 16_384`, `MAX_VIEWERS = 2`, `MAX_READ_ITEMS = 64`.
- Production callers are `codex_operator_adapter.py` (constructs one per adapter) and
  `executive_worker_broker.py`, which exposes it as broker operation
  **`ohf-observe-turn`** (`:1470`, handler `:2115`). That handler returns real `text`
  plus `next_cursor`, `gaps[]`, `terminal`, `publication_epoch`, `retained_scope`,
  `resync_required` (`:2201`).
- Reads are fenced on the **live** generation — `attempt`, `epoch`, `generation`,
  `generation_number`, `worker_id` must all match, else `GENERATION_INVALID`; an unbound
  turn is `TURN_NOT_BOUND`; a revoked grant is `READER_REVOKED`. Peer authorization is
  kernel UID equality against the Executive control principal
  (`executive_worker_broker.py:1410`) — there is no user identity to map a viewer onto.
- Transport is AF_UNIX / mTLS, not HTTP; `ohf-observe-turn` is **not** in
  `remote_worker_broker_client._READ_ONLY_OPERATIONS` (`:30`, which holds only
  `ohf-identity` and `ohf-materialization-status`).
- `executive_dialogue_observation.py` is payload-free by construction: its terminal
  projection validates `candidate.summary` and then omits it from the emitted wire,
  which is digests, ids and timestamps only (`:1071`).
- **Capture is prospective.** `publish()` returns immediately when the turn has no
  viewer (`:353`). Content is retained only if a grant existed **before** it flowed, and
  `mint_observer_grant` (`codex_operator_adapter.py:2122`) requires a live
  `_GenerationState`, so no grant can be minted for a finished attempt.
- **Eviction is silent.** Past 4 turns the oldest record is dropped FIFO with no
  tombstone and no gap record (`:560`); a grant holder then gets `TURN_NOT_BOUND`.
- **`ohf-observe-turn` has no production consumer.** `grep -rn
  "ohf-observe-turn\|mint_observer_grant"` returns the two definition sites and tests.

**Corrected scope.** The accepted OS product direction already selects the **bounded
authorized hot window with explicit gaps** as the first live content release, with full
authorized history a later integration through existing owners. This record therefore
states only that **after-the-fact history is not proven through the admitted path** —
not that "no history exists anywhere" — and it does **not** define conversation as
permanently unavailable. The live-content lane stays bound to the incumbent connected
reader and content-resource work; this record builds no second reader, no transcript
store, and **mints no covert viewer grant to manufacture retention**. `conversation` is
`N` in R2A because R2A is the *mission-tree* sub-slice, not because content is absent
from the product.

**Two traps recorded for whichever wave closes G3.**

1. `ReadResult.resync_required` is `bool(gaps)` (`visible_turn_projection.py:498`),
   forwarded verbatim by the broker (`:2227`). It does **not** mean "reset your cursor";
   the actual reset is the `RESYNC_REQUIRED` *exception*, raised only on a
   publication-epoch change (`:447`). A consumer treating the boolean as a reset will
   loop, because a retained gap keeps it true on every later page.
2. `brain/advisor.py` has a durable per-conversation chat store (`load_history` /
   `append_turn`, JSON under `data/brain/chat_history/`, last 200 turns). It is the
   **portfolio-research advisor popup**, keyed by a `uuid4` conversation id, with no
   Job/Attempt identity, no cursor, no grant and `except Exception: pass` on write. It
   is not a mission transcript and must never be pressed into service as one.

---

## 5. The three repaired predicates

### 5.1 Why v1 was wrong, shown against the real producer

Run against the protected pure producer `compose_fabric_view` with synthetic objects —
no Runtime database, no provider, no grant, no host, no effect:

```
CASE A: COMPLETED job, review_required=True, NO review job, ceo_submit_armed=False
  result.state   = ACCEPTED
  review.verdict = NOT_YET
  root returned? = True  (JOB-X)
  degraded       = ['ceo_submit_armed: false; no Chairman-authenticated
                    admitted job can exist yet']

CASE B: COMPLETED job, empty result payload
  result.state   = ACCEPTED
  result.summary = None
  missingness    = [('DEGRADED','result.summary'), ('EXCLUDED','return_path'),
                    ('NULL_BY_DESIGN','runtime.identity')]
```

Case A and Case B each falsify a v1 predicate, and Case A falsifies two at once.

The mechanism is in the source: `_TERMINAL_RESULT_STATES` maps `"COMPLETED": "ACCEPTED"`
unconditionally (`fabric_job_view.py:198`–`204`), and `_result_state` (`:423`) inspects
job status and attempts only — it contains no reference to review, decision or
acceptance. So `result.state == ACCEPTED` means **"execution terminated COMPLETED"**
and nothing else. v1's §4.3 table made `COMPLETE` fire on `RETURNED` + not historical +
`ACCEPTED`, which declares a Chairman-facing *completion* for an unreviewed job with an
empty payload. v1's own prose said the opposite; the table is what an implementer codes,
so the table was the defect.

### 5.2 Arm state — B2

`ceo_submit_armed=false` prohibits a **new** governed submission. It does not, and
cannot, prove that a previously admitted Job does not exist — Case A returns the root
*and* emits the contrary sentence in the same document. The shipped-template value is
also not installed-host evidence.

The producer's `_UNARMED_ENTRY` string (`fabric_job_view.py:207`, emitted unconditionally
at `:636` and `:859` whenever the bit is `False`) is therefore **an actual upstream
source defect**, not a fact to copy. v1 copied it into §4.2, G6 and negative case 15.

**Repair.**
- Existing roots, children, attempts and results are **retained and rendered** after
  DISARM. Prior evidence is never withdrawn because a submission gate closed.
- New-submission unavailability is explained on its own field,
  `mission.submission_availability`, which carries no existential claim about existing
  Jobs — and which is **asymmetric on purpose**:

  | `ceo_submit_armed` | `submission_availability` |
  |---|---|
  | `False` | `UNAVAILABLE_NEW_SUBMISSION` |
  | `null` (config absent/unreadable) | `UNKNOWN` |
  | `True` | **`UNKNOWN`** — never `AVAILABLE` |

  v2 mapped `True → AVAILABLE`, which repeats the v1 mistake in the opposite direction.
  The raw bit is one gate among several: it establishes no accepted installed generation,
  no sealed authority receipt, no authenticated principal, no live binding, no current
  permission and no admitted sink — exactly the distinctions the H3/H4 owners are
  repairing. A negative bit can close a gate on its own; a positive bit cannot open one.
  `AVAILABLE` is reachable **only** when the existing authority owner supplies a current
  positive readiness/permission projection, and no such projection is consumed by R2A.
  The raw observed bit is retained separately as `armed.ceo_submit_armed` so the
  observation is not lost.
- **R2A does not rebuild the H3/H4 gate in the UI.** It has no submission action, reads
  no secrets or configs from the browser, and implements no second readiness evaluator.
  Required test: `armed=true` with missing receipt, binding or readiness projection
  **never** renders `AVAILABLE`.
- The producer's degraded sentence is **not** echoed in the workspace. It is recorded
  here as a defect against its existing owner, with the reproduction above. **This
  records child takes no source custody of `fabric_job_view.py`** and does not repair it;
  correcting display copy downstream does not repair upstream source, and this record
  does not pretend otherwise.
- Required tests: `admission → DISARM → read existing root` (root still returned,
  no existential claim rendered), and `absent config ≠ false` (all bits `null`,
  `armed.source == "absent"`, availability `UNKNOWN`).
- No real JOB-001 is replayed, duplicated or retried by this record or its implementation.

### 5.3 Acceptance is a fourth facet with no producer — B1 / G7

Four facts are kept structurally separate and are never aliased to one another:

| Facet | Question | Owner | Today |
|---|---|---|---|
| **execution** | did the process terminate, and how | Executive OS | available |
| **review** | did an independent review Job decide | Executive OS | available |
| **transport** | was the return delivered and the obligation acknowledged | W3C / Wake | available |
| **acceptance** | did the accountable owner accept *this artifact revision* as the product | *no producer* | **NOT_PROJECTED** |

W3C `TARGET_ACKNOWLEDGED` / `SOURCE_RESOLVED` is transport and obligation evidence. A
review verdict is a review. Neither is an artifact/product acceptance ruling, and
`result.state == ACCEPTED` is an execution alias. **No combination of the three existing
facets may be displayed as product completion.**

The acceptance facet is populated only by the existing acceptance/decision owner, and
only with an exact mission/brief reference, the exact artifact revision, and the ruling.
Until such a projection exists, `acceptance` is
`{state: "NOT_PROJECTED", reason_codes: ["ACCEPTANCE_OWNER_NOT_PROJECTED"], ruling: null,
artifact_revision: null, owner: null}`. **No universal acceptance store is created, and
no new `DISPATCH_STATES` token is minted.**

### 5.4 The total truth table (v3)

**v2's table was not total, and its accepted branch was unsatisfiable.** Rule 12e read
"12d **and** `acceptance.state == ACCEPTED`" while 12d itself required
`acceptance.state != ACCEPTED` — a conjunction with its own negation. `ACCEPTED_PRODUCT`
was therefore unreachable *by construction*, not by the absence of a producer, which is a
different and much worse thing: a test asserting unreachability could not tell the
intended absence gate apart from a permanently dead branch. Translating the v2 predicates
literally and evaluating them over the finite domain (7 execution × 11 dispatch ×
3 review × 2 acceptance × current × blocker × generation-conflict = 3696 combinations)
found **13 distinct fall-through classes**, `ACCEPTED_PRODUCT` reachable **0** times, and
**18 stale rows announcing present-tense `RUNNING`**.

The v3 rules below factor the common predicate once, evaluate acceptance before the
branches that negate it, separate binding uncertainty from proven effect uncertainty,
gate every present-tense liveness posture on currentness, and end in an unconditional
typed fallback. Rules are ordered; the first match wins; `posture.rule` records which
fired.

| Group | # | Condition | `posture` |
|---|---|---|---|
| **A. proven effect uncertainty** | A1 | `dispatch_state == EFFECT_UNKNOWN` | `EFFECT_UNKNOWN` |
| **B. binding / generation uncertainty** | B1 | `dispatch_state == RUNTIME_BINDING_RECONCILIATION_REQUIRED` | `RECONCILIATION_REQUIRED` |
| | B2 | source-generation conflict, or `runtime_root_state == CONFLICT` | `RECONCILIATION_REQUIRED` |
| **C. terminal execution facts** | C1–C4 | `execution.state ∈ {FAILED, CANCELLED, LOST, RATE_LIMITED}` | `EXECUTION_FAILED` / `_CANCELLED` / `_LOST` / `_RATE_LIMITED` |
| **D. declared blocker** | D1 | Steward `blocker` or Agent-OS `declared_blocker` present | `BLOCKED` |
| **E. consumption negatives and unknowns** | E1 | `dispatch_state == DELIVERY_UNCONSUMED` | `DELIVERED_UNCONSUMED` |
| | E2 | `dispatch_state == WATCH_UNPROVEN` | `CONSUMPTION_UNKNOWN` |
| | E3 | `dispatch_state == RETURNED` and **not** current | `CONSUMPTION_UNKNOWN` |
| **F. terminal ladder** — guarded once by the factored predicate `returned_current := (dispatch_state == RETURNED and current)` | F0 | `returned_current` and `execution.state != ACCEPTED` | `RETURN_EXECUTION_MISMATCH` |
| | F1 | `returned_current`, execution `ACCEPTED`, `acceptance.state == ACCEPTED`, `review.verdict == "reject"` | `ACCEPTANCE_REVIEW_CONFLICT` |
| | F2 | `returned_current`, execution `ACCEPTED`, `acceptance.state == ACCEPTED` with an exact artifact revision and ruling | `ACCEPTED_PRODUCT` |
| | F3 | `returned_current`, execution `ACCEPTED`, acceptance not established, `review.verdict == "reject"` | `REVIEW_REJECTED` |
| | F4 | same, `review.verdict == "NOT_YET"` | `RETURNED_UNREVIEWED` |
| | F5 | same, `review.verdict == "approve"` | `REVIEWED_NOT_ACCEPTED` |
| **G. present-tense liveness, gated on currentness** | G1 | `dispatch_state == STARTED` and current | `RUNNING` |
| | G1h | `dispatch_state == STARTED` and **not** current | `HISTORICAL_OBSERVATION` |
| | G2 | `dispatch_state ∈ {WAITING_CAPACITY, RECEIVER_SELECTED, DELIVERY_SENT, PICKUP_ACKNOWLEDGED}` and current | `WAITING` |
| | G2h | same and **not** current | `HISTORICAL_OBSERVATION` |
| **H. never claimed** | H1 | `execution.state == NOT_STARTED` and `dispatch_state == UNKNOWN` | `NOT_STARTED` |
| **I. unconditional fallback** | I1 | anything else | `UNKNOWN` |

Four properties this structure buys, each of which v2 lacked:

1. **Totality.** I1 has no condition, so every admitted combination resolves. The
   contract test is a full finite-domain sweep asserting zero fall-throughs and exactly
   one effective outcome per combination — not a sample.
2. **A reachable acceptance branch.** F2 is evaluated **before** F3–F5 and never
   conjoins with their negation, so `ACCEPTED_PRODUCT` is satisfiable the moment a
   genuine owner-qualified acceptance exists. It remains **unproduced today** because
   G7 has no producer — an absence gate, not a dead branch. The synthetic positive case
   validates the contract only; **it supplies no live acceptance producer and authorizes
   no such state in R2A**.
3. **Binding uncertainty is not effect evidence.** B1 no longer folds into
   `EFFECT_UNKNOWN`. A reconciliation-required binding says we cannot identify the
   receiver; it is not evidence that an effect occurred.
4. **No stale row announces present tense.** The currentness gate is frozen for *every*
   positive-liveness posture (G1, G2), not only for `RETURNED`. A non-current row renders
   `HISTORICAL_OBSERVATION` carrying the dated underlying observation, never `RUNNING`
   or `WAITING`.

Additional constraints carried forward:

- **A `DEGRADED` missingness fact on `result.summary` never moves a posture.** Case B of
  §5.1 reaches its ladder rule on its own predicates and the damage fact renders beside
  it — neither promoted nor demoted.
- **`RETURN_EXECUTION_MISMATCH` is a real finding, not a filler.** A current return
  against an execution that never terminated (`IN_PROGRESS`, `NOT_STARTED`) is a
  contradiction between two owners and must be visible as one.
- **Discrimination is required.** Every rule above must have a distinct rendered outcome
  and at least one counterexample in §12.3.

**Verification receipt.** The v3 predicates were translated literally and swept over the
3696-combination finite domain: **0 fall-throughs, 20 distinct postures, 0 stale rows
announcing positive liveness, 0 binding-uncertainty rows leaking into `EFFECT_UNKNOWN`,
and `ACCEPTED_PRODUCT` reachable only where `acceptance.state == ACCEPTED`.** The three
literal counterexamples from review 5228672592 now resolve as
`ACCEPTED_PRODUCT` (F2), `RETURN_EXECUTION_MISMATCH` (F0) and `HISTORICAL_OBSERVATION`
(G1h) respectively. Harness sha256
`72b62bb88b5839d227bd4dfa561d7bf8a278d7e87bc46ea0498264470c3ebcbd`. This is a
translation of the written predicates — **not an implemented reducer, not a Runtime
test, and not evidence about any host.**

## 6. The consumer contract — `mastermind.mission_workspace.v1`

### 6.1 Shape

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
    source_generation: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Pure deterministic read-only mission workspace projection."""
```

No I/O, environment, clock, randomness, mutation, provider inspection or second join.
Same inputs ⇒ byte-identical `json.dumps(doc, sort_keys=True)`. Enforced by an AST
anti-authority test, as `tests/test_fabric_job_view.py` D6 and the DF1 plan both do.

Closed top-level key set:

```json
{
  "schema": "mastermind.mission_workspace.v1",
  "generated_at": "…Z",
  "source": {"control_room_schema": "…", "control_room_generated_at": "…Z",
             "fabric_view_schema": "…", "fabric_view_generated_at": "…Z",
             "source_generation": {}, "source_coverage": []},
  "read_state":   {"state": "CURRENT", "reason_codes": [], "usable_sections": []},
  "program":      {"work_ref": "WS:…", "title": null, "state": null,
                   "next_action": null, "evidence": []},
  "mission":      {"root_job_id": null, "root_job_candidates": [],
                   "root_job_ambiguous": false, "runtime_root_state": "UNKNOWN",
                   "status": null, "orchestration_role": null, "plan_step_id": null,
                   "depth": null, "title": null, "armed": {},
                   "submission_availability": "UNKNOWN", "capability": {},
                   "evidence": []},
  "principal":    {"accountable_seat": null, "current_worker": null,
                   "current_sol_target": null, "owed_turn": null, "evidence": []},
  "children":     {"state": "…", "coverage": "…", "reason_codes": [],
                   "total_count": null, "items": [], "overflow_count": null},
  "execution":    {"state": "NOT_STARTED", "summary_present": false, "artifacts": [],
                   "errors_present": false, "next_actions": [], "evidence": []},
  "review":       {"required": null, "reviews_job_id": null, "verdict": "NOT_YET",
                   "evidence": []},
  "transport":    {"dispatch_state": "UNKNOWN", "reason": null, "actionable": false,
                   "historical": true, "watch_proven": null, "carrier": null,
                   "w3c": null, "evidence": []},
  "acceptance":   {"state": "NOT_PROJECTED",
                   "reason_codes": ["ACCEPTANCE_OWNER_NOT_PROJECTED"],
                   "owner": null, "artifact_revision": null, "ruling": null,
                   "evidence": []},
  "posture":      {"value": "UNKNOWN", "rule": null, "evidence": []},
  "conversation": {"state": "UNAVAILABLE", "coverage": "NOT_PROJECTED",
                   "reason_codes": ["MISSION_TREE_SUBSLICE_EXCLUDES_CONTENT"],
                   "total_count": null, "items": [], "overflow_count": null},
  "missingness":  [],
  "degraded":     [],
  "budget":       {},
  "feature_gates": {"conversation": "UNAVAILABLE", "actions": "READ_ONLY",
                    "advanced": "AVAILABLE"}
}
```

Every list section uses the **DF1 §8.3 envelope verbatim** —
`{state, coverage, reason_codes, total_count, items, overflow_count}` — with DF1's rules:
`COMPLETE` permits exact integers; `INCOMPLETE` requires `total_count = null` **and**
`overflow_count = null` while known items stay visible; `NOT_PROJECTED` is never a zero;
`EMPTY` only when coverage is complete and the exact total is zero. Section states are
DF1's five; read states DF1's four. **No parallel vocabulary is minted.**

`missingness[]` uses the `fabric_job_view` fact shape verbatim —
`{missingness_class, target_field, producer_owner, reason}`, class ∈
`{MISSING_PRODUCER, NULL_BY_DESIGN, EXCLUDED, OMITTED, DEGRADED}`.

Every `evidence[]` entry uses the DF1 §11 tuple verbatim —
`{owner, ref, field, source_revision, source_time, observed_at, freshness_state}` — with
DF1's nine closed owners, 0–32 refs per item, no arbitrary URL or filesystem path,
`source_revision` null rather than fabricated, dedupe by the complete tuple.

### 6.2 Field semantics that are not obvious

- **`armed.*` is tri-state.** Absent or unreadable `control.json` ⇒ every bit `null` and
  `armed.source == "absent"` — **never `false`**. A `false` bit is a positive fact the
  host asserted; `null` is ignorance. The workspace renders
  `mission.submission_availability` (§5.2) and **never** the producer's existential
  sentence.
- **`runtime_root_state`** separates three cases that all leave `root_job_id` null:
  `RESOLVED` (exactly one candidate), `CONFLICT` (2+, reconciliation required, never a
  pick), `UNKNOWN` (no runtime evidence at all).
- **`children` coverage is `INCOMPLETE` whenever `unjoined_job_count > 0`** — counted and
  listed (first 50), never dropped, and their presence forbids an exact total.
- **`execution.state == ACCEPTED` is an execution alias**, not acceptance (§5.3).
- **`posture.rule`** names the exact table row (§5.4) that fired, so any rendered posture
  is traceable to its predicate rather than to a reader's inference.

---

## 7. Null, missing and correction rules

1. **Null is not zero.** `NOT_PROJECTED` (no producer in this generation), `UNAVAILABLE`
   (producer exists, this read failed) and `EMPTY` (complete coverage, exact total zero)
   are three states and never collapse.
2. **Absence is never completion.** An item that disappears between two generations does
   not imply it finished or was cancelled. The workspace states the gap.
3. **Known subset is not the queue.** Under `INCOMPLETE`, items may render but totals and
   overflow are `null`, and the copy says the list is known-subset evidence.
4. **A correction preserves identity.** A field whose earlier claim is no longer
   supported keeps its identity and gains a `DEGRADED` missingness fact naming the
   producer; it is never silently rewritten and never silently dropped.
5. **Freshness never renews itself.** `observed_at` comes from the producer; rendering
   does not refresh it. `generated_at` is injected, never sampled.
6. **Source time and observation time stay distinct**, and `source_revision` is `null`
   when unavailable rather than invented. This record's own §0 is the worked example of
   what happens when that rule is broken.
7. **A refusal is a rendered state.** `query_status ∈ {ok, degraded, unknown, refused}`
   and `capability.state ∈ {PROVEN, PARTIAL, UNSUPPORTED, NOT_INSTALLED}` both render. An
   absent runtime is a typed refusal with `root: null` and `children: []`; it must never
   read as "no work".
8. **An upstream source defect is recorded, not laundered.** Where a producer emits a
   statement this consumer knows to be false (§5.2), the consumer declines to echo it,
   records the defect against its owner with a reproduction, and does **not** claim the
   omission repairs the producer.

---

## 8. Auth, exposure and redaction boundaries

### 8.1 Surfaces

| Surface | Boundary | Disposition |
|---|---|---|
| **Local P0A** (`scripts/chairman_control_room.py`) | loopback-only bind, Host allowlist, CSP + nosniff, `X-CCR-Token`. The token is a **per-process browser-origin/CSRF capability nonce, not authentication of a user**: `GET /` is unauthenticated and is what delivers it, so any same-user local process can read it — that adversary is explicitly outside the threat boundary. | **R2A ships here, and only here — as partial evidence.** |
| **Remote X1** | closed-allowlist re-projection keeping only `{schema, observed_at, code_identity, source_freshness, degraded, attention, work, unjoined_open_prs}`, **dropping `sources`, `unbound_surfaces`, `binding_conflicts`, `placement_selection` and `autonomy`**; UNIX socket under systemd, group `caddy`; read routes are statics + `/healthz` + `/api/state`, no POST and no token; `remote.html` ships a 3-anchor nav with Autonomy and Surfaces structurally absent. | **Excluded.** DF1 §23.3 holds X1 from decision-first change without a separate redaction/route/package/install/production-proof operation. |
| **E1 / Executive MCP** | four static readers over authenticated `POST /mcp`; 64 KiB request / 256 KiB response ceilings; typed errors; no submit route. `executive_job` takes one `job_id` and returns no tree. | **Not used by R2A.** |
| **Worker broker** (`ohf-*`) | AF_UNIX / mTLS, generation-fenced, kernel peer-UID equality. | **Not used by R2A** (§4.5). |

### 8.2 The four proof levels, never substituted for one another

v1's error was to call the local token path "authenticated" and then treat a local
canary as the acceptance of the approved journey. Corrected:

| Level | What it proves | State |
|---|---|---|
| **L1 build** | source compiles, reducer is pure, tests green | achievable now |
| **L2 local token-gated proof** | the mission tree renders and matches producers behind the loopback CSRF nonce | **this is R2A's ceiling** |
| **L3 authenticated client proof** | a real authenticated principal reads a real mission over the existing auth/resource boundary | **not closed here**; uses the existing auth owner; no new identity provider or auth store is created |
| **L4 product acceptance** | the accountable owner accepts the journey | separate, and gated on G7 |

Current public-edge readiness is **UNKNOWN to this record**. Earlier host census material
describes a state that is not re-verified here, and an old source description cannot
establish current readiness. L3 requires a fresh reading by its owner, not an inference
from this document.

### 8.3 Bounded acquisition — UNRESOLVED, and the networked path is held

v2 listed budgets — "max child rows / max attempts / max total rows / deadline" — with no
values and no owner-issued callable that could accept them, then required §10 to make
"one budgeted `read_fabric_view`". That callable has no budget parameter, and the failure
is below it, in the producer:

```
JobRegistry.list_jobs(self)                       # executive_runtime.py:10608
    SELECT * FROM jobs ORDER BY priority DESC,created_at_ms,job_id   -- no LIMIT
    .fetchall()                                                       -- full materialization
JobRegistry.list_attempts(self, job_id=None)      # executive_runtime.py:11002
    SELECT * FROM attempts WHERE job_id=? ORDER BY attempt_number     -- no limit
```

`list_jobs` takes **no arguments at all**, so there is no seam through which a caller can
express a bound, and `_BoundReadCursor.fetchall` forwards the whole result. Namespace or
root binding is an authorization scope, **not a read-work budget**.

Three would-be workarounds are named here so they are not reinvented, and all three are
refused:

- **Counting or truncating after the call** bounds the *response*, not the work: the rows
  were already selected, materialized and turned into objects.
- **Timing out the thread** abandons a *caller*, not a scan; the query keeps running and
  the memory stays allocated.
- **A per-viewer "bounded fallback" onto the full-table reader** is the unbounded path
  wearing a budget's name.

**Disposition.** No owner-issued bounded snapshot/read seam exists at the pin. This is
recorded as genuine upstream producer gap **G8**, owned by the Executive Runtime /
`fabric_job_view` owners — **this records child does not design, name or implement that
API, and does not invent an already-bounded one.** Until G8 is closed by its owner with an
exact callable contract, concrete limits (or the exact accepted configuration fields
supplying them), and a discriminator proving records beyond the bound are never
materialized:

> **The networked R2A path is HELD.** `/mission` and `/api/mission` are specified but must
> not be exposed. The pure reducer, its finite-domain truth-table sweep, and every
> contract test proceed, because they take already-composed documents as input and
> acquire nothing.

This is the honest state, not a deferral: **R2A cannot be called an implementation-ready
end-to-end freeze while the acquisition seam is undecided.** §10 is therefore a frozen
consumer contract plus a held route, and the receipt must say so.

**Generation vector across both sources.** When G8 closes, the read must carry a
generation vector spanning *both* contributing owners — the CCR cache generation and the
Runtime generation — obtained the way `_gather_dispatch_evidence` already does it, by
bracketing the read with explicit generation receipts and failing every derived row
closed on movement. A before/after wall-clock timestamp is not a generation vector.

### 8.4 Allowlisted exposure — B6 (this part stands)

`textContent` prevents HTML execution; it does **not** prevent disclosure. The raw
producer carries an absolute filesystem path (`runtime.root`, `fabric_job_view.py:645`),
raw first-line errors (`_bounded(error)`, `:403`) and arbitrary model-authored
result/artifact strings. The workspace emits a **finite allowlisted view**:
`runtime.root` is never emitted; `attempt.error` becomes `error_present` plus an
allowlisted classification; free-text fields pass the **existing** redaction owner
(`chairman_control_room_remote._reject_sensitive_values`, `:497` — email, private host,
path, session, `X-CCR-Token`, `traceback`) using its established redact-to-fixed-token
idiom (`_project_agent_os_freeform`, `:520`) — not a new sanitizer and not a new policy
owner. Errors shown to a viewer are fixed strings.

**"Field-for-field" means allowed fields.** §12.1's cross-check compares the semantics of
the allowlisted projection against its sources. It must never be satisfied by leaking a
raw field, and a deliberately withheld field is checked as *correctly absent*.

**Negative controls are mandatory**: a secret-shaped string, an absolute path, and an
oversize document must each be proven absent from JSON *and* DOM.

## 9. No-rebuild boundaries

Do not create: a second Job/Attempt/Worker lifecycle or store; a conversation or
transcript archive; a second connected reader; a provider-session registry; an evidence
store; an auth plane or identity provider; a graph authority; a universal acceptance
store; a second freshness clock, cursor DB, queue, retry ledger, cache authority or
scheduler; a universal `/api/mission` invoke endpoint; a second sanitizer, redaction or
label authority; a parallel state/coverage vocabulary; a new `DISPATCH_STATES` token.

Do not edit: any producer module in §3; any X1 route, static asset, package or install
closure; `.github/workflows/`; any Figma file.

Do not take over: #702's six paths, #523's DF1 plan, the incumbent connected-reader work,
#595, #600, #653, #677, #684, #688, #697, H3e, AD-RET2, CCTX-1, PF1, DF1, Macro #7120 or
#7181. Source custody of `fabric_job_view.py` stays with its owner (§5.2).

---

## 10. Implementation path list

Create:

1. `control_plane/mission_workspace.py` — the pure reducer of §6.
2. `app/static/chairman_control/mission.html`
3. `app/static/chairman_control/mission.js`
4. `app/static/chairman_control/mission.css`
5. `tests/test_mission_workspace.py` — reducer, total-truth-table matrix, AST anti-authority test.
6. `tests/test_chairman_control_room_mission_server.py` — route, query, auth, budget, size.
7. `tests/test_chairman_control_room_mission_ui.py` — browser tests.
8. `docs/superpowers/plans/<date>-mastermind-os-r2a-mission-workspace.md` — the plan.

Modify:

9. `scripts/chairman_control_room.py` — add exactly four routes.
10. `docs/CHAIRMAN_CONTROL_ROOM.md` — document them.

Plus **path 11**, which is not optional and is not this record's to grant — see §10.1.

Routes, following DF1 §5:

```text
GET /mission?work_ref=<ref>&root_job_id=<id>      token-injected mission.html, same CSP as /
GET /api/mission?work_ref=<ref>&root_job_id=<id>  token + Host + Origin + no-store gated JSON
GET /static/mission.js
GET /static/mission.css
```

### 10.0 The query decision — RESOLVED, with conditions

v1 returned `PATH_BOUNDARY_REQUIRED`. Review 5228415542 resolves it: **a finite query is
allowed for the NEW `/mission` and `/api/mission` resources only.** DF1's `/brief` and
`/api/brief` keep their exact reject-every-query rule; there is **no global relaxation**.
The allowance is bounded by all of the following, every one of which precedes any read:

- **exactly one occurrence each** of the two accepted keys; a repeated key is a refusal,
  not a last-value-wins;
- **length bounds checked before decoding**;
- strict rejection of malformed percent-escapes, invalid UTF-8, blank values, and any
  unknown key;
- current owner grammar for each value (`_WS_TOKEN_RE` for the work ref; the Runtime
  job-ref grammar for the root id);
- **no path, host, argv, endpoint or profile is ever constructed from either value**;
- the exact `(work_ref, root_job_id)` pair is verified to exist as an authorized
  relation, and the named Job is verified to be an actual root — **two individually
  valid ids are neither a join nor a permission**;
- the owning source generation is revalidated; a conflicting or stale relation stays
  refused/unknown rather than rendered.

Any other query shape is a 400 before any read. This closes the boundary question for
this query shape only. It is **not** a source START, not an implementation admission,
and not a release gate.

**These four routes are specified and HELD.** Per §8.3 they must not be exposed until
producer gap **G8** is closed by its owner: the mission acquisition has no bounded seam,
and the R2A request path **must not call the full-table reader as a supposedly bounded
fallback**. What proceeds now is the pure reducer and its contract tests, which acquire
nothing.

Route rules, frozen for when the hold lifts: `/api/mission` reads the one cached CCR
snapshot (no synchronous composition) and performs **one** acquisition through the
owner-issued bounded seam named by G8 — never `read_fabric_view` as it exists at this
pin; canonical-encoded; maximum successful body exactly 262144 bytes; larger returns HTTP
503 with `{"schema":"mastermind.mission_workspace_error.v1",
"error":"MISSION_WORKSPACE_RESPONSE_TOO_LARGE"}`; no partial success bytes; no new POST;
`/` remains Advanced. Whatever seam G8 delivers must be opened with
`Runtime.at(root, create=False)`: a bare `Runtime.at(root)` defaults to `create=True` and
would manufacture an empty database and then report a quiet, job-free company.

### 10.1 The entry journey — path 11, owned elsewhere

The ten paths above produce a **route**, not a journey. §3.1 found a dangling
`root_job_id` string in the existing drawer that navigates nowhere; a browser scenario
that hand-constructs `/mission?work_ref=…&root_job_id=…` in the address bar leaves that
dangling id exactly as it was and proves nothing about the persona.

Two admissible dispositions, and the implementer must land on one explicitly:

- **(a) Close it.** Reconcile with the incumbent DF1 / Control Room writer and freeze
  **one** exact mission link in the existing Program or autonomy drawer, under that
  owner's custody, as path 11. No broad index or style rewrite, no default cutover, no
  second navigation model.
- **(b) Declare it.** If that reconciliation is not granted, the slice ships as
  **route-only and explicitly NOT user-complete**, and says so in the receipt and in the
  UI copy. It does not get described as a Chairman journey.

**The label maps are not the implementer's to clone.** v1 said `mission.js` would carry
its own copy of `AU_DISPATCH` / `AU_DISPATCH_VARIANT` because the path ceiling forbids
editing `control_room.js`, and called that a recorded cost. That is a second label
authority created for path-ceiling convenience, which §9 forbids. Corrected: either
consume the existing map or qualified projection, or freeze a **shared extraction with
its owner** as part of path 11. An inconvenient ceiling is a reconciliation to request,
not a licence to fork a vocabulary.

### 10.2 What R2A must not re-render

Because the shipped inspector already has a work-ref drawer and an autonomy drawer
(§3.1), the mission page is **only the tree and its per-job facets**: mission header,
principal summary, `children[]` with roles and attempts, execution, review, transport,
acceptance, posture, the conversation exclusion, and the missingness list. It must not
re-implement the Agent OS / GitHub / attention / source-drift / navigation rails — link
back to `/#work` and `/#autonomy` — and it introduces no action controls at all
(`feature_gates.actions: READ_ONLY`), so `dispatchUnsafe`'s suppression rule is inherited
by a later wave, never re-derived.

Order of work, split by the G8 hold:

**Unheld now** — reducer + the §5.4 full finite-domain sweep, red-then-green; AST
anti-authority test; pure contract tests over already-composed fixture documents.

**Held on G8** — the four routes, query/budget/auth server tests, assets, UI tests,
path-11 disposition and the L2 browser proof. None of these may be started by calling the
unbounded reader "temporarily".

Return state `DRAFT / HOLD-FOR-SOL / BUILT_NOT_PROVEN`, with the held scope named.

---

## 11. Required producer gaps

Each is owned by an existing owner. **None may be closed by this consumer.**

| Gap | What is missing | Owner | Behaviour until closed |
|---|---|---|---|
| **G1** | per-child worker identity in `mastermind.fabric_job_view.v1` | Executive OS / `fabric_job_view` owner | `children[].worker_id` null + one `MISSING_PRODUCER` fact. A safe closure adds `worker_id` only — never `os_principal_uid` or `provider_home_identity`. |
| **G2** | no producer for `CONTINUED` / `STOPPED` | dispatch-consumption owner + dialogue close-law owner | both `NOT_PROJECTED`; never inferred from Slack text or watcher silence; no new token |
| **G3** | no authorized after-the-fact content history through the admitted path; the hot window is prospective-capture-only, 4-turn FIFO, `agentMessage`-only, and `ohf-observe-turn` has no production consumer | incumbent connected-reader / content-resource owner; organizationally ASD-A4 (`status: todo`, behind ASD-A3 **and** P0B) | bounded authorized hot window with explicit gaps remains the accepted first live-content release under its owner; this sub-slice simply excludes content |
| **G4** | no HTTP read path to `mastermind.fabric_job_view.v1` | this consumer creates it — the only new surface R2A adds | n/a |
| **G5** | no human-readable mission title on an Executive Job | Executive OS | `mission.title` null + `MISSING_PRODUCER`; never synthesized from the workstream title |
| **G6** | *(withdrawn as stated in v1)* the arm-state claim was a copied upstream defect, not a gap. Recorded in §5.2 against `fabric_job_view.py`'s owner. | `fabric_job_view` owner | existing roots retained after DISARM; the producer's existential sentence is not echoed |
| **G7** | **no product/artifact acceptance producer at all** | the existing acceptance/decision owner | `acceptance.state: NOT_PROJECTED`; posture ceiling is `REVIEWED_NOT_ACCEPTED`. F2 is *reachable but unproduced* — an absence gate, not a dead branch (§5.4) |
| **G8** | **no owner-issued bounded snapshot/read seam for mission acquisition.** `list_jobs()` takes no arguments and runs `SELECT * FROM jobs … .fetchall()` with no LIMIT (`executive_runtime.py:10608`); `list_attempts` has no limit (`:11002`); `_BoundReadCursor.fetchall` forwards. Namespace binding is authorization scope, not a read-work budget. | Executive Runtime / `fabric_job_view` owners | **the networked R2A path is HELD** (§8.3). Pure reducer and contract tests proceed; no per-viewer unbounded fallback, no second gather or cache owner. |

---

## 12. Proof obligations

### 12.1 L2 — local token-gated mission-tree proof (R2A's ceiling)

**Gated on G8 (§8.3).** This proof cannot run while the networked path is held, because
it requires the acquisition seam that does not yet exist. It is frozen here so it is ready
when the hold lifts, not scheduled.

Local P0A path, real browser, one real Runtime root. Screenshots are attachments, never
production captures.

1. Start the local Control Room against a checkout whose
   `data/control_plane/executive.sqlite3` holds at least one real root; find a root id
   with `python3 scripts/fabric_job_view.py --list-roots --runtime-root <abs>`.
2. Open `/` (Advanced); confirm the token is delivered and cached state loads.
3. Reach the mission page **through path 11's disposition** — the frozen drawer link if
   §10.1(a) was granted; otherwise record explicitly that entry was hand-constructed and
   the slice is not user-complete.
4. Assert on screen: Program title and state; `root_job_id` with `runtime_root_state`;
   accountable seat and `current_worker`; the child list with each `orchestration_role`
   and `latest_attempt.status`; the posture chip **with its firing rule**; `review
   .verdict`; `execution.state`; `transport.dispatch_state`; `acceptance` reading
   *not projected*; `conversation` reading *excluded from this sub-slice*; every
   `MISSING_PRODUCER` fact visible rather than hidden.
5. **Cross-check the allowlisted projection against its producers in the same session**:
   `python3 scripts/fabric_job_view.py --runtime-root <abs> --root-job-id <id> --json`
   for the tree, and the `autonomy` block of `GET /api/state` for principal and
   transport. Every projected field must agree; every deliberately withheld field must
   be confirmed **absent** from JSON and DOM.
6. Prove the §12.3 negatives that the available fixtures can reach.
7. Prove read-only-ness: no POST, no storage write, no provider or runtime mutation.
8. Desktop 1440, tablet 1024, mobile 390: no horizontal overflow, keyboard activation of
   every known target, focus restoration after any dialog, no colour-only state.

Not proof: a green suite, a screenshot, a merged PR, or a page whose values were never
compared to the producers.

### 12.2 L3 → L4 sequence

`R2A (L2)` → **authorized live content through the incumbent owner** → `L3 authenticated
client proof` → `L4 product acceptance`. The content stage carries its own obligations,
which this record names rather than performs: **one real observed output before native
terminal completion**; **viewer revoke, reconnect and gap behaviour** proven; and **one
terminal result consumed by the original controller**. No covert viewer grant may be
minted to manufacture retention. L4 additionally requires G7.

### 12.3 Negative matrix — each must render distinctly

Truth-table discrimination (§5.4 v3) — one counterexample per rule, plus the
full finite-domain sweep asserting zero fall-throughs and exactly one effective outcome
per admitted combination:

- **A1** proven `EFFECT_UNKNOWN` outranks optimistic progress; every actuator disabled;
  copy says *reconcile the original operation, do not resend*.
- **B1** binding reconciliation required — rendered as `RECONCILIATION_REQUIRED`, and the
  test asserts it is **not** `EFFECT_UNKNOWN`: binding uncertainty is not evidence that an
  effect occurred.
- **B2** source-generation conflict, even where an earlier generation looked terminal.
- **C1–C4** `FAILED` / `CANCELLED` / `LOST` / `RATE_LIMITED` each render as themselves,
  never as a return and never as a completion.
- **D1** Steward blocker or Agent-OS declared blocker.
- **E1** `DELIVERY_UNCONSUMED` / `canonical_wake_unacknowledged`: delivered, never
  acknowledged; must not render active, started or waiting.
- **E2 / E3** `WATCH_UNPROVEN`, and separately a **stale** `RETURNED`: both say *we cannot
  tell*, **not** *unconsumed*.
- **F0** `RETURN_EXECUTION_MISMATCH` — a current return against `IN_PROGRESS` or
  `NOT_STARTED` execution. This is one of the two combinations v2 dropped entirely.
- **F1** `ACCEPTANCE_REVIEW_CONFLICT` — an acceptance ruling against a rejecting review.
- **F2** `ACCEPTED_PRODUCT` — the synthetic positive case, proving the branch is
  **satisfiable**, together with the assertion that it never fires while
  `acceptance.state == NOT_PROJECTED`. The two halves are what distinguish an absence gate
  from v2's dead branch. This fixture **is not a live acceptance producer** and authorizes
  no such state in R2A.
- **F3 / F4 / F5** review rejected / returned-unreviewed (Case A of §5.1) /
  reviewed-not-accepted — the honest ceiling of the current estate.
- **G1 vs G1h** a current `STARTED` renders `RUNNING`; a **stale** `STARTED` renders
  `HISTORICAL_OBSERVATION` with its dated observation. The test asserts no stale row in
  the whole domain announces present-tense liveness.
- **G2 vs G2h** the same gate for the four waiting states.
- **H1** admitted, never claimed; never `RUNNING`, never `FAILED`.
- **I1** an unrecognized combination resolves to typed `UNKNOWN` rather than falling
  through.

Source, coverage and identity:

13. **Absent runtime** — `db_present: false`, `capability.state: NOT_INSTALLED`,
    `root: null`, `children: []`; no directory, file or journal is created; never reads
    as "no work".
14. **Unreadable runtime** — `capability.state: UNSUPPORTED`; distinct from 13.
15. **Unknown root** — `MISSING_PRODUCER` on `root` plus a named degraded entry.
16. **Stale state** — cached snapshot past TTL with a failed refresh: `read_state:
    HISTORICAL`, dated; a retained stale empty section must **not** become a clear zero.
17. **Ambiguous root** — 2+ candidates: `CONFLICT`, candidates listed, `root_job_id`
    stays null; never a pick by recency.
18. **Unjoined children** — coverage `INCOMPLETE`, totals null, ids listed, gap named.
19. **Corrected evidence** — Case B of §5.1: `ACCEPTED` with `summary: None` plus the
    `DEGRADED` fact; posture follows its review verdict and the fact renders beside it.
20. **Undecided review** — absent and empty verdicts both `NOT_YET`; never `reject`.
21. **Terminal STOP** — `CONTINUED`/`STOPPED` render `NOT_PROJECTED` (G2). A terminal
    child wave never implies the parent Program is terminal, and a child STOP never
    disarms a sibling or aggregate lane.
22. **admission → DISARM → read existing root** — the root is still returned; new-submission
    unavailability is explained; **no existential claim is rendered** (§5.2).
23. **Absent config ≠ false** — all five bits `null`, `armed.source: "absent"`,
    `submission_availability: UNKNOWN`.
23b. **`armed=true` is not availability** — with a missing readiness, receipt or binding
    projection, `submission_availability` stays `UNKNOWN`; `AVAILABLE` is never rendered
    in R2A (§5.2).

Query, budget and exposure:

24. **Bad query** — missing, extra, blank, duplicated, over-length, malformed-escape or
    invalid-UTF-8 parameter: 400 before any read.
25. **Valid ids, invalid join** — two individually well-formed values whose pair is not an
    authorized relation, and a well-formed job id that is not a root: both refused.
26. **Budget exceeded** — typed refusal plus `coverage: INCOMPLETE`; never silent
    truncation. *Held on G8: this case cannot be written until the bounded seam exists,
    and a post-hoc truncation test must not be substituted for it (§8.3).*
27. **Oversize** — past 262144 bytes, the typed 503 before any partial bytes.
28. **Secret-shaped and path-shaped material upstream** — absent from JSON **and** DOM;
    `runtime.root` never emitted; `attempt.error` never emitted raw.
29. **Hostile text** — a summary containing HTML, a Slack mention or a ` ` renders
    inert; no interpolation, no execution.

No negative may collapse to a spinner, a blank card, a false zero or a green badge.

---

## 13. Follow-on work — a proposal, not an assignment

**This section assigns nothing.** It describes what a later, separately commissioned
source child would do. #704 is a one-file records operation and does not become a
multi-file implementation because a review returns PASS. Starting that work requires all
of: this freeze clearing one non-author exact-head review; producer gap **G8** closed by
its owner, or an explicit decision to build only the unheld scope; and a **fresh
source-child assignment** through the closed preferred avenue — Terra by default, CTO Sol
where the consequence justifies it — with placement and custody resolved at that time. A
pointer in this file is none of those things.

```text
PROPOSED — Mastermind OS R2A mission-tree implementation (NOT ASSIGNED)
PARENT:   mastermind-os-rollout-contract-20260916-sol-001 (Mastermind #702)
CARRIER:  a NEW source child; #704 stays a one-file records carrier
CONTRACT: docs/superpowers/specs/2026-09-16-mastermind-os-mission-workspace-consumer-freeze.md
GATES:    (1) non-author exact-head review of this freeze
          (2) G8 closed by the Executive Runtime / fabric_job_view owner
          (3) fresh assignment via the closed preferred avenue + current custody

Unheld scope (acquires nothing; buildable once gate 1 clears)
  1. control_plane/mission_workspace.py — the pure reducer of §6.
  2. tests/test_mission_workspace.py — the §5.4 FULL finite-domain sweep asserting zero
     fall-throughs and exactly one effective outcome per admitted combination; the three
     review counterexamples; the paired F2-is-satisfiable / F2-never-fires-while-
     NOT_PROJECTED assertions; the no-stale-liveness assertion; the true-arm refusal
     case; and an AST anti-authority test (no I/O, clock, environment, randomness,
     mutation).

Held scope (gate 2)
  3-10. routes, assets, server/query/budget/UI tests, path-11 disposition, L2 proof.
  The request path must NOT call the full-table reader as a bounded fallback, and no
  second gather or cache owner may be created to work around the missing seam.

Binding constraints
  - Consume producers; create none. §9 is binding.
  - Reuse DF1's vocabularies and fabric_job_view's missingness fact shape verbatim;
    re-read DF1 plan #523 at its current head first.
  - Never display product completion from execution, review or transport aliases (§5.3).
  - Never echo the arm-state existential sentence, and never derive AVAILABLE from a raw
    arm bit (§5.2).
  - Never clone the dispatch label maps (§10.1).
  - G1, G2, G3, G5, G7, G8 stay open and render as typed missingness or an explicit hold.
  - Remote X1 unchanged. No JOB-001 replay, no provider, credential, install or merge.

Completion
  L2 acceptance is §12.1 step 5 plus the §12.3 discrimination matrix. A green suite, a
  screenshot or a merged PR is not acceptance. R2A is not R2.
```

## Sources

Read at inspected commit `bf843961c0e1b5bd45fa481f0138c71f2a87d4e2`; all cited blobs
verified identical at current protected `e8803ba3d3ee928d150d7dcac1a1e2bad2dc0d48` (§0).

- `control_plane/fabric_job_view.py`, `docs/FABRIC_JOB_VIEW.md`
- `control_plane/chairman_control_room.py`, `scripts/chairman_control_room.py`,
  `docs/CHAIRMAN_CONTROL_ROOM.md`, `app/static/chairman_control/control_room.js`
- `control_plane/autonomy_control_room_projection.py`, `control_plane/executive_steward.py`
- `control_plane/chairman_control_room_remote.py`, `ops/control_room_remote/install.sh`
- `control_plane/visible_turn_projection.py`, `control_plane/executive_worker_broker.py`,
  `control_plane/remote_worker_broker_client.py`,
  `control_plane/executive_dialogue_observation.py`
- `control_plane/executive_orchestration_principal.py`,
  `control_plane/executive_orchestration_result.py`,
  `control_plane/executive_terminal_return.py`, `control_plane/runtime_binding_projection.py`
- `control_plane/executive_inbox.py`, `docs/EXECUTIVE_INBOX.md`, `docs/EXECUTIVE_MCP.md`
- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`, `docs/OPERATION_LIVENESS_SOUNDNESS_LAW.md`
- `docs/superpowers/specs/2026-09-07-chairman-control-room-decision-first-experience-design.md`
  (merged, `185dc742`) and its H1A supersession addendum
- DF1 plan at `bf9484a0` (open Draft #523, moved from the earlier `3c0a933b`); Mastermind #702 at `091592da`
- Macro `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md` at `0f62daf54571`
- Review 5228415542 at `8b94141106200f0c48b6d033cca19a8007ef0031`; review 5228672592 at `c09672fc50a5895e7552936d3e585455424d85ae` (file blob `7261e61b582d12a1045a2ef12ba598f4b2e24ee8`)
