# Delivery latency: measured bottlenecks and the 80% target

This is evidence for the existing #917/#945 turnaround programme and #1957 P3.O3. It is not a new plan, release policy, runtime, queue, approval or performance claim.

## Decision from the observations

Prioritize actual reviewer pickup, qualified native-queue admission and reconciliation after queue eviction. The sampled pytest imbalance is a secondary opportunity. New dashboards or additional status documents do not close these execution gaps.

Chairman target: comparable assignment-to-accepted-capability elapsed time at or below 20% of baseline, with no worsening of material failure, rollback or escaped-defect measures. No 80% improvement is currently proven. This sample measures PR creation to source merge; it cannot measure product acceptance.

Procedure source: Mastermind master@7f1242bfa90f0f0448e66e400e054bd5aa5fa15a. Bounded source carrier: delivery-throughput-80-20261102-sol-001. Scope and parent: https://github.com/mastermindx-market-intelligence/Mastermind/issues/917#issuecomment-6597185178 .

## Source observations

| PR | Created to source merge | Key observed interval |
|---|---:|---|
| #1932 | 13h 30m 47s | Explicit release-ready comment to first queue admission: 11h 36m 46s; queue to merge: 46m 40s |
| #1828 | 9d 13h 21m 01s | Successful head CI to first approval: 9d 00h 10m 44s; eviction to readmission: 9h 54m |
| #1616 | 15d 10h 03m 24s | Long-lived six-shard source change; preserve the separately recorded reviewer-independence audit gap |
| #1924 | 19h 14m 21s | Current-head seven-job CI completed successfully; merged review-route instructions still require installed/fresh-load evidence |
| #1959 | 4h 35m 42s | Source release completed; selected native-generation installation is a separate fact |
| #1965 | 2h 22m 33s | Source release completed; installed publisher behavior remains a separate proof |

These six PRs were selected from existing delivery work. They are not a random, risk-matched performance cohort; do not use their median as a company-wide delivery baseline. Work before PR creation, active engineering versus waiting, deployment and customer acceptance are not fully observed.

### #1932: release pickup is larger than test runtime

GitHub records current-head approval at 2026-11-02T06:32:40Z and successful CI run 41396700419 updated at 06:46:21Z. The author explicitly declared release readiness in comment6571089804 at 06:56:58Z. The first native queue admission is 18:33:44Z; merge is 19:20:24Z.

The declared-ready-to-admission interval is 41,806 seconds, 85.9% of creation-to-merge time. Removing that entire interval while holding all other durations fixed would yield 1h54m01s instead of 13h30m47s. This is a counterfactual opportunity, not achieved savings or proof that every minute was legally removable.

Sources:
- https://github.com/mastermindx-market-intelligence/Mastermind/pull/1932
- https://github.com/mastermindx-market-intelligence/Mastermind/pull/1932#issuecomment-6571089804
- https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/41396700419
- https://api.github.com/repos/mastermindx-market-intelligence/Mastermind/issues/1932/timeline?per_page=100

### #1828: fast initial admission, slow eviction recovery

Head CI40069403653 succeeded on October24; first approval arrived November2 at07:05:35Z. Initial queue entry followed in14seconds. The queue removed the candidate at08:53:36Z; readmission was18:47:36Z and merge19:35:17Z.

The 9h54m removal-to-readmission interval identifies a recovery investigation. It does not authorize blind requeue. Recover the canonical removal reason, prior effect, current head/checks/holds and existing retry authority before a next action.

Sources:
- https://github.com/mastermindx-market-intelligence/Mastermind/pull/1828
- https://github.com/mastermindx-market-intelligence/Mastermind/actions/runs/40069403653
- https://api.github.com/repos/mastermindx-market-intelligence/Mastermind/issues/1828/timeline?per_page=100

## CI execution evidence

Raw read-only GitHub run/jobs responses are retained alongside this file for runs41528759464 and41522114032. They include the exact head, run attempt, complete seven-job response and native step timestamps. The report must not use workflow updated_at as completion time or call job-start offset runner-queue time.

