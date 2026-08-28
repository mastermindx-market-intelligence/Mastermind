# Project Recovery Sentinel R8 — Permanent Dead-Project Detection & Fresh-Sol Recovery

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Chairman authority:** Chairman approved the architecture in chat on 2026-08-27 and directed Sol to make the recovery mechanism permanent.  
**Operation key:** `project-recovery-sentinel-r8-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `cef4332d3682991e3e1c3d6160da17cd0a3a8f63`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1 compatible.  
**Observed Macro main during design:** `1b414b94dc7ff38e0e71e5aebaebb4da72c47f67`.  
**Active predecessor carrier:** Mastermind PR #170, `CROSS-PLANE-R1`, head observed `a2c82b5795bf23da2a921118eb7fb80244ee9eaf`; R8 must not modify or duplicate that carrier.  
**Existing organizational parent:** `WS:CHAIRMAN-CONTROL-ROOM`; R8 is a continuation of the accepted cross-plane/fresh-Sol architecture, not a new lifecycle or workstream system.  
**Status:** CHAIRMAN-APPROVED DESIGN / SPEC-ONLY. No runtime, Agent OS schema, Improvement Agenda, Linear, Slack, Executive, Control Room, worker, or scheduler behavior is changed by this document.

---

## 1. Outcome

Mastermind-X must stop silently losing unfinished programs when a Sol/Fable/chat session ends, a Slack commission has no receiver, a PR merges before production proof, or an Agent OS workstream remains `active` after its real frontier disappeared.

The system must make materially unfinished-but-unowned work mechanically visible without making Slack, Linear, chat history, or a new database into a second task/lifecycle authority.

### 1.1 Chairman job

The Chairman should not have to remember which long-running programs were left half-built, audit stale project lists manually, or know which old Sol chat used to own them.

The operating experience should answer, at a glance:

- which materially unfinished programs are actively claimed and moving;
- which are intentionally waiting on a lawful future condition;
- which require a CEO ruling or external action;
- which have lost their carrier/worker/frontier and require CEO recovery;
- which are uncertain because canonical runtime evidence is unavailable;
- why each classification was made and which canonical owners supplied the evidence.

### 1.2 Machine job

Deterministically compare current Agent OS organizational state, semantic program registry, GitHub carrier/evidence state, and Executive runtime state when available; consume Session Truth drift findings rather than reimplementing cross-plane reconciliation; recognize typed intentional waits; emit recovery findings; and feed those findings into the existing Improvement Agenda and projection surfaces.

No model may infer project liveness from prose, title similarity, a Slack delivery, Linear status, or an arbitrary stale-age guess.

### 1.3 10/10 end state

Every materially unfinished program is in exactly one explainable condition:

1. observable active carrier/runtime claim exists;
2. typed intentional wait exists and its review point has not expired;
3. typed CEO/operator/external gate exists;
4. canonical state is unavailable/ambiguous and therefore requires reconciliation rather than duplicate dispatch;
5. `CEO_RECOVERY_REQUIRED` is deterministically raised.

A fresh Sol session can recover the highest-priority recovery item from current canonical truth, reconstruct the full product thesis, adjudicate whether resurrection is lawful, and commission bounded sustained execution without any dependence on the old chat.

---

## 2. Why this is R8, not another Recovery OS

The accepted cross-plane program already owns the machinery needed to answer “what do the current owners say?” and is delivering `mastermind.session_truth_receipt.v1` in R1. R8 is a **consumer/extension of that read-first architecture**.

R8 must not create:

- a recovery database;
- a second work registry;
- a second priority queue;
- a second scheduler;
- a Slack inbox/retry system;
- a Linear-owned lifecycle;
- a chat/session identity authority;
- another Executive Job/Attempt/Worker plane;
- another Agent OS parser;
- another Agent OS → Linear projector;
- another Control Room attention store.

The permanent recovery behavior is a deterministic derived view over existing owners, followed by projection through existing systems.

---

## 3. Authority boundaries

One fact keeps one canonical owner.

| Fact | Canonical owner | R8 behavior |
|---|---|---|
| Workstream/program/decision/handoff organizational state | Agent OS / declared semantic registry | Read; add only the minimal typed wait contract in the Agent OS owner when separately implemented |
| Code/PR/CI/merge/implementation evidence | GitHub | Read exact bound carriers and proof state |
| Job/Attempt/Worker/Event lifecycle and real claim/execution | Executive OS | Read only when production-proven/available; absence remains unknown |
| Cross-plane drift/admission | Mastermind Session Truth | Consume/extend after R1; do not duplicate rules in Macro |
| Ranked “what should we fix?” agenda | Macro Improvement Agenda | Add a recovery source/class; keep it the sole ranker |
| Portfolio display | Linear | Project recovery state; never originate or clear canonical completion |
| Chairman operating view | Chairman Control Room | Read-only recovery/attention composition |
| Transport visibility | Slack `#build-events` | Transition alerts only; never queue/claim/retry/wake |
| Sol identity | Authenticated Sol seat + Project bootstrap + current canonical sources | Never bind recovery ownership to one chat URL |

