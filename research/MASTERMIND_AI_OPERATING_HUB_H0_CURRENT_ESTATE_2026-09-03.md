---
schema: mastermind.ai_operating_hub_h0_current_estate.v1
operation_key: mastermind-ai-operating-hub-h0-current-estate-freeze-20260903-sol-001
parent_program: mastermind-ai-operating-hub-f0-architecture-freeze-20260902-sol-001
protected_master: 642fa62540f0f2565ccc484a350f2cd0a2259015
protected_master_tree: 3017e36c42b55c9dff0f94f31ddd791e97a65508
protected_skillpack: mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap-major 1
f0_source: PR #416 MERGED
capability_state: SPEC_ONLY
production_effect: NONE
selected_first_consumer: local P0A Chairman Control Room
organizational_owner: WS:CHAIRMAN-CONTROL-ROOM
---

# Mastermind AI Operating Hub — H0 Current-Estate Freeze

**Frozen at:** `642fa62540f0f2565ccc484a350f2cd0a2259015`
**Tree:** `3017e36c42b55c9dff0f94f31ddd791e97a65508`
**Program state after this record:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`
**Mission:** identify the real implementation seam for the first useful AI Hub vertical and prove
every required source/authority boundary — **without building it**.

This record is archaeology and contract freeze only. It creates no UI, API, database, cache,
runtime action, deployment, or production claim. It does not implement H1.

## 0. What this record decides

1. The first real HUB-V1 consumer is the **local P0A Chairman Control Room**. Fresh protected
   source proves no exact blocker.
2. Remote **X1 is preserved as a separate, smaller, closed read-only surface**. It is not the
   first consumer and must not be collapsed into P0A.
3. The durable organizational owner is the existing `WS:CHAIRMAN-CONTROL-ROOM`. No `WS:AI-HUB`
   is created.
4. The lawful H1 path ceiling is frozen **after** PR/path archaeology, and is narrowed by the
   discovery that open PR #326 already owns the autonomy status projection.

## 1. Capability ledger — revised from evidence

Vocabulary is exactly the company ledger vocabulary. Nothing here is upgraded because a schema,
route, spike, PR, or Slack delivery exists.

| Sub-capability | State | Evidence and meaning |
|---|---|---|
| Pure Control Room compositor `mastermind.chairman_control_room.v1` | `BUILT_NOT_PROVEN` | `control_plane/chairman_control_room.py` on protected master: pure `compose_control_room` + gather `build_control_room`, closed `OUTPUT_KEYS`. This carrier observed source and its own contract test only — no production readback. |
| Local P0A loopback presentation surface | `PARTIAL` | `scripts/chairman_control_room.py` binds `127.0.0.1:8787` with an allowlisted-hostname + CSP gate and six routes. Loopback/private only; navigation-only binding behavior; no deployed production path observed in this carrier. |
| Remote X1 closed read-only projection + release closure | `PARTIAL` | `control_plane/chairman_control_room_remote.py` (`mastermind.chairman_control_room_remote.v1`), Unix-socket server `scripts/chairman_control_room_remote.py`, `REQUIRED_RUNTIME_PATHS` (37 exact paths), `ops/control_room_remote/install.sh`, systemd unit. Independently accepted; no live remote readback observed in this carrier. |
| Autonomy responsibility projection `mastermind.autonomy_control_room.v1` | `BUILT_NOT_PROVEN` | Exists **only** in open Draft PR #326 (`control_plane/autonomy_control_room_projection.py`). **Absent from protected master.** Not available to H1 until #326 lands. |
| AI Hub F0 architecture | `SPEC_ONLY` | PR #416 merged; `research/MASTERMIND_AI_OPERATING_HUB_F0_ARCHITECTURE_2026-09-02.md` protected. |
| AI Hub H0 current-estate freeze | `SPEC_ONLY` | This record. |
| Cross-system operational identity composition | `NOT_BUILT` | No protected contract joins Executive/Agent OS/GitHub/Linear/Slack identities into one Hub view. |
| Hub workstream room (real-data consumer) | `NOT_BUILT` | No accepted Hub-specific consumer with a complete failure-state journey. |
| Executive attention inbox (Hub-owned) | `NOT_BUILT` | The compositor emits an `attention` branch, but no deterministic *Hub* attention contract exists. |
| Safe CEO action preflight + receipt | `NOT_BUILT` | H2 concern. No Hub action path exists or is authorized. |
| LLM operational synthesis | `SPEC_ONLY` | Advisory-only over cited preselected facts; never status or action authority. |
| Learning / intervention efficacy instrumentation | `NOT_BUILT` | No production instrumentation proves reduced orientation or unblock time. |
| Parallel Hub lifecycle / store / queue / identity / auth / retry / status plane | `REJECTED_BY_DESIGN` | Forbidden by F0 and by this freeze. |

## 2. Reference workstream and real source identity graph

**Reference workstream:** literal `WS:CHAIRMAN-CONTROL-ROOM`.

This token is bound literally, not by title similarity. The compositor's own join law uses a
word-boundary token regex over PR titles and byte-equality over the CEO-intent `workstream`
field; there is no fuzzy matching anywhere in the module. H1 inherits that law unchanged.

| Identity | Canonical owner | Exact locator on protected master |
|---|---|---|
| `workstream_key` | Agent OS | `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md` in `mastermindx-market-intelligence/macro` |
| composed contract | Control Room compositor | `control_plane/chairman_control_room.py` → `SCHEMA = mastermind.chairman_control_room.v1` |
| local presentation | Local P0A | `scripts/chairman_control_room.py`, `app/static/chairman_control/index.html` |
| shared presentation assets | Both P0A and X1 | `app/static/chairman_control/control_room.js`, `app/static/chairman_control/control_room.css` |
| remote contract | Remote X1 | `control_plane/chairman_control_room_remote.py` → `REMOTE_SCHEMA = mastermind.chairman_control_room_remote.v1` |
| remote presentation | Remote X1 | `scripts/chairman_control_room_remote.py`, `app/static/chairman_control/remote.html` |
| remote release closure | Remote X1 | `control_plane.chairman_control_room_remote.REQUIRED_RUNTIME_PATHS`, `RELEASE_SCHEMA = mastermind.control_room_build.v1`, `ops/control_room_remote/install.sh`, `ops/control_room_remote/mastermind-control-room-remote.service` |
| `job_id` / `attempt_id` / `worker_id` | Executive OS | read through `control_plane/executive_inbox.py` and runtime jobs; never recreated |
| PR / check / commit identity | GitHub | `project_active_builds.v1` snapshot; exact immutable identities only |
| portfolio projection | Linear | projection only; disagreement shown, never averaged |
| carrier (`workspace_id`/`channel_id`/`parent_ts`) | Slack | transport evidence only; never runtime consumption |

## 3. Producer / owner boundaries — proven, not assumed

The compositor declares and enforces four design laws that H1 must inherit rather than re-implement:

1. **No synthetic overall status.** There is no combined or overall lifecycle field anywhere in
   the composed document. Every fact stays attributed to its owning source.
2. **Bindings never create canonical facts.** A navigation binding may only attach to a work card
   that already exists from an Agent OS / Executive / GitHub source, or fall into
   `unbound_surfaces`. Deleting the entire bindings file changes only
   `sources.bindings_path_present` and the binding branches — no other field.
3. **Exact joins only.** A GitHub PR joins a card only via a literal word-boundary `WS:<KEY>`
   token in its title; a runtime Job joins only via byte-equal `workstream`. No title-similarity
   matching exists.
4. **Upstream key names are never renamed.** Fields read off `ceo_brief.v1`,
   `mastermind.executive_inbox.v2`, and `project_active_builds.v1` keep their upstream names.

**Two-layer separation.** `compose_control_room` is pure — no file I/O, no subprocess, no clock
read, no environment read; identical inputs yield byte-identical `json.dumps(..., sort_keys=True)`.
`build_control_room` is the only gather layer, and it never raises: every source failure becomes a
`None` input plus a named `degraded` entry. H1 must extend at the gather/consumer edge, never by
adding I/O or clock reads into the pure layer.

**P0A and X1 are separate accepted contracts, not two names for one surface.** They share
`control_room.js`, `control_room.css`, and the pure compositor — and nothing else. Their HTML
entries, servers, route/auth contracts, release packaging, and proof obligations are distinct:

| Dimension | Local P0A | Remote X1 |
|---|---|---|
| contract schema | `mastermind.chairman_control_room.v1` | `mastermind.chairman_control_room_remote.v1` |
| entry | `app/static/chairman_control/index.html` | `app/static/chairman_control/remote.html` |
| server | `scripts/chairman_control_room.py` | `scripts/chairman_control_room_remote.py` |
| transport | TCP loopback `127.0.0.1:8787`, allowlisted hostnames, CSP | Unix socket `/run/mastermind-control-room/remote.sock`, gid/uid gated |
| routes | 7 exact path equalities: `/favicon.ico`, `/api/state`, `/api/discover`, `/api/open`, `/api/bind`, `/api/unbind`, `/api/refresh-builds` | closed `READ_ROUTES` allowlist, 5 entries: `/`, `/static/control_room.css`, `/static/control_room.js`, `/healthz`, `/api/state` |
| mutation | navigation-only local binding writes | **none** — read-only by construction |
| release closure | none | `REQUIRED_RUNTIME_PATHS` + manifest digest + attestation + installer + unit |
| redaction | not applicable | mandatory: email / private-host / path / session patterns rejected |

Collapsing these would break X1's release attestation and its redaction law. **The split is frozen.**

## 4. Field, source, time, null, freshness, correction, permission, failure semantics

Frozen over the actual closed `OUTPUT_KEYS` of `mastermind.chairman_control_room.v1`:
`schema`, `generated_at`, `sources`, `degraded`, `attention`, `work`, `unjoined_open_prs`,
`unbound_surfaces`, `binding_conflicts`, `placement_selection`.

| Field | Canonical owner | Query / source | Time semantics | Null & failure | Correction | Permission | Freshness budget |
|---|---|---|---|---|---|---|---|
| `schema` | compositor | module constant | none | never null | version bump only | public within surface | n/a |
| `generated_at` | caller of the pure layer | injected, never read from a clock inside `compose_control_room` | composition instant, UTC `Z`, second precision | never null | recompose | same as document | drives every staleness judgment |
| `sources` | compositor | per-source presence/`generated_at` echoes | echoes upstream source times | present-but-empty is meaningful | re-gather | local only — **dropped in X1** | per-source |
| `degraded` | gather layer | named failure strings, sorted | observation instant | empty list = no known failure, **not** proof of health | fix the source, recompose | surfaced in both P0A and X1 | immediate |
| `attention` | Executive OS via `executive_inbox` | inbox items | upstream item times | missing inbox ⇒ `executive_inbox: unavailable` in `degraded` | correct in Executive OS | Executive permission | inbox cadence |
| `work` | Agent OS + Executive + GitHub joined by exact `WS:` token | brief / state / jobs / active builds | per-source; **never merged into one time** | a card may exist with null runtime or null PR branches | correct at the owning source, never in the Hub | per-source | per-source |
| `unjoined_open_prs` | GitHub | `project_active_builds.v1` open PRs with no extractable `WS:` token | snapshot compile time | empty = every open PR joined | add the `WS:` token to the PR title | GitHub read | snapshot cadence |
| `unbound_surfaces` | local bindings | bindings file | binding `observed_at` / `last_verified_at` | absent bindings file ⇒ only `bindings_path_present` changes | rebind locally | **local only — dropped in X1** | binding cadence |
| `binding_conflicts` | local bindings | conflict detection | binding times | empty = no detected conflict | rebind | **local only — dropped in X1** | binding cadence |
| `placement_selection` | placement module | optional module | module output | module not shipped ⇒ `placement_selection: unavailable (module not shipped)` in `degraded` | fix upstream module | local | per-call |

**X1 additional semantics.** The remote projection replaces local authority fields with
`code_identity` (`commit`/`tree`/`artifact_digest`, `sha256:` digest form enforced) and
`source_freshness`, a closed map over exactly `agent_os_brief`, `agent_os_state`, `active_builds`,
`executive_runtime`, each with `state ∈ {fresh, stale, unavailable}` plus `observed_at`,
`source_time`, and `reason`. A freshness map whose key set differs raises
`freshness_sources_mismatch`. `observed_at` and `source_time` are **separate** and must never be
conflated. Any non-finite number, or any value matching the sensitive-value patterns, is rejected
rather than redacted-in-place.

**Failure law.** "green", "merged", "delivered", "queued", "running", "deployed", and "accepted"
remain distinct concepts. An empty `degraded` list is the absence of a *detected* failure, never
evidence of health. Silent fallback is forbidden: when a canonical path is unproven or state is
stale, the surface disables the affordance and names the exact blocker.

## 5. Collision census and PR archaeology

Observed against protected master `642fa62540f0f2565ccc484a350f2cd0a2259015`:

- exact branch `sol/ai-operating-hub-h0-current-estate-freeze-20260903` — **absent** before START,
  local and remote
- exact operation PR — **absent** before START
- all four owned H0 paths — **absent** on protected master before START
- no worktree occupied the target path
- `WS:AI-HUB` — **absent** from protected master, and this record does not create it

| PR | State | Head | Relevance |
|---|---|---|---|
| #416 | `MERGED` (merge commit `812be940cec5db025a5ef8f99f71a0e30a92bb8e`) | `e2e8543b3a3bcd4edd33e5f95a611e3c945bbbe5` | F0 architecture protected. This H0 record is its successor; no stale F0-release step is executed. |
| #326 | `OPEN / DRAFT` | `2eb9d23b2f1fc116cd4071c1f4651da9e87366f2` | **Blocking for H1 UI paths.** Owns `control_plane/autonomy_control_room_projection.py` (`mastermind.autonomy_control_room.v1`, own `OUTPUT_KEYS`, `query_status` / `is_actionable` / worst-wins `_combine_status`, source receipts) and modifies `control_room.js`, `control_room.css`, `index.html`, the compositor, and `chairman_control_room_remote.py`. |
| #350 | `OPEN / DRAFT` | `f0e681bf797522e09f2224fbc866f5aab2f62bb1` | Downstream of #326 on the shared packaging paths `control_plane/chairman_control_room_remote.py` and `ops/control_room_remote/install.sh`. |

**The material archaeology finding.** PR #326 is not merely a UI change. It already implements the
derived status/attention combination logic that a naive H1 would invent: a per-card single
`query_status`, worst-wins severity ranking, routine-absence neutralization, and per-source
receipts. Any H1 that re-derives card status would create exactly the duplicate status authority
F0 marks `REJECTED_BY_DESIGN`. This is why the H1 ceiling below is narrower than it would have been
without this archaeology.

## 6. No-rebuild boundary — explicitly reused owners

| Fact or effect | Canonical owner | H1 treatment |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle | Executive OS | read through reviewed APIs; never recreate |
| Workstreams, decisions, discoveries, handoffs | Agent OS | read and deep-link; corrections go to Agent OS |
| Code / PR / checks / evidence | GitHub | exact immutable identities; never mirror as truth |
| Portfolio selection and gate projection | Linear | projection; show disagreement explicitly |
| Delivery and hot-state transport | Slack | transport evidence; never infer runtime consumption |
| Authentication and permission | existing surface owner (P0A loopback gate; X1 socket gid/uid gate) | reuse; **no Hub-local identity or auth authority** |
| Join / composition law | `control_plane/chairman_control_room.py` | reuse the pure compositor; never fork the join law |
| Derived card status / actionability | `control_plane/autonomy_control_room_projection.py` (PR #326) | **consume once merged; never re-derive** |
| Remote redaction + release attestation | `control_plane/chairman_control_room_remote.py` | reuse; never bypass |
| Model synthesis | Hub intelligence layer | advisory only, provenance-bound, never action or status authority |

Any H1 change creating a parallel lifecycle/status store, model-derived current state, hidden
retry or failover, duplicate identity mapping, second auth layer, or Hub-owned workstream truth is
`REJECTED_BY_DESIGN`.

## 7. Selected first consumer — decision and falsifier

**Selected:** local **P0A Chairman Control Room**.

**Why no exact blocker exists.** P0A already has a live server process, a real route surface, a
real static entry, the shared JS/CSS, and a direct dependency on the pure compositor. It is
loopback-private, so an added read-only view carries no public exposure, no new auth layer, and no
deployment step. It is the smallest surface on which an authorized user can complete the H1
orientation job end to end.

**Why X1 is not the first consumer.** X1 is deliberately smaller and closed: a fixed
`READ_ROUTES` allowlist, mandatory redaction, and a release-attestation closure that pins 37 exact
runtime paths plus an installer and a systemd unit. Adding a Hub view there would force a release
manifest change and a remote deployment — both outside the H1 read-only budget. X1 is preserved
unchanged and separately.

**Falsifier for this selection.** If, before H1 START, protected source shows that P0A's
loopback-only binding cannot serve a Hub read view without adding a mutation route or a second auth
layer, this selection is wrong and H1 must return
`DECISION_REQUEST / CONSUMER_BOUNDARY_REQUIRED effect=NONE` rather than widening P0A's mutation
surface.

## 8. Frozen lawful H1 path ceiling

Frozen **after** the PR/path archaeology in §5, and deliberately conditional on it.

**H1 may create (new paths only):**

1. `control_plane/ai_operating_hub_workroom.py` — one typed, pure derived read-only contract
2. `tests/test_ai_operating_hub_workroom.py` — deterministic contract tests
3. `app/static/chairman_control/hub_workroom.js` — one additive presentation module
4. `docs/superpowers/plans/2026-09-XX-ai-operating-hub-h1-implementation-receipt.md` — the H1 receipt

**H1 may modify — only after PR #326 merges:**

5. `scripts/chairman_control_room.py` — one additive read-only route
6. `app/static/chairman_control/index.html` — one additive mount point

**H1 must not touch, in any circumstance:**

- `control_plane/chairman_control_room.py` (the pure compositor join law)
- `control_plane/chairman_control_room_remote.py`, `scripts/chairman_control_room_remote.py`,
  `app/static/chairman_control/remote.html`, `REQUIRED_RUNTIME_PATHS`,
  `ops/control_room_remote/install.sh`, `ops/control_room_remote/mastermind-control-room-remote.service`
- `app/static/chairman_control/control_room.js`, `app/static/chairman_control/control_room.css`
  (owned by PR #326 while it is open)
- `control_plane/autonomy_control_room_projection.py` (PR #326)
- anything owned by PR #350

**Blocking precondition.** Paths 5 and 6 are contended by open PR #326. H1 must not edit them while
#326 is open. If H1 opens before #326 merges, it is limited to paths 1–4 and must return
`BLOCKED UI_PATHS_CONTENDED_BY_PR_326 effect=NONE` for paths 5–6.

A path outside this ceiling requires `DECISION_REQUEST / PATH_BOUNDARY_REQUIRED effect=NONE`
before edit.

## 9. H1 handoff

The bounded H1 mission is specified in
`docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-read-only-workstream.md`.

## 10. Effects and non-effects of this record

**Effects:** one branch, one Draft/HOLD PR, four new records-only files.

**Non-effects:** no H1 implementation; no UI, API, database, cache, or runtime action; no change to
the compositor, P0A, or X1; no change to PR #326 or #350; no `WS:AI-HUB`; no Agent OS, Linear,
Executive, or Slack lifecycle mutation; no Mac or browser action; no deployment; no production
effect; no Ready, merge, or self-review.

**Stop condition.** Stop after the H0 return. H1 remains held and receives implementation authority
only after this H0 record is independently reviewed and protected.
