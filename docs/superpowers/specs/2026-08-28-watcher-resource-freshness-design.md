# Watcher Resource Discipline + Carrier Freshness — Design

**Status:** DESIGN / records-only; no runtime or source-law behavior is changed by this document.

**Chairman directive:** 2026-08-28. Prevent Fable/Opus/other high-reasoning workers from burning extreme token budgets by hot-polling while preserving reliable Sol↔COO/worker continuation. Incorporate the additional observed failure where an Opus session trusted its armed watcher, failed to reread the Slack carrier, and posted stale state after Sol had already issued multiple rulings.

**Current protected source pin:** `mastermindx-market-intelligence/Mastermind@e53f524230ffc4e8730c844f6fc319d50a2050f3`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap-major 1.

## 1. Outcome

A Fable/Opus/Claude/Codex/Sol session can wait for another agent, CI, or an external condition without:

- repeatedly invoking an expensive reasoning model every few seconds;
- treating an armed watcher as evidence that the carrier has been read recently;
- posting `RESULT`, `BLOCKED`, `CI COMPLETE`, `CONTINUE`, `STOP`, or another substantive dialogue edge against a stale thread;
- stacking redundant watchers for the same side/operation/carrier/purpose;
- manufacturing work on `NO_MATERIAL_CHANGE` wakes;
- creating another lifecycle, queue, cursor, watcher database, retry plane, or memory store.

The long-run runtime owner remains the accepted Worker Presence / Agent Dialogue / Wake architecture. Temporary host-native watchers remain non-authoritative bridges only.

## 2. Incidents and failure classes

### Incident A — hot-poll token burn

Chairman reported a Fable high worker consuming more than one million tokens over roughly 2–3 hours while checking for change at approximately 5–10 second intervals.

This is a resource-governance defect, not merely poor model judgment. Current `COMMISSION_WAVE.md` says a temporary scheduled watcher should use the packet-requested cadence or otherwise the "fastest lawful/practical cadence" the host supports. With no resource floor, that phrase can be interpreted as encouragement to poll as fast as technically possible.

### Incident B — armed watcher substituted for carrier freshness

Chairman supplied an Opus-session receipt in which the worker reported that it posted a CI-complete update without rereading the Slack thread. Sol had already posted multiple rulings/continuations, including an earlier ruling hours before the worker's update. The worker explicitly recognized that it trusted the armed watcher to bring Sol to it instead of reading the carrier itself before speaking into it.

This is a distinct failure. Even a perfectly economical watcher may miss a fire, be delayed, lose connector access, or wake the wrong surface. Therefore **watcher presence can never satisfy carrier freshness**.

The policy repair must solve both classes independently.

## 3. Single-owner architecture

Do **not** create a new parallel watcher-policy source.

`docs/AGENT_DIALOGUE_SESSION_CLOSE_LAW.md` remains the universal source-law owner for watcher-enabled reciprocal dialogue. The implementation wave will amend that law with resource and freshness sections, then make the existing procedural surfaces point to those clauses:

- `docs/sol_skills/COMMISSION_WAVE.md` — commissioning/watch cadence and handoff contract;
- `docs/sol_skills/WATCHER_ACTION_LOOP.md` — Sol wake/re-entry behavior;
- `docs/sol_skills/RECONCILE_STATE.md` — stale/missed watcher reconciliation;
- `docs/sol_skills/INDEX.md` — concise universal hard-law summary;
- repository `AGENTS.md` / `CLAUDE.md` — bootstrap pointer/invariant, not a duplicated policy body.

Agent OS may record the Chairman decision and incident rationale, but the Agent OS record cites the Mastermind source law rather than copying and becoming a second procedure authority.

## 4. Resource classes

The law distinguishes *what is polling* from *how often a command checks*.

### Class E — event-driven / passive wait

A provider/webhook/native event waiter or deterministic blocking tool that does not re-invoke a reasoning model on unchanged state.

Examples: an accepted event subscription; a provider-native waiter; a blocking CI watch process that performs lightweight status reads and only returns control on terminal/material change.

- Preferred whenever available.
- May inspect underlying state at the cadence appropriate to the tool/API because unchanged checks do not re-enter Fable/Opus/Sol reasoning.
- Still subject to API/rate-limit law and one-watcher discipline.

