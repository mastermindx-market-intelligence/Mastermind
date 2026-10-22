# OPERATION pbr-res-w2r3-sr2 — Decision Snapshot S0: one strict clock/rights vocabulary (seat ruling SR-2) plus three review follow-ups (F1, F2, F4)
Class: build · Complexity: C2_COMPLEX_BOUNDED · Contract tightening inside the PR #673 carrier. No live call path.

## Base (overrides the Common-rules base line)
Your worktree is a detached checkout of PR #673's head @ `2a830e60` (branch
`sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001`; its base is 600 commits behind master, which is expected).
Work only on the S0 decision-snapshot files named below.

## Seat ruling SR-2 (binding)
"Adopt #1357's stricter clock set; `CALLER_SUPPLIED` is not a qualifying clock; add a `MACRO_VENDORED` rights class."
Today `portfolio/decision_snapshot_contracts.py` admits `SOURCE_DECLARED` and `CALLER_SUPPLIED` in `CLOCK_BASES` (≈:66–73) and
lets `status=AVAILABLE` rest on any clock outside the denylist `UNQUALIFIED_CLOCK_BASES` (≈:92, :273), so a receipt with
`clock_basis=CALLER_SUPPLIED` validates as AVAILABLE. `RIGHTS_CLASSES` (≈:56) is `{FIRST_PARTY_INTERNAL, MACRO_VENDORED}` but no
producer emits `MACRO_VENDORED`: every `EXTERNAL_SOURCE_SPECS` entry in `portfolio/decision_snapshot_sources.py` (≈:96 on) is
labelled `FIRST_PARTY_INTERNAL`, including vendored-Macro artifacts, and AVAILABLE has no rights requirement.

Make these changes:
1. `CLOCK_BASES` = exactly {`FILE_MTIME_FIRST_PARTY_STATE`, `DECLARED_SOURCE_FIELD`, `UNQUALIFIED_EXTERNAL_CLOCK`, `UNKNOWN`}.
   Add `QUALIFIED_CLOCK_BASES` = {`FILE_MTIME_FIRST_PARTY_STATE`, `DECLARED_SOURCE_FIELD`}. AVAILABLE requires
   `clock_basis ∈ QUALIFIED_CLOCK_BASES` (an allowlist; keep `UNQUALIFIED_CLOCK_BASES` defined as the complement for any existing
   reader). `CALLER_SUPPLIED` and `SOURCE_DECLARED` are no longer valid values: the validator rejects them for every status.
2. `RIGHTS_CLASSES` = exactly {`FIRST_PARTY_INTERNAL`, `MACRO_VENDORED`, `UNKNOWN`, `BLOCKED`}. Add `QUALIFIED_RIGHTS_CLASSES` =
   {`FIRST_PARTY_INTERNAL`, `MACRO_VENDORED`}. AVAILABLE requires `rights_class ∈ QUALIFIED_RIGHTS_CLASSES`. Do not add
   `LICENSED_INTERNAL`.
3. Relabel the external sources. Every `EXTERNAL_SOURCE_SPECS` entry is read through `_resolve_external_path` (≈:1294), which
   proves the file lies under the vendored Macro root `_V = vendor/macro` (≈:51), and all 11 entries name a `config/contracts.yml`
   contract whose `owner` is `macro_engine` (parent census at 2a830e60: macro.risk_envelope, macro.regime, macro.sector_rotation,
   macro.r_orth, macro.factor_betas, macro.prophet, macro.neural_web, macro.portfolio_context, macro.intelligence, macro.altdata,
   macro.news). Each is therefore a vendored-Macro artifact: set its `rights_class` to `MACRO_VENDORED`. Internal first-party
   sources (the book/decision/state readers, ≈:929, :1083, :1193) stay `FIRST_PARTY_INTERNAL`. If your reading finds any external
   spec whose contract owner is not `macro_engine`, leave it unchanged and list it under DEVIATIONS. Record source_id → contract
   key → registry owner → class for every external spec in RETURN (RIGHTS_MAP). Do not edit `config/contracts.yml`.
4. Update any comment/docstring in these files that names the removed clock values. No other behaviour change.