---

## 4. Approaches considered

### A. Dedicated Project Recovery OS/database

Rejected. It would become a fourth authority for work/liveness, require synchronization with Agent OS/GitHub/Executive, and create new queue/retry/identity semantics.

### B. Use Linear or Slack as the recovery queue

Rejected. Linear is projection and Slack is transport. Neither can prove an active worker claim, production acceptance, or canonical unfinished scope. This would reproduce the existing dead-letter failure where Slack-shaped commissions looked like execution.

### C. Simple “last updated > N days” stale detector

Rejected. It cannot distinguish a genuinely abandoned build from a valid three-week prospective-evidence wait. It would generate false recovery commissions and collisions.

### D. Selected: deterministic recovery overlay on Session Truth + typed waits + existing Agenda/projections

Selected. This preserves one owner per fact, makes legitimate waiting machine-readable, produces explainable recovery findings, ranks them through the existing Improvement Agenda, and lets any fresh Sol resume CEO responsibility without chat continuity.

---

## 5. Recovery data model: derived, not lifecycle

R8 does not persist a new mutable project state. It produces an immutable assessment/receipt bound to exact observations. The implementation may extend Session Truth with a portfolio-recovery mode or a sibling receipt under the same reconciliation module, but it must not create a separate mutable authority.

Recommended derived schema name if a sibling envelope is needed:

```text
mastermind.project_recovery_assessment.v1
```

It is an **evidence receipt only**. It must contain source SHAs/timestamps/hashes and deterministic findings; committing one later never relabels it as current state.

### 5.1 Derived dispositions

The human/UI layer may summarize each assessed program/workstream as one of:

- `NO_RECOVERY_ACTION` — enough current owner evidence exists;
- `VALID_INTENTIONAL_WAIT` — a typed wait is still within its review window;
- `CEO_ATTENTION` — a typed CEO decision/gate is due but this is not safe to auto-resurrect;
- `RECOVERY_REQUIRED` — unfinished work has no lawful active frontier and current evidence is sufficient to say so;
- `UNKNOWN_RECONCILE` — required runtime/identity/carrier evidence is unavailable or conflicting; surface to Sol but do not commission.

These are derived display/assessment classes only. They are not Agent OS workstream statuses and not Executive lifecycle states.

---

## 6. Minimal Agent OS intentional-wait contract

Current Agent OS already has typed workstream status, wave status, dependencies, advisory claims and `needs_ceo.by_when`, but ordinary `next_action` is prose. R8 must never parse prose to decide whether inactivity is intentional.

Add one optional typed `wait` object, reusable at workstream and wave scope, owned and validated by Macro Agent OS.

Recommended V1 shape:

```yaml
wait:
  kind: natural_evidence | external_dependency | calendar_window | external_action
  review_after: YYYY-MM-DD
  condition: "Human-readable condition; never machine-parsed for authority"
```

Rules:

- `review_after` is required even when the real event has no exact known date; it is the next mandatory review point, not a prediction that the condition will resolve by then.
- `condition` is display/evidence context only. The recovery engine may not parse it to infer completion, authority, provider identity, or a new gate type.
- a non-expired wait suppresses `RECOVERY_REQUIRED` only for the exact workstream/wave it binds;
- an expired wait emits `MISSED_REVIEW_GATE`; it does not silently roll forward;
- existing `needs_ceo.by_when`, `blocked_by`, dependencies, and wave status remain canonical for their own semantics;
- existing Agent OS `claim` remains advisory/day-scale and cannot prove runtime execution by itself.

