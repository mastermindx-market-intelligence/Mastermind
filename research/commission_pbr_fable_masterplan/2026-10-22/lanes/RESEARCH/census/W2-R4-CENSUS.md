# CENSUS — readers/writers assuming one decision row per (book, asof)

> Repo copy of the W2-R4 C0 census (lane `pbr-res-w2r4-census`, ubuntu3). One capture-derived magnitude in row 126 is redacted here; the unredacted original is off-repo at `/Volumes/Mastermind/evidence/pbr/research-w2r4-census-20261022T1336Z/CENSUS.md` (sha256 `a408e72707c5f4d1eb428f008223de224399a4484684cdf77fd6f8239b59eac6`, SHA256SUMS beside it).

Operation `pbr-res-w2r4-census` (extract, C0_MECHANICAL, read-only).
MASTER = `~/lanes/wt/pbr-res-w2r4-census` @ f14fac19 (origin/master). PR673 = `~/lanes/wt/pbr-res-w2r4-census-673` @ 2a830e60.
Scope: hits that read/write `data/portfolios/<book>/decisions.jsonl` rows (the ledger built by
`bot/decision_rows.py` + `bot/*._append_decision_log`) and select/match/dedupe/index/join them by
asof, or assume the newest row is the asof's decision. Pass-throughs that only forward an asof are
excluded (see notes at the end). No `data/` file was opened; expressions below are code only.

## 1. Sites

