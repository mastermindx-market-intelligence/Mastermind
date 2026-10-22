# OPERATION pbr-res-r1757b: independent review of PR #1757 `feat(decision-rows)`, the append-only decision ledger with supersedes and an effective-row accessor (W2-R4)

Class: review · Complexity: C2 · Output: ONE file, `~/lanes/tmp/pbr-res-r1757b/out/REVIEW.md`. You change no repository file.

## Target (exact)

- **PR:** mastermindx-market-intelligence/Mastermind#1757, branch `pbr/research-w2-r4-supersedes`, head `5c4a8658b3ef4c47445742d1ab28361856bb00f0`. Verify it with `git rev-parse HEAD`.
- **Base for this review:** `05a9eb52a54e29fb7bbd0d40813ed12623b176c7`, which is `origin/master`. Read the diff as `git diff 05a9eb52..HEAD`. This overrides the base default given below.
- **Scratch:** you MAY write throwaway scripts under `~/lanes/tmp/pbr-res-r1757b/scratch/`. That directory and REVIEW.md are your only writable paths.
- **Tests to run:**
  `tests/test_decision_rows.py tests/test_decision_rows_supersedes.py tests/test_decision_rows_supersedes_replay.py tests/test_decision_settlement_reconciliation.py tests/test_retry_no_duplicate_effect.py tests/test_settlement_receipt_retention.py tests/test_posture.py tests/test_calibration.py tests/test_forward_evaluation.py tests/test_desk_ab.py tests/test_decision_availability.py tests/test_portfolio_learning.py tests/test_decision_submission_v2.py tests/test_heavyweight.py tests/test_etf_book.py tests/test_china_book.py tests/test_autonomous_portfolio.py`
- **Known lane-environment failures:** this venv has known failures, such as missing vendored `lib` and calendar/price fixtures. The builder recorded them at the base in `~/lanes/tmp/pbr-res-w2r4-sup/baseline_failures.txt` (read-only to you).
  - Classify each failure you see as pre-existing (listed there) or NEW.
  - A NEW failure is a finding.

## What the builder was asked to do (seat GO for W2-R4 step 2, summarised)

1. **Append-only.** `replace_for_asof` becomes append-with-`supersedes=<prior row id>`. Prior bytes are retained, with no in-place overwrite anywhere. The 11 writers converge on that one writer API.
2. **One effective-row accessor** preserves the one-row-per-asof contract for all readers. Readers change only where a raw read must become the accessor call. No PRODUCT reader logic changes.
3. **Settlement.** `bot/settle.py:902` and `:986` keep raising `DecisionSettlementConflict` on a genuine double-settlement but read the effective row. The discriminating tests must show:
   - a superseded row no longer raises a false conflict;
   - a true conflict still raises.
4. **ECON readers.** The ECON-owned readers `portfolio/heavyweight_outcomes.py` and `portfolio/etf_outcomes.py` are touched only via the accessor. The builder left them at zero diff; they consume `load_decisions()`.
5. **Regression.** Replaying a run-event capture through the new writer must give an effective view equal to master's view for every asof, with payloads byte-equal except for the new fields.
   - Here, only the synthetic replay test and the env-gated capture test's code are reviewable.
   - The capture itself is not on this host; the test skips without it.

**The builder's design:**
- New row fields, in this order: `supersedes` (list of row ids), `supersede_mode` (`"asof"` | `"revise"`), and `row_id`.
  - `row_id` is `row.v1.` plus a canonical sha256 prefix of the row without `row_id`.
- The new API is `row_identity`, `effective_rows`, `read_effective_rows`, `plan_decision_row` and `append_decision_row`, which is the one writer.
- `reconcile_settlement`, `refresh_lesson_links` and `validate_queued_decision_snapshot` match over effective rows and append revise rows.

## Acceptance criteria (cite path:line)

**A1. File scope.** The diff touches exactly these files, and nothing else:
- `app/decision_availability.py`, `bot/{autonomous,china,hk,etf,heavyweight,decision_rows}.py`;
- `brain/{calibration,decision_submission,portfolio_learning,posture}.py`, `portfolio/{desk_ab,forward_evaluation}.py`;
- `scripts/{remove_positions,scrub_cn_tiny_trims}.py`;
- the 4 modified tests and the 2 new tests.

Confirm zero diff for each of these: `bot/settle.py`, `portfolio/heavyweight_outcomes.py`, `portfolio/etf_outcomes.py`, `app/web.py`, `brain/management_lifecycle.py`, `app/decision_availability_selection.py`, `config/`.