This is the only new durable organizational field R8 requires.

---

## 7. Deterministic recovery findings

R8 initially supports the following finding families. Exact severity may depend on source availability and explicit proof contracts, but classification is deterministic.

### 7.1 `ORPHAN_BUILDING_PROGRAM`

`config/mastermind_programs.yml` says a program lifecycle is `building`, but the exact inverse mapping through workstream `program:` keys yields no nonterminal organizational owner/frontier.

No fuzzy title matching is allowed. This finding is a CEO recovery candidate, not permission to invent a new workstream.

### 7.2 `ACTIVE_WITHOUT_CARRIER`

Agent OS says a workstream/wave is active/in-progress/awaiting work, but no exact bound GitHub carrier and no accepted current runtime claim/typed wait/gate explains the frontier.

If Executive state required for a conclusive judgment is unavailable, disposition is `UNKNOWN_RECONCILE`, not automatic resurrection.

### 7.3 `UNCLAIMED_COMMISSION`

Durable organizational records say work was commissioned, but the expected receiving worker/session never produced canonical claim/runtime evidence. Slack delivery or addressing a ChatGPT CEO principal is never claim proof.

### 7.4 `MISSED_REVIEW_GATE`

A typed `wait.review_after` or other explicit accepted review date passed without a recorded adjudication/updated gate.

### 7.5 `MERGED_PROOF_DEBT`

Implementation merged, but the declared completion law still requires production/browser/natural-time/security/calibration/Sol acceptance evidence and that evidence remains open at the current review point.

### 7.6 `ACTIVE_BUT_COMPLETE`

Top-level organizational status remains active/awaiting while all canonical waves/obligations represented by that workstream are terminal. This is organizational drift; repair Agent OS rather than inventing new work.

### 7.7 `SUPERSEDED_NEXT_ACTION`

Consume the existing Session Truth/Agent OS disagreement result when a durable next action references a PR/wave/date/action superseded by later canonical proof. R8 must not independently NLP-interpret `next_action`.

### 7.8 `CEO_DECISION_OVERDUE`

Existing typed `needs_ceo.by_when` is past due and the corresponding decision remains unresolved.

### 7.9 `RUNTIME_OWNERSHIP_UNKNOWN`

Organizational state implies work should be live but current Executive/session evidence is unavailable, stale, or cannot be exactly bound. This is visible CEO attention and blocks duplicate commission until reconciled.

---

## 8. What counts as active evidence

R8 must distinguish **frontier evidence** from mere recent text.

Potential positive evidence includes only exact, typed facts such as:

- an open/draft/review GitHub PR carrying the accepted Workstream/Wave metadata for unfinished implementation/proof;
- a fresh Executive Job/Attempt/Worker claim when the approved Executive read path is available;
- an accepted active-session runtime/receiver receipt where current architecture declares it authoritative for that fact;
- a non-expired typed Agent OS `wait`;
- a current typed CEO/operator/external dependency gate;
- an implementation merge whose completion contract explicitly leaves a named natural/prospective proof window open and that window is still valid.

The following do **not** prove active execution:

- Agent OS `status: active` by itself;
- Agent OS advisory `claim` by itself;
- a recently edited markdown file;
- a Linear assignee or status;
- Slack message delivery;
- a branch name containing a project title;
- an old PR body saying “in progress”;
- a ChatGPT1/2/3 Slack identity addressed as a worker;
- model inference from `next_action` prose.

No universal “N days since update = dead” threshold is part of V1.

---

## 9. Portfolio census

R8 must scan both organizational workstreams and the semantic program registry so a program cannot disappear merely because nobody created/maintained a workstream.

Inputs:

1. direct Agent OS workstream records through the existing Macro parser/validator;
2. `config/mastermind_programs.yml` through its existing registry owner/validation path;
3. current GitHub repositories/carriers through the existing Session Truth GitHub observation contract;
4. Executive observation when production-proven and required;
5. existing Session Truth drift findings for stale handoffs, proof-open merges, duplicate carriers, projection disagreement and runtime unknowns.

