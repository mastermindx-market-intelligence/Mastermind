# OPERATION pbr-res-w2r5-minors: three review MINORs from R-1750-r2 (naming, a stale comment, one spec word)

Class: build · Complexity: C1_ROUTINE_BOUNDED · Text- and naming-only. There is no behaviour change, and no live call path.

## Base (overrides the base line in Common rules)

Your worktree is a detached checkout of `origin/master` at `05a9eb52`. Touch only the four files named below.

## The three changes (exact)

**F1. Rename the `compared` field.** In `brain/facts.py`, rename `classless_record_count` to `excluded_non_primary_record_count` everywhere:
- the `_primary_records` return docstring (≈:372) and its local variable;
- the `_compare` parameter (≈:437) and its call sites;
- the emitted dict key (≈:487).

Update `tests/test_pbr_facts.py:543` to assert the new key. Before finishing, run `git grep -n classless_record_count`: it must return nothing in `brain/` or `tests/`.
- Do not change any count's value.
- Do not add a second counter.
- Do not touch `other_identity_record_count`.

**F2. Reword the comment at `brain/shadow_risk_budget.py:401-402`.** The current comment reads "a contradicted or basis-unreconciled supporting fact multiplies by zero". Change it to say that such a fact multiplies by the configured `unreconciled_fact_factor` (0.0 in the frozen config). Change only the comment; no code changes.

**F3. Change one word in `docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md:230`** (§8 E1 item 6):
- "both fixture `external_facts`" becomes "both event-dated fixture `external_facts`".
- Change nothing else in that file.

## Tests

`tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py tests/test_pbr_decision_case_fixtures.py`
- Run them once at the base, before editing, and once after.
- The counts must be identical, apart from the renamed assertion still passing.

## Output

- Write `git diff` of your changes to `~/lanes/tmp/pbr-res-w2r5-minors/out/W2R5.diff`.
- Do not commit.

## RETURN block (your last message)

```
RETURN pbr-res-w2r5-minors
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every changed file, plus out/W2R5.diff)
TESTS_BASELINE: <verbatim summary>   TESTS_NEW: <verbatim summary>
GREP: <output of git grep -n classless_record_count -- brain tests, or "empty">
F1/F2/F3: <done + file:line each>
DEVIATIONS: <numbered, or none>
```

## Common rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research` (Opus), who keeps every git, PR, review and merge step. You are a bounded leaf. No nested workers.
- Repository: your current working directory is a detached worktree of Mastermind at `origin/master` 05a9eb52 (see Base). Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY the output paths named in this packet. Never commit, push, open or comment on PRs, edit other files, or touch `~/lanes/repos/Mastermind` directly.
- Forbidden: network access except none (no web fetches, no APIs); reading credentials/.env/keys; running the bot, scheduler, server or anything against live data; any account reset, seed rewrite, balancing fill, or "repair" trade; changing `brain/decision_submission.py` allocation behaviour; resetting or redefining the V2 marker (sha256 75d5182d…) or the August-11 cohort.
- Shadow/new modules terminate in isolated storage: no registry membership, no pending-target route, no settlement call.
- Tests (only when this packet names them): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <named files>`.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value. If blocked, stop and report the exact blocker.
- Your final assistant message is the ONLY thing returned. **Emit the full RETURN block (format below) as your last message**, including the file list with `sha256sum` of every file you wrote.
