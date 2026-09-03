# Secretary Reasoning-Seat Retirement and Live-Bridge Cutover Amendment

**Date:** 2026-09-02

**Owner:** Sol, AI CEO

**Chairman:** Chris

**Chairman approval:** direct current instruction in the governing Sol session: phase out the overworked Secretary role, preserve it as the live handout/reconciliation bridge while the replacement is built, move quickly, and switch only after the replacement is proven.

**Operation key:** `mastermind-secretary-reasoning-seat-retirement-20260902-sol-001`

**Integration carrier:** Mastermind issue #386, `mastermind-worker-dispatch-consumption-assurance-20260902-sol-001`

**Protected source basis:** `mastermindx-market-intelligence/Mastermind@caa47c1e66fe36dc3521299c918f4b9e7b2a47ca`, `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.
**Capability state:** `SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT`. This amendment itself changes no automation cadence, Slack subscription, watcher resource, Job, Attempt, Worker, RuntimeBinding, provider session, credential, deployment, or production behavior.

---

## 1. Decision and correction

The permanent high-reasoning Grok Secretary seat is a temporary continuity bridge, not the target operating architecture.

The bridge must remain active while deterministic ingress, preflight, wake, checkpoint, return projection, and exception routing are proven. Pausing or archiving the only working handout/reconciliation path before those capabilities reach acceptance is an unsafe cold cutover and is forbidden by this amendment.

The immediate operating rule is therefore:

```text
KEEP the current Secretary bridge live
+ ELIMINATE duplicate reasoning scans
+ BUILD and shadow the existing deterministic owners
+ CANARY against the same live traffic
+ CUT OVER only after parity and adverse proof
= RETIRE the permanent reasoning seat without losing the organizational inbox
```

The initial containment instruction issued during the 2026-09-02 audit is narrowed accordingly. It remains a guardrail against duplicate carriers, duplicate workers, active-writer collisions, blind retries/failover, stale substantive writes, and unauthorized production/provider/account effects. It is not a general dispatch halt.

## 2. Narrow precedence

This amendment governs only:

- continuity of the live Secretary bridge during migration;
- removal of duplicate Secretary-source monitoring;
- the boundary between deterministic detection and principal reasoning;
- cutover gates for retiring the permanent reasoning seat;
- rollback to the same bridge if the replacement degrades.

It extends and does not replace:

- `docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md`;
- `docs/superpowers/specs/2026-08-28-watcher-resource-freshness-design.md`;
- `docs/superpowers/specs/2026-08-28-organizational-continuity-attention-recovery-amendment.md`;
- `docs/superpowers/specs/2026-08-29-autonomous-delegation-operational-fluency-amendment.md`;
- `docs/superpowers/specs/2026-08-31-operation-liveness-soundness-executive-steward-reconciliation.md`;
- `docs/superpowers/specs/2026-09-01-operation-assurance-a2-source-seam-design.md`;
- the existing Executive OS, Agent Dialogue, Wake, RuntimeBinding, Capacity, Steward, Control Room, Agent OS, GitHub, and Slack ownership boundaries.

If this amendment conflicts with a broader source, the broader source wins except for the explicit bridge-preservation and reasoning-seat cutover rules above.

## 3. Audit evidence and problem statement

At the audit snapshot, the current Secretary reasoning task had accumulated:

- 352.6 MB of session transcript;
- 234 context turns and 181 task starts;
- 345,924,690 raw model tokens, including 338,916,864 cached input tokens;
- recent wake inputs of approximately 158,000 to 230,000 tokens;
- 53 child-agent spawns, 278 follow-up commissions, 496 waits, and 4,037 shell/tool orchestration calls.

An overlapping CTO-TRACE reasoning task also claimed the permanent Grok Secretary inbox and scanned the same Slack channels. Its automation prompt was approximately 1.0 MB and its transcript had processed approximately 93.2 million additional raw model tokens.

These counters are not a billing ledger and do not prove that every token was avoidable. They do prove that the operating shape repeatedly rehydrates broad historical context and performs principal reasoning for routine attention work.

The defect is not that the Secretary works hard. The defect is that one reasoning session currently combines:

1. inbox enumeration;
2. cursor/baseline maintenance;
3. event classification;
4. carrier reconciliation;
5. lifecycle inference;
6. capacity and RuntimeBinding census;
7. worker placement and dispatch;
8. reviewer commissioning;
9. active-worker rescue;
10. result adjudication;
11. CI/release follow-through;
12. historical reporting.

The overlapping monitor repeats part of the same work. Prompts and transcripts are functioning as an accidental queue, state store, and control room. That is expensive, stale-prone, and capable of violating a current freeze or sole-writer boundary even when the source law is correct.

## 4. Target outcome

The Chairman sets intent and can observe the company without Slack archaeology. The organization then:

- detects relevant Slack/provider/GitHub/runtime transitions below the reasoning layer;
- admits or refuses one exact logical operation through existing owners;
- preserves delivery, pickup ACK, START, source effect, production effect, RESULT, CONTINUE, and STOP as distinct facts;
- keeps one current action-authoritative worker and one current action-authoritative executive turn;
- wakes Sol only for a material semantic edge requiring CEO judgment;
- survives session/provider loss through canonical checkpoints and exact RuntimeBinding reconciliation;
- reports the complete state through Steward/Control Room and the read-only Secretary MCP;
- performs no duplicate handout while the legacy bridge and replacement run concurrently;
- retires the permanent reasoning heartbeat only after live parity is proven.

The end state removes the **Secretary reasoning role**, not the useful Secretary product surface. A conversational Secretary UI/MCP may remain as a read-only or explicitly governed command shell over approved existing controls. It is not a permanent frontier-model polling seat.

## 5. Non-goals

This amendment does not authorize:

- a new Secretary service, lifecycle, scheduler, queue, cursor store, watcher registry, responsibility database, retry plane, provider pool, RuntimeBinding owner, authority map, Steward, Control Room, or Agent OS;
- semantic-similarity matching as mutation authority;
- migration of lifecycle truth into Slack, Codex task transcripts, automation prompts, or the Secretary MCP;
- immediate shutdown of the current Secretary bridge;
- takeover of PR #268, #323, #362, or another existing writer carrier;
- promotion of Operation Assurance from report-only to admission authority before its accepted calibration/promotion wave;
- autonomous production deploy, credential mutation, provider/account rotation, or merge authority;
- a time-based declaration that silence proves cutover readiness.

## 6. Canonical ownership map

| Fact or action | Existing canonical owner | Secretary-retirement use |
|---|---|---|
| Chairman intent and strategic amendment | Chairman / strategic state | Source of the retirement objective |
| Job, Attempt, Worker, Event, lease/fence, retry/requeue | Executive OS | Sole lifecycle and mutation owner |
| Canonical dialogue parent and Slack semantic messages | Agent Dialogue / Agent Relay | Exact carrier and transport |
| Delivery, attention obligation, exact wake, source resolution | Wake Fabric | Detect and route attention without a second queue |
| Exact current provider/native target | SessionTargetRegistry / RuntimeBinding | Prevent stale or wrong-session action |
| Capacity and placement evidence | Capacity Fabric / shared provider control | Select lawful capacity through existing policy |
| Source-attributed liveness/soundness assessment | Operation Assurance | Shadow preflight first; later promotion only through its accepted waves |
| Cross-owner read/explanation | Executive Steward / Control Room | Small canonical operating projection |
| Conversational Secretary surface | `integrations/mastermind_secretary_mcp` | Read-only visibility and approved control invocation |
| Code, PR, CI, review and protected source | GitHub | Implementation/evidence plane |
| Organizational decisions and handoffs | Macro Agent OS | Knowledge only, never execution authority |
| Slack | Dialogue transport and forensic audit | Never the lifecycle or Chairman workflow |

No row moves to the Secretary task, its automation, or this amendment.

## 7. Architecture

```text
Slack / provider / GitHub / runtime material events
        |
        v
