# Fast-ship implementation and operating guide

Program: existing Mastermind #1607 / #917 and Macro #6351,
`WS:CI-MERGE-CONTROL-PLANE`. Implementation operation:
`fastship-ci-20261104-ryan`. This guide is not a queue, release authority,
worker registry, or replacement for the existing source-linked project records.
The implementation sequence is retained in
[the #1607 source record](https://github.com/mastermindx-market-intelligence/Mastermind/issues/1607#issuecomment-6651130876).

## Outcome

Reduce unnecessary CI execution and integration delay while preserving selected
tests, exact-candidate evidence, actual native review requirements, release holds,
and real product acceptance. More PRs or green checks are not the success metric.

The baseline is protected Mastermind `cb390bfc5a4b85a59a1005bfd3824305a5a4bfee`.
It ALREADY contains six canonical pytest shards, trusted-base PR fast/smoke
selection, full merge-group qualification, a stable `test` fan-in, postmerge
proof reuse, and the offline `scripts/ci_run_profile.py` analyzer. Do not build
second versions or restore the earlier three-shard architecture.

## Automatic CI performance reports

`.github/workflows/ci-profile.yml` consumes completed `CI` workflow runs and
calls `scripts/ci_profile_capture.py`, which uses the existing offline profiler.
It is outside the required CI dependency graph and outside every merge controller.
A failed report cannot turn source CI green, block an otherwise eligible merge,
release a hold, or dispatch a repair worker.

For each exact completed attempt, the Actions summary shows elapsed time,
summed job execution, observed concurrent wall time, the slowest jobs, failed
or incomplete jobs, and explicit evidence gaps. The report artifact retains
`snapshot.json`, `profile.json`, and `summary.md` for 30 days. A short failed
job remains visible even when it is not among the slowest 15 jobs.

Manual recovery after this workflow reaches protected master:

```sh
gh workflow run ci-profile.yml \
  --repo mastermindx-market-intelligence/Mastermind \
  --ref master -f run_id=<existing-run-id> -f run_attempt=<exact-attempt>
```

This requests a diagnostic read of an existing run. It does not rerun tests or
alter the candidate. Workflow dispatch on a non-master branch is not admitted.
Report availability on protected master and a natural completion-event run must
be verified before calling the automatic consumer installed or production-proven.

### Security and evidence boundaries

* Checkout is the reporting workflow's protected source SHA, never the
  triggering PR head. No candidate code, artifact, log, or cache is executed.
* `contents: read` and `actions: read` are the only GitHub token permissions.
  Action implementations are SHA-pinned; checkout does not retain credentials.
* API calls are bounded GETs to `api.github.com`; redirects, arbitrary URLs,
  automatic retries, and all mutation endpoints are excluded.
* The exact repository, run, attempt, workflow path and completed state must
  match. All jobs pages are captured with a fixed maximum. Duplicates,
  contradictory counts, truncated pages and mixed identities are refused.
* Missing native job fields remain missing. The existing profiler exposes them
  as evidence gaps; the collector never manufactures identity or zero timing.
* Start offsets are NOT runner queue time. They also include job dependencies.
  Summed execution is NOT a billing estimate. No speedup, merge, deployment or
  product-acceptance conclusion is computed.
* Candidate-controlled display strings are escaped. Tokens and raw API failure
  bodies are never printed. A failed read is reported, not silently made green.

### Qualification evidence for this implementation

Before the collector existed, its new test suite failed import. The first real
API capture then exposed a compatibility defect in the existing analyzer: the
attempt endpoint emits `/actions/runs/<id>/attempts/<attempt>/jobs`, but the
analyzer accepted only the non-attempt URL. The repair admits exactly the same
validated attempt; foreign attempts and URL variants remain rejected.

Focused collector plus existing analyzer qualification: **110 tests passed**.
A real read of Mastermind CI run **41754096888**, attempt **1**, returned **7 jobs**,
complete job coverage, verified native identities, **1,415 seconds** from creation
to last observed job completion, and **zero evidence gaps**. This is an actual
metadata-consumer check on an existing run, NOT a newly executed CI run, an
installed workflow, an achieved speedup, or a release receipt.

## Remaining program slices and existing owners

| Slice | Existing owner / next acceptance |
| --- | --- |
| Macro pack demand | Extend `scripts/run_ci_pack.py` only; preserve selected logical jobs and plan/evidence contracts. Qualify deterministic compaction against baseline modeled maximum load, then observe natural CI. Model weights are not measured seconds. |
| Mastermind hot test module | #1607; use measured `test_capacity_host_artifacts.py` costs. Never cache security-verification outcomes or remove hostile cases to reduce time. Linux hosted qualification remains necessary when local macOS ancestor/ACL fixtures are incompatible. |
| Macro critical-path jobs | Reconcile existing #10735 / #10738 and failure-signature repair #10745; avoid parallel replacement PRs for their owned functions. Current release eligibility must be read from GitHub, not this guide. |
| Backlog drain | Existing #2028 / #945. Distinguish active, held, completed and superseded work; preserve source and real owners. No bulk auto-merge or automatic deletion of old Drafts. |
| Trusted runner prewarming | Macro #6737 / #6351. Immutable tool/dependency inputs and actual runner isolation proof; no candidate-controlled persistent runner access. |
| Release progression | Native Mastermind queue and Macro's incumbent merge-on-green controller. No second merge service. Exact-head formal approval is required only where binding policy actually requires it. |

Keep p50 and p95 latency, selected coverage, runner-minute demand, failure rate,
and completed user journeys separate. Initial targets (not current results):
ordinary first feedback under 5 minutes, required validation median 10–15 minutes,
and eligible-change-to-protected-merge median under 30 minutes. Capacity and test
selection must be measured together; adding runners or reducing pack count alone
can worsen the critical path.

A completed report or source PR does not finish this program. Completion requires
qualified source adoption, a natural Actions consumer, materially improved
representative CI evidence, and truthful release/product outcomes through the
existing owners. Continue independent ready work while checks or reviews run;
retain one exact candidate and consume its real terminal result.
