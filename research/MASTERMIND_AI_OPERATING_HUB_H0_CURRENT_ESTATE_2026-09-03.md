---
schema: mastermind.ai_operating_hub_h0_current_estate.v1
operation_key: mastermind-ai-operating-hub-h0-current-estate-freeze-20260903-sol-001
parent_program: mastermind-ai-operating-hub-f0-architecture-freeze-20260902-sol-001
protected_master: 771a95586c7a31933ee612eafaa4d1471f57527b
protected_master_tree: 4d132e3202598791f292853937c4bf9ce4c508f7
protected_skillpack: mastermind.sol_skillpack.v1 / 1.0.1 / bootstrap-major 1
f0_source: PR #416 MERGED
capability_state: SPEC_ONLY
production_effect: NONE
selected_first_consumer: local P0A Chairman Control Room
organizational_owner: WS:CHAIRMAN-CONTROL-ROOM
---

# Mastermind AI Operating Hub — H0 Current-Estate Freeze

**Frozen at:** `771a95586c7a31933ee612eafaa4d1471f57527b`
**Tree:** `4d132e3202598791f292853937c4bf9ce4c508f7`
**Program state after this record:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`
**Mission:** identify the real implementation seam for the first useful AI Hub vertical and prove
every required source/authority boundary — **without building it**.

This record is archaeology and contract freeze only. It creates no UI, API, database, cache,
runtime action, deployment, or production claim. It does not implement H1.

> `capability_state: SPEC_ONLY` in the frontmatter above describes **this record's own nature**
> — a records-only freeze document — not the capability state of the underlying Control Room.
> §1 below reports the underlying capability ledger, which correctly contains accepted
> `PROVEN_LIVE` rows. Do not conflate the two.

## 0. What this record decides

1. The first real HUB-V1 consumer is the **local P0A Chairman Control Room**. Fresh protected
   source proves no exact blocker.
2. Remote **X1 is preserved as a separate, smaller, closed read-only surface**. It is not the
   first consumer and must not be collapsed into P0A.
3. The durable organizational owner is the existing `WS:CHAIRMAN-CONTROL-ROOM`. No `WS:AI-HUB`
   is created.
4. The lawful H1 path ceiling is a **nine-path** shape, frozen after PR/path archaeology, and
   H1 source START — all nine paths, not a subset — is held until **both** this H0 record and
   PR #326 are independently reviewed and protected.

## 1. Capability ledger — revised from evidence

Vocabulary is exactly the company ledger vocabulary. Nothing here is upgraded because a schema,
route, spike, PR, or Slack delivery exists — and, symmetrically, an accepted capability already
proven live by the canonical owner is not cosmetically downgraded merely because this records
carrier did not itself rerun that historical production proof. §1a splits accepted capability
truth from this carrier's own narrower observation ceiling; §1b keeps every capability this
carrier cannot itself accept honestly unpromoted.

### 1a. Accepted capability truth (Agent OS owner evidence, not this carrier's observation)

Source: `mastermindx-market-intelligence/macro@6d72b43777f84c9b8040cd641c8580b14876e34b:agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md`
(public repository, fetched directly; dated observation, see §12).

| Sub-capability | State | Accepted evidence |
|---|---|---|
| Local P0A presentation + H0 hardening | `PROVEN_LIVE` | Agent OS: *"P0A plus H0 is `PROVEN_LIVE` on the persistent Chairman path."* Immutable receipts: Mastermind PR #110 (merge `90db9baf5bcc5f2221e3c9870c2aa09a95293c99`), PR #113 H0/H1 hardening (merge `0f319c79a7b3373a96d4866412c734de12cbf701`, CI `32599272414`, CodeQL `32599271255`, Sol review `5001161545`), PR #133 (merge `7cba4ca74003a37064cf46650f4d931a324350ba`), PR #134 (merge `591b7ace4dd9b2d46edccaa5e66eebf1ead8657f`), Macro PR #6225 (merge `5603972754e5320f06c04b08c24ed143bd30b2a2`), Macro PR #6292 (merge `fc94d43ad4142e50ec808b2f1a8d6f922ff1fa7b`, H0 persistent-8787 production adoption). |
| Remote X1 — local acceptance of contract/code | `PROVEN_LIVE` | Agent OS: *"X1 is `ACCEPTED / PROVEN_LIVE_LOCAL`."* Receipt: Mastermind PR #138 exact accepted head `55ec5069e653489541ef273fdb0e76f7df2598e7` merged as `12117ca576cec2c4f054664dd62c4e0809f27e75` after the 261-test Control Room pack, an 18/18 X1 suite, exact-head CI `32724498791`, CodeQL `32724495498`, and Sol real-browser product acceptance (desktop dark/light, compact desktop, dock breakpoint, 375×812 mobile, degraded Executive-DB-absent state, synthetic binding conflict). **Scope: this acceptance evidence was gathered over the supervised loopback service at `http://127.0.0.1:8787/` running that exact merge — it accepts X1's contract and code, not a deployed remote-socket production instance.** |
| Remote X1 — deployed remote-socket production instance | `NOT_BUILT` | No Agent OS receipt asserts a live `/run/mastermind-control-room/remote.sock` deployment; §1a's X1 row must never be read as authorizing this row. Kept as a **separate** ledger key precisely so local acceptance can never be silently promoted into remote production truth. |
| `WS:CHAIRMAN-CONTROL-ROOM` overall workstream | `PARTIAL` | Agent OS: *"`PARTIAL` overall because final P0B real-seat Open Sol foreground reachability and the production ASD transport path remain unproven."* This is the whole-workstream granularity — coarser than, and not in tension with, the `PROVEN_LIVE` P0A/H0/X1-local rows above. |

