# OPERATION pbr-res-w2r4-sup — decision ledger becomes append-only with `supersedes` (W2-R4 step 2)
Class: build · Complexity: C2_COMPLEX_BOUNDED · Source + tests in your worktree. No commit (the parent commits).

## Base (overrides the Common-rules base line)
Your working directory is a detached worktree of Mastermind at `origin/master` **1b7e1b3e**. Capture input (read-only, already
staged): `~/lanes/tmp/pbr-res-w2r4-sup/inputs/run_events.jsonl` (sha256 `6a423ef96978bb698bf38f27cdff2c9dfa1ad1317a788b6f893c045c04da542b`).
Never copy any line, field value, path or count from it into the repository; only the env-gated test reads it at run time.

## Why
`data/portfolios/<book>/decisions.jsonl` (rows built by `bot/decision_rows.py`) is rewritten in place today:
`replace_for_asof` (:287) drops earlier same-asof rows, `reconcile_settlement` (:302) and `refresh_lesson_links` (:497) overwrite
the matched row, and two scripts rewrite every row. A later same-day run therefore erases the earlier row's bytes. The ruling:
the ledger becomes **append-only**. A later write appends a new row that names the rows it supersedes; prior bytes are never
rewritten. One **effective-row accessor** reproduces exactly today's one-row-per-asof view, so readers keep their behaviour.

## Binding constraints
1. Append-only. After every write the new file bytes start with the complete old file bytes (if the old file is non-empty and does
   not end in `\n`, exactly one `\n` is inserted before the new line). Nothing anywhere rewrites, reorders or deletes an existing line.
2. All production writers converge on ONE writer API in `bot/decision_rows.py` (below).
3. The effective view equals today's view for every asof, row payload byte-equal except the three new fields.
4. Readers change ONLY by substituting the accessor at the raw read. No reader logic, ordering, filtering or output changes.
   **Do not edit** `portfolio/heavyweight_outcomes.py`, `portfolio/etf_outcomes.py`, `app/web.py`,
   `app/decision_availability_selection.py`, `brain/management_lifecycle.py`, `bot/settle.py`, `config/`, `vendor/`.
5. Keep every existing return value, exception class and exception message unchanged.

## API to add in `bot/decision_rows.py` (exact names)
New row fields, appended at the END of the key order in this order: `supersedes` (list[str], may be empty),
`supersede_mode` (`"asof"` | `"revise"`), `row_id` (`"row.v1."` + first 24 hex of `_canonical_sha256(row without row_id)`).
`_SUPERSESSION_KEYS = ("supersedes", "supersede_mode", "row_id")`.