| # | tree | file:line | function | R/W | selection today (exact expression, ≤80 chars, code only) | assumption | selection needed once supersedes rows exist | family |
|---|------|-----------|----------|-----|----------------------------------------------------------|------------|----------------------------------------------|--------|
| 1 | MASTER | bot/decision_rows.py:295 | replace_for_asof | W | `kept = [r for r in existing if r.get("asof") != asof]` | OVERWRITE | CHAIN | RESEARCH |
| 2 | MASTER | bot/decision_rows.py:296 | replace_for_asof | R | `same_day = [r for r in existing if r.get("asof") == asof]` | UNIQUE_PER_ASOF | CHAIN | RESEARCH |
| 3 | MASTER | bot/decision_rows.py:166 | validate_queued_decision_snapshot | R | `if str(row.get("accepted_asof") or row.get("asof") or "")[:10] == accepted_asof` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 4 | MASTER | bot/decision_rows.py:174 | validate_queued_decision_snapshot | R | `if len(exact) != 1:` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 5 | MASTER | bot/decision_rows.py:376 | reconcile_settlement | R | `if str(row.get("accepted_asof") or row.get("asof") or "")[:10] == accepted_asof` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 6 | MASTER | bot/decision_rows.py:395 | reconcile_settlement | R/W | `if len(exact) != 1:` (then rewrites `rows[index]` in place) | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 7 | MASTER | bot/decision_rows.py:516 | refresh_lesson_links | R | `if str(row.get("accepted_asof") or row.get("asof") or "")[:10]` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 8 | MASTER | bot/decision_rows.py:522 | refresh_lesson_links | R | `if len(matches) != 1:` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 9 | MASTER | bot/decision_rows.py:126 | accepted_identity_fields | W | `"decision_id": decision_id(portfolio_id, accepted_asof, submission),` | OTHER:identity-derivation | UNCHANGED (decision_id is asof-derived: a re-queued identical submission shares it) | RESEARCH |
| 10 | MASTER | brain/decision_submission.py:231 | _latest_holdings | R | `for line in reversed(lines):` (accepted rows only, `break` after first hit) | LAST_WINS | UNCHANGED | RESEARCH |
| 11 | MASTER | portfolio/forward_evaluation.py:424 | _baseline_for | R | `"decisions": _row_ids(decisions, "asof"),` | OTHER:content-row-ids | UNCHANGED (decision_id preferred; asof:digest:occurrence fallback already tolerates duplicates) | RESEARCH |
| 12 | MASTER | portfolio/forward_evaluation.py:1102 | build_snapshot | R | `_new_indexed_rows(values["decisions"], "asof", baseline.get("decisions") or [],` | COUNT_PER_ASOF | LATEST_NON_SUPERSEDED | RESEARCH |
| 13 | PR673 | portfolio/decision_snapshot_sources.py:1143 | capture_book_state | R | `tail = _parse_jsonl_tail(raw)` (book.decisions spec at :239) | OTHER:bounded-tail-rows | LATEST_NON_SUPERSEDED (fixed byte/row budget otherwise spent on superseded rows) | RESEARCH |
| 14 | MASTER | brain/calibration.py:435 | _book_decisions | R | `p = _PORTFOLIOS / portfolio_id / "decisions.jsonl"` (yields every row) | ALL_ROWS | ALL_ROWS | OTHER (brain/) |
| 15 | MASTER | brain/calibration.py:465 | _book_reliability | R | `d_iso = str(row.get("asof") or "")[:10]` (per row, then labels by d_iso) | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED (else a date is graded twice) | OTHER (brain/) |
| 16 | MASTER | brain/calibration.py:672 | _book_reliability_raw_spy | R | `d_iso = str(row.get("asof") or "")[:10]` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | OTHER (brain/) |
| 17 | MASTER | brain/self_mirror.py:173 | _book_rows | R | `d_iso = str(row.get("asof") or "")[:10]` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | OTHER (brain/) |
| 18 | MASTER | brain/distill.py:77 | _opus_holdings | R | `by_d[d] = {(h.get("ticker") or "").upper().strip()` (d = row asof, dict overwrite) | LAST_WINS | UNCHANGED (append order keeps last-write = superseding row) | OTHER (brain/) |
| 19 | MASTER | brain/posture.py:250 | posture | R | `_latest_meaningful(_read_jsonl_tail(data_dir / "decisions.jsonl"))` | LAST_WINS | UNCHANGED (reversed scan returns the newest appended row) | OTHER (brain/) |
| 20 | MASTER | brain/portfolio_learning.py:413 | _decision_exit | R | `if row.get("decision_id") == decision_id and _accepted_decision_row(row):` | FIRST_WINS | LATEST_NON_SUPERSEDED (first file match can be the superseded row) | OTHER (brain/) |
| 21 | MASTER | brain/portfolio_learning.py:441 | _decision_exit | R | `if str(row.get("asof") or "")[:10] > str(fill_date)[:10]:` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | OTHER (brain/) |
| 22 | MASTER | brain/portfolio_learning.py:456 | _decision_exit | R | `return sorted(candidates, key=lambda x: x[0])[-1][1] if candidates else {}` | LAST_WINS | LATEST_NON_SUPERSEDED (stable sort keeps last-appended among equal asofs) | OTHER (brain/) |
| 23 | MASTER | brain/translate.py:429 | translate_decisions | R | `for d in autonomous.load_decisions(limit):` | ALL_ROWS | UNCHANGED | OTHER (brain/) |
| 24 | MASTER | brain/management_lifecycle.py:439 | _match_row | R | `exact = [row for row in for_book if _text(row.get("run_id")) == brain_run_id]` | BY_DECISION_ID | UNCHANGED | RUNTIME |
| 25 | MASTER | brain/management_lifecycle.py:447 | _match_row | R | `return _newest_row([row for _ts, _index, row in inside])` | LAST_WINS | UNCHANGED | RUNTIME |
| 26 | MASTER | brain/management_lifecycle.py:455 | _newest_row | R | `return max(usable)[2]` (fallback `return rows[-1] if rows else None`) | LAST_WINS | UNCHANGED | RUNTIME |
| 27 | MASTER | brain/management_lifecycle.py:474 | _was_superseded | R | `if _text(row.get("run_id")) != brain_run_id:` (after `asof in wanted`) | UNIQUE_PER_ASOF | CHAIN (absence no longer proves supersession; read the supersedes pointer) | RUNTIME |
| 28 | MASTER | portfolio/heavyweight_outcomes.py:118 | grade | R | `decisions = _hw.load_decisions(400)` then `key = (d_asof, tk)` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | ECON |
| 29 | MASTER | portfolio/heavyweight_outcomes.py:136 | grade | R/W | `elif by_key[key].get("status") == "open":` (updates weight/conviction) | LAST_WINS | LATEST_NON_SUPERSEDED (newest-first iteration means the OLDER row's weights overwrite the newer's) | ECON |
| 30 | MASTER | portfolio/etf_outcomes.py:118 | grade | R | `decisions = _etf.load_decisions(400)` then `key = (d_asof, tk)` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | ECON |
| 31 | MASTER | portfolio/etf_outcomes.py:136 | grade | R/W | `elif by_key[key].get("status") == "open":` | LAST_WINS | LATEST_NON_SUPERSEDED | ECON |
| 32 | MASTER | bot/autonomous.py:918 | _append_decision_log | W | `rows = decision_rows.replace_for_asof(existing, entry, asof)` | OVERWRITE | CHAIN | RUNTIME |
| 33 | MASTER | bot/autonomous.py:941 | load_decisions | R | `rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)` | ALL_ROWS | UNCHANGED (list stays newest-first; consumers see both rows for an asof) | RUNTIME |
| 34 | MASTER | bot/china.py:797 | _append_decision_log | W | `rows = decision_rows.replace_for_asof(existing, entry, asof)` | OVERWRITE | CHAIN | RUNTIME |
| 35 | MASTER | bot/china.py:904 | republish | R | `decs = load_decisions(1)` then `decs[0].get("brain_text")` | LAST_WINS | UNCHANGED | RUNTIME |
| 36 | MASTER | bot/china.py:927 | load_decisions | R | `rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)` | ALL_ROWS | UNCHANGED | RUNTIME |
| 37 | MASTER | bot/hk.py:798 | _append_decision_log | W | `rows = decision_rows.replace_for_asof(existing, entry, asof)` | OVERWRITE | CHAIN | RUNTIME |
| 38 | MASTER | bot/hk.py:905 | republish | R | `decs = load_decisions(1)` then `decs[0].get("brain_text")` | LAST_WINS | UNCHANGED | RUNTIME |
| 39 | MASTER | bot/hk.py:928 | load_decisions | R | `rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)` | ALL_ROWS | UNCHANGED | RUNTIME |
| 40 | MASTER | bot/etf.py:725 | _append_decision_log | W | `rows = decision_rows.replace_for_asof(existing, entry, asof)` | OVERWRITE | CHAIN | RUNTIME |
| 41 | MASTER | bot/etf.py:743 | load_decisions | R | `rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)` | ALL_ROWS | UNCHANGED | RUNTIME |
| 42 | MASTER | bot/heavyweight.py:849 | _append_decision_log | W | `rows = decision_rows.replace_for_asof(existing, entry, asof)` | OVERWRITE | CHAIN | RUNTIME |
| 43 | MASTER | bot/heavyweight.py:867 | load_decisions | R | `rows.sort(key=lambda r: (r.get("asof") or "", r.get("ts") or ""), reverse=True)` | ALL_ROWS | UNCHANGED | RUNTIME |
| 44 | MASTER | portfolio/autonomous_migration.py:740 | _publish_accepted_migration | W | `autonomous._append_decision_log(` | OVERWRITE | CHAIN | RUNTIME |
| 45 | MASTER | app/web.py:1488 | api_portfolio | R | `for rec in src.load_decisions(60):` + `if rec.get("summary"):` (banner fallback) | LAST_WINS | UNCHANGED | PRODUCT |
| 46 | MASTER | app/web.py:1688 | api_decisions | R | `decisions = _src.load_decisions(limit)` | ALL_ROWS | UNCHANGED (both rows for an asof are returned; UI renders duplicates unless filtered) | PRODUCT |
| 47 | MASTER | app/web.py:1727 | api_decisions | R | `_sell.get((sell_asof, (rec.get("ticker") or "").upper()))` | JOIN_BY_ASOF | UNCHANGED (per-row FIFO join on settled_asof stays valid) | PRODUCT |
| 48 | MASTER | app/decision_availability.py:392 | read_decision_availability | R | `selection = select_decision_records(` (consumes `["last_valid"]`) | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT |
| 49 | MASTER | app/decision_availability_selection.py:313 | _dedupe | R | `if cand.content in seen:` | OTHER:exact-dup-dedupe | UNCHANGED (supersedes rows differ in content, so both survive as candidates) | PRODUCT |
| 50 | MASTER | app/decision_availability_selection.py:327 | _drop_identity_conflicts | R | `by_decision.setdefault(decision_id, []).append(cand)` | BY_DECISION_ID | UNCHANGED | PRODUCT |
| 51 | MASTER | app/decision_availability_selection.py:420 | _select_latest | R | `if len(survivors) == 1:` (else `ambiguous_latest_tie`) | LAST_WINS | LATEST_NON_SUPERSEDED (same-day rows with equal/overlapping clocks must resolve via supersedes, not tie) | PRODUCT |
| 52 | MASTER | scripts/repair_live_books_20260730.py:263 | _latest_rationales | R | `for decision in china.load_decisions(500):` (first-with-holdings wins) | FIRST_WINS | UNCHANGED (newest-first order keeps first-seen = superseding row) | OTHER (scripts/) |
| 53 | MASTER | scripts/remove_positions.py:113 | _scrub_decisions | W | `for arr in ("holdings", "executed"):` (rewrites every row in place) | OTHER:in-place-scrub | ALL_ROWS (must keep scrubbing superseded rows too) | OTHER (scripts/) |
| 54 | MASTER | scripts/scrub_cn_tiny_trims.py:85 | (module-level repair) | W | `for d in decisions:` (rewrites each row's `executed`) | OTHER:in-place-scrub | ALL_ROWS | OTHER (scripts/) |
| 55 | MASTER | tests/test_decision_rows.py:41 | test_failed_rerun_does_not_erase_good_book | R | `rows = dr.replace_for_asof([BOOK], STUB, "2026-07-24")` | OVERWRITE | CHAIN | RESEARCH-test |
| 56 | MASTER | tests/test_decision_rows.py:48 | test_good_rerun_still_supersedes | R | `assert dr.replace_for_asof([BOOK], better, "2026-07-24") == [better]` | OVERWRITE | CHAIN | RESEARCH-test |
| 57 | MASTER | tests/test_decision_rows.py:53 | test_barren_entry_recorded_when_nothing_good_exists | R | `assert dr.replace_for_asof([], STUB, "2026-07-24") == [STUB]` | OVERWRITE | CHAIN | RESEARCH-test |
| 58 | MASTER | tests/test_decision_rows.py:59 | test_barren_replaces_barren | R | `assert dr.replace_for_asof([older], STUB, "2026-07-24") == [STUB]` | OVERWRITE | CHAIN | RESEARCH-test |
| 59 | MASTER | tests/test_decision_rows.py:65 | test_other_dates_preserved_in_order | R | `rows = dr.replace_for_asof([d22, d23, BOOK], STUB, "2026-07-24")` | OVERWRITE | CHAIN | RESEARCH-test |
| 60 | MASTER | tests/test_decision_rows.py:74 | test_new_date_appends | R | `assert dr.replace_for_asof([d22], new, "2026-07-27") == [d22, new]` | OVERWRITE | CHAIN | RESEARCH-test |
| 61 | MASTER | tests/test_decision_rows.py:82 | test_duplicate_good_rows_for_a_date_all_survive_a_stub | R | `assert dr.replace_for_asof([a, b], STUB, "2026-07-24") == [a, b]` | UNIQUE_PER_ASOF | CHAIN (pins that 2 same-date rows can already exist) | RESEARCH-test |
| 62 | MASTER | tests/test_decision_settlement_reconciliation.py:82 | test_receipt_reconciles_original_queued_decision_for_all_brains | R | `assert len(rows) == 1` (+ `row["asof"] == row["accepted_asof"]`) | UNIQUE_PER_ASOF | ALL_ROWS | RESEARCH-test |
| 63 | MASTER | tests/test_decision_settlement_reconciliation.py:398 | test_reconciliation_matches_exact_identity_without_overwriting_later_day | R | `by_day = {row["asof"]: row for row in rows}` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 64 | MASTER | tests/test_decision_settlement_reconciliation.py:439 | test_reconciliation_accepts_only_a_complete_deterministic_target_lineage | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 65 | MASTER | tests/test_decision_settlement_reconciliation.py:470 | test_zero_fill_receipt_still_transitions_queued_decision_to_no_change | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 66 | MASTER | tests/test_decision_settlement_reconciliation.py:501 | test_receipt_can_finish_binding_an_already_executed_direct_open_row | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 67 | MASTER | tests/test_decision_settlement_reconciliation.py:528 | test_pre_release_v2_queued_row_is_backfilled_from_exact_effective_target | R | `legacy = json.loads(path.read_text().splitlines()[0])` | OTHER:first-line | BY_DECISION_ID | RESEARCH-test |
| 68 | MASTER | tests/test_decision_settlement_reconciliation.py:554 | test_pre_release_v2_queued_row_is_backfilled_from_exact_effective_target | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 69 | MASTER | tests/test_decision_settlement_reconciliation.py:579 | test_reconciliation_fails_closed_without_mutating_ledger | R | `row = json.loads(path.read_text().splitlines()[0])` | OTHER:first-line | BY_DECISION_ID | RESEARCH-test |
| 70 | MASTER | tests/test_decision_settlement_reconciliation.py:632 | test_zero_weight_is_not_part_of_executable_target_identity | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 71 | MASTER | tests/test_decision_settlement_reconciliation.py:665 | test_accepted_all_cash_target_supersedes_stale_same_day_book | R | `rows = autonomous.load_decisions()` (then `rows[0]["effective_holdings"]`) | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 72 | MASTER | tests/test_decision_settlement_reconciliation.py:703 | test_accepted_post_submission_brain_error_supersedes_stale_same_day_book | R | `rows = autonomous.load_decisions()` (then `rows[0]["summary"]`) | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 73 | MASTER | tests/test_decision_settlement_reconciliation.py:765 | test_direct_open_reconciliation_binds_receipt_fills_before_ack | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 74 | MASTER | tests/test_decision_settlement_reconciliation.py:881 | test_more_than_twenty_target_rewrites_compact_without_breaking_lineage | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 75 | MASTER | tests/test_decision_settlement_reconciliation.py:1034 | test_consumed_queue_without_receipt_never_infers_another_callers_fills | R | `assert autonomous.load_decisions()[0]["target_status"] == "queued"` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 76 | MASTER | tests/test_forward_evaluation.py:132 | _seed_book (fixture) | W | `_write_jsonl(book_dir / "decisions.jsonl", [decisions[1], decisions[0], decisions[2]])` | OTHER:order-independent-ids | UNCHANGED (pins content-ID boundary; must stay order-true with supersedes rows) | RESEARCH-test |
| 77 | MASTER | tests/test_decision_submission_v2.py:140 | test_rejected_target_never_becomes_next_trim_anchor | W | `(tmp_path / "decisions.jsonl").write_text(` (rows: accepted, rejected) | LAST_WINS | UNCHANGED (pins `_latest_holdings` skipping the rejected row) | RESEARCH-test |
| 78 | MASTER | tests/test_decision_submission_v2.py:689 | test_audit_fields_persist_through_every_book_writer | R | `(tmp_path / book / "decisions.jsonl").read_text().splitlines()[-1]` | LAST_WINS | BY_DECISION_ID | RESEARCH-test |
| 79 | MASTER | tests/test_etf_book.py:339 | test_etf_outcomes_grades_and_scores | W | `p = registry.data_dir("etf") / "decisions.jsonl"` (single-row fixture) | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | ECON-test |
| 80 | MASTER | tests/test_etf_book.py:363 | test_grade_is_idempotent | W | `p = registry.data_dir("etf") / "decisions.jsonl"` (single-row fixture) | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | ECON-test |
| 81 | MASTER | tests/test_etf_book.py:377 | test_grade_refreshes_open_entry_weight | W | `p = registry.data_dir("etf") / "decisions.jsonl"` (file re-written with same-asof row) | OVERWRITE | LATEST_NON_SUPERSEDED (with 2 rows, the older row's update pass reverts the newer weight) | ECON-test |
| 82 | MASTER | tests/test_autonomous_portfolio.py:123 | test_run_autonomous_executes_submission | R | `decs = autonomous.load_decisions()` + `decs[0]["summary"] == "barbell"` | LAST_WINS | UNCHANGED | RUNTIME-test |
| 83 | MASTER | tests/test_china_book.py:424 | test_run_china_rejects_offvenue_and_executes_a_shares | R | `decs = china.load_decisions()` + `decs[0]["summary"]` | LAST_WINS | UNCHANGED | RUNTIME-test |
| 84 | MASTER | tests/test_china_book.py:1166 | test_run_china_aborts_on_tushare_feed_outage | R | `decs = china.load_decisions()` + `decs[0]["feed_health"]["status"]` | LAST_WINS | UNCHANGED | RUNTIME-test |
| 85 | MASTER | tests/test_autonomous_etf_migration.py:168 | test_closed_apply_queues_hash_bound_stock_only_target... | R | `assert decisions[-1]["target_status"] == "queued"` | LAST_WINS | BY_DECISION_ID | RUNTIME-test |
| 86 | MASTER | tests/test_autonomous_etf_migration.py:231 | test_open_apply_still_queues_then_scheduler_sells_etfs... | R | `json.loads((migration_book / "decisions.jsonl").read_text().splitlines()[-1])` | LAST_WINS | BY_DECISION_ID | RUNTIME-test |
| 87 | MASTER | tests/test_autonomous_etf_migration.py:697 | test_settlement_link_is_durable_before_ack_and_deduplicates_retry | R | `if row.get("asof") == "2026-08-11" and row.get("target_status") == "executed"` | UNIQUE_PER_ASOF | ALL_ROWS (pins `len(settled) == 1`: "must not create a second date row") | RUNTIME-test |
| 88 | MASTER | tests/test_provider_refusal_book_lineage.py:321 | test_same_day_barren_refusal_does_not_replace_accepted_row_or_run | R | `first_row=h.module.load_decisions()[0]` + `path.read_bytes()==before` | OTHER:barren-rerun-writes-nothing | CHAIN (append changes this contract for barren re-runs) | RUNTIME-test |
| 89 | MASTER | tests/test_provider_failure_typing.py:343 | test_decision_rows_carry_the_typed_record | R | `row = next(r for r in rows if r.get("asof") == "2026-10-20")` | FIRST_WINS | BY_DECISION_ID | RUNTIME-test |
| 90 | MASTER | tests/test_sdk_diagnostic_mounted_consumer.py:125 | test_fresh_sdk_terminal_diagnostics_reach_mounted_accepted_decision | R | `assert len(decisions) == 1` (then `decision = decisions[0]`) | COUNT_PER_ASOF | BY_DECISION_ID | RUNTIME-test |
| 91 | MASTER | tests/test_sdk_diagnostic_bridge.py:528 | test_real_book_owner_keeps_persisted_submission_after_sdk_failure | R | `row = autonomous.load_decisions()[0]` | LAST_WINS | BY_DECISION_ID | RUNTIME-test |
| 92 | MASTER | tests/test_decision_availability.py:94 | test_failure_does_not_erase_origin_or_later_account_and_mark | W | `write(tmp_path, "decisions.jsonl", [row, failed()])` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 93 | MASTER | tests/test_decision_availability.py:181 | test_malformed_journal_tail_remains_partial_and_preserves_prior_valid_record | W | `(tmp_path / "decisions.jsonl").write_text(json.dumps(accepted()) + '\n{"asof":')` | OTHER:malformed-tail | UNCHANGED | PRODUCT-test |
| 94 | MASTER | tests/test_decision_availability.py:240 | test_accepted_with_adapter_error_keeps_target_and_redacts_error | W | `write(tmp_path, "decisions.jsonl", [accepted(), failed()])` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 95 | MASTER | tests/test_decision_availability.py:284 | test_mounted_route_cannot_recover_quarantine_quote_or_write | W | `write(base, "decisions.jsonl", [accepted(book), failed()])` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 96 | MASTER | tests/test_decision_availability.py:422 | test_receipt_inspector_failure_is_independent_of_account_and_target | W | `write(tmp_path, "decisions.jsonl", [row, failed()])` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 97 | MASTER | tests/test_decision_availability_selection.py:171 | test_failed_stub_does_not_replace_accepted_intent | R | `result = self.select([ACCEPTED_OCT9, FAILURE_OCT15])` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 98 | MASTER | tests/test_decision_availability_selection.py:181 | test_same_day_journal_accepted_with_later_bound_failure | R | `result = self.select([ACCEPTED_OCT9], attempts=[expected])` | JOIN_BY_ASOF | UNCHANGED | PRODUCT-test |
| 99 | MASTER | tests/test_decision_availability_selection.py:188 | test_unbound_newer_attempt_cannot_win | R | `result = self.select([ACCEPTED_OCT9], attempts=[FAILURE_OCT15])` | LAST_WINS | UNCHANGED | PRODUCT-test |
| 100 | MASTER | tests/test_decision_availability_selection.py:199 | test_foreign_newer_run_cannot_affect_selection | R | `result = self.select([ACCEPTED_OCT9, foreign(newer)])` (newer asof 2026-10-16) | JOIN_BY_ASOF | UNCHANGED | PRODUCT-test |
| 101 | MASTER | tests/test_decision_availability_selection.py:277 | test_tied_date_only_conflict_not_resolved_by_order | R | `forward = self.select([ACCEPTED_OCT9, early, late])` | OTHER:tie-ambiguous | LATEST_NON_SUPERSEDED (same-day supersedes rows hit this tie) | PRODUCT-test |
| 102 | MASTER | tests/test_decision_availability_selection.py:295 | test_date_only_same_day_as_instant_is_ambiguous | R | `result = self.select([ACCEPTED_OCT9, carry, instant])` | OTHER:tie-ambiguous | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 103 | MASTER | tests/test_decision_availability_selection.py:305 | test_tied_instant_acceptance_conflict | R | `result = self.select([ACCEPTED_OCT9, other])` | OTHER:tie-ambiguous | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 104 | MASTER | tests/test_decision_availability_selection.py:313 | test_exact_duplicates_dedupe | R | `result = self.select([ACCEPTED_OCT9, copy.deepcopy(ACCEPTED_OCT9)])` | OTHER:exact-dup-dedupe | UNCHANGED | PRODUCT-test |
| 105 | MASTER | tests/test_decision_availability_selection.py:322 | test_conflicting_duplicate_identity | R | `result = self.select([ACCEPTED_OCT9, conflict])` | BY_DECISION_ID | UNCHANGED | PRODUCT-test |
| 106 | MASTER | tests/test_decision_availability_selection.py:404 | test_row_reordering_preserves_semantics | R | `backward = self.select(list(reversed(rows)))` | OTHER:order-independent | UNCHANGED | PRODUCT-test |
| 107 | MASTER | tests/test_settlement_price_read.py:384 | (receipt_case consumer) | W | `handle.write(json.dumps(failure) + "\n")` (later failed row appended) | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 108 | MASTER | tests/test_settlement_price_read.py:426 | test_real_api_source_change... (source-change family) | W | `name = "account.json" if change == "account_changed" else "decisions.jsonl"` | OTHER:source-change-invalidation | UNCHANGED | PRODUCT-test |
| 109 | MASTER | tests/test_provider_legacy_failure.py:137 | test_only_changed_decision_source_invalidates_selected_legacy_run | W | `path = base / ("decisions.jsonl" if changed == "decisions" else "account.json")` | OTHER:source-change-invalidation | UNCHANGED | PRODUCT-test |
| 110 | MASTER | tests/test_provider_diagnostic_read.py:70 | book_state (shared fixture; origin + latest rows) | W | `(base / "decisions.jsonl").write_text(json.dumps(origin) + "\n" + json.dumps(latest) + "\n")` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 111 | MASTER | tests/test_provider_diagnostic_local_veto.py:100 | test_unbound_synthetic_attempt_keeps_diagnostics_unavailable... | W | `records[-1]["run_id"] = None` | LAST_WINS | LATEST_NON_SUPERSEDED | PRODUCT-test |
| 112 | MASTER | tests/test_china_book.py:669 | test_api_decisions_attaches_security_names_for_every_region | R | `json.loads(web.api_decisions(portfolio=pid).body)["decisions"][0]` | LAST_WINS | UNCHANGED | PRODUCT-test |
| 113 | MASTER | tests/test_china_book.py:686 | test_api_decisions_attaches_security_names_for_every_region | R | `json.loads(web.api_decisions(portfolio="autonomous").body)["decisions"][0]` | LAST_WINS | UNCHANGED | PRODUCT-test |
| 114 | MASTER | tests/test_china_book.py:711 | test_api_decisions_sell_chips_show_pct_and_realized_pnl | R | `json.loads(web.api_decisions(portfolio="hk").body)["decisions"][0]["executed"][0]` | LAST_WINS | UNCHANGED | PRODUCT-test |
| 115 | MASTER | tests/test_china_book.py:827 | test_api_portfolio_banner_summary_falls_back_to_decision_log | W | `(cdir / "decisions.jsonl").write_text(` (newest row summary-less over a rationale row) | LAST_WINS | UNCHANGED (pins the walk-back-past-empty-newest banner) | PRODUCT-test |
| 116 | MASTER | tests/test_brain_overlay.py:61 | test_book_reliability_produces_multiplier | W | `_write_decisions(tmp_path, pid, _decision_rows())` then `block["n"] == 12` | ALL_ROWS | LATEST_NON_SUPERSEDED (else n double-counts a superseded date) | OTHER (brain/)-test |
| 117 | MASTER | tests/test_brain_overlay.py:145 | test_inject_on_appends_digest | W | `_write_decisions(tmp_path, pid, _decision_rows())` | ALL_ROWS | LATEST_NON_SUPERSEDED | OTHER (brain/)-test |
| 118 | MASTER | tests/test_posture.py:22 | _write_book (fixture) | W | `(d / "decisions.jsonl").write_text("\n".join(json.dumps(r) for r in decisions) + "\n")` | LAST_WINS | UNCHANGED | OTHER (brain/)-test |
| 119 | MASTER | tests/test_calibration_regime.py:95 | _write_book (fixture) | W | `(p / "decisions.jsonl").write_text("\n".join(json.dumps(r) for r in rows))` | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | OTHER (brain/)-test |
| 120 | MASTER | tests/test_lesson_application_trace.py:838 | test_modern_unbound_fill_does_not_fall_back_to_nearest_date (fixture) | W | `decision_dir.joinpath("decisions.jsonl").write_text(` (exact decision_id row + closer-by-date decoy) | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED (decoy is a different decision_id; chain must keep the exact bind) | OTHER (brain/)-test |
| 121 | MASTER | tests/test_lesson_application_trace.py:924 | test_legacy_fill_keeps_explicitly_labelled_date_heuristic (fixture) | W | `decision_dir.joinpath("decisions.jsonl").write_text(json.dumps({` (legacy nearest-prior join) | JOIN_BY_ASOF | LATEST_NON_SUPERSEDED | OTHER (brain/)-test |
| 122 | MASTER | tests/test_desk_ab.py:121 | test_autonomous_clone_replays_submitted_book | W | `(sandbox / "decisions.jsonl").write_text(json.dumps(row) + "\n")` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED (else clone weights double-sum) | OTHER (portfolio/)-test |
| 123 | MASTER | tests/test_desk_ab.py:129 | test_autonomous_clone_renormalizes_when_over_gross_one | W | `(sandbox / "decisions.jsonl").write_text(json.dumps(row) + "\n")` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | OTHER (portfolio/)-test |
| 124 | MASTER | tests/test_desk_ab.py:137 | test_autonomous_clone_no_lookahead_to_future_asof | W | `(sandbox / "decisions.jsonl").write_text(json.dumps(row) + "\n")` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | OTHER (portfolio/)-test |
| 125 | MASTER | tests/test_desk_ab.py:214 | test_run_isolates_to_sandbox_and_builds_all_books | W | `(sandbox / "decisions.jsonl").write_text(json.dumps(row) + "\n")` | UNIQUE_PER_ASOF | LATEST_NON_SUPERSEDED | OTHER (portfolio/)-test |
| 126 | PR673 | tests/test_decision_snapshot_journey.py:124 | _stage_book (fixture) | W | `_write_jsonl(_book_dir() / "decisions.jsonl", decisions)` (multi-row capture-scale fixture; magnitude redacted — see off-repo evidence) | OTHER:row-byte-budget | LATEST_NON_SUPERSEDED (supersedes rows consume the 65,536-byte tail budget) | RESEARCH-test |
| 127 | PR673 | tests/test_decision_snapshot_sources.py:637 | test_decisions_jsonl_after_cutoff_contributes_no_row_and_blocks_section | W | `path = repo / "data/portfolios/autonomous/decisions.jsonl"` (mtime-cutoff partition) | OTHER:mtime-cutoff | UNCHANGED (asof-blind: cutoff is the file write clock, not row asof) | RESEARCH-test |
| 128 | PR673 | tests/test_decision_snapshot_sources.py:968 | test_jsonl_available_generation_tracks_its_own_bytes | W | `_write_jsonl(path, [{"id": "d1"}, {"id": "d2"}])` (generation = bytes) | OTHER:bytes-generation | UNCHANGED | RESEARCH-test |
| 129 | PR673 | tests/test_decision_snapshot_sources.py:1040 | test_jsonl_row_with_non_finite_number_is_counted_as_omitted_not_emitted | W | `'{"id": "d1"}\n{"id": "d2", "score": NaN}\n{"id": "d3"}\n'` | OTHER:row-count | UNCHANGED (rows_total/returned count rows, not asofs) | RESEARCH-test |

## 2. WRITERS — every code path that writes a decision-log row

| path | writer | can overwrite? |
|------|--------|----------------|
| bot/autonomous.py:865 `_append_decision_log` | writes via `decision_rows.replace_for_asof` (:918) + `write_rows` | YES — drops prior same-asof rows (barren-entry guard aside) |
| bot/china.py:748 `_append_decision_log` | `replace_for_asof` (:797) + whole-file `write_text` | YES |
| bot/hk.py:745 `_append_decision_log` | `replace_for_asof` (:798) + whole-file `write_text` | YES |
| bot/etf.py:685 `_append_decision_log` | `replace_for_asof` (:725) + whole-file `write_text` | YES |
| bot/heavyweight.py:810 `_append_decision_log` | `replace_for_asof` (:849) + whole-file `write_text` | YES |
| portfolio/autonomous_migration.py:703 `_publish_accepted_migration` | calls `autonomous._append_decision_log` (:740) | YES (inherits the overwrite) |
| bot/decision_rows.py:287 `replace_for_asof` | pure helper producing the persisted row set (the overwrite engine used by all five books) | YES (returns `kept + [entry]`) |
| bot/decision_rows.py:302 `reconcile_settlement` | rewrites the matched row in place (:462, `_atomic_write_rows` :486) | row content YES (queued→executed advance); never adds/removes rows |
| bot/decision_rows.py:497 `refresh_lesson_links` | rewrites the matched row's lesson-link fields (:537, `write_rows` :542) | row content YES; never adds/removes rows |
| scripts/remove_positions.py:100 `_scrub_decisions` (called :137) | rewrites the whole file, scrubbing `holdings`/`executed` arrays in every row | YES (row content) |
| scripts/scrub_cn_tiny_trims.py:81-92 | rewrites the whole file, filtering each row's `executed` | YES (row content) |

## 3. UNSURE

Nothing remained unclassifiable. Classification notes on near-misses that were **excluded** as
pass-throughs / non-selectors (recorded here so the exclusion is auditable):

- `bot/settle.py:902` and `bot/settle.py:986` — call `decision_rows.reconcile_settlement` (ECON);
  no row selection of their own, but they are the enforcement points that would newly raise
  `DecisionSettlementConflict` if append semantics ever yield 2 matching rows (sites 3–8).
- `portfolio/paper_account.py:3481` — calls `validate_queued_decision_snapshot` before any account
  mutation; pass-through enforcement, selection lives in bot/decision_rows.py:166.
- `app/settlement_price_read.py:172` — recomputes `accepted_identity_fields` and compares identity
  columns of an already-selected row; identity match, not an asof selection.
- `app/web.py:1715` (PR673) `api_decision_snapshot` + PR673 `app/static/index.html` decision-snapshot
  panel and `_decisions` list render — the V3 snapshot plane is keyed by `snapshot_id`/`decision_cutoff`
  (a UTC clock), not by decision-row asof; the decisions list render displays every returned row with no
  per-asof selection (duplicate rows for a date would render twice).
- `config/contracts.yml` (PR673 additions) — declares external macro source receipts consumed by
  `portfolio/decision_snapshot_sources.py`; no decision-row contract.
- `control_plane/packet_gate.py:99` `PacketResult.to_meta` — builds the meta dict embedded into a
  decision row at write time; packet_id is derived from (book, asof, submitted_at) but no rows are selected.
- `data_layer/feed_health.py:10`, `brain/calibration.py:414`, `brain/management_lifecycle.py:10` —
  docstring-only mentions of decisions.jsonl.
- `bot/china.py:385` / `bot/hk.py:380` — `refresh_lesson_links` call sites (pass-through to site 7/8).
- `bridge/macro_snapshot.py:124`, `bot/phase2.py:2550`, `app/static/index.html:4792` (MASTER) — read
  `latest.json`'s per-name `decisions[]` / thesis docs, a different store than `decisions.jsonl`.
- `portfolio/forward_evaluation.py:1561+` — snapshot store keeps one file per (book, asof) with a
  `revisions/` + `corrections/` chain for same-asof rewrites; that is the snapshot plane's own
  identity, not a decisions.jsonl row assumption (relevant prior art for the append design).
- Judgment calls embedded in the table: sites 10, 18, 19, 22, 23, 33, 35–39, 41–43, 45–47, 52,
  82–84, 112–115 are marked UNCHANGED because they already take the newest row by ts/file order,
  which under append stays the superseding row; sites 28–31 (+81) are marked as genuinely breaking
  because their newest-first iteration makes the OLDER row's open-entry update run last.

## 4. Counts

129 sites total, per family:
- RESEARCH: 41 = 13 non-test (1–12 MASTER, 13 PR673) + 28 RESEARCH-test (55–78 MASTER, 126–129 PR673)
- ECON: 7 = 4 non-test (28–31) + 3 ECON-test (79–81)
- RUNTIME: 27 = 17 non-test (24–27 management_lifecycle, 32–44 book runners + migration) + 10 RUNTIME-test (82–91)
- PRODUCT: 31 = 7 non-test (45–51) + 24 PRODUCT-test (92–115)
- OTHER: 23 = 10 OTHER (brain/) (14–23) + 3 OTHER (scripts/) (52–54) + 6 OTHER (brain/)-test (116–121) + 4 OTHER (portfolio/)-test (122–125)

Per tree: MASTER 124, PR673 5 (sites 13, 126–129).
Writers: 11 paths (5 book runners + migration caller + replace_for_asof + 2 in-place
reconcilers + 2 repair scripts). UNSURE: 0 (13 exclusion notes above).
All 129 cited file:line expressions were re-opened and verified to appear verbatim on the cited line.
