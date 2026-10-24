# Fabric request-local queue repair — 2026-10-14

Operation: `fabric-routing-deep-audit-20261013-c2-001`. Same PR #1443 and source branch. Protected procedure pin remains `76576d8680bb70cdb9e1cfe7016aefec0fb3286f`.

## Result

The highest-value independent continuation was the remaining F08 request-demand conflation. The source-backed broker coalesced waiters by `(orchestrator_id, pool)` and cleared every waiter for that pair after one success. The earlier priority-isolation patch prevented borrowing a different-priority sibling's position, but could not distinguish same-priority siblings or protect their demand from overwrite/cleanup.

This continuation adds two inert source patches to the incumbent broker/launcher, not another runtime queue:

- Optional `request_id` creates one stable waiter correlation from original root, canonical pool and the existing run ID. It creates no identity authority, root budget, lease, credential or at-most-once execution guarantee.
- Scoped enqueue/refresh addresses only that request. Distinct siblings preserve their class, host/account demand and heartbeat. A changed priority or resource-demand shape requeues rather than inheriting an earlier FIFO position.
- Successful admission removes only the exact scoped waiter. Legacy calls retain legacy grouping but cannot overwrite, erase or borrow scoped demand.
- Request-level FIFO distinguishes siblings even at the same priority. Equal timestamps use insertion order. The existing distinct-root fair-share calculation and stale-demand heartbeat predicate are unchanged.
- A legacy ID collision no longer uses INSERT OR REPLACE to delete another root's row.
- The existing remote launcher forwards `--request-id "$ID"` at all three acquisition paths while retaining `remote-$MODE`, logical job class, original root, operator-child ID, model, host and existing TTL.

The mechanism does not fix account/model head-of-line eligibility. A waiter still lacks enough model-specific eligibility information for that separate repair. Do not claim all F08 behavior or the full routing mission complete.

## Verification

Final source-backed suite: **49 passed, zero failed**. The corresponding before-decision/identity paths produce **43 failures and six passes**. Test file: `tests/test_native_fabric_request_waiters.py`.

Within those 49 tests are 2,250 request-level priority/FIFO decisions and 32 sibling requests exercised by eight local test threads under an explicit single-writer lock. Root accounting stays based on distinct original roots; siblings do not multiply fair-share capacity. Real SQLite tests cover sibling retention, refresh, exact success cleanup, unqueued success, legacy/scoped mixtures, wrong-scope cleanup, malformed identities, same-name different-root/pool identities, requeueing and stale demand.

The wire tests apply the actual published patch to reviewed source fragments, invoke the amended identity-validation block, and execute only the isolated launcher acquisition block with an argv recorder. They launch no provider, SSH, native broker, real lease or worker. Tests confirm original root and child IDs, job/transport classes and TTL. Structural tests include native method indentation, the intervening `_register_demand` method, 600/800-line offsets and nonblank omitted-source separators.

The first draft's legacy replacement and two source-packaging assumptions were caught and corrected before publication. Tests do not rely solely on a dedented function that cannot be spliced into native source.

**Scope limit:** reference material comprises immutable repository-backed broker excerpts, plus the prior #1443 logical/sibling-priority amendments. It is not a reconstructed or current installed full broker. The original native test-preparation/host-inspection refusals were not retried. This independent source suite does not repair, replace or relabel the original 49-pass/one-failure native fixture result, and is not a full native regression or production proof.

The five source/test artifacts at commit `4d0cf489ff2a05e37c564c34cbd583ca417a8af4` matched the locally tested Git blob identities exactly. The package manifest records SHA256s, source references and release gates. This is reproducible source evidence, not an install receipt.

## Integration contract

Package: `ops/native_fabric/routing_audit_20261013/request_waiters/`.

Apply semantically after the existing `logical_job_priority.patch` and `queue_priority/queue_priority_isolation.patch`; then combine the method and wiring changes into the same reviewed broker/launcher generation. The behavioral patch and wiring patch are inseparable for release. A request ID only scopes queued demand; original run fencing, lease ownership, authorization and return consumption remain the incumbent owners' responsibility.

A full-source owner must reconcile exact current broker and launcher bytes, preserve #1391 and the GLM host-account/operator checks, and produce full postimage hashes. An old external broker override may not support the new flag; it must be qualified as part of the same release, never silently ignore request identity or bypass its original gate. No forced stale patch, live install or source-writer transfer is authorized by these artifacts.

Preserve #1365's account-expiry/selector work, #1441 V4 cache truth, #1248 TaskFit and #1254/#1228 role-reserve ownership. No part of this operation retries their held effects or duplicates their algorithms.

## Current mission position

The previously latest head `ca4b99d6ada2a9af117c76a6c77dcf75823909a4` now has completed-success hosted CI run `38509743661`. That observation covers that old head only. The existing requested independent reviewer has not returned a review. Later source commits need their own CI observation.

No live source, service, provider, account, credential, quota, lease, worker or native host setting changed. No uncertain write remains: GitHub source commits and exact readbacks are retained. The old managed M2 workspace remains unsynchronized and must not overwrite the newer remote branch. Continue from the existing cumulative checkpoint, not a new branch or queue.

Next independent assessment is account selection's raw-occupancy bias, preserving the incumbent atomic selector and #1365 expiry precedence. Release still requires full-source native regression, independent review, protected acceptance, authorized installation and real original-parent consumption. **MISSION_COMPLETE=false; source progress is not runtime acceptance.**
