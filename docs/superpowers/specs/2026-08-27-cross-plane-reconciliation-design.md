# Mastermind-X Cross-Plane Reconciliation & Fresh-Sol Grounding Design

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** Chris explicitly approved the in-chat architecture and directed Sol to own delivery end to end on 2026-08-27.  
**Operation key:** `cross-plane-reconciliation-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `be68ec881460aa60d7d77cdb69f7c1cae81f6310`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1 compatible and loaded atomically.  
**Observed Macro main during design:** `5d07658b899d2d3457dfeeccbc0a91c280f5bc1f`.  
**Status:** ARCHITECTURE FREEZE CANDIDATE / RECORDS ONLY. This document authorizes no Executive Job, Slack app installation, Linear mutation, production service, worker claim, or automatic dispatch by itself.

---

## 1. Outcome

A brand-new Sol CEO session must be able to recover the current company operating truth without relying on chat memory, stale Linear prose, a Slack handoff, or accidental familiarity with the repository estate.

For every materially live program the session must be able to answer, from current owners and exact identities:

1. What workstream/program is canonical?
2. What bounded implementation/proof carrier is currently active?
3. What code/PR/CI/merge evidence exists?
4. What remains unproven after merge?
5. What Linear is projecting, and whether that projection is stale or false-green?
6. What Slack actually transported, and whether a receiving runtime/session existed?
7. What Executive OS says is queued/claimed/running/terminal when runtime state is applicable?
8. Which human, Sol seat, app actor, Executive Worker, provider realm or session owns the relevant action?
9. Whether another carrier/session already owns the same logical modification?
10. Whether a new modifying operation is safe now.

The system must make cross-plane disagreements **visible and typed before modification**, then repair only the wrong projection/owner layer. It must not create a fourth authoritative database that attempts to make GitHub, Linear and Slack identical.

### 1.1 Chairman/user job

The Chairman should be able to open a fresh Sol and delegate an outcome without becoming the manual coordination bus that explains which PR, Linear issue, Slack thread, worker or prior Sol session is current.

### 1.2 Machine/intelligence job

The machine must deterministically recover and compare exact facts from the existing canonical owners, classify disagreements, preserve uncertainty, and refuse unsafe modification where required evidence is stale, unknown or conflicting.

### 1.3 10/10 end state

A fresh Sol bootstraps the protected Skillpack, builds one current `Session Truth Receipt`, sees every material disagreement, knows the exact active carrier and authority boundary, and can proceed or fail closed without reconstructing hidden context. Linear and Slack are useful, low-friction projections; if either is unavailable or stale, canonical work remains recoverable and no truth is lost.

---

## 2. Non-negotiable authority boundaries

One fact has one canonical owner.

| Fact | Canonical owner | Projection/transport behavior |
|---|---|---|
| Job / Attempt / Worker / Event lifecycle, claim, dispatch, retry/reconciliation | Executive OS | May be projected into SOL_STATE / Control Room / dialogue; never inferred from Slack delivery or Linear status |
| Workstream / decision / discovery / handoff organizational truth | Agent OS | Linear may selectively project it; Slack may announce it |
| Code / branch / PR / diff / CI / review / merge / implementation evidence | GitHub | Linear may attach/project; Slack may announce |
| Selected portfolio / gate view | Linear | Never overwrites Agent OS, GitHub or Executive truth |
| Message delivery / dialogue / hot-state visibility | Slack | Never becomes work/lifecycle authority |
| Prior-chat convenience | Shared Project memory | Advisory only |

### 2.1 No-majority-vote law

If three systems disagree, the answer is not “two out of three.” The owner of the disputed fact wins. The disagreement remains visible until the wrong projection is repaired.

### 2.2 No fourth truth store

This program must not introduce a `sync_state`, `reconciliation_db`, `slack_linear_github_state`, durable cursor database, parallel lifecycle ledger, retry table, queue, work registry or other persistent store whose purpose is to become the new authority over the existing planes.

Deterministic generated receipts may be persisted as immutable evidence in an owning repository after the observation is complete. They are receipts, not mutable current-state authorities.

---

## 3. Current capability ledger and known drift

This is a dated design-time census, not timeless architecture law.

### 3.1 Operating law

The protected Mastermind reconciliation in PR #168 is merged at `be68ec881460aa60d7d77cdb69f7c1cae81f6310`. It freezes the separation among Executive routing, Agent OS, GitHub, Linear and Slack and forbids absent-recipient Slack dispatch from being treated as execution.

**State:** `PROVEN_LIVE` as current source law; it does not itself provide runtime enforcement.

### 3.2 Agent OS reconciliation carrier

Macro PR #6509 carries the matching Agent OS decision, no-worker-receiver discovery, continuation handoff and stale Capacity Fabric repair. During this design its current head was `a6a1864640e2e0572219104c627e2663be046791`, open and not mergeable against a Macro main that had continued moving.

**State:** `BUILT_NOT_PROVEN / NOT LANDED` as durable organizational reconciliation. The same carrier must be reconciled; no replacement Agent OS carrier should be created for those exact records.

### 3.3 GitHub ↔ Linear linkage

The native integration is live enough to attach PR activity. MAS-67 already records a false-completion failure family and distinguishes merge-is-done, contributing, architecture/evidence and production/program gates.

**State:** `PARTIAL`.

### 3.4 PR ↔ Workstream ↔ Linear validator

MAS-28 has a merged deterministic report-only implementation and a recorded incident where the native integration moved MAS-28 to `Done` after an implementation merge although its semantic completion law remained unmet. Calibration and final recommendation are still owed.

**State:** `BUILT_NOT_PROVEN`.

### 3.5 Agent OS → Linear projector

MAS-65 has the deterministic report-only desired-state compiler and real-main receipt work substantially advanced. MAS-66 remains the project-only read/diff/apply adapter specification and intentionally has not been armed for portfolio-wide mutation.

**State:** P0 `BUILT_NOT_PROVEN`; P1 `SPEC_ONLY`.

### 3.6 Slack visibility

MAS-103 (Linear → `#build-events`) and MAS-104 (GitHub → `#build-events`) remain unbuilt operator/admin paths. Live `#build-events` contains policy but no useful machine event stream.

