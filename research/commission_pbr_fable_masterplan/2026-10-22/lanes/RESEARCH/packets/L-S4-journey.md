# OPERATION pbr-res-ls4-journey — byte-bounded decision-memory tail + snapshot→inspector journey on captured data, with negatives
Class: build · Complexity: C2_COMPLEX_BOUNDED · Code repair + tests in the existing #673 decision-snapshot family.

## Base (overrides the Common-rules base line)
Your worktree is a detached checkout of PR #673 head `0b960590c77101b3f3b5545896423f9ad07b7d56`
(branch `sol/mastermind-portfolio-v3-s0-decision-snapshot-20260915-sol-001`), NOT origin/master.
Read first: `portfolio/decision_snapshot.py`, `portfolio/decision_snapshot_sources.py`,
`portfolio/decision_snapshot_contracts.py`, `scripts/portfolio_decision_snapshot.py`,
`tests/test_decision_snapshot.py` (fixture `snapshot_root` at :83–95 patches `sources._ROOT`,
`sources._V` and `snapshots._ROOT`; `_V` is fixed at import, so it must be patched too).

## Inputs (read-only, on this host)
`~/lanes/tmp/pbr-res-ls4-journey/capture/` = `MANIFEST.json` + `host/portfolios/autonomous/{decisions.jsonl,fills.jsonl,pending_target.json,positions_ledger.json}`
+ `host/portfolios/china/{decisions.jsonl,fills.jsonl,positions_ledger.json}`. These are byte copies of the
production **paper** books captured read-only at 2026-10-22T07:35–07:37Z. `MANIFEST.json` `files[]` gives
`local_path` (relative to the capture dir), `sha256`, `bytes`, `host_mtime_utc` for each.

**PUBLIC REPOSITORY RULE (binding):** this repository is public. Never copy any byte, row, field value,
ticker list, memo text, digest-of-content-you-paste, or excerpt of the capture files into any repository file.
Tests that read the capture must locate it only through the env var `PBR_CAPTURE_DIR` and skip when it is unset.
The only capture-derived literals allowed in repo files: none. (Compare digests against `MANIFEST.json` at run time.)

## Observed baseline (orchestrator probe on 0b960590 against the same capture; reproduce, do not trust)
- A. cutoff `2026-10-22T07:35:49Z`, recorded `2026-10-22T07:36:57Z`, autonomous files staged under
  `<root>/data/portfolios/autonomous/` with mtimes set to MANIFEST `host_mtime_utc`:
  `create_snapshot` raises `DecisionSnapshotContractError("snapshot exceeds 262144-byte limit")`.
  Section `historical_memory` was COMPLETE with 100 rows / 87 omitted but **970,862 canonical bytes**:
  `_parse_jsonl_tail` (sources :716) bounds rows by count only (`MAX_JSONL_TAIL_ROWS=100`), and the real
  decision rows average ~10.7 KB (autonomous max 31,327 B; china max 49,775 B). So #673 cannot snapshot the real book.
- B. cutoff `2026-10-02T23:15:00Z`: seals BLOCKED; book.decisions / fills / pending_target / positions_ledger all
  `FUTURE_AT_CUTOFF` (the `FILE_MTIME_FIRST_PARTY_STATE` clock). A historical decision cannot be reconstructed
  from current append-only files. This is a recorded limitation, not something you fix.

## Outputs (create/modify ONLY these)
1. `portfolio/decision_snapshot_contracts.py` — add one constant `MAX_JSONL_TAIL_BYTES` (default proposal
   `65_536`; it must be ≥ the largest single observed row 49,775 B). Do not change any existing limit
   (`MAX_SNAPSHOT_BYTES`, `MAX_SECTION_RESPONSE_BYTES`, `MAX_SOURCE_BYTES`, row caps).
2. `portfolio/decision_snapshot_sources.py` — make `_parse_jsonl_tail` keep the **newest** valid rows while their
   cumulative size, measured with the same canonical serializer the seal uses (find it in contracts; cite path:line),
   stays ≤ `MAX_JSONL_TAIL_BYTES`, AND within `max_rows`. Returned order stays oldest→newest as today.
   Rows dropped by the byte budget count in `omitted_rows` exactly like count-cap omissions (same coverage
   semantics; do not add new keys unless the contract validator already permits them — cite it).
   If at least one valid row exists but the newest valid row alone exceeds the budget, the source must NOT end
   COMPLETE with zero rows: route it through the module's existing fail-closed status for an oversize/unusable
   source (find the status used for `MAX_SOURCE_BYTES` overflow; cite path:line) — no new status vocabulary.
   Put the budget arithmetic in a short code comment: worst-case `historical_memory` + `book_truth` bytes with the
   new cap vs `MAX_SNAPSHOT_BYTES`, and state the residual (a single non-JSONL object larger than its budget still
   fails closed at seal — say so; do not "fix" it).
