# Existing native pool: model-aware planning repair

The hash-bound `patches/lease_broker_model_planning.patch` targets the native
pool broker observed for operation `fabric-capacity-orchestration-upgrade-20261005-sol-001`
on 2026-10-05. It is a reviewable source candidate, not a new broker, lease
database, scheduler, quota engine, installer or live deployment. Its inert fixture
preserves that observed source and contains no runtime account configuration or
credentials; it is not proof of the current selected native generation. The patch
changes only `plan`, `_plan_pool`, `_print_plan` and the `plan` branch of `main`;
admission, renewal, fairness, reconciliation and release function bodies remain
unchanged.

## Defect and result

At the 2026-10-05 census, the observed broker's acquisition path checked an
account cap and a model cap, while its plan reported only the aggregate pool cap.
In the observed configuration,
three GLM accounts each have account cap 10, full-model cap 5 and Flash cap 20.
For otherwise idle, eligible accounts the full-model upper bound is 15, not 30;
the Flash bound is 30, not 60. They are not additive. After 15 full-model leases,
only 15 aggregate account slots remain for Flash. These are configuration
examples, not verified entitlements or live free capacity.

The patch adds optional `--pool`, `--model` and `--json` on the existing `plan`
command. It intersects account and model free slots before applying the existing
fair-share result. Legacy calls keep their pool-aggregate values but explicitly
state that model and quota capacity have not been checked. Unknown GLM model
limits offer zero model-specific headroom. Non-GLM account-only results do not
pretend to prove model-specific limits. No provider cap is increased.

`selection_is_commitment=false` and `claim_time_revalidation_required=true` apply
to every result. `quota_capacity_checked=false` is intentional: the existing
Shared AI Provider Control quota-economics owner must supply that evidence. The
old `window_remaining` display text is not a numeric quota budget. `wait_est` is
labelled as a lease-TTL hint, not a completion or refill guarantee.

## Verification and installation boundary

The manifest records exact before/after/patch SHA-256 values. Tests apply the
patch to a disposable exact-hash fixture, verify the resulting hash and exercise
the real broker/CLI with temporary SQLite and synthetic accounts. They also
prove untouched lifecycle/admission function bodies and no new leases or demand
from model planning. Broker construction and the legacy plan's GC/housekeeping
are not claimed to be globally read-only.

Before installation, the assigned receiver must reconcile the actual source
writer, installed generation, leases and effects through the incumbent native
release path, then:

1. Accept the exact published candidate through normal review and release gates.
2. Reconcile the current installed broker, incumbent source writer and active
   effects. Exact before-hash equality is mandatory; drift is a rebase/review
   requirement, never permission for fuzzy application or overwriting live work.
3. Apply the accepted one-file change through that existing owner, preserving the
   same lease store, account policy, wrapper, host bindings and permission profile.
   No new default broker path or account enrollment is introduced here.
4. Verify exact after-hash, wrapper argument forwarding and new CLI output on the
   intended native clients. Then prove real model/account caps under normal
   admission, including mixed full/Flash contention, without changing limits.

A source merge alone does not install this patch. Do not execute the fixture as a
replacement production broker. Existing native broker installation remains with
its incumbent owner; this candidate intentionally adds no alternate deploy tool.

These model-planning results do not resolve the TaskFit-to-native classification
handoff recorded in [#1248 finding6187002077](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1248#issuecomment-6187002077).
