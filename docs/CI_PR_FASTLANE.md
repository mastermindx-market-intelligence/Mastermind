# CI PR Fast Lane — Risk-Tiered Work Without Duplicate Full Suites

Status: **merged and running** (#2016), with the merge_group path changed by
#2129 (risk-scoped queue), #2439 (STANDARD groups run full) and #2413 (parallel
qualification job). The table below describes `scripts/ci_pr_scope.py` as it is
now; the 2026-11-03 measurements are the original motivation, kept as history.
Owning repo: `mastermindx-market-intelligence/Mastermind`.

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
**protected base commit**, not PR-authored files: the PR's recorded base for a
pull request, protected `origin/master` for a merge group. This avoids allowing
untrusted PR changes to reclassify their own CI. The classifier's closure is
four files (`scripts/__init__.py`, `scripts/ci_pr_scope.py`,
`control_plane/__init__.py`, `control_plane/github_review_risk_policy.py`). The
smoke selector `scripts/ci_pr_smoke.py` is not part of it; the workflow
extracts it only for a protected classifier that still imports it (bases
between #2380 and #2439). If source is unavailable, forked, moved,
binary/nonvisual, a deletion/rename, inconsistent or exceeds the accepted
policy bound, `mode=full` fails closed with tier HOLD.

A merge group is classified as a whole: `classify_merge_group` verifies the
event identity (base ref `master`, a `gh-readonly-queue/master/` head ref, the
checked-out head, protected `origin/master`) and then tiers the entire
`protected base..group head` diff, so one CRITICAL entry makes the whole group
full.

| Verified tier | Pull request | Merge group (whole integrated candidate) |
| --- | --- | --- |
| FAST | `mode=fast`: `pr_fast` source/whitespace checks; shards and qualification job skipped | `mode=fast` (since #2129): the same `pr_fast` checks on the exact queue candidate; shards and qualification job skipped |
| STANDARD | `mode=smoke`: `pr_fast` checks + bounded source-proximate Python tests; web app typecheck when `app/mastermind_os/` is touched | `mode=full`, reason `MERGE_GROUP_STANDARD_REQUIRES_FULL` (since #2439): all six pytest shards and the qualification job; never smoke |
| CRITICAL | `mode=full`: all six pytest shards and the qualification job | `mode=full`: all six pytest shards and the qualification job |
| HOLD (unverifiable) | `mode=full`, fail closed | `mode=full`, fail closed |
| Any push / manual dispatch | not applicable | No scope job. All six shards and the qualification job; a protected push may reuse a same-SHA merge-group proof for the pytest step only |

A merge group can therefore reach the required `test` job only as `fast` (FAST
tier) or `full`. Between #2129 and #2439 a STANDARD group certified on the
bounded smoke selection; that is no longer possible, because a selection
cannot prove the tests it did not select (cross-repository pins,
package-membership counts).

`pr_scope`, `pr_fast`, `pin_guards`, `qualification` and `pytest_shards` feed
the same existing required `test` job. The fan-in accepts a skipped shard
matrix only when the trusted scope is `fast` or `smoke` and the fast job
succeeded; in full mode, and on every push or manual run, the shard matrix and
the qualification job **must** succeed. A failed scope/test/dependency fails
the required gate.

The fast job has read-only permission, no PR-secret exposure, bounded tests and
an eight-minute job budget. It does not run Fabric, deploy services, publish a
review, bypass GitHub protections or allow a branch merge. Full code coverage
and all security/non-Python qualification occur at every STANDARD, CRITICAL
and HOLD merge group and at every protected push.

### Web application typecheck

`npm --prefix app/mastermind_os run typecheck` has two owners that never run
in the same event:

- `pr_fast` (fast/smoke), only when the verified diff touches
  `app/mastermind_os/` (`needs_node=true`).
- The qualification job (full mode, push, manual dispatch), unconditionally.

The full-mode gate is not conditioned on `needs_node`. `pr_scope` does not run
on a push or manual dispatch, so the output does not exist there, and every
fail-closed HOLD decision reports `needs_node=false` even when the diff
deletes, renames or re-modes a web application file. Before this gate, no full
merge group and no push typechecked the web application.

### Measured full merge group (2026-11-10)

Merge group run 42919263806 (PR #2438), after #2439 and #2413: 40 minutes from
enqueue to green, about 1 minute of runner wait. Pytest shards 3 / 1 / 2 / 4 /
0 / 5 ran 22 / 25 / 33 / 36 / 38 / 39 minutes; the qualification job ran 4
minutes beside them. Before those fixes a full group took 70–80 minutes with
shards 0 and 5 at 41–54 minutes. This is one run, not a p50.

## Required proof after source acceptance

1. A real docs-only PR on the protected base version containing this selector:
   scope FAST, fast job success, six shard jobs skipped, `test` successful.
2. A normal application PR: scope STANDARD, bounded smoke tests and optional
   frontend typecheck, full PR matrix skipped, `test` successful.
3. A CI/security/authority PR: scope CRITICAL, all full shards completed,
   `test` successful.
4. A native merge_group: a FAST group runs the fast job with shards skipped;
   a STANDARD or CRITICAL group runs **all six full shards** and the
   qualification job (including the web application typecheck); `test` is
   successful only if every job on that path did.
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