For PR-head run41528759464:
- Creation to final observed job completion:1,385seconds (23m05s).
- Sum of job-running time:6,322seconds. This is concurrent compute occupancy, not elapsed latency.
- Six pytest-step durations:743,1003,994,1244,942,785seconds; total5,711seconds.
- Shard1 finished after shard0, which contained Paper/Fabric qualification. Merely moving those shard0 checks into a parallel job would not remove the latest-finishing shard in this observation.
- Perfectly divisible six-way pytest work would average951.8seconds, versus observed maximum1244seconds. The 23.5% difference is an idealized balancing comparison, not measured savings. Module indivisibility, setup, runner variance and dependency waiting remain.

Both raw runs support inspecting actual test-duration skew. They do not establish that all future runs have the same bottleneck.

## Qualification finding that must precede fast-lane activation

At #1989 head3a89bf1d1022d447f4fd5cca32ec01a736cae42b, exact policy blob6371ea1a323ebbf3d3b8f23d85de577a9ec66c15 was independently reproduced. A one-line replacement in each of these existing paths returned FAST / zero formal non-author approvals:
- tests/conftest.py
- tests/test_ci_pytest_policy.py
- skills/mastermind-fabric-delegate/SKILL.md

These are executable test/gate or consumed instruction owners. Complete file pagination and a patch_available boolean do not prove inert semantics. This evidence was returned to the incumbent writer and reviewer at https://github.com/mastermindx-market-intelligence/Mastermind/pull/1989#issuecomment-6597325691 . No competing source changes or replacement review were created. Preserve positive fast treatment for proven inert/presentation work; conservatively qualify unknown executable behavior.

## Implementation and adoption priorities

1. Correct and independently qualify the incumbent #1989 risk policy; connect it to #1977 before automatic lifecycle enrollment. Prove FAST creates no reviewer Job, STANDARD one eligible original Job, CRITICAL required scrutiny, HOLD no exemption, and manual reviews unchanged. Source merge alone is insufficient.
2. Use the existing GitHub/Executive/Wake/release owners to consume a material approved/green event and perform one lawful native-queue action. Fresh current-head checks, actual non-author identity, existing holds, source custody and original effect reconciliation remain mandatory. Already queued/merged/uncertain events must never duplicate admission. Queue removal is an attention event, not automatic retry permission.
3. Finish the incumbent #1570 same-input proof-reuse path, including required negative/full-test fallback and actual postmerge behavior. Do not duplicate its active source/review work.
4. Consume the CI profile and rebalance observed hot tests through the existing exact-cover shard planner only when the evidence identifies a concrete next move. Preserve every required module and security/real-path test.
5. Prove installed session and runtime adoption of accepted continuation work. A readied PR, merged instruction, message or controller PID is not a running reviewer, installed consumer or resumed task.
6. Keep candidate heads stable during qualification. Store receipts in existing result/comment/artifact owners; avoid new evidence-only commits that restart the full source pipeline. Small independently useful releases remain the batch unit; a mechanical worker task need not be a separate release.

Suggested initial operational objectives, not currently enforced guarantees: a qualified release event acted on within2minutes; eligible reviewer pickup within5minutes; fast local checks within3minutes; standard CI p95 within10minutes after the required suite is properly optimized. Exceptions remain visible and risk-specific. They must be validated against capacity and existing policy, not converted into permission to bypass a refusal.

## Measurement of the target

Track two separate clocks from existing evidence: assignment to accepted capability, and first coherent candidate to accepted capability. Retain PR creation-to-merge as a source-delivery diagnostic. Report median and p90 by comparable risk/size cohort, counts, incomplete/censored age, false CI failures, repeated candidate qualification, rollback and escaped material defects.

Never add concurrent review and CI durations as serial delay. Never silently drop unfinished work, count missing acceptance as zero, equate a source merge with customer delivery or call a modeled saving achieved. The next accepted report should show the changed production/installed path and comparable observations, not merely another larger inventory.

## Current bounded effects

The #1977 review request delivery80-review1977-26369a2a-20261103-01, original #917 root, parent delivery-throughput-80-20261102-sol-001 and controller85515 returned terminal admission refusal rc75 with host_temperature_at_or_above_limit; no review was performed and retry_allowed=false. This exact operation remains held and was not rerouted.