**State:** `NOT_BUILT`.

### 3.7 Executive hot-state visibility

MAS-109 / Mastermind PR #155 owns production C1 `MMX/SOL_STATE_V1`. Live private `#sol-runtime` exists but has no Relay bot/state message.

**State:** `NOT_BUILT / IN PROGRESS`.

### 3.8 Active-session dialogue

MAS-127 owns ASD-A2 production Agent Relay. It remains pre-flight gated/unstarted. Current `#agent-dispatch` membership is Chairman + ChatGPT1/2/3, not a worker/Fable receiver.

**State:** `NOT_BUILT`.

### 3.9 Dispatch policy enforcement

The freeze against absent-recipient commissions is canonical, but an additional `FABLE/CODEX BOUNDED PICKUP` was posted to `#agent-dispatch` roughly minutes after the hold, addressed to a ChatGPT CEO principal. This proves policy text alone does not prevent drift.

**State:** `BROKEN` as systemic enforcement; the law itself remains valid.

### 3.10 Identity registry

MAS-99 keeps Slack/Linear/GitHub seat identity separate from runtime/role. ChatGPT2/3 GitHub mappings remain typed unknown until first-party evidence exists.

**State:** `PARTIAL`.

---

## 4. Architecture overview

The architecture is a **read-first reconciler over existing canonical owners**, followed by bounded owner-specific projection repair.

```text
Protected Skillpack
       |
       v
Fresh Sol bootstrap
       |
       v
Canonical observation adapters
  |       |        |        |        |
AgentOS  GitHub   Linear   Slack   Executive OS
  |       |        |        |        |
  +-------+--------+--------+--------+
                  |
                  v
       deterministic normalize
                  |
                  v
       cross-plane reconciliation
                  |
        +---------+----------+
        |                    |
        v                    v
 Session Truth Receipt   Drift findings
        |                    |
        +---------+----------+
                  |
                  v
           admission mode
     GROUNDING_COMPLETE
     GROUNDING_PARTIAL
     DIALOGUE_ONLY
     MODIFICATION_REFUSED
                  |
                  v
     bounded owner-specific repair
       (only after separate gate)
```

The reconciler answers “what do the current owners say, and where do projections disagree?” It does not own the underlying facts.

---

## 5. `Session Truth Receipt`

### 5.1 Purpose

The first independently useful vertical is one deterministic read-only receipt that a cold Sol can inspect before substantial modifying work.

Recommended schema name:

```text
mastermind.session_truth_receipt.v1
```

### 5.2 Receipt identity

The receipt is immutable and bound to:

- exact protected Mastermind Skillpack SHA;
- observation start/end timestamps;
- exact observed repository default-branch SHAs;
- exact normalized observation hashes for each available source;
- requested program/workstream/operation scope;
- tool/source availability states.

It must never claim that a later source state was observed merely because the receipt file is committed later.

### 5.3 Core shape

```json
{
  "schema": "mastermind.session_truth_receipt.v1",
  "scope": {
    "workstreams": ["WS:..."],
    "linear": ["MAS-..."],
    "repositories": ["owner/name"]
  },
  "skillpack": {
    "repository": "mastermindx-market-intelligence/Mastermind",
    "sha": "<40hex>",
    "schema": "mastermind.sol_skillpack.v1",
    "version": "1.0.0",
    "bootstrap_major": 1
  },
  "observations": {
    "agentos": {"available": true, "source_sha": "<40hex>", "facts": []},
    "github": {"available": true, "facts": []},
    "linear": {"available": true, "facts": []},
    "slack": {"available": true, "facts": []},
    "executive": {"available": false, "reason": "C1_NOT_PROVEN"}
  },
  "findings": [],
  "admission": {
    "mode": "GROUNDING_PARTIAL",
    "modification_safe": false,
    "reasons": ["RUNTIME_STATE_UNAVAILABLE"]
  },
  "semantic_hash": "sha256:..."
}
```

The implementation may refine field names, but the semantics above are frozen.

### 5.4 Deterministic vs model-generated behavior

All source normalization, key matching, freshness comparison, explicit binding validation, drift classification and admission calculation are deterministic.

A model may produce a human summary **after** the receipt exists. Model prose has zero authority to create a missing binding, upgrade an unknown identity, infer runtime execution, waive a blocker or change the machine verdict.

---

## 6. Observation adapters

Each adapter reads only the existing owner and emits a normalized observation. The adapter does not mutate the source.

### 6.1 Agent OS adapter

Use the existing Agent OS parser/schema and direct workstream/decision/discovery/handoff records. Do not build a second YAML/frontmatter parser when the repository already owns one.

Required output includes exact source path, record key, status, owner, declared repos, current waves/next action where schema supplies them, and content hash.

Generated `docs/AGENT_OS_STATE.md` or summaries may be compared for drift but never outrank direct records.

### 6.2 GitHub adapter

Normalize repository default branch, open relevant PRs, immutable head SHAs, base SHA, changed files, CI/check state, merge state, merge SHA and explicit PR metadata bindings.

GitHub adapter may not infer Agent OS completion from a PR title or branch name.

### 6.3 Linear adapter

Read exact issue/project identifiers. Capture state/status, labels, parent/project relationships, explicit attachments/PR relationships and updated timestamp.

Linear remains projection. A missing Linear object may be a projection gap rather than a missing company workstream.

### 6.4 Slack adapter

Normalize exact workspace/channel/message/thread/sender identity, declared operation key, transport classification, timestamps and current channel membership when receiver capability matters.

Slack adapter may state `message_delivered=true`; it may not state `runtime_acked=true` without a separately valid runtime/session receipt.

### 6.5 Executive adapter

When C1/approved Executive read capability is production-proven, normalize the accepted current read-only Executive state including grounding, admission readiness, relevant intent/Job status, freshness and explicit degraded state.

Before that production capability exists, the adapter must return an explicit unavailable state. It must not substitute old fixtures, local developer state or Slack prose.

---

## 7. Binding registry and identity law

Cross-plane reconciliation requires exact bindings, never fuzzy title matching.

### 7.1 Separate identities

The following are distinct facts:

- Chairman authority seat;
- Sol seat (`ChatGPT1/2/3`);
- current chat/session;
- Slack principal;
- Linear employee actor;
- GitHub account;
- service/app actor;
- Executive Worker ID;
- provider realm (`codex-pro-01`, etc.);
- model/role binding (`Sol`, `Terra`, `Luna`, Fable, Claude, Codex, etc.);
- workstream;
- bounded wave;
- operation key.

No name similarity may collapse them.

### 7.2 Typed unknowns

Unknown identities are valid explicit states. `UNKNOWN_GITHUB_SEAT_BINDING` is safer than guessing `MastermindX2 == ChatGPT2`.

A typed unknown blocks only actions whose attribution/authority depends on that identity; it does not automatically block unrelated read-only reasoning.

### 7.3 Service actors

Portfolio Projector, Executive Relay, Agent Relay, official GitHub/Slack/Linear integrations and future automation actors are separate service identities with their own scope/permission/revocation receipts.