Program ↔ workstream mapping uses the exact required Agent OS `program:` key and registry program key. Similar titles are never a join key.

---

## 10. Improvement Agenda integration

Macro Improvement Agenda remains the **sole priority engine**. R8 adds one evidence source/class; it does not rank projects in Mastermind and does not create another queue.

Recommended new class:

```text
project-recovery
```

Recommended new owner vocabulary entry:

```text
ceo-sol
```

Each agenda row must carry:

- exact program/workstream/wave identity where available;
- recovery finding code;
- disposition;
- exact observation/revision evidence;
- why current work is or is not safely recoverable;
- suggested CEO action;
- current typed wait/gate if applicable;
- no invented worker/commission.

`project-recovery` should rank above routine maintenance when `RECOVERY_REQUIRED`, `CEO_DECISION_OVERDUE`, or expired proof/wait obligations exist. `UNKNOWN_RECONCILE` should remain highly visible but must not be transformed into a runnable worker commission.

The Agenda may persist its normal existing weekly/on-demand artifacts. Those remain ranked advisory artifacts, not lifecycle truth.

---

## 11. Linear projection

Linear is the durable portfolio dashboard, not the recovery authority.

After the existing MAS-65/MAS-64/MAS-66 projector/app-actor lane is accepted for the relevant project-only mutation scope, R8 may project onto the **existing project/workstream object**:

- label: `CEO Recovery Required` for `RECOVERY_REQUIRED`;
- label/managed state for `CEO Attention` or `Runtime Unknown` if the accepted Linear projection contract supports it;
- a managed recovery block with finding code, source observation time/revision, unresolved capability and exact next CEO action;
- clearing the managed recovery block when a later canonical assessment no longer supports it.

V1 does **not** create one new Linear issue per recovery finding. It does not let a native PR integration close a recovery/proof gate. It does not mutate issue lifecycle unless separately authorized by the existing Linear program.

If no exact Linear projection exists, emit `MISSING_LINEAR_PROJECTION`; do not fuzzy-create or bind one.

---

## 12. Chairman Control Room

Add a read-only **CEO Attention / Recovery** composition after its data dependencies are accepted.

Minimum product questions:

- How many projects are actively healthy?
- How many are valid intentional waits?
- How many CEO decisions/reviews are overdue?
- How many are `RECOVERY_REQUIRED`?
- How many are `UNKNOWN_RECONCILE` because runtime/identity evidence is unavailable?
- Why was each item classified, and which source owns each fact?

The panel may provide navigation such as **Open Sol** for the selected workstream. Existing Control Room law remains: opening/focusing a chat is navigation only; R8 does not type prompts, wake an inactive ChatGPT turn, create an Executive Job, or define one canonical Sol conversation.

A fresh Sol session reconstructs the work from current sources; the old chat is optional navigation history, never required memory.

---

## 13. Slack visibility

Use `#build-events` only after its existing accepted visibility path is live.

Emit transition-only, low-noise events such as:

```text
CEO RECOVERY REQUIRED — <program/workstream>
reason: ACTIVE_WITHOUT_CARRIER
canonical_work: still_owed
runtime_state: none | unknown | unavailable
next: Sol reconciliation before commission
```

and a corresponding recovery-cleared transition.

Do not:

- use `#agent-dispatch` as the recovery queue;
- address ChatGPT1/2/3 as workers;
- post runnable Fable pickups when no receiver exists;
- retry delivery;
- infer ACK/execution from Slack;
- store a Slack cursor/inbox/queue for recovery.

If Slack is unavailable for a month, no recovery truth is lost.

---

## 14. How a turn-based Sol receives the work

R8 deliberately does **not** try to wake an inactive ChatGPT conversation.

The persistent handoff is outside the chat:

```text
canonical owners
  -> Session Truth / recovery assessment
  -> Improvement Agenda
  -> Linear + Control Room + optional Slack visibility
  -> next fresh Sol bootstrap
  -> exact workstream recovery
```

When any approved Sol seat/chat starts substantive Mastermind work, the fresh-Sol bootstrap can inspect the current CEO Attention/Agenda state and select or be directed to the highest-priority recovery item. The session then cold-starts that exact program from current protected sources.

