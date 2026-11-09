# CI PR Fast Lane — Risk-Tiered Work Without Duplicate Full Suites

Status: **source candidate**, not installed/proven until merged and verified by
real PR and merge_group runs. Owning repo:
`mastermindx-market-intelligence/Mastermind`.

## Why this is needed

Measured CI runs on 2026-11-03:
- Mastermind PR CI 41676744085: six pytest shards took 698–1386 seconds
  (slowest >23 minutes), then the separate stable `test` fan-in.
- Mastermind merge_group CI 41730696661: six pytest shards took 892–1323 seconds
  (slowest >22 minutes). This is a *second* complete run of the same suite.
- Protected master push CI 41733939711 reused prior merge proof, with longest
  pytest shard 198 seconds. That existing exact-SHA reuse remains in place.
- Current canonical test plan discovered 1,786 Python modules split 330/261/297/
  290/283/325 across six exhaustive, disjoint shards.

The previous workflow ran full shards for every PR *and* for merge_group,
regardless of what changed. This costs capacity and delays every review loop.

## Single CI owner and unchanged protected result

`.github/workflows/ci.yml` still owns one stable required `test` context.
The existing `scripts/ci_pytest.py` owns exact discovery, exclusions and six-way
partition. No second status owner, test exclusion, hidden approval, fake success
or altered merge-queue admission is introduced.

The new `pr_scope` job uses exact GitHub-generated PR/base identity, a local
complete Git diff, and the **accepted** `control_plane/github_review_risk_policy.py`.
It runs both itself and its risk-policy import from `git archive` of the
**protected PR base commit**, not PR-authored files. This avoids allowing
untrusted PR changes to reclassify their own CI. If source is unavailable,
forked, moved, binary/nonvisual, a deletion/rename, inconsistent or exceeds
the accepted policy bound, `mode=full` fails closed.

| Verified PR tier | PR path | Exact merge_group path |
| --- | --- | --- |
| FAST | Source/whitespace checks, `pr_fast`; no full PR shards | All six complete canonical pytest shards, required `test` |
| STANDARD | Source/whitespace checks + bounded source-proximate Python tests; web app typecheck when touched | All six complete canonical pytest shards, required `test` |
| CRITICAL/HOLD | All six complete pytest shards and existing non-pytest qualification | All six complete pytest shards and required `test` |
| Any push / manual dispatch | No PR-only fast mode | Existing full suite; protected push may reuse an exact accepted merge_group proof |

`pr_scope`, `pr_fast` and `pytest_shards` feed the same existing required
`test` job. This fan-in rejects a skipped shard matrix unless a verified
FAST/STANDARD PR's fast job succeeded. For merge_group and protected pushes
the matrix **must** succeed; no FAST outcome can replace integration proof.
A failed scope/test/dependency fails the required gate.

The fast job has read-only permission, no PR-secret exposure, bounded tests and
an eight-minute job budget. It does not run Fabric, deploy services, publish a
review, bypass GitHub protections or allow a branch merge. Full code coverage
and all security/non-Python qualification still occur at every merge_group.

## Required proof after source acceptance

1. A real docs-only PR on the protected base version containing this selector:
   scope FAST, fast job success, six shard jobs skipped, `test` successful.
2. A normal application PR: scope STANDARD, bounded smoke tests and optional
   frontend typecheck, full PR matrix skipped, `test` successful.
3. A CI/security/authority PR: scope CRITICAL, all full shards completed,
   `test` successful.
4. A native merge_group for the same PR: **all six full shards** and the
   original non-pytest gates completed, `test` successful only if all did.
5. Missing/invalid source and failed test: required `test` red, not skipped.
6. Compare GitHub run p50/p95 and compute after rollout: target ordinary PR
   feedback within a few minutes, not a timing guarantee or evidence of live
   performance before measurement. Full integration wall time is a subsequent
   optimization lane, not removed by this change.

If the queue's required checks do not observe the expected single `test` context,
do not bypass the queue or mark a partial gate green. Revert this source workflow
through the normal protected release path after obtaining evidence.

Review requirements are **separate** from CI. The merged #1989 FAST review policy
requires no independent approval for verified low-risk changes, but its #1977
live consumer and any governing native review rules still require independent
acceptance; this CI source alone is not an approval exemption or publication.