---

## 8. Drift taxonomy

Every mismatch is a named finding with:

- code;
- severity;
- canonical owner;
- exact identities/source revisions;
- source A observation;
- source B observation;
- repair owner;
- modification consequence;
- optional falsifier/remediation.

### 8.1 Required initial finding codes

#### Projection

- `STALE_LINEAR_PROJECTION`
- `FALSE_LINEAR_COMPLETION`
- `MISSING_LINEAR_PROJECTION`
- `LINEAR_PARENT_CHILD_DIVERGENCE`
- `ORPHAN_LINEAR_ISSUE`
- `BUILD_VISIBILITY_STALE`

#### GitHub / carrier

- `GITHUB_PR_UNBOUND`
- `GITHUB_MERGE_WITH_PROOF_OPEN`
- `ORPHAN_GITHUB_CARRIER`
- `MULTIPLE_ACTIVE_CARRIERS`
- `CARRIER_HEAD_MOVED`
- `PR_BINDING_CONFLICT`

#### Agent OS

- `AGENTOS_GITHUB_DISAGREEMENT`
- `STALE_HANDOFF`
- `SUPERSEDED_NEXT_ACTION`
- `DIRECT_GENERATED_STATE_DIVERGENCE`

#### Slack / transport

- `SLACK_TRANSPORT_WITHOUT_RECEIVER`
- `SLACK_TRANSPORT_WITHOUT_ACK`
- `CEO_SEAT_USED_AS_WORKER`
- `DUPLICATE_OPERATION_CARRIER`
- `POST_FREEZE_DISPATCH_VIOLATION`

#### Runtime

- `RUNTIME_STATE_UNAVAILABLE`
- `RUNTIME_STATE_STALE`
- `SLACK_ACK_WITHOUT_EXECUTIVE_STATE`
- `EXECUTIVE_GROUNDING_DIVERGED`

#### Identity

- `UNKNOWN_SEAT_IDENTITY`
- `SERVICE_ACTOR_UNBOUND`
- `ACTOR_ROLE_COLLISION`

### 8.2 Severity

`FATAL` — evidence indicates a constitutional/authority collision or duplicate/effect-unknown modification; modification is prohibited.

`BLOCKING` — required owner state is stale/unavailable/conflicting for the requested modifying action.

`WARNING` — real drift exists but does not prevent this action; repair debt must remain visible.

`INFO` — expected projection lag or non-authoritative informational discrepancy.

Severity is deterministic by rule, not model judgment.

---

## 9. Session admission modes

The receipt computes one of four modes.

### 9.1 `GROUNDING_COMPLETE`

All required canonical sources for the requested operation are fresh, exact bindings are known, no fatal/blocking disagreement applies, and any required Executive hot-state gate is current.

This does **not** itself authorize modification. The normal Chairman intent, Skillpack, carrier and app/runtime permission gates still apply.

### 9.2 `GROUNDING_PARTIAL`

Read-only reasoning can continue, but at least one nonrequired source is unavailable or one warning/typed unknown remains.

The receipt states exactly which kinds of modification remain safe or unsafe.

### 9.3 `DIALOGUE_ONLY`

The session may discuss/research/review but cannot make the requested canonical modification because a required current-state, identity, runtime or carrier gate is missing.

### 9.4 `MODIFICATION_REFUSED`

A fatal conflict, duplicate/effect-unknown operation, stale required runtime state, active carrier collision or other explicit refusal makes a new modification unsafe.

No alternate carrier is attempted automatically.

---

## 10. Repair architecture

The reconciler is read-only by default. Repair is a second, owner-specific operation.

### 10.1 Linear repair

If GitHub/Agent OS/production evidence proves Linear stale, update only Linear projection fields covered by the relevant approved projection contract. Do not rewrite Agent OS merely to match Linear.

Automatic project projection remains downstream of MAS-65/MAS-64/MAS-66 acceptance. Issue lifecycle mutation is not implicitly authorized by project projection.

### 10.2 Slack repair

Slack visibility may be reconstructed from canonical current state. Missing historical Slack events are not lifecycle loss.

Do not reconstruct a missing runtime ACK merely by posting new prose.

### 10.3 Agent OS repair

When a direct organizational record is independently stale, repair it in Agent OS under its existing parser/schema/ownership law and preserve supersession.

### 10.4 GitHub repair

Unexpected branch movement, missing metadata, merge/CI defects or PR collisions are repaired in the same lawful carrier. Do not reset/rebase/force over unknown work merely to make the reconciler green.