The distinct offline CI-profile request delivery80-ci-profile-20261103-01 is now TERMINAL, root/parent verified, rc0, on original controller93798. The complete 3,940-byte return has SHA256 ab92db1c4b449094d63a644102068c5da5cc0cc4aae68f0b32ffaa847c2c0e80. It supplied artifact paths rather than source bytes. The exact two artifacts were recovered read-only from the original ubuntu1 device through its exposed, permitted filesystem surface; no worker replay, alternate implementation or host mutation was used. The recovered script/test SHA256 values exactly matched e6ef07ff077b2544192352c47306f59ec945b96ff38c66e1329943c7d54233a3 and 0bbffbe9a6582726ae13b091dafe67035923701b9c89ce691a4e1d50e03128ca.

The original 36 focused tests passed independently in this source workspace. Parent acceptance then reproduced false verified/completed output for missing job identity, inconsistent repository URLs, boolean attempt values, a queued empty job response and an in-progress run with currently completed jobs; malformed identity also escaped as TypeError. The source carrier contains bounded parent repairs and 25 additional regressions, with all61 cases passing. The original worker return is consumed as a partial contribution, not accepted as an unchanged correct implementation. Its terminal state is not a background execution claim.

## Reproducible offline profiler

The two new source files are scripts/ci_run_profile.py and tests/test_ci_run_profile.py. The utility reads one captured native run plus complete jobs response, derives the timing report, and writes JSON to stdout only. It performs no network, dispatch, cancellation, gate or authoritative-state write.

From the repository root:

```sh
python3 -m scripts.ci_run_profile research/evidence/delivery_latency_20261103/ci_run_41528759464.json
python3 -m pytest tests/test_ci_run_profile.py -q
```

The same CLI accepts "-" for stdin, with an8MiB input bound. Missing identity and unfinished runs stay unverified/incomplete; observed partial compute is labeled. Skipped or incompletely timed pytest steps cannot create a fictitious balancing bound. Supplied source URLs must agree with the repository/run/job identifiers. Identity verification is metadata consistency, not independent authentication of an offline capture.

Final local qualification at this checkpoint:61 cases passed, Python3.14.7 / pytest9.1.1, original conftest unchanged. Both real retained captures then reproduced the measured totals with no evidence gaps:

| Run | Elapsed seconds | Sum of job seconds | Union of running intervals | Pytest seconds |
|---|---:|---:|---:|---:|
|41528759464|1385|6322|1322|5711|
|41522114032|1402|6765|1305|6176|

Script SHA256:9b914f92cc507f5e0db56facf852ca05b9f5a48da4d231508ef41afc85bfaf9f.
Test SHA256:3d3d051380d1f87555a0d88b78ea7acf02cf52f904b6bed210f8cb90f43ad7c9.
This source utility is a diagnostic, not an installed delivery optimization or proof of an80% improvement.

## Independent qualification advanced

The policy blob in #1989 remained unchanged at head31f1453a1f242e80f1ade90b87ebc29be213bb41. Independent MastermindX1 review5748343198 binds that current head and the complete11-path diff. Exact-source collector-to-dispatch probes reproduce all three governing/test paths as FAST / SKIP_NO_REVIEW_NEEDED; the bounded repair is required before enrollment:
https://github.com/mastermindx-market-intelligence/Mastermind/pull/1989#pullrequestreview-5748343198

The separate Terminal static-only CI pilot #1251 was reviewed at4dedfaa92bc3fb9510fdb9734156f4c1592fe1f4. All23 new tests, including the aggregate bash truth table, passed independently. Two real isolated Git probes found nested instruction files in allowed documentation directories still receive FAST: terminal/docs/ux-notes/AGENTS.md and docs/product-previews/CLAUDE.md. Review5748486833 requests the small recognized-filename boundary repair while preserving ordinary-note FAST and the existing architecture:
https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/1251#pullrequestreview-5748486833

Neither review changes an incumbent source branch, replays the refused #1977 review, authorizes a merge, or proves live rollout. Current-source review procedure was refreshed to compatible protected b2326bbe30e9988d26199f5e774a482b9c09068a; the governing procedure paths were unchanged from the original pin.

## Research basis

DORA recommends small batches, limits on work in progress, peer review during development and automation instead of heavyweight external approval. Its guidance does not authorize removing an existing security/release control.
- https://dora.dev/capabilities/streamlining-change-approval/
- https://dora.dev/capabilities/working-in-small-batches/
- https://dora.dev/capabilities/wip-limits/
- https://dora.dev/capabilities/continuous-integration/

GitHub native merge queues qualify the integrated merge-group candidate; preserve merge_group checks and actual admission/merge receipts.
- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
