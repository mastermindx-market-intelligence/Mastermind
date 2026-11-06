# Fabric account balancing and request-queue composition — 2026-10-14

Operation `fabric-routing-deep-audit-20261013-c2-001`; same PR #1443 and branch. Compatible protected procedure pin: `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`. **SOURCE CANDIDATES / NOT INSTALLED / MISSION INCOMPLETE.**

## Outcome advanced

The continuation completed a source repair for raw account-occupancy bias, preserved the existing GLM expiry preference, and checked its composition with the new request-local queue repair. The two changes use the incumbent broker, request/run identity, lease history and root fairness; they create no new queue, account registry, quota owner, routing service or execution grant.

A source candidate now chooses among already-grantable accounts by the maximum of total-account utilization and target-model utilization. It then uses least-recent grant from the same pool's existing lease history, followed by capacity and name for deterministic residual ties. A binding model cap therefore matters even when total account occupancy is low. Otherwise equivalent sequential idle accounts rotate instead of permanently favoring one account name or capacity.

Example reproduced in the tests: one held job on a two-slot account no longer beats two jobs on a twelve-slot account merely because one is less than two. A separate model-cap test distinguishes account room from target-model room. This is a capacity-aware ranking heuristic, not a measured fleet-wide savings result or proof of globally optimal cost/latency.

### Boundaries preserved

Explicit account pinning still returns the pinned eligible account or refuses; it never silently falls back. Full account or model capacity still excludes an account. The host-compatible `grantable_override` subset is never expanded. #1365's qualified GLM expiry preference and earlier-reset ordering stay ahead of utilization. The existing `_fresh_glm_expiring_accounts` implementation remains owned by #1365; these tests supply synthetic eligibility maps and do not claim to requalify its provider observations.

Account ranking itself performs no database writes. Existing atomic claim, original-root fairness, authorization, model/host compatibility, lease settlement and original-parent return remain their existing owners' responsibilities.

## Additional defect caught in the new queue candidate

Composition review led to a discriminating repeated-clock test. Updating a scoped request's priority or host at the same timestamp as another waiter reset the timestamp but retained the old SQLite rowid, allowing it to keep an earlier FIFO position. Two tests failed the initial new request candidate.

The correction reinserts only that exact scoped demand under the incumbent lock when its demand shape changes. This refreshes its insertion order even when the clock repeats. Unchanged heartbeats retain their original position, sibling rows remain intact, and the stable request correlation does not become execution idempotency. The request behavior patch and its manifest now contain this correction; the old 49-test file is byte-identical, with the two new regressions in `tests/test_native_fabric_requeue_clock_ties.py`.

## Verification and evidence scope

The complete independent source workspace's five test files pass: **89 passed, zero failed**.

| Suite | Passed | Scope |
|---|---:|---|
| Request-local waiter lifecycle and launcher wiring | 49 | Real synthetic SQLite; exact source-method/wiring patches; no provider or native broker launch |
| Requeue with equal timestamps | 2 | Priority/host changes cannot preserve stale FIFO credit |
| Normalized account/model utilization | 30 | Already-eligible account choice, pins, caps, same-pool history and preserved expiry precedence |
| Legacy queue compatibility | 1 | 3,750 internal unscoped priority/FIFO comparisons against the new method |
| Patch composition | 7 | One assembled source-backed Broker fragment, both patch orders and unchanged root-accounting methods |

The account baseline was **15 failed / 15 passed**. The request baseline with the two new clock cases was **45 failed / 6 passed**. Internal matrices include 400 account-capacity combinations and 2,250 scoped request FIFO decisions; those are inside, not additional to, the reported test counts. Thirty-two sibling requests were tested using eight local test threads under an explicit single-writer lock, not native workers or a distributed-runtime proof.

The composition test applies both published patches to the same source-backed method fragment in either order; the resulting bytes are identical. AST comparisons preserve `_active_orchestrators`, `fair_share` and `_register_demand`. Synthetic combined tests verify that account selection neither modifies demand nor widens host-compatible accounts, and that completing one queued request leaves its sibling queued while original-root accounting is conserved.

Verified composition test blob: `40107f0e63f20cb40ac140ac307625a3b59b6b5b`.
Final request patch blob: `33eb8ce7f95b7b042b365471dac8bc8c3b737248`.
Final combined method-fragment SHA256: `a0a2068ee050c806307f50f5f92646eb2ec28acc11c2d8f637e647504ea6309a`.
Exact source/test file hashes and reviewed dependency identities are in the package manifests. They are not installed full-file postimages.

**Do not conflate scopes:** the original native test-preparation/host-inspection refusals remain intact. The original first-phase result is still **49 passed / one disclosed GLM fixture failure**, and its complete native regression is still unqualified. The earlier 31-test sibling-priority method proof remains separate. This new 89-test result does not combine with or replace those results, qualify a full native broker, finish independent review, or authorize installation.

## Source packages and integration order

- `request_waiters/request_waiters.patch` and `request_waiters/request_waiters_wiring.patch`: use after #1443's original logical-priority and sibling-priority amendments. Broker and launcher must be qualified together, including any external broker override.
- `account_balance/normalized_account_balance.patch`: use after #1365's existing GLM-expiry account-selector change; preserve its helper, host/account subset and original native source writer.
- `tests/test_native_fabric_routing_patch_composition.py`: verifies the new method changes commute on the source-backed fragment. This is not permission to sequentially install separate stale whole-file manifests.

The fragments are development/review fixtures and must never be installed as native source. Actual acceptance requires a current full-file owner to reconcile these changes with #1365 selector/expiry, #1441 V4 quota cache, #1391 current native admission/process/cleanup source, and the applicable #1248 TaskFit and #1254/#1228 role-policy changes. Do not copy or redo their algorithms, transfer their custody, or replay their refusals.

## Remaining frontier

The next release-critical work is exact-source independent review and permitted current-native integration/verification. The existing review request is not a running worker or a returned review. This continuation made no host-inspection retry, provider/worker launch, account/credential/quota/lease change, service restart, installation, merge or autonomous-wake claim. All source modifications have acknowledged GitHub commits; no effect is unknown. The old managed M2 workspace remains behind the remote branch and must not overwrite it.

Account/model-aware head-of-line blocking remains open: the waiter data does not yet carry sufficient model-specific eligibility for safe bypass of an ineligible head. Strict request FIFO may also expose such blocking between siblings; do not label that solved by demand isolation. Effective pool scoring/preference configuration and quality-confidence/cold-start policy also remain open. Those changes must use the actual current suitability, evidence and admission owners rather than an unverified rewrite from older snippets.

The best next executable dependency is review/integration of this tested source against the accepted native generation once the real source/action gates permit. The original GLM fixture and complete native regression, exact-head CI, protected acceptance, coordinated installation and a useful original-parent execution/return still determine production completion. Source success is not production success.