### 10.5 Executive repair

Runtime canonical defects require an Executive-owned bounded repair. The reconciliation layer cannot terminalize Jobs, claim Workers, invent retries or create an alternate runtime store.

---

## 11. `#agent-dispatch` enforcement

### 11.1 Target role

`#agent-dispatch` is not a general task queue. After ASD-A2/A3 are production-proven it carries active-session dialogue/attention for already-active, already-commissioned workers/COOs.

### 11.2 Pre-send commission guard

Before a Sol-authored actionable worker/Fable pickup is emitted through Slack, the producer must deterministically prove all applicable fields:

- exact operation key;
- exact bounded commission/carrier;
- target worker/session identity;
- target is not merely a Sol CEO Slack principal;
- current receiver/session is known active and eligible to consume the carrier;
- no duplicate/conflicting carrier exists;
- current source-law/authority pin is valid;
- transport mode is lawful for the current capability state;
- Executive admission exists when the operation requires canonical Executive execution.

If those conditions fail, a runnable pickup message is refused.

### 11.3 Visibility-only fallback

When a real worker receiver is absent, Slack may display a non-actionable status such as:

```text
NON_ACTIONABLE_VISIBILITY
receiver_state: unavailable
canonical_work: still_owed
```

It must not use executable pickup grammar that later sessions can mistake for a commission.

### 11.4 No Slack-owned retry

No Slack retry queue, delivery cursor, durable inbox or `pending_dispatches` table is allowed.

Historical DELIVERY_ONLY messages remain individually reconciled against current owners before any later canonical re-issue.

---

## 12. GitHub ↔ Linear correctness

### 12.1 Existing six-field PR grammar remains canonical

```text
Workstream: WS:<KEY> | NONE
Linear: MAS-### | NONE
Portfolio-Mode: <typed class>
Wave: <bounded identifier>
Authority: <typed authority>
Completion: <typed completion law>
```

This program should consume and extend existing MAS-6/MAS-28 contracts, not create a parallel metadata grammar.

### 12.2 Relationship classes

GitHub/Linear relationships stay explicitly classified:

1. merge-is-done implementation;
2. non-closing contribution;
3. architecture/source-law/research/evidence;
4. program/production-proof/CEO/operator gate;
5. wrong embedded issue ID suppressed/ignored and proven inert.

No branch issue ID is treated as a neutral join key when it can drive native automation.

### 12.3 False-completion rule

If a native integration closes a Linear issue but the issue completion contract still requires production, browser, natural-time, calibration, security or Sol acceptance proof, emit `FALSE_LINEAR_COMPLETION` and repair Linear projection after canonical proof review.

No production-proof sibling closes merely because an implementation sibling merged.

---

## 13. Agent OS → Linear desired-state projection

The accepted direction is one-way:

```text
Agent OS direct records
  -> deterministic `linear_portfolio_plan.v1`
  -> real Linear read/diff
  -> bounded project-only apply
```

The current MAS-65 compiler remains the desired-state producer. MAS-66 remains the first project-only mutation adapter after app-actor prerequisites.

### 13.1 Required properties

- exact `WS:<KEY>` binding;
- no fuzzy title matching;
- deterministic same-input output;
- stale generated Agent OS view cannot override direct records;
- optimistic re-read before apply;
- `remote_changed` refusal;
- idempotent replay;
- managed block cannot overwrite manual content outside its markers;
- excluded/done project handling remains non-destructive in first production vertical;
- no issue/gate lifecycle mutation is smuggled into project projection.

### 13.2 Scheduling

Continuous scheduling is not part of the first project-only P1 acceptance. A later explicit arming decision may schedule reconciliation only after current dry-run and mutation canaries are accepted.

---

## 14. `#build-events` visibility stream

`#build-events` is a regenerable, non-authoritative observability surface.

### 14.1 GitHub events

Use the already-specified MAS-104 official integration path for selected repositories and low-noise PR/review/selected-workflow events. Do not subscribe default-branch commit firehoses or enable Slack-side GitHub mutation as an operating path.

### 14.2 Linear events

Use MAS-103 opt-in `Build Event Projection` custom view/label path. Do not subscribe entire teams/portfolio or synchronize Slack threads into Linear lifecycle.

### 14.3 Semantics

A message can report:

- PR opened/ready/merged/closed;
- selected CI/fence pass/fail;
- deploy/render visibility;
- selected Linear projection transition.

