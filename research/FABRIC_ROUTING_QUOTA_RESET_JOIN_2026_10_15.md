# Quota reset truth and complete broker composition

Operation `fabric-routing-deep-audit-20261013-c2-001`; existing PR #1443 and branch.
Protected procedure pin `2cc4942e136ad4fb544fd5c72ab1856608a5dac1`.
Input branch head `69f5767fda0fe8c41efc50f2e8881ec58b288ace`.
**SOURCE CANDIDATES / NOT INSTALLED / MISSION INCOMPLETE.**

## Current dependency, not the older quota candidate

#1441 has advanced to V5 at `fee58a0aad8a996b2df0d9222502e0c4c8a610e6`.
Its complete quota preimage is exactly the #1469 quota reader already carried in
our fixture: SHA256 `a1dab11da10264836e6271955b375b8e6508c23f23d0444c99d96464deb70f2b`.
The new test fixture extracts ONLY the quota_remote.py file section from its
published patch blob `fb853e50690f1c1bf538aa1500f100a5198677dd`; this is not a new
quota implementation or a claim that its newer picker/ledger are integrated here.
The section begins with `--- a/ext/quota_remote.py` and ends before the next file
header. Its own digest is checked, and applying it to the exact complete quota
preimage reproduces V5 component SHA256
`42f3a5f9b4d820ab5fafd9b739944a685dab4ebe254fb9c190f9ab75129ebfab`.

The current V5 picker and ledger have newer source identities than our original
audit. Do not deploy an older picker or apply stale full-file manifests to close
that remaining integration gap. Preserve #1441's current source writer.

## Reproduced reset-boundary inconsistency and correction

V5's advisory filter checks observation age but not the reset time of the window
being observed. A recent pre-reset two-percent-remaining observation survives
its reset and still reports provider-authoritative PARKED. The complete #1469
account-admission reader correctly stops enforcing that old hold after reset.
A whole-module test reproduced their disagreement from the same synthetic cache.
A recent old high-remaining observation can likewise imply current OK despite
belonging to an ended window; it must not be invented current capacity either.

`quota_reset/advisory_reset_boundary.patch` changes only
`_advisory_fresh_states`: when reset metadata is present, it must parse and lie
strictly after the evaluation time. Passed, equal-time and malformed resets are
not current authoritative observations. Missing reset retains the existing
contract; this repair does not silently require new provider fields. Uncertain
or partial observations feed the existing UNKNOWN/local-reconstruction behavior,
never an invented post-reset balance. A genuinely fresh, unexpired exhausted
account is still excluded. Explicit refresh/non-advisory behavior and #1469's
cached account admission helper are unchanged.

Twenty-five complete-reader and joint-broker tests pass. The original V5 behavior
produces fifteen failures and ten passes in the same new suite. Failure cases
include passed/equal reset PARKED, expired-window false OK, stale local-fallback
suppression, partial multi-account truth, and direct filter/wiring expectations.
The corrected file has SHA256
`06a10fecbc60ed30d43bcfd933d2aea0dbf234f32c16f8a2c65ce2da95648e8c`.

## Quota, pinned-account bypass and reclamation on one complete broker

The earlier #1469 five-case quota composition suite passes unchanged locally.
Fifteen further tests compose that exact gate with the existing full-account
bypass and newly published reclamation fix. Applying quota first versus last
produces identical complete broker bytes:
`7b185deb7a0a3a8c557a9dc04ad52127a11777479793e5316a34698c83e628cb`.

Tests preserve hard exhausted-account exclusion before ranking, unknown-data
behavior, pinned sibling retention, idle borrowing, native-uncertain capacity and
surplus reclamation. The three reset/admission join cases then load the corrected
complete V5 reader behind this same broker. AST checks preserve the incumbent
account/native/expiry implementations and isolate the intended changes.

The two new suites run together: **40 passed / zero failed** (fifteen composition
checks plus twenty-five reset checks). Assertions intentionally reuse relevant
published cases on the new composition; these are not forty independent product
capabilities. Socket connections, provider readers, credential lookup and quota
writes are blocked; synthetic account listings and cached observations are supplied
by test fixtures. No provider, host, native worker or installed lease is used.

## Integration and unfinished obligations

New source tests:
- `tests/test_native_fabric_quota_pinned_reclaim_composition.py`
- `tests/test_native_fabric_advisory_reset_boundary.py`

The reset patch follows #1441 V5's quota file section; it does not replace that
owner's complete release bundle. The three-way broker composition retains the
#1391 native postimage, #1365 expiry allocator, #1469 quota gate and current #1443
queue/account amendments. Broker source and native helper must still be released
as one version-qualified support generation with the actual current launcher and
external broker overrides. Fixtures must never be installed as production files.

Existing denied host inspection and original native fixture/preparation effects
remain NOT_DISPATCHED and are not retried here. Original native verification is
still 49 passed/one disclosed GLM-fixture failure, not replaced by this result.
Independent review, full current picker/launcher/native regression, protected CI,
current source custody, coordinated installation and useful original-parent
execution/return remain required. Model/host-specific head-of-line eligibility,
effective preference/scoring controls and quality-confidence policy remain open.

Exact source/test digests, units and verification scopes are retained in
`research/evidence/fabric_routing_reset_join_20261015.json`.
