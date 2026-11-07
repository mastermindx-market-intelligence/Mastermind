# CI timing: measured next optimization, not another generic parallelism proposal

Observed 2026-10-15 on the Mastermind CI workflow. Raw selected GitHub job/step timestamps are retained in `ci_timing_observation.json`. This is a small, descriptive sample, not a fleet-wide latency or cancellation-rate estimate.

## Measured bottleneck

| Successful run | Run-record elapsed | Job elapsed | Repository test gate | Test-gate share of job |
|---|---:|---:|---:|---:|
| 38684100093 | 1220 s | 1216 s | 1155 s | 94.98% |
| 38682695635 | 1414 s | 1412 s | 1343 s | 95.11% |
| 38682319484 | 1246 s | 1225 s | 1159 s | 94.61% |

Run-record elapsed is `updated_at - created_at`; job elapsed uses the actual job start and completion fields. These are not interchangeable with CPU execution time. The repository-test step accounted for approximately 95% of each sampled job. Installing the project took 21–27 seconds. Further dependency caching alone cannot remove the dominant cost shown here.

The existing `.github/workflows/ci.yml` already runs `scripts/ci_pytest.py --jobs 3` inside the single protected `test` check. `ci_pytest.py` already verifies a disjoint, total module partition, emits per-shard elapsed time, reports 25 slowest pytest entries, and uses two measured placement overrides. Replacing this with a second generic matrix or dropping tests is not justified by the observations.

The latest 20 completed workflow records contained 12 cancellations, 5 successes and 3 failures. This query selects completed records and has a short moving window; it is not a population rate. These records do not identify cancellation cause. Diagnose actual supersession/user cancellation/concurrency events before attributing that count to unnecessary commits. Candidate stability and review/CI overlap remain low-risk improvements without weakening validation.

## Next bounded optimization

Use the existing shard timing output to identify whether current expensive modules or tests dominate the critical shard, then benchmark the narrow repair against the unchanged discovery-first gate. Retain stable placement for unrelated modules, total coverage, the one protected check identity and actual head/merge-group qualification. Do not add another scheduler, change required checks, or raise performance bounds merely to obtain green.

The attempted detailed log read for the first sampled successful job returned a sanitized `CLI_READ_FAILED`. That did not provide per-test timing evidence, and it was not turned into an account-wide permission claim or retried on a different carrier. The job/step timestamps above are sufficient to prioritize test execution over setup caching; they are insufficient to identify a particular slow test as the fix.

## Change completed during this assessment

A separate adversarial reader test exposed an avoidable interruption at the active-workflow/current-job boundary: when a positively active attempt had not yet returned a current job, the initial reader terminated instead of remaining pending. The follow-on source keeps the required check identity, omits the unqualified old success, and lets the existing classifier/waiter continue as PENDING. Missing membership without positive active-workflow evidence, permission errors and generation changes still refuse. Six new cases were observed failing before this repair. The new source is bound in `pending_review_subject.json` and has its own independent review; it is not silently covered by the earlier source review.

This is a continuity fix, not a measured reduction in the 20–24 minute successful CI duration. The overall programme still requires the admitted native consumer and real-product finish proof.