### Class T — tool-only polling

A deterministic process polls but does not invoke a reasoning model on every unchanged sample.

- A 60-second CI/status check can remain lawful where existing repo law permits it.
- The polling process must suppress unchanged samples and return/wake the model only on a qualifying state transition, terminal result, error requiring judgment, or configured coarse heartbeat.
- Tight command polling is never justification for tight model wake cadence.

### Class M — reasoning-model scheduled polling

A Task/Automation/background completion that causes a new Fable/Opus/Claude/Codex/Sol reasoning turn merely to ask whether anything changed.

- **Default interval: 60 minutes.**
- **Absolute minimum interval: 15 minutes** unless a later explicit source-law exception is approved for a named safety-critical condition.
- A requested cadence below 15 minutes must be refused or rounded up; "fastest supported" is not an exception.
- If an urgent Class-M watcher starts at 15 minutes and sees no material change, back off `15m -> 30m -> 60m` and remain at 60m until a material event resets the cycle.
- A `NO_MATERIAL_CHANGE` turn performs one bounded exact-carrier/status delta read and exits. It must not run repo archaeology, broad CI scans, spawn subagents, write summaries, or restate the project.
- Where the surface permits a deterministic or cheaper detection layer, use it for change detection. Fable/Opus/principal reasoning should begin on a material event, not to classify repetitive no-change samples.

**Fable/Opus/high-reasoning models are principals, not polling daemons.** Waiting itself is not principal work.

### External-wait yield boundary

Once the current operation has done all immediately executable work and its only remaining dependency is an external event — another agent reply, CI completion, approval, deployment, scheduled data arrival, or equivalent — the reasoning session must stop issuing iterative status checks. It arms/reuses exactly one approved waiter/watch path and yields the turn.

A live `check -> no change -> wait a few seconds -> check again` model loop is forbidden even if no formal scheduled watcher was created. This closes the loophole where hot polling is performed manually inside one long principal session rather than by a Task/Automation.

## 5. One-watcher discipline

For one side of one reciprocal dialogue, there may be at most one active watcher for the same:

`side + operation_key + exact carrier + purpose`.

Sol and the worker may each have one watcher because they are different sides. A CI watcher and a Slack-return watcher may coexist only when their purposes/endpoints are genuinely distinct; two watchers observing the same condition are redundant and forbidden.

Before arming a watcher, the session checks whether an equivalent active watcher already exists on the current surface. If it does, reuse it rather than stacking another wake source.

This is attention/resource discipline only. It creates no durable watcher registry or new lifecycle store.

## 6. Read-before-write carrier freshness fence

This is the principal amendment required by Incident B.

The current pickup handshake may continue to send the minimal pickup `ACK` before the required full-thread read when the controlling commission law explicitly requires that order. The ACK proves receipt/context only and must not assert substantive gate, execution, result, or completion state.

Before sending any **substantive/stateful** message into a reciprocal carrier — including `START`, progress that asserts a gate changed, `BLOCKED`, `DECISION_REQUEST`, `RESULT`, CI/proof completion, `CONTINUE`, `RULING`, repair, `PARK`, or terminal `STOP` — the sending session must:

1. **Fresh-read the exact bound carrier/thread in the same interactive turn.**
2. Perform that read **after the latest local evidence-producing action** that the outbound message is about. A thread read from before a long CI run, code review, background task, sleep, or watcher interval is stale for the later post.
3. Compare against the latest consumed baseline and identify any unseen opposite-side messages.
4. If an unseen opposite-side semantic edge exists, adjudicate/consume it before composing the outbound message. Do not post the pre-existing local conclusion first and "catch up" afterward.
5. Only then send the substantive message on the same lawful carrier.

An armed watcher, `WATCH_ARMED` receipt, absence of a notification, local memory, or "I would have been woken if Sol replied" **never satisfies this freshness fence**.

If the carrier cannot be freshly read, the session must not make a stale state assertion. It reports the existing accepted transport/read blocker when possible and preserves the current operation without blind retry/failover.

This fence is deliberately stronger than "reread after receiving a Sol continuation." It applies before the worker speaks substantively into the carrier even when the watcher never woke it.