It cannot report `PROVEN_LIVE` or final acceptance unless the corresponding canonical proof owner actually supports that claim.

### 14.4 Regenerability

If Slack misses or loses a week of build events, no canonical work is lost. A later Session Truth Receipt reconstructs current state from GitHub/Agent OS/Linear/Executive owners.

---

## 15. `#sol-runtime` / Executive blindness removal

C1 / MAS-109 / PR #155 remains the only production `MMX/SOL_STATE_V1` carrier.

This reconciliation program does not build a competing runtime-state projection.

Once C1 is production-proven, the Session Truth Receipt consumes fresh SOL_STATE when a requested action depends on Executive readiness/grounding.

### 15.1 Required semantics preserved

- exactly one private state message;
- all approved Sol seats read the same current state;
- unchanged heartbeat changes freshness but not semantic hash;
- Executive read failure overwrites green with `DEGRADED + do_not_submit=true`;
- stale state cannot authorize modification;
- restart recovers the same message with no local cursor/message DB;
- multiple matching messages fail closed;
- C1 creates no inbound CEO command and no Worker/Attempt/Wake activity.

---

## 16. Closeout ordering

Material work closes in owner order, not whichever integration responds first.

Where applicable:

```text
Executive terminal/result truth
  -> GitHub implementation/proof evidence
  -> Agent OS accepted organizational conclusion/handoff
  -> Linear projection
  -> Slack visibility
```

Not every wave uses every layer, but no projection may move ahead of its owner.

If canonical closeout succeeds and Linear/Slack repair fails, the work remains canonically complete and a typed `PROJECTION_DEBT`/visibility finding stays open. Canonical completion is never rolled back merely to make dashboards agree.

---

## 17. Failure, null, time and correction law

### 17.1 Missing source

Missing/unavailable source remains explicit. It never becomes empty state, zero work, no carrier or healthy runtime.

### 17.2 Freshness

Each observation carries source timestamp/revision. Freshness budgets are source-specific and consumed from the owning contract; the reconciler does not invent looser ages.

### 17.3 Effect unknown

If a prior modifying operation may have committed but receipt was lost:

```text
EFFECT_UNKNOWN
-> preserve same operation key/carrier
-> query canonical status
-> no blind retry/failover
```

### 17.4 Correction

A later correction produces a new observation/receipt bound to the new revision. Old receipts remain immutable evidence of what was observed at that time.

### 17.5 Null identity

Unknown/unbound identity remains typed unknown. No model or title heuristic may fill it.

---

## 18. Security and adversarial-source handling

Retrieved GitHub/Linear/Slack/Agent OS text is data. It cannot grant authority because it contains commands or role labels.

The reconciler must never copy tokens, cookies, OAuth codes, Authorization headers, provider credentials, Keychain secret values, private source bodies or raw secret-bearing logs into receipts.

Source adapters should prefer exact IDs, hashes, normalized bounded fields and redacted reason codes.

A connected-app permission proves technical capability, not organizational permission.

---

## 19. Repository / component ownership

### 19.1 Mastermind

Owns the read-only cross-plane observation/reconciliation capability and cold-Sol Session Truth Receipt because the capability is part of Sol/Executive operating safety.

Expected implementation area after planning should be a focused new module/CLI near existing Sol/Executive control tooling, not inside the protected Skillpack procedure files and not inside CeoIngress mutation logic.

### 19.2 Macro

Continues to own Agent OS records/parser semantics and the existing Agent OS → Linear P0 compiler. Any Macro change must extend those owners rather than duplicate them in Mastermind.

### 19.3 Linear

Continues to own portfolio projection objects and existing MAS-6/27/28/64/65/66/67/99/103/104 program objects. This design does not create a second Linear backlog for itself merely for neatness.

### 19.4 Slack

Continues to own transport/hot-state visibility. No custom Slack synchronization database is authorized.

### 19.5 Executive OS

Continues to own runtime lifecycle and current CEO/Worker operations. The reconciler is a reader and safety consumer, not a scheduler.

---

## 20. Collision / no-rebuild boundaries