Once Sol lawfully commissions execution, Executive OS remains the only runtime Job/Attempt/Worker authority. Fable/worker sustained execution may continue independently; later Sol chats are interchangeable CEO review/adjudication seats because intent, decisions, carriers, receipts and unresolved gates are durable outside chat.

---

## 15. Triggering and scheduling

R8 V1 introduces no new daemon or scheduler.

Required triggers:

1. **Fresh Sol / on-demand:** recovery assessment can be generated as part of current-state grounding when a Sol needs portfolio/CEO-attention truth.
2. **Existing Improvement Agenda:** the established weekly/on-demand agenda run consumes the latest deterministic assessment/source and keeps ignored recovery items visible/aged through its existing mechanics.
3. **Control Room refresh:** may render current read-only recovery assessment through existing compose/read paths when that dependency is accepted.

A later daily/continuous schedule may be armed only through an already accepted scheduler/projector path after false-positive/negative evidence exists. R8 must not create its own cron/daemon merely to look permanent.

---

## 16. Correction and safety law

### 16.1 Unknown is not dead

If required Executive/runtime/identity evidence is unavailable, emit `RUNTIME_OWNERSHIP_UNKNOWN` / `UNKNOWN_RECONCILE`. Do not auto-commission another worker.

### 16.2 One carrier law

If an existing active carrier is found, recovery must attach/reconcile that same carrier or stop. Never create a second carrier because the prior Sol chat is unavailable.

### 16.3 Effect unknown

A possibly committed prior modification remains bound to its original operation key/carrier and is reconciled through the canonical owner. Recovery never blind-retries it.

### 16.4 Wait correction

An expired `wait` is not automatically renewed. A lawful owner must write a new review point/condition based on current evidence.

### 16.5 Projection correction

Linear/Slack/Control Room may lag or fail. Canonical completion/recovery state remains with Agent OS/GitHub/Executive/Session Truth owners; projection debt does not roll canonical work backward.

---

## 17. Recovery examples / required falsifiers

R8 acceptance must include at least these real or synthetic cases:

1. **Abandoned Stock-Identity-shaped case:** unfinished W3+ work, no current carrier, no valid wait, runtime confirms no worker → `RECOVERY_REQUIRED`.
2. **Breathing-shaped case:** explicit natural acceptance review date passed without adjudication → `MISSED_REVIEW_GATE`.
3. **Prospective-evidence case:** non-expired typed wait for next earnings/session cohort → `VALID_INTENTIONAL_WAIT`, no recovery commission.
4. **MarketOntology-shaped case:** current exact carrier/worker exists → `NO_RECOVERY_ACTION`.
5. **Slack dead-letter case:** commission-shaped Slack message delivered but no runtime receiver → `UNCLAIMED_COMMISSION`; Slack does not suppress recovery.
6. **Merged-but-unproven case:** implementation merge plus open browser/production/natural-time gate → `MERGED_PROOF_DEBT`.
7. **Runtime unavailable case:** Agent OS active and GitHub quiet but Executive truth unavailable → `UNKNOWN_RECONCILE`, not resurrection.
8. **Orphan registry case:** lifecycle=`building` program with no exact workstream mapping → `ORPHAN_BUILDING_PROGRAM`.
9. **Active-but-complete case:** all waves terminal but top-level active → organizational correction, not new build.
10. **Duplicate carrier case:** two active carriers for the same logical work → fatal/blocking reconciliation; no recovery commission.
11. **Linear false-green case:** Linear Done while canonical proof open → recovery/false-completion remains visible.
12. **Stale prose case:** `next_action` names an old PR but later canonical state superseded it → consume Session Truth `SUPERSEDED_NEXT_ACTION`; do not NLP-guess.

No acceptance suite may prove success solely with fixtures. A final production-relevant census of the current portfolio is required.

---

## 18. Delivery sequence

R8 is decomposed so active R1/#170 stays isolated.

### R8-A — recovery contract and classifier

**Depends on:** R1 Session Truth contract acceptance.  
**Capability:** exact observations produce deterministic recovery findings/dispositions with zero mutation.

Scope: Mastermind reconciliation layer only, plus fixtures/tests/current-estate read-only receipt. No Macro/Linear/Slack/Control Room mutation.

### R8-B — Agent OS typed wait + portfolio source