**A2. Append-only, whole tree.** At HEAD, `git grep` the whole tree, excluding `research/` and `docs/`, for every code path that can write, truncate or rewrite a per-book `decisions.jsonl`:
- `decisions.jsonl` literals;
- `write_text`, `open(... "w"`, `os.replace` and `shutil` on a decision path;
- `_atomic_write_rows`, `write_rows(` and `replace_for_asof(` callers.

Name any production writer that still rewrites prior bytes or bypasses `append_decision_row`. Verify these properties of `append_decision_row`:
- the payload is `old_bytes + optional separator + one line`;
- the write is atomic;
- `assert payload.startswith(old_bytes)` is the only invariant check. Note that it is stripped under `python -O`.

Is the static guard `test_no_production_module_rewrites_the_decision_ledger` sound? What does it scan, and what could evade it, such as an alias import or a `write_bytes`?

**A3. Accessor semantics.** Read `effective_rows` line by line and attack it. Cover each of these cases:
- a legacy file with no pointers (it must return the input unchanged, in order);
- a pointer to an unknown id;
- a pointer to a row of a different asof;
- a cycle or self-pointer;
- duplicate byte-identical rows that share one `row_id`;
- a stored `row_id` that does not match its content (tamper);
- a revise of a revise;
- an asof row after a revise;
- non-dict rows in strict and in lenient mode;
- the `tail=` semantics.

For each case, state what happens and whether the one-row-per-asof contract holds. Then check `tests/test_decision_rows_supersedes.py`:
- the property test against the verbatim copy of master's `replace_for_asof`. Is the copy truly verbatim with the base? Diff it against `git show 05a9eb52:bot/decision_rows.py`.
- whether its generator covers barren-after-substantive, identical re-write and multi-asof interleaving.

**A4. Readers.** List every reader of a decision ledger at HEAD (`load_decisions`, `read_rows(`, raw `decisions.jsonl` reads), including ones the PR did not touch. For each untouched raw reader, say whether it now sees superseded rows and whether that changes behaviour. Typical traps:
- counting rows;
- last-line-wins;
- `_MAX_ROWS` caps;
- tail-N reads.

Check that each touched reader is a pure raw-to-accessor substitution, especially `app/decision_availability.py`, which is PRODUCT-owned and must have no logic change. Also check `brain/posture.py`'s tail change and `brain/decision_submission.py`'s malformed-line behaviour change.

**A5. Settlement discrimination.**
- `bot/settle.py` is unchanged; confirm it, and identify what it calls at the two `DecisionSettlementConflict` sites.
- For the three settlement tests the builder cites in `tests/test_decision_rows_supersedes.py` (retry over a superseded row stays idempotent; a different transaction raises lineage conflict; two unsuperseded queued rows raise "exactly one"), prove discrimination. Write a scratch script that loads the base `bot/decision_rows.py` (`git show 05a9eb52:bot/decision_rows.py > scratch/master_decision_rows.py`, then import it by path). Build the same ledger the test builds, and show that master's `reconcile_settlement` matching raises a false conflict on the superseded case.
- Also mutate HEAD's `effective_rows`, for example by making revise mode behave like asof mode or by ignoring pointers. Copy the original aside under `scratch/`, then show which new tests fail. Restore it and confirm that `git status --porcelain` is empty.

**A6. Identity and hashes.** Do the new fields leak into any identity or hash that must stay stable? Check:
- `_row_target_sha256`, `accepted_identity_fields` and `target_sha256`;
- `validate_queued_decision_snapshot` exact matching;
- decision-snapshot digests;
- `paper_account` pending-target bindings;
- `brain/decision_submission.py` receipts.

`git grep` for consumers that hash or compare a whole decision row. Is `strip_supersession` applied wherever a row is compared to a pre-W2-R4 row?

**A7. Writers.** For each of the 11 writers, check:
- the lock it held on master is still held (autonomous, china and hk are strict and locked; etf and heavyweight are lenient and unlocked, as on master);
- strict versus lenient parse matches master's behaviour on a malformed line;
- the return value and side effects are unchanged.

**A8. Scrub scripts** (`scripts/remove_positions.py`, `scripts/scrub_cn_tiny_trims.py`): check their behaviour on duplicate identical rows, on rows missing `asof`, and on the `ensure_ascii` change. These are operator-only scripts, so state the severity accordingly.

**A9. Performance.** `effective_rows` is called on every `load_decisions` path. State its complexity, and flag any quadratic step on a ledger of a few thousand rows.

**A10. Public-repo rule.** The diff contains no capture-derived literal, PM prose or IP address. Tests write only under `tmp_path`, make no network call, and touch no live path. The capture test is env-gated and skips cleanly.