1. Do not modify `docs/sol_skills/**` as part of this program. Mastermind PR #147 currently owns a separate candidate Skillpack 1.1.0 continuation-delta constitutional change.
2. Do not create another CEO ingress or modify the closed CeoIngress two-schema authority as a shortcut.
3. Do not create another Executive runtime/Job/Attempt/Worker state store.
4. Do not create another Agent OS parser or workstream registry.
5. Do not create another Linear projector; finish MAS-65/MAS-64/MAS-66.
6. Do not create another PR metadata grammar; consume MAS-6/MAS-28.
7. Do not create another production SOL_STATE lane; finish PR #155 / MAS-109.
8. Do not create another Agent Relay/dialogue system; finish MAS-127 and accepted ASD architecture.
9. Do not turn `#build-events` into a command channel.
10. Do not turn `#agent-dispatch` into a queue, inbox, retry ledger or wake system.
11. Do not bulk-replay historical Slack DELIVERY_ONLY posts into Executive OS.
12. Do not infer worker identity from ChatGPT Slack principal.
13. Do not let Linear `Done` override explicit production/acceptance law.
14. Do not block all read-only Sol reasoning merely because one optional projection source is down; degrade precisely.
15. Do not mark the program `PROVEN_LIVE` on docs, green CI, native integration installation or one correct drift report. Fresh-session adversarial production proof is required.

---

## 21. Delivery program

The architecture is delivered as bounded verticals; each one is independently useful and reviewable.

### R0 — architecture freeze + durable drift ledger

**Capability:** current authority, no-rebuild law, known disagreements and exact program sequence are durable outside chat.

Actions:

- land this architecture after Chairman written-spec review;
- reconcile the existing Macro #6509 carrier on the same branch if still semantically valid and land only after exact-head gates;
- record any newly discovered cross-plane drift in the owning durable records without inventing a new workstream parent.

**Stop:** records are merged and a fresh session can recover the program and exact R1 action.

### R1 — read-only Session Truth Receipt

**Capability:** a cold Sol can generate one deterministic current cross-plane receipt without mutating any external system.

Minimum scope:

- protected Skillpack identity;
- Agent OS direct records;
- GitHub current/default/open PR evidence;
- normalized Linear snapshot input/adapter;
- normalized Slack snapshot input/adapter;
- explicit Executive unavailable/current input;
- drift taxonomy + admission mode;
- JSON + concise human report;
- no network in the pure reconciliation core; source acquisition adapters remain separable.

**Stop:** real current estate receipt produced twice with byte-identical semantics for unchanged observations; required falsifiers pass; no external mutation.

### R2 — GitHub/Linear correctness closure

**Capability:** materially live PRs and portfolio projections have exact traceability and false completion is detected/contained.

Use existing carriers/programs:

- finish MAS-28 calibration/recommendation;
- finish MAS-65 acceptance;
- finish MAS-67 native integration canaries and cross-repo readback;
- repair only proven stale Linear projection after owner evidence is known.

**Stop:** representative calibration + current-portfolio drift report + native relationship canaries are accepted; enforcement remains report-only unless separately authorized.

### R3 — `#build-events` visibility

**Capability:** the Chairman/Sol seats receive low-noise GitHub + selected Linear visibility while protected channels remain untouched.

Use MAS-103/104 official integration runbooks. Do not build a custom relay solely to avoid official-app action surfaces.

**Stop:** inert canaries prove selected events, zero protected-channel routing, no Slack-caused mutation and documented rollback.

### R4 — Executive blindness removal

**Capability:** all approved Sol seats read fresh canonical Executive state from one `MMX/SOL_STATE_V1` projection.

Continue PR #155 / MAS-109 only; no replacement carrier.

**Stop:** production three-seat stale/degraded/restart/ACK-loss proof accepted; still no inbound write path.

### R5 — safe Linear project apply

**Capability:** canonical Agent OS desired project state can be dry-run compared and boundedly projected by the dedicated app actor without overwriting concurrent/manual state.

Sequence: MAS-65 acceptance -> MAS-64 app actor -> MAS-66 P1 project-only canary and real-portfolio dry-run -> separate arming review for wider apply/scheduling.

**Stop:** project-only adapter canary + dry run accepted; issue lifecycle remains outside scope.

### R6 — active-session transport enforcement

**Capability:** worker/COO dialogue is carried by the accepted Agent Relay and absent-recipient runnable Slack pickups are refused before emission.

Sequence: MAS-127 A2 -> A3 real decision round trip -> add/use pre-send commission guard at the accepted pre-CeoIngress/commission emit seam without modifying protected Skillpack law or creating another queue.

**Stop:** real active-session round trip, receiver identity proof, duplicate/effect-unknown/restart falsifiers and post-freeze-dispatch regression pass.

### R7 — fresh-Sol adversarial integration canary

