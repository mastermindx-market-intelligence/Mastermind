# OPERATION pbr-res-ls5-modules — typed PM facts, durable thesis store, shadow risk budget (isolated new modules) + the three regressions
Class: build · Complexity: C2_COMPLEX_BOUNDED · New isolated modules + tests; NOT wired into live decisions.

## Base (overrides the Common-rules base line)
Your worktree is a detached checkout of branch `pbr/research-w6-decision-case-fixtures` @ `a71544d9` (PR #1703),
which adds the five case fixtures under `tests/fixtures/pbr/decision_cases/` (+ `DECISION_CASES.md`). Use them in place;
never modify them.

## Inputs (read-only)
- `~/lanes/tmp/pbr-res-ls5-modules/SPEC.md` — the binding spec (PR #1701, `docs/superpowers/specs/2026-10-22-pbr-pm-facts-thesis-risk-budget.md`).
  Read it completely before writing code. Interfaces, enums, schemas, the 20 named tests (§5) and non-goals (§6) are binding.
- The five fixtures and `tests/fixtures/pbr/DECISION_CASES.md` in this worktree.
- `brain/decision_submission.py` (read-only: `normalize` :609, `_allocate_deterministically` :544, caps :444/:450,
  `_latest_holdings`, `_instrument_identity_for_book` :342), `brain/calibration.py` (read-only).

## Outputs (create ONLY these; in this order)
1. **First**, before any test file exists: `config/pbr_shadow_risk_budget.yml`, schema `pbr.shadow_risk_budget_params.v1`,
   with `version: 1`, `frozen_at: <UTC ISO time you write it>`, `freeze_owner: PENDING_SEAT_RULING` (spec §7 Q3), and for
   EVERY parameter (tolerance band §2.2(ii), role loss budgets, evidence-multiplier table, concentration factors) a
   `justification` grounded in general principles. Anti-fitting (spec §4.3, binding): no parameter may be chosen to hit a
   number for any case; the file must not name any case ticker or company (688062, MU, Micron, XOM, Exxon) nor the
   realised loss figure. Immediately record `sha256sum config/pbr_shadow_risk_budget.yml` — it goes in RETURN as
   CONFIG_SHA256_AT_FREEZE, and the file must be byte-identical at the end (if you must change it, bump `version`,
   add a justification, and report it as a DEVIATION with both digests).
2. `brain/facts.py`, `brain/thesis_store.py`, `brain/shadow_risk_budget.py` per SPEC §2–§4.
   - Storage only under a caller-supplied `store_dir: Path`; no default path, no module-level data path, no writes elsewhere.
   - Imports: stdlib + `yaml` + read-only `brain.calibration` constants if needed. Must NOT import
     `brain.decision_submission`, `brain.ledger`, `portfolio.registry`, `portfolio.paper_account`, `bot.settle`, any
     pending-target/order/fill writer, `app.*`, or network clients.
   - Reference mark for the §2.2(ii) bridge is a caller-supplied argument (spec §7 Q2); tests pass the fixture fill price.
   - UNRECORDED_AMENDMENT change-set includes `conviction` plus the thesis-semantic fields, held in one module constant
     documented as provisional pending the seat ruling on spec §7 Q1.
   - Terminal amendments (INVALIDATED/EXCLUDED) accept a free-text reason this wave (spec §7 Q4 open); say so in a docstring.
3. Tests — exactly the 20 named tests of SPEC §5 across `tests/test_pbr_facts.py`, `tests/test_pbr_thesis_store.py`,
   `tests/test_pbr_shadow_risk_budget.py`, plus two more in `tests/test_pbr_shadow_risk_budget.py`:
   - `test_config_names_no_case_ticker` — the config text contains none of `688062`, `MU`(as a word), `Micron`, `XOM`,
     `Exxon`, `22196`.
   - `test_new_modules_have_no_live_write_path` — AST import check of the three modules against the forbidden list above;
     and a thesis-store round trip with `store_dir=tmp_path` creates files only under `tmp_path`.
   Rules for tests:
   - Contract tests import the new module **inside the test body** (`from brain import facts` etc.), so on code without
     the modules they FAIL with ModuleNotFoundError. Forbidden: `pytest.importorskip`, `xfail`, module-level imports of the
     new modules, try/except around those imports.
   - Contract tests assert the specific verdict (enum value, finding code, strict inequality), not just "no exception".
   - Facts are constructed by hand in the test from fixture fields (no prose parser this wave, spec §6 item 6); each
     hand-built fact must assert that its cited value literally appears in the cited fixture field, so the test stays
     grounded in the recorded row.
   - The four `test_baseline_master_*` tests must PASS on the current code: monkeypatch only
     `brain.decision_submission._latest_holdings` and `_instrument_identity_for_book` as SPEC §5 says. If `normalize()`
     reaches any other live read, you may patch that additional READ seam to a fixture-derived value — list every patched
     seam in RETURN. Never patch a write path into a no-op to make a test pass; if a baseline call would write, stop and
     report it as BLOCKED with the call path.
   - No network, no live data, every store under `tmp_path`. Do not paste fixture narrative text into test files beyond
     the identifiers/dates/prices needed for assertions.

Forbidden edits: `brain/decision_submission.py`, `brain/ledger.py`, anything under `portfolio/`, `bot/`, `app/`, existing
tests, the fixtures, `config/` other than the one new file.

## Verify, then return
1. `<Common pytest command> tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py tests/test_pbr_decision_case_fixtures.py`
2. Old-code discrimination: move the three new `brain/*.py` modules to `~/lanes/tmp/pbr-res-ls5-modules/aside/`, run the
   three new test files (expect: the 4 baseline tests pass, every contract test fails with
   ModuleNotFoundError), then move them back and re-run. Report both summary lines verbatim plus the list of tests that
   failed on the old code.
3. `git status --porcelain --untracked-files=all` and `sha256sum` of every file you created.

## RETURN block (your last message)
```
RETURN pbr-res-ls5-modules
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every created file)
CONFIG_SHA256_AT_FREEZE: <sha256 recorded before any test file existed>  CONFIG_SHA256_FINAL: <sha256>
TESTS_OLD: <verbatim summary with modules aside>  FAILED_ON_OLD: <test names>
TESTS_NEW: <verbatim summary>
NAMED_TESTS: <n>/20 spec tests present (+<n> extra); missing: <names or none>
REGRESSIONS: MU-date(A14)=<pass/fail + outcome values>; MU-amendment(A15)=<…>; 688062-budget(A16)=<eligible_weight vs cap>; XOM control=<…>
SEAMS_PATCHED: <module.attr list>
OPEN_QUESTIONS: Q1=<handling> Q2=<…> Q3=<…> Q4=<…>
DEVIATIONS: <numbered, or none>
```
## Common rules (binding)
- Program: Portfolio Bot Rebuild (PBR), issue mastermindx-market-intelligence/Mastermind#1693. Parent orchestrator: `pbr-research` (Opus), who keeps every git, PR, review and merge step. You are a bounded leaf. No nested workers.
- Repository: your current working directory is a detached worktree of Mastermind at the base named in the packet header. Python: `~/lanes/venv/bin/python`.
- Allowed writes: ONLY the output paths named in this packet. Never commit, push, open or comment on PRs, edit other files, or touch `~/lanes/repos/Mastermind` directly.
- Forbidden: network access except none (no web fetches, no APIs); reading credentials/.env/keys; running the bot, scheduler, server or anything against live data; any account reset, seed rewrite, balancing fill, or "repair" trade; changing `brain/decision_submission.py` allocation behaviour; resetting or redefining the V2 marker (sha256 75d5182d…) or the August-11 cohort.
- Shadow/new modules terminate in isolated storage: no registry membership, no pending-target route, no settlement call.
- Tests (only when this packet names them): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <named files>`.
- Honesty: distinguish observed from inferred; mark `(unverified)` where you did not read the source. Never claim investment value. If blocked, stop and report the exact blocker.
- Your final assistant message is the ONLY thing returned. **Emit the full RETURN block (format below) as your last message**, including the file list with `sha256sum` of every file you wrote.