existing Agent Dialogue / Wake / owner-native adapters
        |
        |  Class-E event or Class-T delta detection
        |  unchanged samples suppressed
        v
existing Executive OS lifecycle + current RuntimeBinding
        |
        +----> Operation Assurance report-only source compilation
        |      (shadow until separately promoted)
        |
        v
deterministic transition and exact-carrier preflight
        |
        +---- no material change ----> quiescent receipt, no Sol turn
        |
        +---- deterministic valid edge -> existing worker/continuation avenue
        |
        +---- ambiguity / conflict / high-impact edge
                                      |
                                      v
                               one exact Sol turn
                                      |
                                      v
                           CONTINUE / HOLD / STOP / decision
                                      |
                                      v
                    Steward / Control Room / read-only Secretary surface
```

### 7.1 Fast detection, sparse reasoning

The replacement does not make Slack checking slow. It moves frequent checking below the reasoning layer:

- Class E receives a provider/webhook/native event without a model turn.
- Class T polls owner-native state, suppresses unchanged samples, and emits only a qualifying delta.
- Class M remains a temporary compatibility bridge. Its default interval is 60 minutes, its absolute floor is 15 minutes, and urgent no-change polling backs off `15m -> 30m -> 60m`.

Class-T detection may run frequently where API and owner law permit. A tight deterministic check never justifies a tight Sol/Fable/Codex wake.

### 7.2 Material-event envelope

The detector must project a bounded immutable envelope containing owner-native references, not copied lifecycle truth:

```text
schema
event_id
observed_at
source_owner
source_ref
workspace
channel_or_surface
thread_root_or_carrier
operation_key
semantic_edge
baseline_ref
payload_digest
current_runtime_binding_ref
current_job_attempt_worker_ref
```

The exact schema belongs to the current owner wave. This amendment freezes only the required properties:

- deterministic identity;
- source attribution;
- bounded payload;
- baseline/delta comparability;
- exact carrier reference;
- references to lifecycle and RuntimeBinding owners rather than duplicated state;
- no authority derived from human-readable titles or model prose.

### 7.3 Qualifying material edges

Examples that may wake Sol or another exact principal include:

- a valid current assignment requiring CEO/COO action;
- `BLOCKED`, `DECISION_REQUEST`, or `RESULT` on the exact carrier;
- carrier/source movement affecting a pending substantive action;
- active-writer, RuntimeBinding, provider/account, or effect conflict;
- a genuine CI/review/release failure requiring adjudication;
- a missed-fire or session-loss condition that cannot be settled deterministically;
- a strategic or Chairman gate.

These do not justify a reasoning turn:

- unchanged channel state;
- duplicate delivery;
- baseline or older messages;
- already-consumed receipts;
- normal pending CI;
- an already-terminal child;
- elapsed time below a declared missed-fire threshold;
- a backlog row with no current authority;
- routine task, worktree, or PR enumeration with no relevant delta.

### 7.4 Deterministic preflight

Before a new handout or continuation, existing owners must determine:

1. exact operation and canonical carrier;
2. trusted current source and semantic edge;
3. whether delivery already occurred;
4. whether pickup ACK occurred;
5. whether START occurred;
6. current Job, Attempt, Worker, lease/fence, and RuntimeBinding;
7. active-writer or duplicate-executor collision;
8. known/unknown source and production effects;
9. terminal, frozen, parked, or held state;
10. lawful capacity/placement;
11. shortest deterministic refusal, counterexample, or valid wait.

Operation Assurance supplies a report-only assessment while A2-A6 mature. It becomes an admission dependency only through the separately accepted and calibrated A7 promotion. Until then, current Executive/Dialogue/Wake guards remain authoritative and the Secretary bridge catches gaps.

## 8. Live bridge contract

### 8.1 Bridge stays active

The current Secretary aggregate seat/principal inbox remains active throughout shadow, canary, and small-fleet stages. A child STOP removes only that child source. It does not terminate the aggregate Secretary bridge.

The bridge may continue lawful handout, reconciliation, adjudication, and recovery required to prevent organizational stall. It must preserve:

- exact carrier identity;
- current sole writers;
- current source freshness;
- delivery versus ACK versus START;
- source effects versus production effects;
- one-watcher discipline;
- no blind retry/failover;
- no duplicate control plane.

### 8.2 One permanent inbox scanner

During migration, exactly one aggregate reasoning resource may own the permanent Secretary inbox. The CTO-TRACE resource must not independently preserve or scan the same permanent Secretary source.

Removing that duplicate source must not disable distinct valid CTO-TRACE sources, sibling operations, or the Secretary bridge itself. Source lifetime and watcher-resource lifetime remain distinct.

### 8.3 Dual-run dedupe

Shadow and canary execution must not create a second handout merely because both paths observed the event.

```text
replacement path = observer/shadow until explicit canary authority
Secretary bridge = action owner during shadow