**Required discriminators for §1a (do not regress):** an accepted capability above must not be
cosmetically downgraded to `BUILT_NOT_PROVEN`/`PARTIAL` merely because this carrier's own H0
archaeology did not rerun its historical production proof; the X1-local row must never be copied
onto the deployed-remote-socket row; the overall-workstream `PARTIAL` state must not be read as
demoting the accepted sub-capability rows, and the sub-capability rows must not be read as
promoting the overall workstream past `PARTIAL`.

### 1b. This carrier's own observation ceiling — everything not independently accepted above

| Sub-capability | State | Evidence and meaning |
|---|---|---|
| Pure Control Room compositor `mastermind.chairman_control_room.v1` | `BUILT_NOT_PROVEN` | `control_plane/chairman_control_room.py` on protected master. This carrier observed source and its own contract test only; §1a's P0A/H0 acceptance is the owner's evidence for the *presentation* capability built on this compositor, not a claim that this carrier itself reran that proof. |
| Autonomy responsibility projection `mastermind.autonomy_control_room.v1` | `BUILT_NOT_PROVEN` | Open Draft PR #326 at head `8639d7a3f06277ea84c1e071b9d298d39695d91c`, **unresolved, three `CHANGES_REQUESTED` reviews** (§5). **Absent from protected master.** Treated strictly as an unaccepted open-PR candidate, never protected or live capability — see §5's blocker summary before assuming any of its dispatch/status output is trustworthy. |
| Protected Agent Dialogue Wake runtime (PR #357) | `BUILT_NOT_PROVEN` | Merged as `b28023f92458ba186937afa1e619f3b4464e149f` (§5). A protected *source* movement H1 may later read from once wired by an accepting owner; not itself a Hub capability. |
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
| `workstream_key` | Agent OS | `agentos/workstreams/WS-CHAIRMAN-CONTROL-ROOM.md` in `mastermindx-market-intelligence/macro`, current tip `6d72b43777f84c9b8040cd641c8580b14876e34b` |
| composed contract | Control Room compositor | `control_plane/chairman_control_room.py` → `SCHEMA = mastermind.chairman_control_room.v1` |
| local presentation | Local P0A | `scripts/chairman_control_room.py`, `app/static/chairman_control/index.html` |
| shared presentation assets | Both P0A and X1 | `app/static/chairman_control/control_room.js`, `app/static/chairman_control/control_room.css` |
| remote contract | Remote X1 | `control_plane/chairman_control_room_remote.py` → `REMOTE_SCHEMA = mastermind.chairman_control_room_remote.v1` |
| remote presentation | Remote X1 | `scripts/chairman_control_room_remote.py`, `app/static/chairman_control/remote.html` |
| remote release closure | Remote X1 | `control_plane.chairman_control_room_remote.REQUIRED_RUNTIME_PATHS`, `RELEASE_SCHEMA = mastermind.control_room_build.v1`, `ops/control_room_remote/install.sh`, `ops/control_room_remote/mastermind-control-room-remote.service` |
| candidate dispatch/status projection | PR #326 (unaccepted) | `control_plane/autonomy_control_room_projection.py`, `SCHEMA = mastermind.autonomy_control_room.v1` |
| Agent Dialogue Wake runtime | PR #357 (protected, disjoint) | `integrations/slack_agent_dialogue/{engine_v2,runtime,turn_routing_facts,turn_runtime_primitives,wake_projection}.py` |
| `job_id` / `attempt_id` / `worker_id` | Executive OS | read through `control_plane/executive_inbox.py` and runtime jobs; never recreated |
| PR / check / commit identity | GitHub | `project_active_builds.v1` snapshot; exact immutable identities only |
| portfolio projection | Linear | projection only; disagreement shown, never averaged; current epoch `7 / 65 / 63 / 2` (§11) |
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

**H1 is a derived read-only consumer, never a second lifecycle.** Once accepting owners wire them
in, H1 may read Executive Runtime/Event facts, current `RuntimeBinding` facts, the Wake Ledger's
canonical status reduction, and validated Agent Dialogue turn/return evidence — but it may never
become a Slack parser, a second lifecycle, a watcher registry, a cursor, a queue, a receipt owner,
a dispatch authority, or a second classifier. Three specific misclassifications are named because
PR #326's own current review (§5) caught real instances of each, and H1 must not reintroduce them
once it consumes that projection:

- **Terminal Attempt state is not a worker return.** A `FAILED`, `LOST`, or `CANCELLED` Attempt
  with no observed `BLOCKED`/`DECISION_REQUEST`/`RESULT` edge must never render as "Returned."
- **Nonblank strings are not watcher proof.** A watcher claim requires a validated exact
  child + operation + carrier + mechanism + handled-baseline receipt, not merely nonblank text.
- **Stale prose is not causal decision evidence.** A `STOP`/`CONTINUE` edge must bind causally
  *after* the return it claims to close; an older or wrongly-bound decision must refuse, not
  silently close the dialogue.

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

**Evidence-link typing law.** Every composed claim links to its canonical owner. Where the composed
owner fact has no lawful deep link, the field must render `NOT_AVAILABLE` or `NOT_APPLICABLE` with
the owner/source identity attached — never a fabricated URL manufactured merely to satisfy "every
claim has a deep link." `NOT_AVAILABLE` means a link is expected at that owner but is not currently
obtainable; `NOT_APPLICABLE` means no deep-link concept applies to that owner/fact at all. §12
lists real deep links this record actually cites, as the positive contrast case.

## 5. Collision census and PR archaeology

Observed against the original H0 genesis base `642fa62540f0f2565ccc484a350f2cd0a2259015`
(collision census — a one-time, dated fact that does not change on later integration):

- exact branch `sol/ai-operating-hub-h0-current-estate-freeze-20260903` — **absent** before START,
  local and remote
- exact operation PR — **absent** before START
- all four owned H0 paths — **absent** on protected master before START
- no worktree occupied the target path
- `WS:AI-HUB` — **absent** from protected master, and this record does not create it

PR archaeology, re-verified live at `observed_at` `2026-09-03T16:59:38Z` against the current
protected base in this record's frontmatter. One further protected movement, PR #396
("protect exact Realm1 peer profile lifecycle," merge `771a95586c7a31933ee612eafaa4d1471f57527b`),
landed after that census and before this record's final integration; it touches
`docs/CHAIRMAN_CONTROL_ROOM.md`, `integrations/chairman_surfaces/nonseat_canary_vendors.py`,
`scripts/mas115_setup.py`, and two test files — entirely disjoint from H0's owned paths, every
Control Room/dialogue/portfolio owner path, and the Skillpack, and it changes neither PR #326's
nor PR #350's head. Classified path-disjoint and non-material; folded in by ordinary non-force
integration under §12's law without a further semantic repair round.

| PR | State | Head | Relevance |
|---|---|---|---|
| #416 | `MERGED` (merge commit `812be940cec5db025a5ef8f99f71a0e30a92bb8e`) | `e2e8543b3a3bcd4edd33e5f95a611e3c945bbbe5` | F0 architecture protected. This H0 record is its successor; no stale F0-release step is executed. |
| #326 | `OPEN / DRAFT`, **UNRESOLVED — three `CHANGES_REQUESTED` reviews** | `8639d7a3f06277ea84c1e071b9d298d39695d91c` | **Blocking for all nine H1 paths, not only the UI subset.** Effective delta remains 10 paths (adds `control_plane/autonomy_control_room_projection.py`, `tests/test_autonomy_control_room_projection.py`, modifies `control_room.js`/`.css`/`index.html`, the compositor, `chairman_control_room_remote.py`, and three more Control Room test files). Three reviews, all `CHANGES_REQUESTED`: `5100408653` (09:51), `5103135217` (14:24), `5105026300` (17:43, latest). This PR is under active concurrent development by another party — its head has moved repeatedly during this H0 operation — and each successive review has surfaced *deeper* incompleteness, not less: the latest finds the real Agent-OS-to-Runtime-root join unreachable (every card falls back to `UNKNOWN`), Attempt/Wake correlation wrong for responsibility roots with child work, and the protected terminal-RESULT owner still unconsumed, on top of the earlier dark dispatch producer, unvalidated input mappings, terminal-Attempt misclassification, forgeable watcher/decision proof, and de-historicized unknown evidence. **Its dispatch-consumption output is therefore treated strictly as an unaccepted open-PR candidate — never a protected or live capability — until independently re-reviewed and merged.** |
| #350 | `OPEN / DRAFT` | `f0e681bf797522e09f2224fbc866f5aab2f62bb1` | Downstream of #326 on the shared packaging paths `control_plane/chairman_control_room_remote.py` and `ops/control_room_remote/install.sh`. |
| #357 | `MERGED` (merge commit `b28023f92458ba186937afa1e619f3b4464e149f`) | `58c884c418ff6dc2603d7e0db153c20825499d4f` | "[W3C] Trusted Agent Dialogue Wake runtime." Protects `integrations/slack_agent_dialogue/{engine_v2,runtime,turn_routing_facts,turn_runtime_primitives,wake_projection}.py` plus tests. **Disjoint from H0's four owned paths and from every Control Room owner path.** Recorded here as current Agent Dialogue source movement; Slack remains transport evidence, Executive OS remains lifecycle owner, and the Hub remains a read-only consumer of this boundary once an accepting owner wires it in — H1 may not independently derive dialogue/dispatch lifecycle from these modules. |
| #421 | `MERGED` (merge commit `6c5c2a6225a3fa2c2ec3e3398dcc8b8629b3a988`) | `7a34f6c43e76c8a6cac565e11bde7f3eee703108` | "[LINEAR] Advance Initiative portfolio to current 7/65/63/2 epoch." Adds `docs/superpowers/specs/2026-09-03-linear-initiative-portfolio-v1-temporal-grain-current-epoch-amendment.md`. **Disjoint from H0's four owned paths.** Portfolio/source movement only — see §11. |

**The material archaeology finding.** PR #326 is not merely a UI change. It already implements the
derived status/attention combination logic that a naive H1 would invent: a per-card single
`query_status`, worst-wins severity ranking, routine-absence neutralization, and per-source
receipts. Any H1 that re-derives card status would create exactly the duplicate status authority
F0 marks `REJECTED_BY_DESIGN`. Its current unresolved review additionally proves that even its own
dispatch/status output is not yet trustworthy on its own terms — which is why H1 must wait for
protection, not merely for existence, before consuming it.

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
| Derived card status / actionability / dispatch consumption | `control_plane/autonomy_control_room_projection.py` (PR #326, unresolved) | **consume only once independently re-reviewed and merged; never re-derive** |
| Agent Dialogue turn/return/wake evidence | `integrations/slack_agent_dialogue/*` (PR #357, protected) | read-only consumption via an accepting owner once wired; H1 never becomes a second dialogue classifier |
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
deployment step. It is the smallest surface on which the Chairman or a supervised local operator
inside the accepted P0A host/account threat boundary can complete the H1 orientation job end to
end. This selection is corroborated, not merely permitted, by §1a's
accepted `PROVEN_LIVE` evidence for the local P0A path.

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

## 8. Frozen lawful H1 path ceiling — nine paths, dual-protection gate

Frozen after the PR/path archaeology in §5. **Preferred shape, subject to a fresh collision census
immediately before H1 START** — this ceiling is deliberately frozen in advance of PR #326
protecting.

**H1 source START — all nine paths — is held until both this H0 record and PR #326 are
independently reviewed and merged into protected master.** Starting paths 1–7 early, before the
real consumer paths (8–9) are unblocked, would create a dark foundation PR rather than one
independently useful user capability, and is **not authorized under any circumstance**.

**May create (new paths only):**

1. `control_plane/ai_operating_hub_workroom.py` — one typed, pure derived read-only contract
2. `app/static/chairman_control/hub_workroom.js` — one additive presentation module
3. `app/static/chairman_control/hub_workroom.css` — one additive stylesheet
4. `tests/test_ai_operating_hub_workroom.py` — deterministic contract tests
5. `tests/test_chairman_control_room_ai_hub.py` — Hub-specific Control Room integration tests
6. `tests/test_chairman_control_room_ui_ai_hub.py` — Hub-specific UI/browser-proof tests
7. `docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-implementation-receipt.md` — the H1 receipt

**May modify — only once both H0 and PR #326 are protected:**

8. `scripts/chairman_control_room.py` — exactly one additive read-only route
9. `app/static/chairman_control/index.html` — exactly one additive mount point

The new JS/CSS (paths 2–3) remain strictly additive. H1 must never edit or reimplement PR #326's
`control_room.js`, `control_room.css`, its autonomy projection, or that projection's status,
actionability, dialogue, dispatch, watcher, or evidence classifiers.

**H1 must not touch, in any circumstance:**

- `control_plane/chairman_control_room.py` (the pure compositor join law)
- `control_plane/chairman_control_room_remote.py`, `scripts/chairman_control_room_remote.py`,
  `app/static/chairman_control/remote.html`, `REQUIRED_RUNTIME_PATHS`,
  `ops/control_room_remote/install.sh`, `ops/control_room_remote/mastermind-control-room-remote.service`
- `app/static/chairman_control/control_room.js`, `app/static/chairman_control/control_room.css`
  (owned by PR #326 while it is open)
- `control_plane/autonomy_control_room_projection.py` and its dialogue, dispatch, watcher, and
  evidence-classifier logic (PR #326)
- `integrations/slack_agent_dialogue/*` (PR #357) — read-only consumption via an accepting owner
  only; H1 never reimplements this boundary
- anything owned by PR #350

## 9. Exact local route, security, cache, and threat boundary for H1

Because the first consumer is local P0A, H1 may expose **exactly one** fixed read route. The three
security layers below are verified directly against real `scripts/chairman_control_room.py`
source — an earlier draft of this record incorrectly claimed two protections the real source does
not provide on a JSON GET; §9 now states only what is actually true of the code.

- **Route:** `GET /api/hub/workstream/chairman-control-room`
- **Resolves server-side to the literal workstream** `WS:CHAIRMAN-CONTROL-ROOM` — no arbitrary
  workstream query parameter, no non-empty query string of any kind, and no fuzzy match.
- **Data source:** the existing process-memory cached `mastermind.chairman_control_room.v1`
  composed document only. No request-time re-gather, no network call, no subprocess, no file
  discovery, and no second compositor.

**Three real, separated security layers — not one blanket inheritance from `/api/state`:**

1. **HTML/static shell.** `Content-Security-Policy` and same-origin static policy are properties of
   `_serve_index` (the HTML shell, `csp=True`) only. `_send_json()` — the function every JSON route
   including `/api/state` and the new H1 route uses — never sets CSP. H1 must not claim or invent a
   CSP response header on its JSON GET.
2. **H1 JSON GET, the actual inherited gate.** Loopback-only binding, `Host` header check, `Origin`
   header check, the same `X-CCR-Token` gate, and `Cache-Control: no-store` — verified as the real
   behavior of `_loopback_and_host_ok()` and `_api_auth_ok()`. H1 additionally freezes its own
   deterministic maximum canonical Workroom payload of **`262144` bytes**: the response is fully
   serialized and length-checked before any byte is written, and on overflow the route returns the
   fixed refusal state `WORKROOM_RESPONSE_TOO_LARGE` rather than a partial body. This response cap
   is new to H1 — P0A's real `_MAX_BODY_BYTES` (64 KiB) does not bound outbound JSON at all;
   `_handle_state()`'s call to `_send_json` has no length check on its payload.
3. **Existing POST routes, unrelated to this GET.** `_MAX_BODY_BYTES` (64 KiB) is enforced only
   inside `_read_json_body()`, called only from `do_POST`. The H1 GET route reads no request body,
   so this cap does not bound it and must never be described as an H1 GET protection.

- **Token honesty law.** Per the Agent OS source's own landmine record: *"`X-CCR-Token` is a
  per-process browser-origin/CSRF capability nonce, not authentication against another same-user
  local process; `GET /` intentionally bootstraps that nonce."* This is independently corroborated
  by `_api_auth_ok()`'s own docstring in `scripts/chairman_control_room.py`, which cites an earlier
  Sol review (`5000983751`) making the identical point. H1 must state this honestly and must never
  claim a verified user identity or public/remote authorization from this token.
- **Human boundary law.** H1 and its production receipt describe **the Chairman or a supervised
  local operator inside the accepted P0A host/account threat boundary** — never an
  authenticated/authorized human identity, public authorization, or protection from another
  same-user local process. The separate remote/public authorization problem stays out of scope.

**Forward-compatible route and static-asset closure.** H0's own source-law test parses P0A's real
`path == <literal>` route set and its static-asset map. Both are closed sets today, and both must
stay closed after H1 legitimately adds its one route and its two static assets — never open-ended:

| | Baseline (today) | The only permitted future addition |
|---|---|---|
| API routes | `/favicon.ico`, `/api/state`, `/api/discover`, `/api/open`, `/api/bind`, `/api/unbind`, `/api/refresh-builds` | exactly `/api/hub/workstream/chairman-control-room` |
| Static assets | `index.html`, `control_room.js`, `control_room.css` | exactly `hub_workroom.js`, `hub_workroom.css` |

Any arbitrary workstream-parameterized route, any second Hub route, any new POST/mutation route, or
any static asset name outside this closure fails. Remote X1's route allowlist stays exact and
unchanged by this law.

## 10. Closed field and redaction law for H1 (from protected F0)

Protected F0 forbids the Hub from ever rendering credentials, raw tokens, hidden provider prompts,
private reasoning/chain-of-thought, or secret-bearing exception text. H0 freezes the missing
implementation law now, so H1 cannot treat this as an afterthought:

- H1's pure reducer uses **explicit per-section field allowlists**. It must not recursively pass
  through arbitrary `work`, `executive`, `github`, `autonomy`, `sources`, `issues`, error, or
  receipt mappings into the browser contract.
- Unknown privileged or source fields **fail closed or are omitted with a typed `NOT_AVAILABLE`**;
  they never acquire authority merely by being present in an input mapping.
- The Workroom output refuses or redacts: credentials, bearer/cookie/token material, hidden
  prompts, private reasoning/chain-of-thought, raw traceback/exception bodies, absolute host paths,
  browser profile/session secrets, and other source-owner-private values. Repository-relative
  source identities and reviewed public GitHub links remain allowed.
- Error output carries **static reason codes**, never the offending value.
- **The local P0A threat boundary does not waive F0's secret/private-evidence law.**

This law is implemented later, inside H1's own pure reducer/route using this frozen closed
contract — it creates no second redaction service and makes no change to remote X1. H1's browser
proof must confirm every forbidden value category is absent from both the DOM and the serialized
H1 JSON response.

## 11. Linear portfolio — current epoch (dated observation)

Protected source: `docs/superpowers/specs/2026-09-03-linear-initiative-portfolio-v1-temporal-grain-current-epoch-amendment.md`
(PR #421, merged as `6c5c2a6225a3fa2c2ec3e3398dcc8b8629b3a988`).

The prior `7 Initiatives / 64 Projects / 62 memberships / 2 exceptions` epoch became stale because
Agent OS gained one active workstream, `WS:TEMPORAL-GRAIN-INTELLIGENCE`, classified under primary
Initiative *Legendary Alpha Discovery & Timing*. The current accepted live ruler is:

```text
Initiatives: 7
Projects: 65
Projects with exactly one primary Initiative: 63
unassigned exceptions: 2
```

Exact membership counts in frozen Initiative order: `10, 17, 11, 6, 4, 8, 7` (sum `63`). The two
deliberate exceptions (`WS:WATCHLIST-PORTFOLIO-CEO`, Linear Project `9aef6461-306a-4a3c-911b-c6a4b6635a78`)
remain exactly unchanged and unassigned.

This is a **portfolio/source movement only**. Linear remains a selected human projection, never
runtime, completion, or Hub truth authority — this ruler tells H1 nothing about capability state
and must not be read into §1's ledger.

## 12. Immutable contract versus dated observation

Two different kinds of fact live in this record, and they must never be conflated:

**Immutable contract facts** are derived directly from source code via `ast` parsing and change
only when that source itself changes: the compositor's `SCHEMA`/`OUTPUT_KEYS`, the remote
projection's `REMOTE_SCHEMA`/`RELEASE_SCHEMA`/`REQUIRED_RUNTIME_PATHS`, the P0A/X1
transport/route/token laws in §3 and §9, the forward-compatible route/asset closure and the field
redaction law in §9–§10, the reference workstream token, and the H1 path ceiling itself. These are
verified by direct source parsing in `tests/test_ai_operating_hub_h0_source_law.py` and hold
regardless of how much time has passed.

**Dated observations** are point-in-time receipts captured at an explicit `observed_at`: the
protected-master SHA in this record's frontmatter, PR #326's exact head and review state (§5), the
Linear portfolio ruler (§11), and the accepted-capability citations in §1a. These are expected to
go stale as protected source moves. The source law proves this record's **internal**
consistency — that the record, the evidence JSON, and the H1 plan agree with each other and with
the source they cite — and proves derivation from the cited snapshot. It deliberately does **not**
compare against a live-fetched `origin/master`, so a future path-disjoint protected-source movement
does not itself turn this record red. A change to an immutable contract fact, a Control Room owner,
the Agent Dialogue boundary, an H1 path owner, or a governing source still requires a fresh
same-carrier repair before the next return — dated observations going stale on their own does not.

Real deep links this record actually cites, as the positive contrast to the evidence-link typing
law in §4: <https://github.com/mastermindx-market-intelligence/Mastermind/pull/110>,
`.../pull/113`, `.../pull/133`, `.../pull/134`, `.../pull/138`, `.../pull/326`, `.../pull/357`,
`.../pull/421`.

## 13. H1 handoff

The bounded H1 mission is specified in
`docs/superpowers/plans/2026-09-03-ai-operating-hub-h1-read-only-workstream.md`.

## 14. Effects and non-effects of this record

**Effects:** one branch, one Draft/HOLD PR, four records-only files (this repair modifies the same
four files; no fifth path was added), history-preserving non-force integration of current protected
master.

**Non-effects:** no H1 implementation; no UI, API, database, cache, or runtime action; no change to
the compositor, P0A, or X1; no change to PR #326, #350, or #357 themselves; no `WS:AI-HUB`; no
Agent OS, Linear, Executive, or Slack lifecycle mutation; no Mac or browser action; no deployment;
no production effect; no Ready, merge, or self-review.

**Stop condition.** Stop after the H0 return. H1 remains held and receives implementation authority
only after this H0 record is independently reviewed and protected, **and** PR #326 is independently
re-reviewed and protected.