A same-turn read/write sequence is not falsely described as atomic. Another message can still arrive in the network race after the read and before the write. Future managed transport may close that race with a version/baseline precondition, but until then the procedure supplies the strongest truthful freshness fence available without inventing transactional guarantees.

## 7. Missed-fire / degraded-watcher behavior

A watcher is a best-effort attention mechanism, not proof that no reply exists.

On any interactive resume, before relying on watcher silence, compare elapsed time with the watcher receipt's actual cadence when that information is available. If multiple expected Class-M fire opportunities have passed with no observed watcher run/wake while the dialogue remained nonterminal:

- treat the watcher as **degraded evidence**, not as proof of no change;
- immediately perform the read-before-write carrier freshness check before any substantive post;
- do not shorten the cadence to compensate;
- repair/re-arm at the resource-safe cadence if the current surface can do so, or return the currently accepted watcher-unavailable/degraded blocker without inventing a new lifecycle state.

No new canonical runtime status enum is created by this design. A human-readable degraded diagnosis is sufficient until the accepted Worker Presence / Turn-Watcher owner defines a machine contract.

## 8. `NO_MATERIAL_CHANGE` quiescence

A scheduled wake with no qualifying new event is a quiescent path:

`WAKE -> one bounded delta read -> NO_MATERIAL_CHANGE -> exit`

It must not:

- re-run the full Skillpack archaeology merely to rediscover that nothing changed;
- repeatedly fetch full thread history when the connector supports a bounded baseline read;
- poll CI plus Slack plus GitHub plus Agent OS "just in case";
- emit long prose to the Chairman;
- create another watcher if one remains active;
- renew authority, retry work, merge, fail over, or advance lifecycle state.

When a model-owning watcher does observe a qualifying return, normal current-Skillpack re-pin and adjudication applies before modification.

## 9. Commissioning contract repair

The implementation must remove/replace the ambiguous phrase in `COMMISSION_WAVE.md`:

> use the fastest lawful/practical cadence the host actually supports

with a resource-safe rule derived from Section 4.

Every future `WATCH_ARMED` receipt should continue to state the actual cadence. Handoffs that request a model-wake cadence below the universal floor are invalid and must be normalized/refused rather than obeyed.

For CI or another condition with an available Class-E/Class-T waiter, commissions should prefer that deterministic waiter over a recurring premium-model Task. For Slack reciprocal dialogue while no production event-driven path exists, the temporary Class-M bridge uses the 60-minute default or a justified 15/30/60 bounded backoff.

The commission must also state that **watcher silence does not satisfy the carrier freshness fence** and that a worker returning from local work must reread the exact thread before a substantive post.

## 10. Propagation / "Fable memory"

Account-local Claude/Fable chat memory is not the company memory mechanism. The durable propagation path is:

1. merge the universal Mastermind source-law amendment;
2. update Mastermind `AGENTS.md` and `CLAUDE.md` with a concise mandatory pointer/invariant;
3. record one Agent OS `DEC:` in Macro containing the Chairman ruling, incidents, source-law citation, and rollout state;
4. after reconciling the currently open Macro ship-loop watcher PR #6381 (which already modifies Macro `AGENTS.md`/`CLAUDE.md` and implements specialized one-watcher/quiescence behavior), amend current Macro `AGENTS.md` + `CLAUDE.md` without overwriting that work;
5. after the source law is merged, use a one-time Slack visibility broadcast/targeted continuation to already-running Fable/Opus/COO sessions so they reread the merged law and re-arm any violating watcher. Slack is transport only; the merged law remains authority.

Fresh sessions then inherit the rule from repository instructions; active sessions receive a transport nudge rather than relying on inaccessible account-local memory.

## 11. Relationship to Macro PR #6381

Macro #6381 is open and currently owns specialized ship-loop watcher quiescence/one-watcher changes in `.claude/hooks/ship_loop_guard.py`, `scripts/ship_loop_hold_wrapper.py`, Macro `AGENTS.md`/`CLAUDE.md`, and related tests/Agent OS records.

Do not duplicate or overwrite its specialized runtime mechanism.

The universal policy is broader and transport-agnostic. Implementation should:

- land the Mastermind source-law change independently;
- reconcile #6381 before editing the same Macro instruction files;
- reuse #6381's proven one-watcher/quiescence concepts where compatible;
- leave CI ship-loop runtime ownership with the existing Macro guard;
- leave reciprocal Sol↔worker turn continuation with Worker Presence / Agent Dialogue / Wake.

## 12. Mechanical enforcement roadmap

Policy alone is insufficient long-term. After the source-law amendment is accepted, bounded implementation waves should extend existing owners rather than create new daemons:

1. **Watcher creation guard:** where the accepted host/watcher creation surface is controllable, reject Class-M schedules below 15 minutes and duplicate equivalent watchers.
2. **Deterministic transition filter:** move frequent Class-T reads below the reasoning layer so unchanged samples do not wake Fable/Opus/Sol.
3. **Carrier-freshness guard where feasible:** before a managed substantive dialogue write, require a same-turn exact-carrier read/baseline check or return a typed transport/freshness refusal. If the connector cannot support atomic read-then-write, preserve the procedural fence rather than inventing a false transaction guarantee.
4. **Observability:** expose watcher kind (`event`, `tool_poll`, `model_poll`), actual cadence, last successful read, and duplicate/coalesced/refused counts through the existing telemetry/control-room owners. Observability is not lifecycle authority.
5. **Production proof:** demonstrate an unchanged 2–3 hour wait with bounded model re-entry/token use, a material reply waking the correct side, a deliberately missed watcher fire still caught by read-before-write, and terminal STOP disarming the temporary watcher.

## 13. Acceptance matrix

The source-law implementation is acceptable only if all of the following are explicit and non-contradictory:

- 5–10 second Class-M polling is forbidden.
- a principal session whose only remaining dependency is external yields instead of live-polling.
- 60 minutes is the normal model-wake default; 15 minutes is the hard floor.
- urgent no-change Class-M waits back off 15→30→60 minutes.
- fast tool-only/event-driven checks remain possible without premium-model re-entry on every sample.
- a cheaper/deterministic change detector is preferred when the surface allows it.
- one active watcher per side/operation/carrier/purpose.
- the minimal pickup ACK remains compatible with the current ACK-before-read handshake and carries no substantive state claim.
- every later substantive carrier write is preceded by a fresh same-turn carrier read after the latest evidence-producing action.
- watcher silence never proves carrier freshness.
- missed watcher fires trigger direct carrier reconciliation, not faster polling.
- `NO_MATERIAL_CHANGE` is a cheap quiescent exit path.
- STOP/shutdown/new-wave laws remain unchanged.
- no Job/Attempt/Worker/queue/cursor/retry/memory authority moves into watcher infrastructure.
- Macro #6381 is reconciled rather than overwritten or duplicated.

### Discriminating incident replays

The implementation/proof plan must include at least these negative controls:

1. **Hot-loop replay:** a proposed Class-M 5–10 second watcher or repeated in-session polling loop is refused/normalized; no expensive reasoning loop occurs.
2. **No-change replay:** an unchanged 2–3 hour wait causes only bounded delta checks/model wakes under the defined cadence/backoff and does not perform broad archaeology.
3. **Stale-thread replay:** worker reads thread, performs/awaits local CI, Sol posts a ruling during that interval, then worker attempts `CI COMPLETE`; the required fresh post-CI carrier read exposes Sol's unseen ruling before the worker can post its stale conclusion.
4. **Missed-watcher replay:** the scheduled watcher intentionally fails to wake across multiple expected opportunities; when the session next becomes interactive, it treats watcher silence as degraded and directly rereads the thread instead of asserting no reply.
5. **Terminal replay:** Sol STOP leaves the child terminal and the temporary watcher disarmed; no leftover wake originates a next wave.

## 14. Capability-state honesty

This design is `SPEC_ONLY`.

Writing/merging this design does **not** make current Fable sessions resource-safe, does not change any existing watcher cadence, does not prove a host can enforce the floor, does not repair the Opus session that already missed Sol messages, and does not make the Worker Presence / Turn-Watcher path production-live.

The first real capability delta occurs only when the source law and shared bootstrap instructions are accepted and active sessions are repinned; mechanical enforcement and production proof remain later bounded waves.