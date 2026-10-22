# OPERATION pbr-res-r1701r3 — independent DELTA re-review of PR #1701 (findings F1/F2 of R-1701-r2)
Class: review · Complexity: C2 · Output: ONE file `~/lanes/tmp/pbr-res-r1701r2/out/REVIEW-r3.md` (this lane's tmp dir is `~/lanes/tmp/pbr-res-r1701r2/`; wherever the common rules below say REVIEW.md, read REVIEW-r3.md — never overwrite the prior REVIEW.md). You change no repository file.

## Target (exact)
- PR mastermindx-market-intelligence/Mastermind#1701, branch `pbr/research-w6-facts-thesis-budget-spec`, head `a654035853b9316dde2b273c38a94a153ccd273d` (verify `git rev-parse HEAD`). Base for this delta: `5d35d0f0eb84de565ea2bfd9880db6dcc5a12d29`. Read `git diff 5d35d0f0..HEAD` (one file, `docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md`).
- Prior review (yours to re-check): `~/lanes/tmp/pbr-res-r1701r2/out/REVIEW.md` (sha256 `9fc32dff6345ca31007083a5fe0d28e015d7adbd4072b3671391b8944623befe`); its F1 (MAJOR, rule (2) cannot supply the why_now/exit_plan event_date) and F2 (MINOR, XOM row attribution and distances).
- Out-of-repo inputs (read-only; this repo is PUBLIC — copy no PM prose into your output): `~/lanes/tmp/pbr-res-r1701r2/inputs/{case_rows.jsonl,case_fills.jsonl,MANIFEST.json}`. Verify sha256 `3f2fae42e8bb062c02400e30acac2d06db8b754dd61be095addb6f11e62e49f9`, `ca0390d5968cfe111b5beabab6396a4f5a2904c616ab6db3fd74a282b85ab6bc` and `4c55f3f8df454ecfcb2742b0b7bec5043ac35d4919a66026888541fa4bf976aa`.
- Fixtures for digest checks: `git show a641e69a45f40114b3ca70233c41cff5f283b1b6:tests/fixtures/pbr/decision_cases/<name>.json` (fetch that commit if absent: `git fetch origin pbr/research-w6-decision-case-fixtures`).

## Acceptance (cite path:line)
D1. F1 closed: rule (2) now qualifies on a digest recording a date; rule (3) declares the MU why_now and exit_plan catalyst event_date 2026-10-22 as a typed claim with digest-path provenance plus an env-gated month/day-token occurrence check. Verify against the inputs, by sha256 match and without printing prose, that both originals behind `abd5e36612e0` and `bda8a5c4fd80` contain the token `10/22` and no ISO date. Check that the four-component test at §5.1 is now implementable without cross-field date import (§2.2(i)). Check that nothing in the new text contradicts §2.2 or another rule.
D2. F2 closed: the XOM cell attributes add/medium/0.10 to row 38 and records row 39 weight 0.100178 and row 40 add/high/0.15. Check the distances 153 (about 3.2% below) and 137.50 (about 13.0% below) against fill 158.03. Verify each value from the inputs.
D3. No PM prose: run your own sliding-window scan (30-char windows, step ≤ 5) of the whole spec at HEAD against every whitespace-containing string in both input files; report the hit count. A hit on a bare enum/identifier is not a leak; say which.
D4. Scope: one file; no other section changed (`git diff --stat`).

## Output
REVIEW-r3.md: per-criterion PASS/FAIL with evidence; numbered findings (severity BLOCKER/MAJOR/MINOR, path:line, smallest fix); last line exactly `VERDICT: PASS|FAIL|PARTIAL`. Print the file's sha256 at the end of your reply. Run no repository tests.

## Independent review rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research`. You are an independent reviewer leaf: you did not build this change and must not repair it. No nested workers.
- Your working directory is a detached worktree at the exact PR head named above. `origin/master` base is 230e9a301 unless stated. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY `~/lanes/tmp/<this lane>/out/REVIEW.md` (path given above). Never edit repository files, commit, push, or comment on GitHub.
- Forbidden: network access; credentials/.env/keys; running the bot, scheduler, server or anything against live data.
- Method: (1) read the commissioning packet excerpt and acceptance criteria above; (2) read the full diff `git diff 230e9a301..HEAD`; (3) run the named tests with `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <files>` and report counts; (4) check each acceptance criterion against the actual code/text, citing `path:line`; (5) for code, attempt to break it: a test that passes on the old code is not discriminating; an `xfail(raises=...)` that can absorb the wrong exception is a defect; any import of registry/pending-target/settlement code from a shadow or snapshot module is a defect.
- Severity: BLOCKER (acceptance criterion unmet, false claim, unsafe path), MAJOR (correctness/clarity problem a later lane will trip on), MINOR (polish).
- `REVIEW.md` and your final message both end with exactly one line `VERDICT: PASS` (no BLOCKER and no MAJOR), `VERDICT: PARTIAL` (no BLOCKER, ≥1 MAJOR) or `VERDICT: FAIL` (≥1 BLOCKER), preceded by numbered findings `F1..Fn` each with severity, `path:line`, problem, and the smallest fix.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value.
- Your final assistant message is the ONLY thing returned: emit the full REVIEW.md content plus `sha256sum` of REVIEW.md as your last message.
