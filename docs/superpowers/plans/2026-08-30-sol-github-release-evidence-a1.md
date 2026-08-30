# Sol GitHub Release Evidence A1 — Implementation Plan

> **Operator instruction:** Follow RED → observed discriminating failure → minimal GREEN. Keep this wave pure and read-only. Do not add a GitHub client, MCP server or release action.

**Operation:** `mastermind-sol-github-evidence-a1-20260830-sol-001`  
**Parent:** `mastermind-sol-executive-capability-surface-f0-20260830-sol-001`  
**Goal:** Build `mastermind.github_release_evidence.v1`, a deterministic source-attributed release assessment for one exact GitHub carrier.  
**Architecture:** `docs/superpowers/specs/2026-08-30-sol-executive-capability-surface-design.md` §6  
**Technology:** Python standard library, immutable dataclasses/enums, pytest

## Exact scope

Create only:

- `integrations/mastermind_github_evidence/__init__.py`
- `integrations/mastermind_github_evidence/release_gate.py`
- `tests/test_mastermind_github_release_gate.py`

Do not modify GitHub estate governance, Executive, Steward, RuntimeBinding, Wake, model routing, Business auth, plugin packages, CodeIntel or any current owner.

## Task 1 — freeze typed contract in tests

Write failing tests for:

- exact policy and source references;
- exact repository/PR/base/head branch and SHA identity;
- complete pull-request and compare changed-path census;
- exact merge base, ahead/behind relation and zero-behind requirement;
- protected branch and allowed merge method;
- required check identity by context + app ID;
- required check target SHA and GitHub success/neutral/skipped semantics;
- pending/failed/missing/duplicate checks;
- exact-head review, changes requested, unknown review and unresolved threads;
- stale/incomplete evidence;
- draft/closed/conflicting/unknown mergeability;
- already-merged effect reconciliation after base movement;
- stable ordering/digest across input permutation;
- closed JSON-serializable output;
- static no-network/no-process/no-filesystem/no-mutation fence.

Run:

```bash
python3 -m pytest -q tests/test_mastermind_github_release_gate.py
```

Expected RED: collection fails with missing `integrations.mastermind_github_evidence` package. Any unrelated collection/syntax failure is a defect.

## Task 2 — implement immutable value contract

Implement closed enums/dataclasses for:

```text
SourceRef
CheckIdentity
ReleasePolicy
PullRequestFact
BranchPolicyFact
CompareFact
CheckFact
ReviewGateFact
ReleaseSnapshot
GuardedReleaseCandidate
ReleaseAssessment
```

Validation requirements:

- lower-case exact 40-hex SHAs;
- exact owner/repository form;
- bounded operation, branch, context, source and path strings;
- unique normalized changed paths/check identities/merge methods;
- current/stale sources require observation time;
- completed checks require a conclusion; nonterminal checks do not;
- merged PR requires a normalized merged commit SHA and cannot be draft/open;
- expected changed paths cannot be empty.

Run focused tests; stop on failures.

## Task 3 — implement deterministic assessment

Assessment order:

1. validate exact carrier/head/payload evidence required to reconcile an already-merged effect;
2. if exact PR is merged, return `ALREADY_MERGED` with its merged commit SHA and no action candidate, even when base subsequently moved;
3. for an unmerged carrier, require exact current base/head/merge-base and complete compare/check/review/source evidence;
4. refuse duplicate check identities, old-head checks, review target movement and owner/source incompleteness as reconciliation;
5. block path drift, behind base, no delta, draft/closed/conflict, unprotected base, unavailable merge method, check/review failures and unresolved threads;
6. emit `READY_FOR_EXPECTED_HEAD_RELEASE` only when all gates pass.

The positive result includes only:

```text
repository
pr_number
expected_head_branch
expected_head_sha
merge_method
```

Always emit:

```text
organizational_authority_granted=false
production_acceptance_claimed=false
```

## Task 4 — canonical evidence digest

Create a deterministic SHA-256 digest over the exact normalized policy and snapshot. Sort checks and source references by identity so caller ordering cannot change the result.

The digest is an evidence fingerprint, not a credential, idempotency key, release token or authority grant.

## Task 5 — prove adversarial behavior

Run focused GREEN and manually kill at least these mutants:

- failed required check treated as success;
- old-head check accepted;
- `behind_by > 0` ignored;
- changed-path policy ignored;
- merged changed-path mismatch treated as exact already-merged effect.

Each mutant must produce at least one failing test, then restore the exact clean implementation.

Run:

```bash
python3 -m pytest -q tests/test_mastermind_github_release_gate.py
python3 -m compileall -q integrations/mastermind_github_evidence tests/test_mastermind_github_release_gate.py
```

If formatter/type-checker tooling is absent in the isolated environment, disclose that rather than claiming it passed. Hosted repository gates remain mandatory.

## Task 6 — publish same-operation carrier

Create an isolated branch from the exact accepted F0 head:

```text
sol/sol-github-evidence-a1-20260830
```

Open a draft stacked PR against the F0 branch. Record:

- protected/parent base SHA;
- exact A1 head SHA;
- exact three-file diff;
- RED receipt;
- focused GREEN count;
- compile/static fence;
- mutant-kill receipt;
- explicit no-network/no-MCP/no-GitHub-effect boundary.

Do not mark ready, merge, publish an app or call GitHub from production.

## Acceptance and stop

A1 returns `BUILT_NOT_PROVEN / PRODUCTION_INERT` after local proof and draft publication. Hosted exact-head repository test/security checks and independent Sol review are still required.

Even accepted merge makes only the pure semantic release assessor available to code consumers. GH-A2 remains responsible for authenticated GitHub gathering and any Chat/MCP exposure. A separate action-time Sol edge remains responsible for an actual expected-head merge.
