# OPERATION pbr-res-r1746 — independent review of PR #1746 `feat(s0)`: strict clock/rights vocabulary (seat ruling SR-2) + R-1735 follow-ups F1/F2/F4
Class: review · Complexity: C2 · Output: ONE file `~/lanes/tmp/pbr-res-r1746/out/REVIEW.md`. You change no repository file.

## Target (exact)
- PR mastermindx-market-intelligence/Mastermind#1746, branch `pbr/research-w2-r3-sr2-vocab`, head `a2d3a6c17b44ff5ab5b8fd3b8cda32f439e4e8a5` (verify `git rev-parse HEAD`).
- **Stacked on the #673 carrier. Base for this review: `2a830e60588c0389b8670abeb99cef524cbef84b` (#673 head). Read the diff as `git diff 2a830e60..HEAD`.** (Overrides the base default below.)
- Tests to run: `tests/test_decision_snapshot.py tests/test_decision_snapshot_contracts.py tests/test_decision_snapshot_sources.py tests/test_decision_snapshot_cli.py tests/test_decision_snapshot_journey.py tests/test_decision_snapshot_no_effect.py tests/test_decision_snapshot_ui.py tests/test_decision_snapshot_real_capture.py tests/test_contracts.py`. `tests/test_decision_snapshot_api.py` needs `fastapi`, which this venv lacks; if it fails at collection, record that and read the file instead (grep it for any assertion on a rights/clock literal the change could break).

## What the builder was asked to do (commissioning packet W2-R3, summarised)
Seat ruling SR-2: "Adopt #1357's stricter clock set; `CALLER_SUPPLIED` is not a qualifying clock; add a `MACRO_VENDORED` rights class." Plus three MINOR follow-ups from review R-1735 of PR #1735:
- F1: drop capture-derived size magnitudes from two test comments;
- F2: make the `MAX_JSONL_TAIL_BYTES` invariant comment match the list-encoding measurement;
- F4: keep the known `rows_total`/`omitted_rows` on the fail-closed OVERSIZE JSONL-tail receipt and section.

## Acceptance criteria (cite path:line)
A1. Files: only `portfolio/decision_snapshot_contracts.py`, `portfolio/decision_snapshot_sources.py`, `tests/test_decision_snapshot_contracts.py`, `tests/test_decision_snapshot_sources.py`, `tests/test_decision_snapshot_real_capture.py` (comments only). `config/contracts.yml` unchanged. No constant other than the vocabulary sets changes value; diff every constant.
A2. Clocks: `CLOCK_BASES` is exactly {FILE_MTIME_FIRST_PARTY_STATE, DECLARED_SOURCE_FIELD, UNQUALIFIED_EXTERNAL_CLOCK, UNKNOWN}. `QUALIFIED_CLOCK_BASES` = {FILE_MTIME_FIRST_PARTY_STATE, DECLARED_SOURCE_FIELD}. The AVAILABLE gate is an allowlist (`not in QUALIFIED_CLOCK_BASES`). `CALLER_SUPPLIED`/`SOURCE_DECLARED` are refused for every status. `UNQUALIFIED_CLOCK_BASES` is the exact complement. `git grep` the WHOLE tree at HEAD for any other producer, reader or doc that still names a removed value or depends on the old denylist (exclude `research/` and `docs/superpowers/`), and cite what you find.
A3. Rights: `RIGHTS_CLASSES` is exactly {FIRST_PARTY_INTERNAL, MACRO_VENDORED, UNKNOWN, BLOCKED}, with no LICENSED_INTERNAL. AVAILABLE requires `QUALIFIED_RIGHTS_CLASSES` = {FIRST_PARTY_INTERNAL, MACRO_VENDORED}. Verify that every producer path in `decision_snapshot_sources.py` that can emit AVAILABLE emits a qualified class, so the new gate never turns a lawful receipt into a validation crash. Name any path that can now raise where it previously degraded.
A4. Relabel: every `EXTERNAL_SOURCE_SPECS` entry is `MACRO_VENDORED`, and the basis holds. Check that each is read via `_resolve_external_path` (containment under `_V = vendor/macro`) and that its `config/contracts.yml` contract `owner` is `macro_engine` (open the registry and check all 11 yourself). The internal readers stay `FIRST_PARTY_INTERNAL`. `test_vendored_macro_external_specs_are_macro_vendored` derives its expectation from the registry, not a hard-coded list.
A5. F1/F2/F4 are done exactly:
  - F1: comments only; no numeral, byte count, digest, ticker, id or row value from any capture remains in the file.
  - F2: check the arithmetic against the retention code (`kept_bytes` initial value and per-row increment). Is the effective single-row ceiling really `MAX_JSONL_TAIL_BYTES − 2`, and does the worst-case-pair statement still hold?
  - F4: `rows_total`/`omitted_rows` come from `tail`; `rows_returned` stays 0; status, coverage and gap are unchanged; both the receipt and section validators accept the result.
A6. Discrimination: with `portfolio/decision_snapshot_contracts.py` and `portfolio/decision_snapshot_sources.py` restored to `2a830e60` (copy the HEAD versions aside under `~/lanes/tmp/pbr-res-r1746/aside/`, then `git show 2a830e60:<path> > <path>`), the 7 new tests fail for the stated reason, not an import error or fixture typo. Restore the HEAD versions afterwards and confirm `git status --porcelain` is empty.
A7. Public repo rule: no capture-derived literal anywhere in the diff, and no IP address.
A8. Safety: no new import in the snapshot modules; tests write only under `tmp_path`; no network; no live call path.