canary path = action owner only for enumerated canary operation keys
Secretary bridge = observes and suppresses action for those exact keys

all other operations = Secretary bridge remains action owner
```

Authority changes per exact operation key and carrier, never by vague global prompt language.

### 8.4 Compact bridge context

The bridge prompt may contain stable law pointers, active source locators, the last consumed baselines, and bounded current exceptions. It must not embed terminal operation history, large GitHub/Slack transcripts, old review packets, or a copied responsibility database.

Terminal evidence remains in its canonical owner. The bridge rereads only the exact current source needed for a material action.

## 9. Sol exception contract

Sol is a principal adjudicator, not an inbox polling daemon.

Every Sol wake from the replacement path must identify:

- exact operation key;
- exact carrier;
- current source pin;
- latest unconsumed material semantic edge;
- deterministic preflight result;
- unresolved choice requiring Sol;
- allowed effects;
- forbidden effects;
- shortest valid response family.

The normal output is one of:

```text
CONTINUE
REQUEST_REPAIR
HOLD
STOP
DECISION
SOURCE_OR_CARRIER_MOVED
ACTIVE_WRITER_COLLISION
EFFECT_UNKNOWN_RECONCILIATION_REQUIRED
NO_MATERIAL_CHANGE
```

`NO_MATERIAL_CHANGE` is generated below the reasoning layer whenever possible. It never grants authority or advances lifecycle state.

## 10. Rollout stages

### R0 — Live bridge restored and measured

- Keep the current Secretary task active.
- Narrow prior containment to collision/effect guardrails rather than a dispatch halt.
- Capture bounded counters: material events, unchanged scans, model wakes, handouts, ACK latency, START latency, duplicate suppressions, carrier mismatches, manual rescues, and missed fires.
- Remove only the duplicated permanent Secretary source from CTO-TRACE.
- Preserve every unrelated watcher source and current lawful carrier.

Exit evidence: Secretary handout continuity remains intact; duplicate source ownership is absent; no operation is lost or double-dispatched by the change.

### R1 — Deterministic detector shadow

- Reuse Agent Dialogue/Wake owner-native inputs.
- Produce bounded source-attributed deltas without model reasoning on unchanged samples.
- Run as shadow only; the Secretary bridge remains action owner.
- Compare every shadow classification with the bridge's actual action.

Exit evidence: the detector sees all qualifying events in the canary corpus, produces no action from unchanged samples, and creates no lifecycle or RuntimeBinding writes.

### R2 — Preflight and continuity convergence

Reuse existing carriers rather than creating replacements:

- PR #383 exact Slack thread-root fence: protected source dependency;
- PR #362 Operation Assurance A2: repair current reviewed carrier, then shadow source compilation;
- PR #323 Secretary grounding: repair the current RuntimeBinding-attempt and per-subject schema blockers;
- PR #268 structured watcher hardening: finish the current direct-source repair and exact-head review;
- issue #346 remote checkpoint;
- issue #343 remote-complete writer release;
- issue #345 exact wake and missed-fire handling.

No retirement carrier takes ownership of those files. Their current writers and review gates remain authoritative.

Exit evidence: exact carrier, current writer, checkpoint, release, and wake state can be reconciled without broad Secretary archaeology.

### R3 — One exact canary operation

Authorize the replacement path for one harmless, explicitly named operation key while the Secretary bridge observes but does not duplicate action for that key.

The canary must demonstrate:

```text
canonical commission
-> exact delivery
-> PICKUP_ACK
-> START
-> remote checkpoint
-> nonterminal RESULT
-> Sol CONTINUE
-> same logical worker continuation
-> final RESULT
-> Sol STOP
-> exact child-source removal
-> aggregate seat watcher survives
-> Steward/Secretary readback
```

Exit evidence: zero lost handouts, duplicate workers, carrier splits, stale-writer effects, or manual prompt shuttles.

### R4 — Small fleet

- Admit ten consecutive bounded real operations through the replacement path.
- Keep the Secretary bridge active as non-acting observer for exact migrated keys and acting owner for all others.
- Include at least one worker block, one continuation, one terminal STOP, one provider/session degradation, and one duplicate-delivery replay.

Exit evidence:

- zero lost qualifying events;
- zero duplicate handouts or executors;
- zero incorrect ACK/START projection;
- zero blind retry/failover;
- zero Chairman prompt shuttle;
- at least 80% fewer principal reasoning wakes per migrated operation than the measured bridge baseline;
- every exceptional Sol wake names one material unresolved choice.

### R5 — Retire the permanent reasoning seat

After R3 and R4 evidence is accepted:

- stop new operation intake through the Secretary reasoning heartbeat;
- allow any remaining exact bridge-owned operation to reach checkpoint and terminal closure;
- pause/archive the existing aggregate reasoning task only after its source set is empty or safely transferred;
- preserve the read-only Secretary MCP/conversational product surface;
- preserve deterministic ingress, Wake, Executive OS, Steward, and Control Room;
- retain no permanent reasoning-model poller for unchanged inbox state.

Retirement is an explicit cutover receipt, not inference from silence.

## 11. Rollback and degradation

Any of these conditions blocks or reverses cutover:

- qualifying event missed or delivered late beyond the accepted bound;
- duplicate handout/executor;
- unknown effect without same-operation reconciliation;
- stale or wrong RuntimeBinding action;
- invalid delivery projected as ACK or START;
- lost continuation or STOP;
- aggregate seat resource disabled by child-source removal;
- inability to explain current state from canonical owners;
- material increase in Chairman manual intervention.

Rollback reactivates or returns action ownership to the **same existing Secretary bridge** for the affected exact operations. It does not mint a successor Secretary, new watcher resource, new queue, or alternate control plane.

The bridge remains warm through R4 specifically so rollback is an ownership toggle over exact operation keys, not an emergency reconstruction.

## 12. Adverse acceptance matrix

Before R5, automated tests or controlled canaries must cover:

1. unchanged Slack/API sample;
2. duplicate message/event delivery;
3. same channel but wrong thread root;
4. stale baseline followed by a new Sol ruling;
5. delivery without pickup ACK;
6. ACK without START;
7. active writer on the same path;
8. current branch/head moves after preflight;
9. source effect known, production effect unknown;
10. launch response lost after a possible effect;
11. RuntimeBinding generation moves during action preparation;
12. provider/session disappears before checkpoint;
13. provider/session disappears after checkpoint;
14. missed watcher fire;
15. late return after terminal STOP;
16. child STOP on an aggregate seat watcher;
17. malformed Slack/provider payload;
18. deeply nested JSON;
19. non-string human-readable fields;
20. untrusted model/message text claiming authority;
21. current freeze or hold;
22. Slack unavailable while Executive state remains available;
23. replacement path unavailable while the Secretary bridge remains healthy;
24. Secretary bridge unavailable after accepted cutover.

Each case must state expected lifecycle effect, source effect, production effect, model-wake behavior, and rollback owner.

## 13. Observability and resource accounting

Use existing telemetry and Control Room owners to expose:

- watcher class (`event`, `tool_poll`, `model_poll`);
- source and purpose;
- actual cadence;
- last successful source read;
- last consumed baseline;
- material versus unchanged detections;
- suppressed duplicates;
- refused dispatches and reasons;
- delivery-to-ACK and ACK-to-START latency;
- missed-fire count;
- principal model wakes and input/output token counters;
- bridge-versus-replacement classification disagreements;
- current action owner per exact operation.

These are observations only. Metrics cannot grant lifecycle, retry, merge, provider, deployment, or production authority.

## 14. Completion standard

This program is not complete when a detector exists, a PR is green, or the Secretary prompt is shorter.

It is complete only when:

1. the live Secretary bridge remained available throughout migration;
2. duplicate permanent inbox monitoring was removed without losing any valid source;
3. unchanged samples no longer invoke principal reasoning;
4. material events reach the correct existing owner with exact carrier and RuntimeBinding evidence;
5. the complete R3 dialogue canary passes;
6. the ten-operation R4 fleet passes its reliability and resource gates;
7. adverse controls pass;
8. the Chairman accepts the cutover receipt;
9. the permanent Secretary reasoning task is paused/archived only after safe drain;
10. the read-only Secretary/Control Room experience remains available;
11. production behavior is verified separately from protected source.

The terminal outcome is:

> The Secretary product remains; the Secretary polling job disappears. Routine attention and handout are deterministic, Sol handles only material judgment, and the Chairman never becomes the fallback dispatcher.
