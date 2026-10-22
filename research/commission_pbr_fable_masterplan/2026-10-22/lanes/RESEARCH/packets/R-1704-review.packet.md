# OPERATION pbr-res-r1704 — independent review of PR #1704 `[PBR][W7/W8][SPEC]` experiment registry and protocols
Class: review · Complexity: C2 · Output: ONE file `~/lanes/tmp/pbr-res-r1704/out/REVIEW.md`. You change no repository file.

## Target (exact)
- PR mastermindx-market-intelligence/Mastermind#1704, branch `pbr/research-w78-experiment-protocols`, head `6d1195f8f84b77e270b943c76904f24e72b995ae` (your worktree is detached here; verify with `git rev-parse HEAD`).
- **Base for this review: `d31aade92b969e8897513d8634ecd59dba00e1e3` (merge-base with origin/master). Read the diff as `git diff d31aade9..HEAD`.** (This overrides the "230e9a301" default in the rules below.)
- Changed file: `docs/superpowers/specs/2026-10-22-pbr-experiment-registry-and-protocols.md` (docs only; no tests to run — state that and run none).
- Reference inputs (read-only): `~/lanes/tmp/pbr-res-r1704/MASTERPLAN.md` (sha256 4c7a0d449f02de080e4d8d310af5db09515af86683ac6a3bca1298f2e034d970 — verify) and the repo files the spec cites.

## Acceptance criteria (from the commissioning packet L-S6; check each, cite path:line in the spec AND the source it relies on)
A1. Authority + non-goals: protocols only; no code, no promotion, no live effect; V2 marker and August-11 cohort never reset or redefined; three verdicts reported separately; the document claims no investment value.
A2. Trial registry (masterplan §9.1): immutable `pbr.trial_protocol.v1` schema with hypothesis, owner, policy version, simulator version, data versions, universe, dates (design/train/validation/test, embargo/purge), cost model, primary metric, economic minimum declared before unblinding, risk limits, comparison family, sample floors, stopping rule, status, failed/abandoned variants retained. Registration rules (register before running; amendments = new version; abandoned trials stay in the family). Storage location is a proposal flagged as a seat decision.
A3. E0–E6 (§9.2): one subsection each with hold-fixed, compared arms (incl. current categorical allocator and equal-weight controls where §9.2 names them), primary + secondary metrics, economic-minimum placeholder + how it is set, main falsifier, sample floor, dependency gates (E1/E2/E5 V3 order; cash/exit diagnostics cannot promote parameters early), prospective vs retrospective data, the common-economic-model rule (corrected economics never credited as policy alpha).
A4. Benchmark ladder (§6.2) and metrics (§6.3) tables per book/currency — check they match the masterplan, not invented.
A5. Statistical discipline (§9.4): paired differences, declared block bootstrap with a block-length rule, effective-sample reporting, clustered dates / overlapping horizons, multiple-comparison control over the registered family (incl. Deflated Sharpe applicability conditions), cost/delay stress, a "no rescue search" rule, negative/inconclusive is a valid outcome.
A6. Preserved gates (§9.5) quoted EXACTLY: V2 first-review floors (60 matched sessions, 40 effective PM decisions, 12 material-change decisions, ≥95% applicable coverage, no unresolved integrity defects; churn ruling 30 authoritative full-close episodes) and the V3 ladder (first vertical / 20 / 60 / 126 / 252 sessions with conditions) with section citations; plus the power/economic-materiality analysis requirement. **Compare every number character-for-character against MASTERPLAN.md and against `portfolio/forward_evaluation.py` / `docs/PORTFOLIO_V2_FORWARD_EVALUATION_2026-08-11.md`; any drift is a BLOCKER.**
A7. HK prospective opening checkpoint rule as a protocol: components enumerated, corroborated vs assumed labelling, pending-effect disposition, unsupported cost basis cannot become certified realized P&L, checkpoint visible in every affected evaluation; ECON owns any accounting proposal.
A8. Attribution chain (§9.3): `snapshot → claim → PM view → target → feasible order → receipt → fill → position episode → outcome`; proposed/queued actions are unexecuted until receipts.
A9. Open questions are consequential only; doc under ~500 lines; every factual claim cites a masterplan section or repo file:line — **spot-check at least 10 repo file:line citations by opening the file at that line**; a citation that does not support its claim is MAJOR (BLOCKER if it misstates a preserved floor or the V2 marker/cohort).
A10. Safety: nothing in the doc authorizes resetting the V2 marker/cohort, registry membership, a pending-target route, settlement, or promotion; no statistic of `portfolio/forward_evaluation.py` is redefined.

## Also check
- The spec's statements about the V2 marker (sha256 75d5182d…) and cohort location match `portfolio/forward_evaluation.py` (around lines 282 and 528–546).
- Internal consistency: E-numbering, dependency order, and floors used identically across sections.

## Independent review rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research`. You are an independent reviewer leaf: you did not build this change and must not repair it. No nested workers.
- Your working directory is a detached worktree at the exact PR head named above. `origin/master` base is d31aade9 unless stated. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY `~/lanes/tmp/<this lane>/out/REVIEW.md` (path given above). Never edit repository files, commit, push, or comment on GitHub.
- Forbidden: network access; credentials/.env/keys; running the bot, scheduler, server or anything against live data.
- Method: (1) read the commissioning packet excerpt and acceptance criteria above; (2) read the full diff `git diff d31aade9..HEAD`; (3) run the named tests with `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <files>` and report counts; (4) check each acceptance criterion against the actual code/text, citing `path:line`; (5) for code, attempt to break it: a test that passes on the old code is not discriminating; an `xfail(raises=...)` that can absorb the wrong exception is a defect; any import of registry/pending-target/settlement code from a shadow or snapshot module is a defect.
- Severity: BLOCKER (acceptance criterion unmet, false claim, unsafe path), MAJOR (correctness/clarity problem a later lane will trip on), MINOR (polish).
- `REVIEW.md` and your final message both end with exactly one line `VERDICT: PASS` (no BLOCKER and no MAJOR), `VERDICT: PARTIAL` (no BLOCKER, ≥1 MAJOR) or `VERDICT: FAIL` (≥1 BLOCKER), preceded by numbered findings `F1..Fn` each with severity, `path:line`, problem, and the smallest fix.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value.
- Your final assistant message is the ONLY thing returned: emit the full REVIEW.md content plus `sha256sum` of REVIEW.md as your last message.
