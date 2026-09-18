# Source Continuity bounded census implementation plan

> Execute inline, test first; keep the existing source/verifier owners.

**Goal:** Let the official source-continuity command finish a complete,
bounded collision proof for repositories with 101–256 open pull requests.
**Architecture:** Extend only the existing adapter with one invocation-local
GET budget shared by its first and second observations. The existing pure
verifier, Git proof, refusal and authority contracts remain.
**Spec:** Mastermind issue #346, proposal #issuecomment-5571320837 and current
Sol admission #issuecomment-5589693928; protected source
379f6ceaf138b40a9374ed896e0f7c05a355fb3b.
**Stack:** Python standard library, pytest, existing Git/HTTP probe seams.

## Fixed boundary

Exactly four paths: scripts/source_continuity.py, the owning new
tests/test_source_continuity_census_budget.py, one existing fixture in
tests/test_source_continuity.py, and this plan. No schema,
core verifier, token path, retries, persistent state, public knobs or release
rules change. Limits: 256 PRs; 640 logical GET calls and 32 MiB normalized
JSON across both observations; 180 seconds cooperative read/result budget.
The existing 5 MB raw-response and 20-second call limits remain. A cooperative
deadline rejects late results; it cannot preempt transport, JSON or Git work.

## Ordered execution

- [x] Inspect the actual adapter, prior proposal and source custody; baseline
  the two current Source Continuity modules (175 passed).
- [x] Add actual-main fixtures at 1/100/143/200/256 and rejection at 257;
  prove the over-100 cases fail on the unchanged adapter before implementation.
- [x] Add shared call/byte/deadline regressions, last-PR overlap, changed second
  observation, duplicate pagination, large foreign file fanout and auth controls.
- [x] Add `_ReadBudgetExceeded` and `_BoundedHTTPGet` inside the existing adapter.
  The wrapper checks finite/nondecreasing monotonic time before and after calls
  and accounting; clips timeout to remaining budget; counts each attempted
  logical GET once; accounts canonical JSON with UTF-8/backslashreplace so the
  existing path validator still owns malformed Unicode refusal.
- [x] In `main`, construct one wrapper and pass it to both existing remote
  observations. Recheck after pure verification. Only budget exhaustion maps
  to REMOTE_CENSUS_INCOMPLETE; retain auth/remote/internal distinctions.
- [x] Run the complete existing two-module suite and the new test module:
  `python3.12 -B -m pytest -q -p no:cacheprovider -o addopts= tests/test_source_continuity.py tests/test_source_continuity_r3_hardening.py tests/test_source_continuity_census_budget.py`.
- [x] Extend to real disposable Git with synthetic HTTP and replay all relevant
  refusal/negative cases. Check unchanged core/CLI and preexisting functions.
- [x] Reject independent faulty mutations: cap-only, dropped closing census,
  reset budgets, missing final/post-accounting clock, changed auth translation.
- [ ] Publish one normal commit and one Draft/HOLD PR; verify exact remote
  head/tree/source and use the current protected official checkpoint adapter.
- [ ] Obtain non-author review and natural whole-repository/security CI.
  Do not promote a focused pass into whole-repository or production acceptance.
- [ ] After explicit accepted source protection, separately measure one genuine
  read-only consumer census. Preserve original refusal and fail closed on any
  still-exceeded bound. No Macro release follows from fixtures or this plan.

## Completion and stop boundary

This slice unlocks a trustworthy official source checkpoint at observed estate
scale. It does not itself improve Prophet selection, activate ranking, transfer
writers, merge products or certify production. Keep the source on its one
carrier through review; record exact remaining proof rather than restart work.


## Scope correction from the full-suite regression

The first combined run returned 201 passes / one failure. Its existing
final-incomplete fixture sent 101 PRs then had no foreign-file responses:
101 is now intentionally within the supported range. Keep every old assertion
and strengthen that fixture to continue full 100-row pages past the 256 ceiling.
This is the only added existing-test edit; no assertion or production error
translation is weakened. A current 53-open-PR complete scan and 187-worktree
path scan found no competing writer on that fixture. The own new tests preserve
explicit 257 refusal and exact 256 success separately.


## Pre-publication evidence

Existing baseline:175 passed. The first new actual-main run on unchanged
production source returned18 intended failures /9 controls passing. The first
combined implemented run had201 passes and the one stale ceiling fixture
failure described above; its assertions were preserved and fixture corrected.
Final current Source Continuity selection:215 passed, zero skipped, including
three actual disposable-Git CLI cases at143/200/256 with synthetic HTTP only.

Eleven distinct bad mutations are rejected. Eight of the initial nine were
caught; the post-accounting mutation initially survived because the next GET
still refused the late result. A direct one-GET return-boundary test then
reproduced that missing discrimination (DID NOT RAISE), killed that mutant and
passed with source restored. Removing the closing observation and resetting
budgets only on that observation were separately killed. No mutation remains
in the candidate. Only main changes among preexisting adapter AST definitions;
the core verifier is byte-identical. The worktree was fully materialized for
honest index verification; no skip-worktree flag was silently waived.

These are source tests and static structure evidence, not a genuine GitHub
consumer census, natural whole-repository CI, independent review or source
protection. The current official adapter, not this candidate, must checkpoint
this source PR before long review. A later protected consumer canary remains.
