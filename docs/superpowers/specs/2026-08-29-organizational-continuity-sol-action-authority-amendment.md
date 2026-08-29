# Organizational Continuity — Multi-Watch / Single-Action-Authority Amendment

**Date:** 2026-08-29  
**Owner:** Sol, AI CEO  
**Chairman:** Chris  
**Parent operation:** `mastermind-operating-surface-continuity-incident-amendment-20260828-sol-001`  
**Canonical carrier:** Mastermind PR #214, same branch as closed metadata-only predecessor #211  
**Current protected re-pin:** `Mastermind@613fcc9176cb93a93734540fbd43ce8d8a13d417`, Skillpack `mastermind.sol_skillpack.v1` v1.0.1 / bootstrap major 1  
**Authority:** narrow same-carrier amendment requested by the Sol architecture review of #211 and explicitly approved by the Chairman. For watcher cardinality, exact Sol action authority, transfer/recovery and conflict behavior, this amendment wins over the earlier two #214 specs.  
**Capability state:** `SPEC_ONLY`. No watcher/runtime/session/owner registry, lifecycle, Wake obligation, Slack message, provider session, queue, database or production behavior is created here.

## 1. Multi-watch scale law

One Sol reasoning/session target may maintain and supervise many simultaneous watcher/action loops for **different** operation keys.

The architecture must never imply:

```text
one Sol session = one watcher
one watcher = one dedicated Sol account
```

A single action-authoritative Sol surface may therefore supervise a portfolio of disjoint child operations concurrently, subject to normal context/resource limits and watcher resource-discipline law.

Multiple operation-scoped temporary watchers owned by one Sol are lawful transition scaffolding. The prohibition is against duplicate semantic/action ownership or a second watcher control plane, not against portfolio-scale observation.

## 2. Per-child semantic action exclusivity

For one current child operation and one unresolved semantic turn, **exactly one CEO/Sol target is action-authoritative at a time**.

Other Sol surfaces may read, observe, project health, assist with read-only reconciliation, or provide advisory analysis. They may not independently emit or authorize for that child:

```text
CONTINUE
RULING
REQUEST_REPAIR
STOP
merge / release
retry / resubmit
successor commission
another modifying semantic edge
```

The exclusivity boundary is per child/semantic turn, not per Sol session.

## 3. Reuse existing identity/binding owners

Do not add a `sol_owner` table, watcher registry, action-owner database or sister-Sol election service.

Exact action targeting must resolve from the already-accepted responsibility/session/runtime binding owners appropriate to the current operation, including existing responsibility/root-job/workstream binding, SessionTargetRegistry/accepted successor, RuntimeBinding and current dialogue applicability evidence.

Human-facing:

```text
turn_owner = SOL
```

means the **Sol role** owes the next semantic turn. It does not mean any available ChatGPT account or Sol tab may act.

Control Room / Steward should separately expose the exact currently resolved action target when that source is available, and `UNKNOWN` when it is not.

## 4. Transfer / recovery law

If the currently action-authoritative Sol target is unavailable, degraded, context-exhausted or intentionally retired, another Sol surface may become action-authoritative only after the existing responsibility/session binding is canonically reconciled/transferred.

Never elect a replacement from:

- newest active Sol tab;
- newest Slack responder;
- apparent browser responsiveness;
- provider/account quota guess;
- most recent screenshot;
- title similarity;
- whichever sister Sol happens to notice first.

If a prior modifying Sol edge is `EFFECT_UNKNOWN` or its ownership/commit state is ambiguous, silent action-target transfer is blocked until that same operation is reconciled.

A context-rotation transfer must preserve the logical Sol responsibility and operation identity while changing only the allowed reasoning-surface binding.

## 5. Conflict behavior

Before divergent semantic edges exist, two simultaneously action-authoritative Sol bindings for the same current child/turn are a derived attention defect:

```text
ATTENTION_OWNER_CONFLICT
```

This is not a lifecycle state.

Required behavior:

```text
fail closed
-> no semantic modification by an observer
-> reconcile exact responsibility/session binding
-> never elect by timestamp recency
```

If competing valid semantic leaves have already been written, existing Agent Dialogue fork/conflict law such as `DIALOGUE_FORKED` remains controlling. This amendment does not create a replacement conflict resolver.

## 6. Parent continuation belongs to responsibility, not watcher identity

Terminal child STOP closes that child's reciprocal watcher cycle only.

If the parent remains active and no successor exists, `PARENT_ACTIVE_NO_SUCCESSOR` re-enters the accountable Sol responsibility even when the same Sol surface is simultaneously supervising many other child operations.

This creates attention only. It never auto-starts a successor and never lets an old child watcher authorize the next child.

## 7. Web-Sol / Grok / OpenClaw consequence

The new Web-Sol exact-surface adapter may health-check or foreground only the **already-resolved action-authoritative Sol surface** for the relevant responsibility.

It must not use browser state to elect a Sol owner.

Grok Secretary may explain that Sol attention is owed and may request an approved exact-surface action, but it may not choose between competing Sol sessions.

OpenClaw likewise may operate only on one already-resolved exact target. No "wake newest Sol" or "pick another healthy tab" fallback is permitted.

## 8. Acceptance canaries

### Positive portfolio canary

One Sol reasoning surface supervises at least three disjoint watcher-enabled children concurrently.

For each child prove independently:

```text
exact operation key
correct latest worker/COO return
one correct Sol action edge
watcher remains operation-scoped
one child's STOP does not disturb the other children
no duplicate Job/Wake/semantic edge
```

### Adverse sister-Sol canary

Two Sol surfaces observe the same worker return.

Prove:

```text
both may read/observe
only canonically resolved action target may act
observer cannot CONTINUE/RULING/STOP/merge/retry/commission successor
no duplicate semantic edge
no duplicate Wake
no duplicate Job
```

Then deliberately make the authoritative Sol surface unavailable and prove that another Sol cannot act until the existing binding is reconciled/transferred.

### Conflict canary

Inject conflicting active Sol ownership before any divergent semantic edge and prove `ATTENTION_OWNER_CONFLICT` / equivalent fail-closed projection. Timestamp recency must not elect a winner.

## 9. Completion boundary

Merge of the #214 records carrier makes this action-authority law durable only.

It does not make multi-watch runtime enforcement, exact Sol targeting, Web-Sol wake, Worker Presence/Wake, OCR-6 Steward or zero-touch operation live.

Implementation must extend existing responsibility/SessionTargetRegistry/RuntimeBinding/Agent Dialogue/Wake owners and must not create a second ownership or watcher control plane.