- `strip_supersession(row) -> dict`: copy without the three keys (non-dicts returned unchanged).
- `row_identity(row) -> str`: `row["row_id"]` when it matches `^row\.v1\.[0-9a-f]{24}$`, else `"row.v1." + _canonical_sha256(row)[:24]` (legacy rows).
- `effective_rows(rows) -> list`: pure; never mutates. Non-dict items pass through at their position, never superseded, never superseding.
  A dict row R at index j supersedes every EARLIER dict row i (i < j) whose identity is listed in R's `supersedes` AND whose `asof`
  equals R's `asof`; unknown, forward or cross-asof pointers are ignored; a `supersedes` that is not a list of str is ignored.
  Ordering (this reproduces today's file order): each row has a slot = its own index, except a `supersede_mode == "revise"` row,
  which takes the slot of the row it supersedes. Return the surviving rows sorted by (slot, index).
  Fast path: if no row carries a non-empty `supersedes`, return `list(rows)` without hashing anything; otherwise hash only legacy
  rows whose `asof` occurs among superseding rows.
- `read_effective_rows(path, *, strict=False, tail=None) -> list[dict]`: `strict=True` parses exactly like `read_rows` (raises the
  same errors); `strict=False` returns `[]` for a missing/unreadable file and skips blank, undecodable and non-dict lines. Then
  `effective_rows`; with `tail=N` return the last N effective rows (the whole file is always read first).
- `plan_decision_row(existing, entry, asof, *, revises=None) -> dict | None`: pure. Raises `ValueError` when `entry.get("asof") != asof`.
  Let `eff = effective_rows(existing)`.
  * asof mode (`revises is None`): `same_day = [r for r in eff if isinstance(r, dict) and r.get("asof") == asof]`. If `same_day` and
    `not is_substantive(entry)` and `any(is_substantive(r) for r in same_day)` → `None` (today's barren guard: nothing written).
    If `len(same_day) == 1` and `strip_supersession(same_day[0]) == strip_supersession(entry)` → `None` (identical re-write).
    Else the new row supersedes every row in `same_day` (dedup identities, keep order), mode `"asof"`.
  * revise mode: `revises` must be a dict present in `eff` (by identity) with `revises.get("asof") == asof`, else `ValueError`.
    If `strip_supersession(entry) == strip_supersession(revises)` → `None`. Else supersedes `[row_identity(revises)]`, mode `"revise"`.
  * Build: `row = strip_supersession(entry)` (insertion order kept) + the three keys in the order above.
- `replace_for_asof(existing, entry, asof) -> list`: keep the name and signature; now returns `list(existing) + [planned]`, or
  `list(existing)` when planned is `None`. Update its docstring (append-only law).
- `append_decision_row(path, entry, asof, *, revises=None, strict=False) -> dict | None` — **the one writer**: read the file bytes ONCE
  (`b""` if missing), parse rows from those same bytes (strict or lenient as above), plan, and when the plan is not `None` write
  `old_bytes + sep + json.dumps(row, default=str, ensure_ascii=False).encode() + b"\n"` atomically (tmp + fsync + `os.replace` +
  directory fsync; factor today's `_atomic_write_rows` body into `_atomic_write_bytes(path, payload)`; create the parent dir as
  today). Assert `payload.startswith(old_bytes)` before replacing. Return the appended row, or `None` when nothing was written.
  No new locking: callers keep exactly the lock they hold today.
- Update the module docstring: append-only + supersedes; the 2026-07-24 barren-row rule still holds (a barren re-run writes nothing).

## Writers (all 11 census writers converge)
- `bot/autonomous.py::_append_decision_log` `_persist`: `decision_rows.append_decision_row(p, entry, asof, strict=True)` (same lock).
- `bot/china.py`, `bot/hk.py` `_persist`: same, `strict=True`, same lock.
- `bot/etf.py`, `bot/heavyweight.py`: replace the lenient parse + `replace_for_asof` + `p.write_text(...)` with
  `decision_rows.append_decision_row(p, entry, asof)` (lenient, no lock — as today).
- `portfolio/autonomous_migration.py` inherits via `autonomous._append_decision_log` (no edit unless a test proves one is needed).
- `reconcile_settlement`, `refresh_lesson_links`, `validate_queued_decision_snapshot`: inside the existing lock, read bytes once,
  parse strict, run ALL matching/dedupe/conflict logic over `effective_rows(rows)` instead of `rows`; build the revised dict exactly
  as today; persist with an append in revise mode targeting the matched effective row (skip when unchanged). Same return dicts,
  same exceptions and messages. `validate_queued_decision_snapshot` only reads (effective).
- `scripts/remove_positions.py::_scrub_decisions` and `scripts/scrub_cn_tiny_trims.py` (:81-92): compute the scrubbed copy of
  each EFFECTIVE row exactly as today; append a revise-mode row for each row that changed (`append_decision_row(path, scrubbed,
  row["asof"], revises=row)`); same printed counts/return values. Superseded history keeps its original bytes by design.
- `write_rows` stays defined (tests seed fixtures with it) but no production module may call it or `_atomic_write_rows`.

## Readers — accessor substitution only (raw read → effective rows; nothing else changes)
- `load_decisions` in `bot/autonomous.py`, `bot/china.py`, `bot/etf.py`, `bot/heavyweight.py`, `bot/hk.py`: keep the parse loop; insert
  `rows = decision_rows.effective_rows(rows)` before the sort. (This alone covers `app/web.py`, `brain/translate.py`, the ECON
  `*_outcomes.grade` readers and `scripts/repair_live_books_20260730.py`.)
- `brain/calibration.py::_book_decisions` (covers `brain/distill.py`, `brain/self_mirror.py`): parse every line as today (skip bad
  lines), then yield from `effective_rows(parsed)`; same early-return on a missing/unreadable file.
- `brain/decision_submission.py` (~:225-245, prior targets): parse ALL lines with the same `json.loads` (a malformed line still
  raises into the same handler), apply `effective_rows`, then run the existing reversed scan over that list unchanged.
- `brain/portfolio_learning.py` (~:362): `rows = decision_rows.effective_rows(_read_jsonl(path))` (same handler).
- `brain/posture.py` (:250): `decision_rows.read_effective_rows(data_dir / "decisions.jsonl", tail=80)` in place of
  `_read_jsonl_tail(...)`; keep `_read_jsonl_tail` for its other uses.
- `portfolio/desk_ab.py` (:208): wrap the parsed list in `decision_rows.effective_rows(...)` inside the same `try`.
- `portfolio/forward_evaluation.py` (:251): `decisions = decision_rows.effective_rows(decisions)` right after `_read_jsonl`.
- `app/decision_availability.py` (:379-385, PRODUCT): after the read loop, if `data["decisions"]` is a list, replace it with
  `decision_rows.effective_rows(data["decisions"])`. Sources/signatures stay computed on the raw file. Nothing else in that file.
- Any other raw reader you find that selects rows by asof: report it under UNSURE; do not edit it.

## Tests
A. Baseline FIRST, at base, before any edit: run the suite list below; record pass/fail/error per file (pre-existing failures are
   not yours to fix; list them).
B. New `tests/test_decision_rows_supersedes.py`:
   1. accessor units: `row_identity` (stored vs legacy), `effective_rows` (cross-asof/forward/unknown pointers ignored, non-dict
      pass-through, revise-slot ordering, fast path returns an equal list), `read_effective_rows` strict vs lenient vs `tail`.
   2. append-only: for asof mode, revise mode, barren drop and identical re-write, assert new bytes startswith old bytes (and the
      two no-op cases leave the file byte-identical); a file lacking a trailing newline gets exactly one separator.
   3. legacy file with TWO same-day rows (no row_id) + one substantive entry → one appended row whose `supersedes` lists both
      identities; effective view = [entry].
   4. property equivalence: a frozen verbatim copy of master's `replace_for_asof` (named `_master_replace_for_asof`) plus an
      in-place revision reference; ≥200 seeded random sequences of ≥30 ops (substantive / barren / accepted entries over ≥4 asofs
      in random order including older asofs; revise ops on a random effective row). After every op: per-asof
      `[strip_supersession(r) …]` equals the reference rows for that asof; the global effective order equals the reference order
      except after a reference barren-guard reorder (count those; assert per-asof equality there); bytes are append-only.
   5. settlement (discriminating, through `reconcile_settlement` with the fixtures/monkeypatches used in
      `tests/test_decision_settlement_reconciliation.py`): (a) settle txn A, then retry txn A → same success result, no
      exception, file bytes unchanged — and assert that master's raw matcher predicate over the RAW rows would match 2 rows
      (proving the old path would have raised a false conflict); (b) settle A then reconcile with a different transaction id →
      `DecisionSettlementConflict` with today's message, bytes unchanged; (c) two unsuperseded queued rows for the same decision
      → today's "exactly one" conflict.
   6. `refresh_lesson_links` then `validate_queued_decision_snapshot` still finds exactly one row (raw file has 2).
   7. static guard: no file under `bot/ brain/ portfolio/ app/ scripts/ control_plane/ loop/ data_layer/ bridge/` except
      `bot/decision_rows.py` calls `write_rows(` or `_atomic_write_rows(`.
C. New `tests/test_decision_rows_supersedes_replay.py` — event replay. One function `replay(events, root)` used by both tests:
   events sorted by `(ts, event_id)`; book from `book` or the `<book>_daily` job prefix; `asof = ts[:10]`. Mapping:
   `run_finished` of `autonomous_daily|china_daily|hk_daily`: status ok and `extra.target_status` in {queued, executed} → accepted
   row (`decision_effective` True, `target_status` "queued", `target_sha256` = sha256(run_id), `decision_id` = "decision.v1." +
   sha256(book+asof)[:24], one synthetic holding, summary "synthetic"); otherwise a barren row (`error` "synthetic", `holdings` [],
   `target_status` = extra.target_status or "rejected_no_submission", `decision_effective` False).
   `run_finished` of `watch_asia_overnight` (books hk, china) / `watch_us_overnight` (autonomous): ok → narrative row (summary
   "synthetic narrative", no `decision_effective` key); error → barren row. `run_finished` of `settle_brain_asia` (hk, china) /
   `settle_pending` (autonomous), status ok → for the newest effective queued accepted row with asof ≤ event date: revise to
   `target_status` "executed", `settled_asof`, `settlement_transaction_id` = "txn." + sha256(event_id)[:24].
   `packet_accepted` (book given) → revise that book's newest effective accepted row with asof ≤ event date, adding
   `lesson_link_ids` = [sha256(event_id)[:12]]. Every other event is counted and ignored. Payloads are synthetic only.
   NEW side: real files under `root` via `append_decision_row`. REFERENCE side: in-memory list via `_master_replace_for_asof` (import
   it from the test module above) + in-place revision. After EVERY event assert: per-(book, asof) stripped effective rows,
   serialized with `json.dumps(r, default=str, ensure_ascii=False)`, are byte-equal to the reference; append-only bytes.
   Return counts only (events by kind, writes, barren drops, supersessions, revisions, order-diff count, raw vs effective rows).
   - `test_replay_synthetic_events`: always on; ≥40 hand-built events covering every branch (incl. barren after accepted,
     narrative after accepted, settle then packet link, settle before any accepted row).
   - `test_replay_runtime_capture`: skip unless env `PBR_DECISION_ROW_REPLAY_CAPTURE` names a file; assert its sha256 equals
     `6a423ef96978bb698bf38f27cdff2c9dfa1ad1317a788b6f893c045c04da542b`; run `replay`; assert zero mismatches; print ONLY the counts.
D. Existing tests that read the raw ledger and assume one row per asof: change the read to `read_effective_rows` /
   `effective_rows` / `strip_supersession` so the SAME assertion is checked on the effective view. Never delete or weaken an
   assertion; where the raw file now has more rows, add a raw assertion of the new truth beside the kept one. List every
   edited test (file::test, one-line reason) in REPORT.md.
E. Final run: the suite list + the two new files. Then run the capture replay once:
   `PBR_DECISION_ROW_REPLAY_CAPTURE=~/lanes/tmp/pbr-res-w2r4-sup/inputs/run_events.jsonl` + the replay file with `-s`.

Suite list: tests/test_autonomous_etf_migration.py tests/test_autonomous_portfolio.py tests/test_brain_overlay.py tests/test_brain_pending_truth.py tests/test_calibration.py tests/test_calibration_regime.py tests/test_china_book.py tests/test_decision_availability.py tests/test_decision_availability_selection.py tests/test_decision_rows.py tests/test_decision_settlement_reconciliation.py tests/test_decision_submission_v2.py tests/test_desk_ab.py tests/test_desk_ab_asof_propagation.py tests/test_distill.py tests/test_etf_book.py tests/test_execution_quote_gap.py tests/test_forward_evaluation.py tests/test_fx_price_evidence.py tests/test_heavyweight.py tests/test_lesson_application_trace.py tests/test_management_lifecycle.py tests/test_outcomes.py tests/test_outstanding_receipt_fence.py tests/test_paper_transaction_boundary.py tests/test_perception_custody.py tests/test_portfolio_learning.py tests/test_posture.py tests/test_provider_diagnostic_local_veto.py tests/test_provider_diagnostic_read.py tests/test_provider_failure_typing.py tests/test_provider_legacy_failure.py tests/test_provider_refusal_book_lineage.py tests/test_retry_no_duplicate_effect.py tests/test_scheduler_decision_outcomes.py tests/test_sdk_diagnostic_bridge.py tests/test_sdk_diagnostic_mounted_consumer.py tests/test_selected_price_evidence.py tests/test_selected_price_receipt_integration.py tests/test_self_mirror.py tests/test_session_calendar_consistency.py tests/test_settle_open_price.py tests/test_settlement_price_read.py tests/test_settlement_receipt_retention.py tests/test_translate.py 

## Output
- Source + test edits in your worktree only (the parent reads `git diff` and untracked files).
- `~/lanes/tmp/pbr-res-w2r4-sup/out/REPORT.md`: files changed (one line each, why); baseline vs final per suite file
  (pass/fail counts, pre-existing failures named); test edits list (D); replay counts for synthetic and capture runs (counts only);
  UNSURE items; deviations from this packet (should be none).

## RETURN block (your last message)
```
RETURN pbr-res-w2r4-sup
STATUS: COMPLETE | BLOCKED <exact blocker>
FILES_CHANGED: <n>  (list path per line)
BASELINE: <passed>/<failed>/<errors>   FINAL: <passed>/<failed>/<errors>   NEW_FAILURES: <list or none>
REPLAY_SYNTHETIC: mismatches=<n> events=<n>   REPLAY_CAPTURE: mismatches=<n> events=<n> sha256_ok=<yes|no>
REPORT: <path> <sha256>
```
