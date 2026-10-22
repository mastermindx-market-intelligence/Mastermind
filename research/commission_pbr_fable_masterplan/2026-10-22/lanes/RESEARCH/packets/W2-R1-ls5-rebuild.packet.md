# OPERATION pbr-res-w2r1-ls5 — rebuild typed PM facts, durable thesis store and shadow risk budget on the redacted fixture shape, with the seat's Q1–Q4 rulings and the three regressions enforced
Class: build · Complexity: C2_COMPLEX_BOUNDED · New isolated modules plus tests. NOT wired into live decisions.

## Base (overrides the Common-rules base line)
Your worktree is a detached checkout of `origin/master` @ `f14fac19`. It already holds the five SR-1 redacted case fixtures
under `tests/fixtures/pbr/decision_cases/`, `tests/fixtures/pbr/DECISION_CASES.md`, `tests/fixtures/pbr/_build_decision_cases.py`
and `tests/test_pbr_decision_case_fixtures.py`. Use them in place; never modify them.

## Inputs (read-only)
- `~/lanes/tmp/pbr-res-w2r1-ls5/SPEC.md`: the spec (PR #1701 head `a654035`). Read it completely first. Interfaces, enums, schemas,
  the 20 named tests (§5), the SR-1 fixture rules (1)–(4) in §5 and the non-goals (§6) are binding, EXCEPT where the seat rulings
  below change them. Where they conflict, the rulings win; list each such point under DEVIATIONS as "ruling-driven".
- `~/lanes/tmp/pbr-res-w2r1-ls5/prior/`: a non-authoritative earlier draft (`brain/facts.py`, `brain/thesis_store.py`,
  `brain/shadow_risk_budget.py`, `tests/test_pbr_thesis_store.py`, `tests/test_pbr_shadow_risk_budget.py`). It was written against
  the pre-redaction fixture shape (prose as plain strings) and before the rulings. Reuse what is correct; do not trust it.
- `config/pbr_shadow_risk_budget.yml`: ALREADY PRESENT in your worktree (untracked), written by the parent before any test
  exists. sha256 `355eba682718818246c419735b7ad5de8acaffd945deaa47f7ce6da181351806`. **Do not modify it.** If you believe it must
  change, stop and report BLOCKED with the reason; do not edit it.
- `~/lanes/tmp/pbr-res-w2r1-ls5/inputs/` (case_rows.jsonl, case_fills.jsonl, MANIFEST.json): the ORIGINAL off-repo extracts for
  the env-gated tests only. They contain original PM prose. Never copy, quote, paraphrase or excerpt any of their text into any
  file you write. Use them only through `PBR_DECISION_CASE_INPUT_DIR`.
- `brain/decision_submission.py` (read-only: `normalize`, `_allocate_deterministically`, the categorical caps, `_latest_holdings`,
  `_instrument_identity_for_book`), `brain/calibration.py` (read-only), `portfolio/marks.py` (read-only: the ECON union-mark
  store `data/marks/<asof>.json` and `mark_symbols()` `sources`; do NOT import it from the new modules).

## Seat rulings (binding; they override the spec where they differ)
- **Q1.** `AMENDMENT_WATCHED_FIELDS` is one module constant in `brain/thesis_store.py`, mapping thesis fields to the holding-row
  fields they watch: thesis_statement←rationale, falsifiers←falsifier, check_by/time_stop←expected_horizon,
  exit_conditions←exit_plan, size_cap/target_weight←proposed_weight, catalyst←why_now. A null/absent `proposed_weight` in the later
  row means "not restated", not a change. Realised `weight` and `weight_source` are never watched. **Conviction is NOT watched**: it
  is a per-cycle observation, recorded append-only in `observations.jsonl` under the caller's `store_dir`, schema
  `pbr.thesis_observation.v1`, carrying `thesis_id`, `cycle_id` (= the row's `decision_id`), `asof`, `field`, `value`. It never
  produces an amendment or an UNRECORDED_AMENDMENT finding. This changes spec §3.3 and the expected content of
  `test_unrecorded_amendment_detected_mu_75_to_76`: the finding lists falsifier and exit_plan (and any other watched field the
  fixture's `derived.case_holding_changes` shows changed) and must NOT list conviction; the MU medium→high change is recorded
  as an observation instead.
- **The MU silent amendment is REJECTED, not just reported.** Add `check_continuity(store_dir, prior_row, new_row) -> verdict`
  (or an equivalent single function; name it in RETURN) that, when a watched field changed between consecutive held-episode rows
  and no AmendmentRecord links the two decision ids, returns status `REJECTED_UNRECORDED_AMENDMENT` with the
  UNRECORDED_AMENDMENT finding and leaves the stored thesis unchanged (`thesis_as_of` still returns the original falsifiers and
  exit conditions). With a covering AmendmentRecord it returns an accepted status. This is a shadow verdict on the lineage, never a
  live-action veto.
- **Q2.** The §2.2(ii) reference mark is a typed `ReferenceMark` (schema `pbr.reference_mark.v1`) with `value`, `currency`,
  `basis`, `symbol`, `asof` and `source` ∈ {`ECON_UNION_MARK`, `CALLER_SUPPLIED`}. Only `ECON_UNION_MARK` with complete
  provenance (`store_ref`, `asof`, `symbol`, `mark_source`, all non-empty; mark `asof` ≤ the fact's decision asof; symbol equal to
  the fact's) qualifies. `CALLER_SUPPLIED`, an incomplete-provenance mark, or no mark at all → outcome `BASIS_UNRECONCILED` with
  reason `reference_mark_not_qualified` (or `reference_mark_absent`), never VERIFIED and never "inside band". Remove the spec's
  "else the episode entry fill" fallback: a fill price is not a qualifying mark. In tests, build the ECON mark as a test double
  with `store_ref="test-double"`, `mark_source="test-double"` and the value of the cited fixture fill; say so in a comment.
- **Q3.** `freeze_owner` is `pbr-seat` (already in the config). The three new modules are shadow-only: no file on any sizing or
  decision path may import them. Add the negative test below.
- **Q4.** AmendmentRecord carries `reason_code` from the closed enum {FALSIFIED, TIME_STOP, EXIT_PLAN_HIT, SUPERSEDED, MANUAL},
  REQUIRED when the amendment is terminal (INVALIDATED / EXCLUDED) and validated for every amendment that carries one. An
  optional free-text `note` is accepted by the runtime API as a plain string (runtime records live off-repo). In fixtures and
  tests the note is never prose: tests pass a `pbr.prose_digest.v1`-shaped dict (sha256 + length) or omit it.
- **CR-R7.** Schema/version strings are module constants (`pbr.fact.v1`, `pbr.thesis.v1`, `pbr.thesis_amendment.v1`,
  `pbr.thesis_observation.v1`, `pbr.reference_mark.v1`, `pbr.shadow_risk_budget_params.v1`). Tests pin them. Do NOT add anything
  to `config/contracts.yml`.
- **SR-1.** No original PM prose in any file you write: no narrative sentence, phrase or excerpt from a fixture's original text.
  Use digests' `sha256`/`length`/`iso_dates`/`period_labels`/`terms`, typed fields and the declared values of spec §5 rule (3).

## Outputs (create ONLY these)
1. `brain/facts.py`, `brain/thesis_store.py`, `brain/shadow_risk_budget.py` per SPEC §2–§4 and the rulings.
   - Storage only under a caller-supplied `store_dir: Path`; no default path, no module-level data path, no writes elsewhere.
   - Imports: stdlib + `yaml` + read-only `brain.calibration` constants if needed. Must NOT import `brain.decision_submission`,
     `brain.ledger`, `portfolio.*`, `bot.*`, `app.*`, `loop.*`, any pending-target/order/fill writer or any network client.
   - `shadow_risk_budget` loads params from a caller-supplied config path and refuses a missing `frozen_at`, `freeze_owner`,
     `version` or any bare (missing/empty) `justification`.
2. Tests: exactly the 20 named tests of SPEC §5 across `tests/test_pbr_facts.py`, `tests/test_pbr_thesis_store.py`,
   `tests/test_pbr_shadow_risk_budget.py` (content adjusted only where a ruling requires), plus these extra tests:
   - `test_pbr_thesis_store.py::test_conviction_change_is_observation_not_amendment`: a perturbed row pair differing ONLY in
     conviction → no UNRECORDED_AMENDMENT, continuity accepted, and one `pbr.thesis_observation.v1` line with the later
     `decision_id` as `cycle_id`.
   - `test_pbr_thesis_store.py::test_mu_silent_amendment_rejected`: MU 75→76 with no AmendmentRecord →
     `REJECTED_UNRECORDED_AMENDMENT`, and `thesis_as_of` after the call still returns the original falsifier/exit-condition digests.
     With a covering AmendmentRecord → accepted.
   - `test_pbr_thesis_store.py::test_terminal_amendment_requires_closed_reason_code`: INVALIDATED without `reason_code` → refused;
     an unknown `reason_code` → refused; `FALSIFIED` → accepted; `note` as a digest dict accepted.
   - `test_pbr_facts.py::test_caller_supplied_reference_mark_never_qualifies`: the XOM in-band price levels with the SAME value
     supplied as `CALLER_SUPPLIED` → `BASIS_UNRECONCILED` reason `reference_mark_not_qualified`; with no mark →
     `reference_mark_absent`; with an ECON test double whose `asof` is after the decision asof → not qualified.
   - `test_pbr_facts.py::test_declared_values_occur_in_original_prose`: ENV-GATED per spec §5 rule (3); skips with an SR-1 reason
     when `PBR_DECISION_CASE_INPUT_DIR` is unset or its files are absent.
   - `test_pbr_shadow_risk_budget.py::test_config_names_no_case_ticker`: the config text contains none of `688062`, `MU` (as a
     word), `Micron`, `XOM`, `Exxon`, `22196`.
   - `test_pbr_shadow_risk_budget.py::test_new_modules_have_no_live_write_path`: AST import check of the three modules against the
     forbidden list above; a thesis-store round trip with `store_dir=tmp_path` creates files only under `tmp_path`.
   - `test_pbr_shadow_risk_budget.py::test_no_sizing_or_decision_path_imports_shadow_modules`: AST scan of every `.py` under
     `brain/`, `bot/`, `portfolio/`, `app/`, `loop/`, `data_layer/`, `bridge/` (excluding the three new modules themselves) finds
     no import of `brain.facts`, `brain.thesis_store` or `brain.shadow_risk_budget` (any form: `import x`, `from brain import x`,
     `from brain.x import y`, `importlib.import_module("brain.x")` string literals).
   - `test_pbr_shadow_risk_budget.py::test_schema_constants_pinned`: each module constant equals its literal schema string, and the
     config's `schema` equals the params constant.
   - `test_pbr_shadow_risk_budget.py::test_new_files_carry_no_original_prose`: ENV-GATED; reuse the approach of
     `tests/test_pbr_decision_case_fixtures.py::test_no_original_prose_is_committed_under_fixtures` to assert that none of the
     original prose strings (or any 30-character span of one) occurs in the three new modules, the three new test files or the
     config.
   Test rules:
   - Contract tests import the new module **inside the test body** (`from brain import facts` etc.), so on code without the
     modules they FAIL with ModuleNotFoundError. Forbidden: `pytest.importorskip`, `xfail`, module-level imports of the new
     modules, try/except around those imports.
   - Contract tests assert the specific verdict (enum value, finding code, reason string, strict inequality), not just "no exception".
   - Facts are hand-built in the test from fixture fields under SR-1 rules (2)/(3); no prose parser this wave (spec §6).
   - The `test_baseline_master_*` tests must PASS on the current code, monkeypatching only
     `brain.decision_submission._latest_holdings` and `_instrument_identity_for_book` (plus any other READ seam `normalize()`
     reaches; list each in RETURN). Feed digests to string-typed seams via the rule (1) placeholder. Never patch a write path into a
     no-op; if a baseline call would write, stop and report BLOCKED with the call path.
   - No network, no live data; every store under `tmp_path`.

Forbidden edits: everything not listed under Outputs, including `config/pbr_shadow_risk_budget.yml`, `config/contracts.yml`,
`bot/decision_rows.py`, `brain/decision_submission.py`, `brain/ledger.py`, anything under `portfolio/`, `bot/`, `app/`, existing
tests and the fixtures.

## Verify, then return
1. `<Common pytest command> tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py tests/test_pbr_decision_case_fixtures.py`
   (env var unset: env-gated tests skip).
2. The same with `PBR_DECISION_CASE_INPUT_DIR=~/lanes/tmp/pbr-res-w2r1-ls5/inputs` (env-gated tests must run and pass).
3. Old-code discrimination: move the three new `brain/*.py` to `~/lanes/tmp/pbr-res-w2r1-ls5/aside/`, run the three new test
   files (expect: baseline and repo-scan tests pass, every contract test fails with ModuleNotFoundError), move them back and re-run.
   Report both summary lines verbatim and the list of tests that failed on the old code.
4. `git status --porcelain --untracked-files=all`, and `sha256sum` of every file you created plus the config.

## RETURN block (your last message)
```
RETURN pbr-res-w2r1-ls5
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every created file)
CONFIG_SHA256_FINAL: <sha256; must equal 355eba68…>
TESTS_NEW: <verbatim summary, env unset>   TESTS_ENV: <verbatim summary, env set>
TESTS_OLD: <verbatim summary with modules aside>  FAILED_ON_OLD: <test names>
NAMED_TESTS: <n>/20 spec tests present (+<n> extra); missing: <names or none>
REGRESSIONS: MU-silent-amendment=<verdict>; 688062-budget=<eligible_weight> vs cap <cap>; planless-MU=<local status + finding>; MU-date=<outcomes>; XOM control=<…>
RULINGS: Q1=<constant + observation path> Q2=<qualification rule + reasons> Q3=<negative test result> Q4=<enum + note handling> CR-R7=<constants>
CONTINUITY_API: <function name + statuses>
SEAMS_PATCHED: <module.attr list>
DEVIATIONS: <numbered (mark ruling-driven ones), or none>
```
## Common rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research` (Opus), who keeps every git, PR, review and merge step. You are a bounded leaf. No nested workers.
- Repository: your current working directory is a detached worktree of Mastermind at `origin/master` 230e9a301. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY the output paths named in this packet. Never commit, push, open or comment on PRs, edit other files, or touch `~/lanes/repos/Mastermind` directly.
- Forbidden: network access except none (no web fetches, no APIs); reading credentials/.env/keys; running the bot, scheduler, server or anything against live data; any account reset, seed rewrite, balancing fill, or "repair" trade; changing `brain/decision_submission.py` allocation behaviour; resetting or redefining the V2 marker (sha256 75d5182d…) or the August-11 cohort.
- Shadow/new modules terminate in isolated storage: no registry membership, no pending-target route, no settlement call.
- Tests (only when this packet names them): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <named files>`.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value. If blocked, stop and report the exact blocker.
- Your final assistant message is the ONLY thing returned. **Emit the full RETURN block (format below) as your last message**, including the file list with `sha256sum` of every file you wrote.
