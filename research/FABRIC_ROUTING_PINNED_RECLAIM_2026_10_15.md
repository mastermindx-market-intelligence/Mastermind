# Pinned-account eligibility must preserve surplus reclamation

Operation `fabric-routing-deep-audit-20261013-c2-001`; original PR #1443 and branch.
Source assessed: `03e68c120d4d8b1667b9c41e1e14a02706c6bded`.
Refreshed compatible protected procedure pin: `2cc4942e136ad4fb544fd5c72ab1856608a5dac1`.
**SOURCE CANDIDATE / NOT INSTALLED / MISSION INCOMPLETE.**

## Reproduced regression

The new pinned-account bypass correctly lets another account do ready work. Its
shared `_below_share_waiters` filter also removes the full-account waiter from
surplus reclamation. A root occupying three slots on a full account can retain
all three after another root's demand reduces its fair share to two. Repeated
heartbeats keep that surplus alive, and the waiting root still cannot acquire
at the original lease-step boundary. A later ready acquire can also restore all
leases to renewable because `below_any` appears empty.

Three new full-broker/temporary-SQLite scenarios failed the published candidate:
missing surplus marking, unrelated acquisition rearming, and starvation despite
live waiting demand after the original borrowed-step boundary. This is not merely
a theoretical observation or a test against a substituted scheduling function.

## Bounded correction

Keep the existing full-account eligibility filter for FIFO and decisions to lend
otherwise idle capacity. Add a keyword-only `include_full_pins` demand view and
use it only for the two existing reclamation decisions: `_register_demand` and
`_try_acquire`'s `below_any`. Thus ineligible current work can be bypassed without
losing its claim on borrowed capacity. Existing grant/TTL/drain rules still decide
when capacity returns; no live step is killed or native hold released by this patch.

`pinned_waiters/pinned_account_reclaim.patch` applies AFTER the existing pinned
eligibility patch on the composed native-safe broker. It changes only
`_below_share_waiters`, `_register_demand` and `_try_acquire`. Original FIFO,
account/model ranking, pin observation, root denominator, schema, native guards,
GC, heartbeat/release and actual surplus-marking implementation remain unchanged.
Do not install source fixtures or apply this to an unreconciled current host.

## Verification

The exact published five-case pinned composition suite passed locally unchanged.
The new `tests/test_native_fabric_pinned_waiter_reclaim.py` passes **11/11**.
Its full before-state is six failures/five passes, including the three original
behavioral counterexamples plus new interface/structural checks. The suite reuses
all five prior pinned scenarios against the corrected full broker, preserving
other-account progress, idle borrowing, unpinned priority and native uncertainty.
Additional checks retain one original-root denominator for six queued siblings.

All test databases/configuration are temporary and synthetic. No provider call,
installed database, account, credential, service, worker or host inspection occurs.
These results neither clear the original denied native fixture/preparation actions
nor replace its 49-pass/one-failure result, full provider verification or review.
A temporary test-fixture naming error was corrected before the final 11-pass run;
it was not a product-code failure and is not counted as a before-state result.

## Exact artifacts

- New patch SHA256: `d56924f67c0b38ee9063aba8f1d8160a78f9729bd90a0b4380e9c4e09408e8d1`.
- New test SHA256: `44779d8508d9ddb7f4fa193f52e4a5c93829e8b530d728d3a3fc998352f3ca0b`.
- Full input after published pinned patch: `ae864a33775c8532f7aa1b3db5f32263172d4dfaa812a6455127aa887c1b0fa7`.
- Corrected full component: `400a780fdfd2d133c7c25bd09f4feeae1c1cce69f9750f3b7340b344a0c07acc`.

Those hashes describe the reproduced component without #1469's additional quota
patch; combined quota/pin/reclamation validation is the next source phase. They
are not current installed identities. Existing #1365/#1441/#1469 algorithms and
native source/loader custody remain unchanged. The prior local report/package was
read and its exact verified broker hash reused, not treated as a deployment.

Next: qualify composition with current quota admission, consume exact-head CI and
independent review, then use the actual current native writer for complete source,
launcher/override compatibility, protected release and original-parent execution
proof. Source tests are not installation or production acceptance.