**Capability:** a genuinely fresh Sol can recover current truth and refuse unsafe modification without Chairman explanation.

Inject or construct bounded test scenarios representing:

1. stale Linear parent text while child/current owner advanced;
2. merged GitHub implementation with production proof still open;
3. Slack DELIVERY_ONLY message with no eligible receiver;
4. ChatGPT CEO principal addressed as worker;
5. unknown seat GitHub binding;
6. active duplicate carrier;
7. stale/unavailable Executive SOL_STATE;
8. same operation key with changed payload/effect unknown;
9. missing optional visibility source while canonical read-only reasoning should still proceed;
10. real fully grounded safe read path.

The fresh session must classify every case correctly and refuse the unsafe modifications.

**Stop:** adversarial fresh-session proof passes on the production-relevant Sol path and all required durable closeout/projections are updated.

---

## 22. Testing strategy

### 22.1 Unit / contract

Every finding code receives positive + negative fixtures. Same normalized input must generate byte-identical semantic output. One-field changes must cause bounded report deltas.

### 22.2 Mutation/adversarial tests

Tests must fail if implementation:

- allows Linear majority-vote over Agent OS/GitHub;
- treats Slack delivery as ACK/execution;
- maps ChatGPT seat to worker realm by name;
- silently converts unknown source into empty/healthy;
- allows stale SOL_STATE to authorize modification;
- permits same operation key with changed payload;
- creates a second active carrier;
- treats implementation merge as production proof;
- overwrites concurrent Linear state without re-read;
- introduces hidden durable retry/cursor/state storage.

### 22.3 Integration

Use real normalized observations from the current repositories/apps in read-only mode. External reads and pure reconciliation must remain separable so deterministic tests do not depend on network availability.

### 22.4 Production proof

Program completion requires a genuinely fresh Sol session using current protected procedure plus production-relevant observation paths. Fixtures alone cannot prove the anti-blindness outcome.

---

## 23. Success metrics

The program succeeds when:

- a fresh Sol catches every known material stale/false-green condition without chat archaeology;
- no new duplicate work carrier is created from Slack ambiguity;
- every materially live GitHub carrier has an explainable WS/Linear/completion classification or an explicit typed exception;
- current Agent OS portfolio drift can be deterministically compared to Linear;
- `#build-events` provides useful visibility but can be deleted/rebuilt without truth loss;
- `#sol-runtime` exposes fresh/degraded Executive truth to all approved Sol seats;
- a missing optional source degrades honestly rather than blinding the whole session;
- no new lifecycle, identity, queue, retry, memory or synchronization authority exists;
- R7 adversarial fresh-session canary passes.

---

## 24. Product/operational value

### User value

The Chairman no longer has to explain “which session did what” or manually reconcile GitHub, Linear and Slack before delegating the next outcome.

### Machine value

Sol sessions start with current typed grounding rather than hidden conversational state. Operators receive bounded carriers with fewer duplicate/replayed commissions.

### Research/signal value

Not directly signal-generating, but it protects all research/product programs from stale authority, duplicate work and false completion.

### Distribution/operability value

`#build-events`, Linear portfolio and Control Room/SOL_STATE become trustworthy navigation surfaces instead of implicit truth stores.

### Data moat / learning value

Typed drift receipts create an evidence base for which integration failure modes actually recur, without becoming a mutable lifecycle database. Future enforcement may be promoted only from observed failure frequency and false-positive/negative evidence.

---

## 25. Completion law

This program is **not complete** when:

- this spec merges;
- R1 produces one drift report;
- MAS-65/MAS-28 CI is green;
- Slack official integrations are installed;
- `#sol-runtime` shows one state message;
- ASD carries one message;
- Linear and GitHub look visually aligned on one day.

It is `PROVEN_LIVE` only when a genuinely fresh Sol can run the production-relevant reconciliation path, correctly detect the declared adversarial drift classes, consume fresh Executive state where required, refuse unsafe modification, proceed on a safe grounded case, and leave durable/projection/transport state correctly reconciled without Chairman prompt carriage or a hidden second control plane.

---

## 26. Exact next action after approval of this written spec

Create the implementation plan for **R1 only** first, because R1 is the new independently useful software capability and should not absorb existing MAS-28/65/67/103/104/109/127 lanes.

In parallel, Sol may continue read-only review/reconciliation of the existing Macro #6509 records carrier. No code or app-install wave begins from this architecture carrier until the written spec is reviewed and the corresponding bounded plan/commission exists.