**Capability:** legitimate long waits are machine-readable without prose inference; semantic-registry `building` programs can be exact-joined to workstreams.

Scope: Macro Agent OS schema/parser/compiler owner only. No second registry/parser.

### R8-C — Improvement Agenda ingestion

**Capability:** recovery findings appear in the existing ranked agenda with `owner=ceo-sol` and exact evidence/readiness.

Scope: extend the existing Improvement Agenda; preserve it as sole ranker.

### R8-D — Linear projection

**Depends on:** accepted MAS-65/MAS-64/MAS-66 project-only projection path.  
**Capability:** existing projects visibly show `CEO Recovery Required`/managed reason without becoming truth.

### R8-E — Control Room CEO Attention

**Capability:** Chairman sees recovery/valid waits/unknowns in one read-only surface and can navigate to a Sol seat/chat.

No prompt typing, wake, lifecycle mutation, or new attention store.

### R8-F — Slack transition visibility

**Depends on:** accepted `#build-events` visibility path.  
**Capability:** low-noise entered/cleared recovery transitions; no queue semantics.

### R8-G — fresh-Sol adversarial production canary

A genuinely fresh Sol must:

- identify the current highest-priority recovery item without prior-chat explanation;
- distinguish valid waits from abandoned work;
- refuse duplicate commission on runtime unknown/collision;
- recover the full program outcome rather than only the stale next PR;
- commission only after normal Chairman/Skillpack/runtime gates;
- close the recovery finding after accepted durable closeout/projection repair.

---

## 19. Permanent portfolio invariant

After R8 is accepted, an unfinished material program may no longer be considered healthy merely because it is labeled `active`.

At every recovery assessment, it must have at least one explainable frontier:

```text
ACTIVE_CARRIER
or ACTIVE_RUNTIME_CLAIM
or VALID_TYPED_WAIT
or TYPED_GATE
or UNKNOWN_RECONCILE
or CEO_RECOVERY_REQUIRED
```

“Invisible work is not healthy work.”

An absent current frontier cannot silently disappear. Conversely, uncertainty cannot be converted into duplicate work.

---

## 20. Completion standard

R8 is not complete when a schema, report, Linear label, Slack message, or Control Room card exists.

It is `PROVEN_LIVE` only when:

- the full current portfolio can be censused through exact current owners;
- known stale/dead project examples are raised correctly;
- legitimate future evidence waits are not falsely resurrected;
- runtime-unknown and duplicate-carrier cases fail closed;
- the existing Improvement Agenda ranks the recovery items;
- accepted Linear/Control Room projections show them without becoming authority;
- optional Slack loss cannot lose or recreate work;
- a genuinely fresh Sol recovers one real dead/unfinished program from the system without Chairman context carriage;
- that Sol can lawfully hand sustained execution to Fable/Executive and later close the recovery item through real proof and durable Agent OS closeout;
- no duplicate lifecycle, queue, identity, memory, grounding, retry, scheduler, parser or truth store was introduced.

---

## 21. Non-goals

R8 does not:

- automatically declare every quiet project dead;
- automatically wake ChatGPT;
- automatically assign Fable from a recovery finding;
- bulk-replay historical Slack commissions;
- create one Linear issue per stale project;
- turn Control Room into an inbox;
- alter provider capacity/routing;
- change product/research promotion authority;
- close proof gates because CI or a PR merge is green;
- replace the active R1 Session Truth carrier;
- change protected `docs/sol_skills/**` in this architecture wave.

---

## 22. Exact next action after written-spec approval

After the Chairman reviews this checked-in spec, invoke the current `writing-plans` workflow and produce a bounded implementation plan that:

1. leaves Mastermind #170/R1 untouched;
2. begins with R8-A after exact R1 contract/current-head reconciliation;
3. separates Mastermind pure classification from Macro Agent OS/Agenda mutations;
4. treats R8-D/E/F as dependency-gated projections rather than first-wave requirements;
5. specifies RED-first tests for every finding and the legitimate-wait/runtime-unknown negative cases;
6. requires a current-estate recovery census and fresh-Sol production canary before final acceptance;
7. records the implementation carrier and continuation in the existing Agent OS/Control Room parent rather than creating a new recovery workstream/control plane.
