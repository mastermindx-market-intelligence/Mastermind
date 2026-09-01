# Operator Continuity — Fable Root/Seat Continuity Amendment

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This resolves how sustained Fable/COO responsibility maps onto the already-accepted Phase 1F-C Job/Attempt/role law. No Job, Attempt, Worker, provider session, Slack message or production capability is created by this record.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Protected Mastermind / Skillpack basis:** `af43f356f4f7f34cb3514d1d1099b50444af8487`, `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1.  
**Parent architecture:** `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`  
**Existing law preserved:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`; Phase 1F-C orchestration role/cardinality law.

## 1. Problem resolved

The hybrid-workforce architecture says Fable is the sustained COO/program-owner surface across many bounded waves. Phase 1F-C, however, deliberately constrains every orchestration Attempt to one provider session, at most one same-session resume, and at most two provider work-turn calls under the closed G1/G2 recovery law. The accepted orchestration-role vocabulary remains exactly:

```text
plan | work | review | repair | aggregation
```

Creating a durable `fable_session`, `coo_operator`, or sixth orchestration role merely to retain a Claude conversation would violate the no-rebuild law and the existing role contract.

## 2. Ruling — Fable continuity lives above a provider session

**Fable is the logical COO responsibility for a root program, not one provider-native conversation and not a new Job role.**

The stable logical identity is derived from existing accepted identities:

```text
root_job_id
+ target_seat = coo
+ root-specific logical session_alias / company-dialogue session
+ accepted commission / operation context
```

Human-visible presentation may remain:

```text
Mastermind · Fable
```

The runtime episodes beneath that logical responsibility are ordinary accepted Executive Jobs/Attempts using existing Phase 1F-C roles and Operator Harness modes.

Conceptually:

```text
FABLE / root JOB-R
        |
        +--> plan Job P / Attempt P1 / Claude realm A / provider session S1
        |      rate-limited before candidate
        |      -> same plan Job requeued
        |      -> Attempt P2 / Claude realm B / new provider session S2
        |      -> plan completes
        |
        +--> work/review/repair child Jobs on governed workers
        |
        +--> aggregation Job A / bounded COO Attempt
        |
        +--> later attention episode / next bounded Executive work
```

Fable's company responsibility survives all of those provider sessions. No provider transcript is the durable program memory.

## 3. Cross-realm rollover inside an orchestration Job

Phase 1F-C already permits `max_attempts_per_orchestration_job=2` for non-review orchestration Jobs. Operator Continuity uses the existing adverse-Attempt/requeue mechanism; it does not widen this ceiling.

A first production Fable rollover can therefore prove:

```text
same root Job / same plan Job
Attempt 1 on claude-pro-A
-> exact pre-candidate quota/rate-limit terminal state
-> same Job requeue under existing law
Attempt 2 on claude-pro-B
-> fresh provider-native session
-> continuation capsule binds P1 -> P2
-> plan result completes through existing Phase 1F-C result law
```

The second Attempt is not a same-session resume. It receives a new provider session and a deterministic continuation capsule containing only the canonical state the new Attempt is allowed to consume.

### 3.1 Retry is not guaranteed

The numeric Attempt ceiling is a maximum, not automatic retry permission. Requeue is allowed only when existing Executive state/reconciliation and Phase 1F-C lineage rules say it is lawful.

`EFFECT_UNKNOWN`, an existing candidate/result, an invalid provider writer state, exhausted Attempt limit, cancelled root, stale plan phase, or another current-lineage conflict can stop continuation before Attempt 2.

## 4. Same-realm sustained session remains an execution optimization

OCR-4 may prove multiple safe turns or same-session process recovery inside one ordinary/rich Operator Harness Attempt where the current contract permits it. That does not redefine Fable's organizational identity and does not widen the Phase 1F-C orchestration turn/cardinality law.

For Phase 1F-C role Attempts, current G1/G2 limits remain exactly as accepted. A future need for more same-Attempt role turns requires its own architecture amendment and cannot be justified merely by calling the provider session “Fable.”

## 5. Slack/dialogue continuity

Worker Presence/Agent Relay binds the company dialogue to the root commission/session context, not to one provider Attempt.

The logical thread may show:

```text
Mastermind · Fable
  plan attempt P1 started on realm A
  P1 rate-limited / reconciled
  runtime rebound: plan attempt P2 on realm B
  P2 ACKed continuation capsule
  plan completed
```

The exact Worker-attempt `actor_ref` changes for worker-origin machine frames when the Attempt changes. The human-visible Fable company actor and immutable dialogue parent/root context do not.

Slack does not create P2 or select realm B.

## 6. Wake relationship

Wake targets the current logical COO session/root binding and current RuntimeBinding projection. Same-session Wake may revive the exact current Attempt/provider session. A cross-realm replacement is first an Executive requeue/new claim; only after the new Attempt/provider session is bound does Wake/Control Room point at that new runtime.

Wake never performs the realm change itself.

## 7. Continuation capsule scope

For a Phase 1F-C retry, the continuation packet must be **role-specific and phase-safe**. It may include:

- root Job identity and current role Job identity;
- source/target Attempt IDs;
- immutable plan/root/role lineage fields already present on the Job;
- prior terminal Attempt checkpoint/error classification;
- effective grant / placement source refs;
- current source-law/GitHub/Agent OS/dialogue refs;
- exact next action.

It may not smuggle an unaccepted plan candidate, model-private transcript or source Attempt work product that existing Phase 1F-C would not permit the retry to consume.

For a pre-candidate rate-limit plan retry, the safe continuation material is the immutable root/plan Job contract plus any explicitly accepted checkpoint. If Phase 1F-C says the adverse Attempt produced evidence that closes the retry path, Operator Continuity must preserve that refusal.

## 8. No-rebuild implications

Do not create:

- a `fable_sessions` table;
- a `fable_job_id` parallel to root Job;
- a durable `coo_operator`/`fable` orchestration role;
- a provider conversation transcript as organizational memory;
- a Slack-owned Fable lifecycle;
- a new Attempt-retry rule just for Claude/Fable.

Existing root Job, seat/session alias, Agent OS organizational state, Executive Attempts, Operator Harness provider sessions, Slack dialogue and GitHub evidence compose the capability.

## 9. Acceptance implication

The first cross-realm Fable canary should use a real/fixture-valid **existing orchestration role with current retry law**, preferably a pre-candidate `plan` Attempt because its retry boundary is clean and easy to falsify. It must not relax the G1/G2 turn cardinality or create a role-null surrogate merely to avoid Phase 1F-C laws.

A later full program canary proves the same logical Fable root/thread persists from planning through worker fan-out, decision dialogue, aggregation and final return even though many provider-native sessions/Attempts may have come and gone underneath it.