3. `tests/test_decision_snapshot_journey.py` (new, CI-runnable, synthetic shape-faithful data only, stdlib + pytest;
   copy the `snapshot_root` fixture pattern). Journey-level tests, not duplicates of existing unit tests:
   - `test_journey_compose_project_cli_on_book_without_account` — synthetic autonomous book: ≥90 decision rows of
     ~10 KB each (plausible keys: decision_id, asof, holdings list, summary/memo filler text you generate), ≥90 fill
     rows, a pending_target.json, a positions_ledger.json, **no** account.json, mtimes ≤ cutoff, `_V` → empty dir.
     `create_snapshot` seals; coverage state is not COMPLETE; `book.account` is MISSING and `book_truth` is BLOCKED;
     the decisions receipt has `omitted_rows > 0`; `read_projection` and `latest_snapshot` return the same snapshot id;
     the CLI `main([...status...])` and `main([...show...])` (read the real argument names) return 0 and print that id.
   - `test_byte_bounded_tail_discriminates` — the same book: on the old `_parse_jsonl_tail` this raises
     `DecisionSnapshotContractError` (exceeds 262144); on the new code it seals and every section's canonical size is
     reported. Also a unit check: newest-first retention order, `omitted_rows` arithmetic, and the oversize-single-row case.
   - `test_missing_consumed_context_ends_non_complete` — consumed macro/context sources absent (`_V` empty) → the
     snapshot is never COMPLETE and its gap list names each missing source id.
   - `test_future_dated_sources_block` — cutoff earlier than the book files' mtimes → those sources
     `FUTURE_AT_CUTOFF`, owning section BLOCKED, snapshot not COMPLETE.
   - `test_forged_snapshot_digest_is_corrupt` — persist, then flip one byte of the stored snapshot file under the
     tmp store → `load_snapshot` raises `SnapshotCorrupt`; CLI `show` returns the exit code the source actually
     returns for corrupt (read `scripts/portfolio_decision_snapshot.py` `main`; the orchestrator read `1`), prints the
     corrupt status on stderr and no snapshot body on stdout.
   - `test_changed_context_mints_correction_and_preserves_original` — snapshot S1 at cutoff C; change
     pending_target.json content (mtime still ≤ C); `create_snapshot` at C → S2 with correction status CORRECTED that
     references S1; S1's stored bytes sha256 identical before/after and `load_snapshot(S1)` still verifies.
   - `test_compose_is_read_only_and_isolated` — after composing: every staged book file is byte- and mtime-identical,
     no file was created outside `<storage>/data/shadow/decision_snapshots/<book>/`, and the four modules
     (`portfolio/decision_snapshot*.py`, `scripts/portfolio_decision_snapshot.py`) import no settlement, pending-target
     writer or registry-mutating function (AST check of imports; cite what `registry` use exists and why it is read-only).
4. `tests/test_decision_snapshot_real_capture.py` (new; `pytest.mark.skipif` when `PBR_CAPTURE_DIR` is unset, with a
   reason string). Copy the capture files into `tmp_path` (never write in `PBR_CAPTURE_DIR`); verify each sha256
   against MANIFEST; `os.utime` each to MANIFEST `host_mtime_utc`; patch `_ROOT`s and `_V` (empty dir).
   - `test_real_autonomous_capture_seals_non_complete_at_capture_time` — cutoff `2026-10-22T07:35:49Z`, recorded
     `2026-10-22T07:36:57Z`: seals (no exception); state not COMPLETE; `book.pending_target` AVAILABLE with digest equal
     to `"sha256:" + MANIFEST sha256` of that file; decisions `omitted_rows > 0`; `book.account` MISSING.
   - `test_real_autonomous_capture_historical_cutoff_is_future_blocked` — cutoff `2026-10-02T23:15:00Z`: the four
     autonomous sources are `FUTURE_AT_CUTOFF`; not COMPLETE.
   - `test_real_china_capture_seals_non_complete` — china files at the same capture-time cutoff: seals, not COMPLETE
     (verify the china book directory from `portfolio/registry.py`; cite it).
   - After each test: the capture files' sha256 are unchanged.

You MAY edit `tests/test_decision_snapshot.py` / `tests/test_decision_snapshot_contracts.py` only if an existing test
breaks because of the byte bound; list every such edit with the reason under DEVIATIONS. Nothing else.

## Verify, then return
1. New code: `<Common pytest command> tests/test_decision_snapshot.py tests/test_decision_snapshot_contracts.py tests/test_decision_snapshot_journey.py tests/test_decision_snapshot_real_capture.py`
   once without and once with `PBR_CAPTURE_DIR=~/lanes/tmp/pbr-res-ls4-journey/capture` (expand `~` to the absolute path).
2. Old-code discrimination: copy your two modified `portfolio/` files to `~/lanes/tmp/pbr-res-ls4-journey/aside/`,
   restore the originals with `git show HEAD:<path> > <path>`, run `tests/test_decision_snapshot_journey.py` (expect
   `test_byte_bounded_tail_discriminates` and the journey test to fail), then copy your versions back and re-run.
   Report both summary lines verbatim. Do not use `git stash`, `git checkout` of branches, or commits.
3. `git status --porcelain --untracked-files=all` and `sha256sum` of every file you created or modified.

## RETURN block (your last message)
```
RETURN pbr-res-ls4-journey
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES: <path> <sha256>   (every created/modified file)
BUDGET: MAX_JSONL_TAIL_BYTES=<n>; canonical serializer=<file:line>; oversize-row status=<status> at <file:line>; arithmetic=<one line>
TESTS_OLD: <verbatim summary, old portfolio/ sources + new journey tests>
TESTS_NEW: <verbatim summary, no PBR_CAPTURE_DIR>
TESTS_REAL: <verbatim summary, PBR_CAPTURE_DIR set>
REAL_CAPTURE: capture-time: snapshot_id=<…> state=<…> sizes=<section:bytes,…> decisions rows_returned=<n> omitted_rows=<n> pending_target=<status digest>; historical: <source:status,…>; china: state=<…>
CLI_EXIT_CODES: status_ok=<n> show_ok=<n> show_corrupt=<n> show_not_found=<n>
DEVIATIONS: <numbered, or none>
```