## Review follow-ups to fold in (from R-1735; all MINOR)
- **F1.** `tests/test_decision_snapshot_real_capture.py` ≈:170 and ≈:253: comments carry capture-derived size magnitudes
  ("~10 KB-per-row", "1.3 MB"). Drop the numerals (e.g. "a multi-megabyte real decision tail", "the large-per-row real decision
  tail"). Comments only; no code or assertion change. Leave no other byte count, digest, ticker, id or row value from any capture.
- **F2.** `portfolio/decision_snapshot_contracts.py` ≈:82–83: the comment says `MAX_JSONL_TAIL_BYTES` "must stay >= the largest
  single lawful row", but retention measures the list encoding (`kept_bytes` starts at 2, sources ≈:778), so the effective
  single-row ceiling is `MAX_JSONL_TAIL_BYTES − 2`. Reword the comment to state that. Constant value unchanged.
- **F4.** `portfolio/decision_snapshot_sources.py` ≈:1152–1170: the fail-closed OVERSIZE JSONL-tail branch leaves
  `rows_total`/`omitted_rows` at zero although `tail["rows_total"]` and `tail["omitted_rows"]` are known. Set
  `receipt["rows_total"] = tail["rows_total"]`, `receipt["omitted_rows"] = tail["omitted_rows"]`, and pass
  `omitted_rows=tail["omitted_rows"]` to `_merge_into_section`. Status, coverage and gap unchanged. Check the receipt and section
  validators still accept the result (rows_returned stays 0); if a validator invariant forbids it, stop and report BLOCKED with
  the invariant.

## Outputs (modify ONLY these files)
`portfolio/decision_snapshot_contracts.py`, `portfolio/decision_snapshot_sources.py`, `tests/test_decision_snapshot_contracts.py`,
`tests/test_decision_snapshot_sources.py`, `tests/test_decision_snapshot_real_capture.py` (F1 comments only), and — only if they
assert the old vocabulary or a digest that the relabel changes — `tests/test_decision_snapshot.py`,
`tests/test_decision_snapshot_api.py`, `tests/test_decision_snapshot_cli.py`, `tests/test_decision_snapshot_journey.py`,
`tests/test_decision_snapshot_no_effect.py`, `tests/test_decision_snapshot_ui.py`, `docs/runbooks/portfolio-v3-decision-snapshot.md`.
List every changed golden value in RETURN with old → new and why.

Tests to add (each must FAIL on `2a830e60` and PASS after your change; prove it, see Verify):
- `test_clock_bases_are_the_strict_set` — exact sets for `CLOCK_BASES` and `QUALIFIED_CLOCK_BASES`.
- `test_caller_supplied_and_source_declared_clocks_rejected` — an otherwise-valid receipt with either value is refused for status
  AVAILABLE and for a non-available status.
- `test_available_requires_qualified_clock_allowlist` — AVAILABLE with `UNKNOWN` or `UNQUALIFIED_EXTERNAL_CLOCK` refused; with each
  qualified clock accepted.
- `test_rights_classes_and_available_requires_qualified_rights` — exact sets; AVAILABLE with `UNKNOWN` or `BLOCKED` refused; with
  `MACRO_VENDORED` accepted.
- `test_vendored_macro_external_specs_are_macro_vendored` — for every `EXTERNAL_SOURCE_SPECS` entry, look up its contract via
  `control_plane.contracts.contract(spec.contract_key)`; owner `macro_engine` ⇒ `MACRO_VENDORED`; and every internal receipt the
  producer emits stays `FIRST_PARTY_INTERNAL` (derive from the registry, not a hard-coded list).
- `test_oversize_jsonl_tail_receipt_keeps_known_row_counts` (F4) — extend or add next to the existing OVERSIZE-tail test.

Forbidden: `config/contracts.yml`, `app/**`, `scripts/**`, `bot/**`, `brain/**`, any file outside the list; network; reading
anything under `data/`; changing snapshot semantics beyond the four SR-2 points and F1/F2/F4.

## Verify, then return
1. `<Common pytest command> tests/test_decision_snapshot_contracts.py tests/test_decision_snapshot_sources.py tests/test_decision_snapshot.py tests/test_decision_snapshot_api.py tests/test_decision_snapshot_cli.py tests/test_decision_snapshot_journey.py tests/test_decision_snapshot_no_effect.py tests/test_decision_snapshot_ui.py tests/test_decision_snapshot_real_capture.py tests/test_contracts.py`
   Record the summary before any edit (baseline) and after.
2. Discrimination: copy your changed `portfolio/decision_snapshot_contracts.py` and `portfolio/decision_snapshot_sources.py` to
   `~/lanes/tmp/pbr-res-w2r3-sr2/aside/`, restore the two originals with `git show HEAD:<path> > <path>`, run the two test files
   that hold the new tests (each new test must fail), then copy your versions back and re-run. Report both summary lines verbatim.
3. `git status --porcelain --untracked-files=all`; `git diff --stat`; save `git diff > ~/lanes/tmp/pbr-res-w2r3-sr2/out/W2R3.diff`
   and `sha256sum` it and every changed file.

## RETURN block (your last message)
```
RETURN pbr-res-w2r3-sr2
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every changed file, plus out/W2R3.diff)
TESTS_BASELINE: <verbatim summary at 2a830e60>   TESTS_NEW: <verbatim summary after>
DISCRIMINATION: <verbatim summary with originals restored>  FAILED_ON_OLD: <test names>
RIGHTS_MAP: <source_id → contract path → class>, one per external spec
GOLDEN_CHANGES: <file:line old → new, why> or none
SR2: clocks=<final set> qualified=<set>; rights=<final set> qualified=<set>
F1/F2/F4: <done + file:line each>
DEVIATIONS: <numbered, or none>
```
