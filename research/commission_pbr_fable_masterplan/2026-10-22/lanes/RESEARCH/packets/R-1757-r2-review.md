# OPERATION pbr-res-r1757r2: independent DELTA review of PR #1757 fix round 1 (append-only decision ledger, W2-R4)

Class: review · Complexity: C2 · Output: ONE file, `~/lanes/tmp/pbr-res-r1757r2/out/REVIEW.md`. You change no repository file.

## Target (exact)
- **PR:** mastermindx-market-intelligence/Mastermind#1757, branch `pbr/research-w2-r4-supersedes`, head `8c47d5210f2b21e3ac0b5f68fb7ec0f9c4227a13`. Verify with `git rev-parse HEAD`.
- **Prior reviewed head:** `5c4a8658b3ef4c47445742d1ab28361856bb00f0` (review R-1757, VERDICT PARTIAL). **PR base:** `05a9eb52a54e29fb7bbd0d40813ed12623b176c7`.
- Read the DELTA as `git diff 5c4a8658..HEAD` (primary) and consult `git diff 05a9eb52..HEAD` only for context. This overrides the base default below.
- **Scratch:** you MAY write throwaway scripts under `~/lanes/tmp/pbr-res-r1757r2/scratch/` (only there and REVIEW.md). If you mutate a tracked file to probe, restore it and show `git status --porcelain` empty at the end.
- **Tests to run:** `tests/test_decision_rows.py tests/test_decision_rows_supersedes.py tests/test_decision_rows_supersedes_replay.py tests/test_decision_submission_v2.py tests/test_decision_settlement_reconciliation.py tests/test_portfolio_learning.py tests/test_posture.py tests/test_forward_evaluation.py tests/test_calibration.py tests/test_desk_ab.py tests/test_decision_availability.py`
- **Known lane-environment failures** are listed in `~/lanes/tmp/pbr-res-w2r4-fix1/baseline_failures.txt` (read-only). Classify every failure as pre-existing or NEW; a NEW failure is a finding.

## Prior findings and what fix round 1 was asked to do
- **F2 (MAJOR)** `scripts/remove_positions.py` docstring promised byte erasure; the append-only ledger keeps superseded bytes by design. Asked: docstring-only scoping to the effective view, no behaviour change.
- **F3** scrub scripts crashed on duplicate identical effective rows (`ValueError` from the revise guard) and rows missing `asof` (`KeyError`). Asked: skip a re-revise of an identity already revised in the run (its drops still counted); skip rows without `asof` (not counted) with one stderr count line; tests that fail at 5c4a8658.
- **F4** `brain/decision_submission.py::_latest_holdings`: one malformed line anywhere aborted the prior-target scan. Asked: lenient per-line parse (skip malformed/non-dict) before the effective view, keep the reversed scan; a test that fails at 5c4a8658; no allocation arithmetic change.
- **F5** static append-only guard was a name-based tripwire over 9 dirs. Asked: whole-repo scan (minus vendor/tests/research/docs/node_modules/dot-dirs), alias-import, getattr and direct-byte-write-on-`decisions.jsonl` detection, a helper with a discriminating synthetic test; allowlist only provable non-writers with a justification.
- **F7** `row_identity` docstring: identity, not tamper evidence. **F8** memoize `_slot` in `effective_rows`, identical semantics, long-chain test.
- **F1 (MAJOR, PRODUCT-owned `app/decision_availability.py` raw-row cap):** NOT part of this delta. The seat's GO forbids PRODUCT reader-logic changes in this PR and a seat ruling on F1 is pending. Record F1 in a separate `## Carried` section as CARRIED (open, seat ruling pending); do not re-score it and do not count it toward the VERDICT. Base the VERDICT on the delta and the fixes of F2-F8 only.
- F6/F9/F10 were notes; no change expected.

## Acceptance criteria
**B1. Delta scope.** `git diff --name-status 5c4a8658..HEAD` touches only: `bot/decision_rows.py`, `brain/decision_submission.py`, `scripts/remove_positions.py`, `scripts/scrub_cn_tiny_trims.py`, `tests/test_decision_rows_supersedes.py`, `tests/test_decision_submission_v2.py`. Anything else is a finding.
**B2. Each fix is real.** For F3, F4, F5, F8: show the new test fails (or the guard misses) on the 5c4a8658 version of the fixed file and passes at HEAD — run it yourself (e.g. load `git show 5c4a8658:<path>` from scratch). A test that passes on the old code is not discriminating.
**B3. No semantic drift in the accessor.** `effective_rows` output must be identical to 5c4a8658's for every input: diff the two implementations and run a randomized comparison (≥ 200 trials incl. revise chains, cross-asof/unknown/self pointers, duplicates, non-dict items) between `git show 5c4a8658:bot/decision_rows.py` and HEAD. Report trial count and mismatches.
**B4. Append-only law still holds** in the scrub scripts and every writer touched by the delta: no rewrite, reorder or delete of an existing ledger line; F3's skip paths write nothing.
**B5. F4 boundary.** Only the prior-target record source changed; prior-target selection order, account authority and allocation arithmetic are unchanged (cite lines). Missing file / unreadable file paths still degrade exactly as before.
**B6. F5 guard quality.** Run the new guard; list what it flags and allowlists; try at least three evasions it should catch and one it still misses (name the residual class honestly). Check its runtime.
**B7. Public-repo rule.** No IP literal, URL, credential, capture-derived literal or PM prose in the delta; tests write only under `tmp_path`.
**B8. Prior PASS areas unchanged.** Confirm the delta does not touch settlement reconciliation, writer locks, the five book writers, or the ECON readers (zero diff on `bot/etf.py`, `bot/heavyweight.py`, `portfolio/etf_outcomes.py`, `portfolio/heavyweight_outcomes.py`, `bot/settle.py`).
