# OPERATION pbr-res-r1766: independent review of PR #1766 (W2-R5 review minors: one rename, one stale comment, one spec word)

Class: review · Complexity: C1_ROUTINE_BOUNDED · Output: ONE file, `~/lanes/tmp/pbr-res-r1766/out/REVIEW.md`. You change no repository file.

## Target (exact; overrides the base line in the common rules)
- **PR:** mastermindx-market-intelligence/Mastermind#1766, branch `pbr/research-w2-r5-minors`, head `7ce2865def75dbe325cce83195db764374e31486`. Verify with `git rev-parse HEAD`.
- **Base:** `05a9eb52a54e29fb7bbd0d40813ed12623b176c7` (`origin/master`). Read the full diff as `git diff 05a9eb52..HEAD`.
- **Tests to run, at the base and at HEAD:** `tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py tests/test_pbr_decision_case_fixtures.py`. For the base run, use a throwaway worktree: `git worktree add -q --detach ~/lanes/tmp/pbr-res-r1766/basewt 05a9eb52` and remove it afterwards with `git worktree remove --force`.

## What was commissioned (from review R-1750-r2's three MINORs)
1. In `brain/facts.py`, rename `classless_record_count` to `excluded_non_primary_record_count` everywhere: the `_primary_records` return docstring and local variable, the `_verify_event_date`/compare parameter and its call site, and the emitted `compared` key. Update the assertion in `tests/test_pbr_facts.py`. Change no count value, add no counter, and leave `other_identity_record_count` alone.
2. Change only the Step 3 comment at `brain/shadow_risk_budget.py:401-403`: a contradicted or basis-unreconciled supporting fact multiplies by the configured `unreconciled_fact_factor` (0.0 in the frozen config), not "by zero".
3. In `docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md` §8 E1 item 6, "both fixture `external_facts`" becomes "both event-dated fixture `external_facts`". Nothing else in that file changes.

## Acceptance criteria
**C1. Scope.** `git diff --name-status 05a9eb52..HEAD` touches exactly these four files: `brain/facts.py`, `brain/shadow_risk_budget.py`, `docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md`, `tests/test_pbr_facts.py`. Anything else is a finding.
**C2. The rename is complete and value-preserving.** `git grep -n classless_record_count` at HEAD returns nothing anywhere in the repository. The renamed counter is computed by the same expression as before (cite base and HEAD lines), and every consumer of the `compared` dict in the repo (search for the key and for `compared[`/`compared.get`) is either updated or unaffected. Name any reader of the old key that would now silently get `None` or `KeyError`.
**C3. The comment is now true.** Read the code next to `brain/shadow_risk_budget.py:401-403` and the frozen config value of `unreconciled_fact_factor` (cite the file and line where it is set). Confirm that the comment matches what the code does. The code itself must be byte-identical apart from the comment lines.
**C4. The spec item is now true.** Confirm from the fixture (cite path:line) that exactly two of its `external_facts` carry `event_date`, so that "both event-dated" is accurate, and that the spec diff is one line.
**C5. Tests.** Pass/fail/skip counts at the base and at HEAD must be identical. A changed count, or any new failure, is a finding.
**C6. Public-repo rule.** No IP literal, URL, credential, capture-derived literal or PM prose in the diff.
**C7. No behaviour change.** Apart from the emitted key name, nothing observable changes. State whether any persisted artifact, fixture or golden file in the repo embeds the old key.
