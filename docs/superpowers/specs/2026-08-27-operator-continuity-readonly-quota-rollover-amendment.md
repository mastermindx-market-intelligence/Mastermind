# Operator Continuity — V1 Automatic Quota Rollover Is Read-Only Only

**Date:** 2026-08-27  
**Owner:** Sol, AI CEO  
**Status:** **ARCHITECTURE AMENDMENT / RECORDS ONLY.** This closes a work-effect safety gap found during Sol adversarial review of OCR-5.  
**Operation key:** `operator-continuity-realm-rebinding-20260827-sol-001`  
**Current protected review basis:** `65d5f07eb7667304c50c9673c61b9a0a6b95d3f3`, compatible Skillpack v1.0.0 / bootstrap major 1.  
**Affected plan:** `docs/superpowers/plans/2026-08-27-operator-continuity-ocr5-cross-realm-rollover.md`  
**Existing law preserved:** Phase 1F-C authority/effective-grant, Operator Harness effect-unknown/reconcile, Executive Attempt terminal/requeue law.

## 1. Defect found

OCR-5's first draft allowed a reconciled `QUOTA_OR_RATE_LIMIT` provider failure with no final candidate/result to terminalize the current Attempt and permit same-Job requeue. For a write-capable operator turn, absence of a final candidate is not proof that no local or external work effect occurred. Tools may have modified the worktree or another authorized target before the provider hit a quota boundary.

Automatically treating that state as retryable on another provider/account could duplicate or conflict with a real modification even if no provider result envelope exists.

## 2. Frozen V1 ruling

**Automatic quota-driven cross-realm rollover is permitted only for an Attempt whose effective grant is provably non-modifying.**

For the first V1 Fable rollover canary, require an existing read-only operator role/grant, preferably Phase 1F-C `plan`, with effective authorities no wider than the currently accepted read-only planner ceiling.

The terminalization/requeue safety predicate must re-derive from canonical Executive evidence that the Attempt had:

```text
no WRITE_BRANCH or other modifying authority
no allowed write paths
no modifying MCP/native helper/browser/computer capability
no external mutation capability in the accepted profile
no unreconciled OPERATOR_OPERATION_EFFECT_UNKNOWN
provider generation PROVEN_DEAD
ProviderWriterState.RELEASED
no candidate/result/seal that closes the accepted retry path
attempt limit remaining
current Phase 1F-C lineage still retryable
```

Only then may a provider `QUOTA_OR_RATE_LIMIT` be converted through the existing `rate_limit_attempt()` -> same-Job `requeue_job()` path.

## 3. Write-capable Attempt behavior

For any write-capable or otherwise modifying Attempt, a quota/rate-limit after provider work begins is **not automatically retryable across realms in V1**.

Required behavior:

```text
provider quota/rate-limit
-> stop/reconcile exact current generation/turn
-> preserve current Attempt/workspace/effect evidence
-> BLOCKED / reconciliation-required unless existing canonical result/checkpoint law proves a safe terminal outcome
-> zero cross-realm claim from Operator Continuity
```

A later architecture may define exact workspace/effect checkpointing that makes some modifying retries safe. This approval does not invent that capability.

Ordinary sealed-worker retry/repair law that already has its own accepted result/effect semantics is not broadened or replaced by this amendment.

## 4. Why this still satisfies Fable continuity

Fable's durable responsibility is root Job + COO seat + logical company session, not one write-capable provider turn. The intended first cross-realm proof uses the read-only Fable planning/coordination surface; implementation mutations remain bounded child Jobs under their existing lifecycle/review/repair rules.

Thus the company can prove that Fable survives Claude account exhaustion without granting a generic "repeat any interrupted modification on another account" mechanism.

## 5. OCR-5 plan corrections

The OCR-5 provider-failure terminalization classifier must include the exact effective-grant/capability evidence required to establish `NON_MODIFYING_ATTEMPT`.

Supersede any OCR-5 wording that suggests these conditions alone are sufficient for cross-realm requeue:

```text
QUOTA_OR_RATE_LIMIT
+ writer dead/released
+ no final candidate
+ no EFFECT_UNKNOWN
```

The additional non-modifying authority/capability predicate is mandatory.

Required tests:

1. read-only `plan` Attempt + safe quota failure -> may terminalize RATE_LIMITED and requeue;
2. same state but `WRITE_BRANCH` present -> refuse rollover;
3. same state but non-empty allowed write paths -> refuse;
4. modifying MCP/browser/native-helper capability present -> refuse;
5. no obvious file diff but write grant existed -> still refuse; absence of observed diff is not enough;
6. effect unknown -> refuse regardless of read-only classification until reconciled.

## 6. Final product language

Control Room/Steward must not display `REBINDING` or `WAITING_FOR_REPLACEMENT` for a write-capable quota-failed Attempt unless a separate accepted safety law has made it rollover-eligible. It should display `RECONCILIATION_REQUIRED`/`BLOCKED` truthfully.

## 7. No-rebuild proof

This amendment adds no workspace journal, mutation log, retry table or checkpoint database. It deliberately **shrinks** V1 automatic rollover to the subset current canonical evidence can prove safe.
