# Retained waiter after a quota-exhaustion transition

Operation `fabric-routing-deep-audit-20261013-c2-001`; original PR #1443 and branch.
Input head `82187d431b1b56c5fea254aba2d1a59a350e36f4`.
Protected procedure pin `2cc4942e136ad4fb544fd5c72ab1856608a5dac1`.
**SOURCE CANDIDATE / NOT INSTALLED / MISSION INCOMPLETE.**

## Full-component counterexample

A request can join a pinned account's queue while that account is full, before
a fresh quota observation excludes the account. Once the incumbent #1469 gate
marks that account exhausted, the previous total-capacity helper cannot find it
among grantable accounts. It therefore conservatively leaves the old waiter
blocking every lower-priority request, including work pinned to another ready
account. The queue row survives, so a new exhausted-account check only at fresh
submission does not repair this transition.

This was reproduced on the complete native-safe broker with the composed V5
quota reader, synthetic cached observations and temporary SQLite. No provider
or physical account was used. Both full and already-vacated account variants
blocked unrelated ready work with `priority_wait` before the repair.

## Narrow correction, no provider failover

`pinned_waiters/pinned_quota_waiter.patch` adds one read-only predicate. It accepts
only an enabled GLM path with external quota admission enabled, an explicit pin
to one uniquely configured account, and TRUE from the existing
`cached_glm_account_parked` helper. The provider's existing freshness/reset policy
remains authoritative; missing, stale, future, passed-reset, ambiguous or failed
observations do not establish this skip.

Only FIFO/ready-demand and idle-borrowing views use that predicate. The exact
waiter remains queued and its account is never changed. Its own acquire still
refuses, cannot receive a different account, and creates no lease. Reclamation
retains the full demand view introduced in the previous fix. When a valid new
observation reopens the original account, the same waiting request resumes its
priority and may acquire only that account through the normal broker.

The change does not add routing fallback, authorization, a cache, queue, account
registry, retry policy or new capacity. Native-held capacity is not released.
Actual account admission, model limits, root denominator, grant transaction,
GC, native retention, release/heartbeat and expiry ranking are unchanged.

## Verification

`tests/test_native_fabric_quota_waiter_transition.py`: **32 passed** on the final
candidate, versus **15 failed / 17 passed** before it. The suite includes current
quota transitions, idle borrowing, retained refusal, recovery of original
priority, native retention, unknown/ambiguous pins and failure of observation.
It also reuses eleven prior reclamation, native/ordinary-binding, sibling and
account-balancing assertions on this final component. Three guard cases prove
that disabled external admission, another pool or a disabled provider never
invokes the GLM quota reader for this predicate.

AST checks limit changed existing methods to `_front_of_queue` and
`_below_share_waiters`; the only new method is `_waiter_pinned_quota_parked`.
The original surplus-reclamation callers remain intact. All source reads are
repository-backed fixtures; all observations are synthetic. No original denied
host/fixture operation, real credential lookup, provider request, native worker,
service, installed source or live database was touched.

Exact input full broker: `7b185deb7a0a3a8c557a9dc04ad52127a11777479793e5316a34698c83e628cb`.
Exact final broker: `72fd13153e81349a76acae001ecc38e860f30cf055cdb2ba42411fbe209aa4d5`.
Composed quota reader: `06a10fecbc60ed30d43bcfd933d2aea0dbf234f32c16f8a2c65ce2da95648e8c`.
Patch SHA256: `933f46e9a3e48a82ed0b1780d0b3069ce10110b9388f25648f594223058fa458`.
Test SHA256: `68da98f26dff381f596654040cea6783834630ee7a9c7b28939d156f6ed08284`.

These are complete source-component identities, not current installed generation
receipts. The earlier forty-case join and eleven-case reclamation results remain
separate evidence scopes and must not be summed into production acceptance.
The original native 49-pass/one-fixture-failure record is unchanged.

## Remaining release dependency

Apply only after the prior native-safe, expiry, request/account, #1469 quota,
pinned eligibility and reclamation patches in the same reviewed support
composition. Preserve #1391/#1365/#1441/#1469 owners and all explicit holds.
Current full picker/launcher integration and override compatibility, independent
review, exact-head CI, protected release, installed generation and a useful
original-parent execution/return are not proven here. Unobserved model/host
eligibility, effective scoring/preferences and quality-confidence policy remain
open. This completes the narrow source transition repair, not the parent mission.
