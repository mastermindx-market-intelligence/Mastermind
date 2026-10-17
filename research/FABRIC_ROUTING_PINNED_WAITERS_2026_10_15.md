# Pinned-account queue eligibility — bounded follow-on

Operation `fabric-routing-deep-audit-20261013-c2-001`, same PR #1443 and branch.
Source candidate only; no provider, live account, native host or lease effect.

## Problem and narrow repair

An older waiting request pinned to a fully occupied account can block a new
request that could use another account. Fixing only `_front_of_queue` is
insufficient: `_below_share_waiters` can still prohibit use of otherwise idle
capacity. Both now consult one read-only helper, under the existing broker lock,
which proves total-account saturation from a unique currently grantable account
and its actual same-pool held count.

Only explicit, uniquely observed, positive integer account limits qualify. The
original waiter's row remains intact and participates again when capacity opens.
An unpinned waiter, missing/ambiguous observation, observation error or
model-only constraint remains blocking. No schema/model-default invention,
root-fair-share change, native release, account switch or capacity grant is added.
This addresses the provable pinned-account case, not every model/host eligibility
case originally identified in the audit.

## Verification scope

The source-method test applies the real patch to the two source-backed queue
methods. It changes four failed and twelve passed cases into sixteen passed.
The test covers both same-root and cross-root contenders, idle-capacity lending,
re-entry after capacity frees, unknown/invalid observations, pool isolation and
no mutation. These are narrow development proofs, not installed performance.

Five separately collected complete-broker tests compare those reference methods
with the assembled protected source before applying the patch. They exercise
actual temporary-SQLite acquisition and shared capacity, including preserved
native uncertain holds. Their behavioral result requires the exact full fixture;
none is claimed before execution. Source-only syntax/collection has passed.

## Source and effect boundaries

This follow-on is prepared on top of `47c43e6eb5f583bd2fbffefbd6157275e3892957`,
which contains #1391 native-binding compatibility and #1469 quota-exclusion
composition checks. The current PR head is intentionally not displaced while
its hosted repository test is being evaluated. A prepared Git commit is not a
branch update, hosted pass, merge, installation or accepted worker run.

Preserve original native fixture/host refusals, the original 49-pass/one-failure
result, prior 89-source-test scope, current independent review requirement and
native source ownership. Do not re-run the denied operations through these tests.
Before adopting this follow-on, consume the current composition result, reconcile
its full-source inputs, and run these new complete-broker cases. The broader
model-specific FIFO, effective pool-scoring and quality-evidence work remains
open; unknown eligibility must not be converted into permission to skip a waiter.
