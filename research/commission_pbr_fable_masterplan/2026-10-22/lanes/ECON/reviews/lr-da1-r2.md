# Review record — lr-da1-r2 (PR #1747, D-ACCT-1 fail-closed account state)

Lane: pool `ubuntu0`, model glm-5.3, class review C2_COMPLEX_BOUNDED, run-id `pbr-econ-lr-da1-r2`, 2026-10-22T13:23Z–13:38Z, rc=0. (`pbr-econ-lr-da1-r1` was refused at admission, rc 78 `bounded_complexity_requires_escalation`, before any effect; r2 carried an escalation reason.)
Reviewed head: #1747 1c6027c85b412a7937a1cf22f1d7492a888be0f3 (base fc4db8de).
Verdict: PASS #1747 (4 MINOR, 0 BLOCKER). `fresh_book_path_reachable: NO`. All three mutations caught by shipped tests.

ECON disposition:
- MINOR 1 (an `already_quarantined` re-detection writes no new ledger row or run_event): not repaired. It conforms to the contract's "one row per distinct content", which the PR's idempotency test pins. Follow-up candidate: re-register when the ledger row for a surviving copy is missing.
- MINOR 2 (an unreadable file has no bytes to copy, so the status is `quarantine_failed`): not repaired. The raise, the HARD_STOP event and the untouched original all hold.
- MINOR 3 (check-then-write window against an external, non-cooperating writer): not repaired. It is inherent to check-then-write, and in-process writers are serialised under `_paper_transaction_lock`.
- MINOR 4 (strict replay message while a WAL is outstanding): cosmetic. The exception type and the quarantine and alert effects are the same.
- Landing gate (seat): the PR's `validate_account_state` was run by the parent against every captured `account.json` in `/Volumes/Mastermind/evidence/pbr/econ-capture-20261022T073119Z/live-data`. 14/14 are VALID, including c8fc39d3b91c0be8c46691b15c0e6bd91faa8e3d5b731895ac48ccba23809e6e.
- not_verified: `tests/test_decision_availability.py` could not run on the lane because fastapi is absent from the lane venv. It failed to collect on both HEAD and master. CI is the evidence for that file.
- #1747 is RESERVED (NAV/account semantics), so it returns to the seat for the merge.

---

All checks are complete. Here is the review.

---

# Independent frontier review — PR #1747 (D-ACCT-1 fail-closed account state)

## Check 1 — Contract conformance and the fresh-book question

Read the full diff of `portfolio/paper_account.py`. Clause by clause:

| Contract clause | Verdict | Evidence (HEAD `portfolio/paper_account.py`) |
|---|---|---|
| Missing file → `_fresh_account()` as before | ✓ | `:419-425` — early `not exists` + `except FileNotFoundError` returns |
| Original never moved/renamed/truncated/deleted | ✓ | Only account.json write is `_save_account:498`; `_durable_unlink` targets are WAL `:1554`, receipts `:1308`, pending target `:3623/:3656`, tmp `:460` — never account.json. Inode test (e) confirms |
| Byte copy `account.quarantine.<sha256[:16]>.json`, idempotent per content | ✓ | `:331-337` (`candidate`, `already_quarantined`), `_atomic_write_bytes` writes the copy only |
| One `account_quarantine.jsonl` row + one `run_events` (`kind=account_state_invalid`, `severity=HARD_STOP`) per distinct content | ✓ | `:339-361`; idempotency pinned by PR test 4 (3 loads → 1 row) and different content → 2nd row |
| RAISE `AccountStateInvalid ⊂ PaperTransactionConflict` | ✓ | class at `:634-643` |
| Never a fresh book for an existing file, either mode | ✓ | `_load_account_file` is the only `_fresh_account()` producer (`:421,425`), both missing-file-gated; mutation (i) confirms tests catch the restore |
| `strict=True` messages preserved | ✓ | `_account_invalid_error` — byte-equal legacy strings; PR test 10 |
| `_save_account` refuses invalid file / invalid state | ✓ | `:482-500` — `validate_account_state(state)` raise (record=None), then `_assert_existing_account_valid` |
| `validate_account_state` pure, exact codes, number = int/float-not-bool-finite, extra keys OK, negatives valid | ✓ | Probed directly: negatives → `[]`, `'starting_nav': 'rich'` → `starting_nav_invalid` (no TypeError — comparison short-circuited by the type check), extra keys ignored, `None`/`3.5` → `not_an_object`, never raises |
| `account_file_status` read-only, MISSING/VALID/INVALID + sha256 | ✓ | `:269-297` — `.exists()`/`.read_bytes()` only; PR test 13's directory-listing assertion |
| `reset_cost_basis_to_market` removed, no alias | ✓ | No source references at HEAD; master had no non-test caller (only its own def + one test) |
| Out-of-scope surfaces untouched | ✓ | Diff = 3 files; `mark()`/`valuation()`/`nav()`/`settle.py`/callers/`_fresh_account()` unhunked |

**All 15 load sites traced** (the 14 + the internal delegation at `:193`): `accrue_cash_yield` `:552` and fallback `:567`; recovery strict `:1511`; `valuation:1987`; `nav:2179`; `positions_pnl:2201`; `unpriceable_exit_tickers:2251`; `unpriceable_target_requirements:2292`; `rebalance:2475`; `execute_fill:2678`; `queue_orders:2808`; `fill_pending:2950`; `save_pending_target` strict `:3602`; `mark:3818`. Every one either raises through before any write, or (accrue only) is caught and its fallback load **re-raises → returns 0.0 with no write**. All 5 `_save_account` sites (`:563, :1516, :3835, :3838, :3887`) sit after a successful load and behind the existing-file guard. The only `except Exception` that can swallow a load failure inside this module is `accrue_cash_yield:565/568`, and it cannot write.

**Answer: NO path exists** in `portfolio/paper_account.py` by which an existing invalid account.json is overwritten or replaced by a fresh/seeded state.

## Findings

1. **MINOR (fragility)** — `portfolio/paper_account.py:339`: re-detections of unchanged content with the quarantine copy already present (`already_quarantined`) skip both audit sinks (ledger row and run_events); only the ERROR log fires. If `account_quarantine.jsonl` is later lost while the copy survives, no new row/event is ever recorded for that content. Conforms to the contract's "per distinct content" as pinned by the PR's own idempotency test — an audit-trail edge, not a guard breach.
2. **MINOR (wording)** — an *unreadable* existing file yields `raw_bytes=None`, so no byte copy is possible; the record is `quarantine_failed` with one row + one HARD_STOP event and the raise still happens (`:312-328`). Contract-conformant in effect (original untouched, fail-closed); there are no bytes to copy.
3. **MINOR (fragility)** — `_save_account` has a check-then-write TOCTOU window between `_assert_existing_account_valid` and `_atomic_write_bytes` against an *external, non-cooperating* process. All in-process writers hold `_paper_transaction_lock`, and the same-call window (check c) is closed by the guard; the residual window is inherent to check-then-write.
4. **MINOR (cosmetic)** — with an outstanding WAL, `_load_account` surfaces the *strict* replay message (recovery loads with `strict=True` at `:1511`) rather than the non-strict one. Same exception type, same quarantine/alert effects.

No BLOCKER findings.

## Existing-test edits in the diff (one only)

`tests/test_engine_guardrails.py` — `test_reset_cost_basis_zeroes_unrealized` (exercised the deleted `reset_cost_basis_to_market`) is replaced by `test_reset_cost_basis_to_market_is_removed` asserting `not hasattr(pa, "reset_cost_basis_to_market")` and absence from `inspect.getsource(pa)`. **Justified, no guard weakened**: the contract mandates removal with no alias; master had no non-test caller; the old test's only purpose was to verify the removed function worked.

## Adversarial, mutations, regression, authority, blast radius

Summarized in the RETURN block below; all adversarial tests passed (12/12) after I fixed three of my own harness errors (a dust-filtered $500 buy, a never-fired monkeypatch seam, an over-strict WAL assertion — the WAL surviving a stopped commit is the designed write-ahead artifact, and the corrupted account bytes stayed untouched). All three mutations are caught by PR tests; the 16 runnable named files have byte-identical outcome ids on HEAD and master (107 pre-existing offline-lane non-passes on both sides); the authority grep found no reset/seed/balancing-fill/NAV/mark/settlement change and no write beyond the quarantine copy, its ledger, and the contract-required governance event.

```
RETURN pbr-econ-lr-da1
head: 1c6027c85b412a7937a1cf22f1d7492a888be0f3
findings:
  1. MINOR (fragility) paper_account.py:339 — "already_quarantined" re-detections skip the ledger row and run_events (ERROR log only); if account_quarantine.jsonl is lost while the copy survives, that content is never re-registered. Conforms to "per distinct content" as pinned by the PR's own idempotency test.
  2. MINOR (wording) paper_account.py:312-328 — an UNREADABLE existing file cannot produce a byte copy (raw_bytes=None -> status quarantine_failed); row + HARD_STOP event + raise still happen; original untouched. Contract-conformant in effect.
  3. MINOR (fragility) paper_account.py:482-500 — _save_account check-then-write TOCTOU vs an external non-cooperating process corrupting the file between the guard and the write; in-process writers are serialized under _paper_transaction_lock and the same-call window is closed.
  4. MINOR (cosmetic) paper_account.py:1511 via _load_account — with an outstanding WAL the strict replay message is raised instead of the non-strict one; same type, same quarantine/alert effects.
fresh_book_path_reachable: NO (both _fresh_account() returns in _load_account_file:421,425 are missing-file-gated; the only account.json writer is _save_account:498 behind both guards; accrue_cash_yield's except-Exception fallback re-raises internally and returns 0.0 with no write; all 15 load + 5 save sites traced)
adversarial:
  (a) mark() on invalid file -> AccountStateInvalid; no nav_history.jsonl, no fills.jsonl; original byte-identical; only artifacts = quarantine copy + ledger row. PASS
  (b) execute_fill / rebalance / fill_pending(queued) / queue_orders -> all AccountStateInvalid before any write; no fills.jsonl, no WAL; original unchanged. PASS
  (c) corrupt-after-load same call: mark (via _benchmark_for seam) -> _save_account existing-file guard quarantines + raises, no nav row; execute_fill (via _persisted_fill_facts seam) -> WAL written by design, recovery strict load raises, corrupted bytes preserved, no fills row; accrue_cash_yield (via pending_settlement_receipts seam) -> never raises, returns 0.0, corrupted bytes preserved. PASS
  (d) non-default book "autonomous" via registry: _load_account / mark / sell-side execute_fill / _save_account all fail closed with their own quarantine copy; account_file_status("autonomous")=INVALID+sha256. (A non-canonical BUY on that book is rejected by the identity gate BEFORE the account check — both fail closed.) PASS
  (e) st_ino/st_dev/st_mtime_ns unchanged after quarantine; copy has a different inode (copy, not rename); bytes identical. PASS
  (f) extra: pending WAL + invalid file -> raises via recovery strict path; WAL retained for inspection. PASS
mutations:
  (i) fresh-book restore (non-strict) -> 28 PR tests: all 24 test_invalid_existing_file_fails_closed_and_quarantines[*] + test_repeated_invalid_loads_are_idempotent_until_content_changes + test_execute_fill_on_invalid_account_raises_without_fill_or_save + test_run_event_failure_does_not_soften_the_raise + test_quarantine_copy_failure_keeps_the_raise_and_the_original (+7 adversarial)
  (ii) quarantine MOVES the original -> 31 PR tests incl. all parametrized cases, both mark tests, accrue, execute_fill, save-refusal, event-failure (+10 adversarial incl. the inode test)
  (iii) _save_account existing-file guard dropped -> tests/test_paper_account_invalid_state.py::test_save_account_refuses_to_overwrite_an_invalid_file (+3 adversarial: c1, c3, d2)
  none UNCAUGHT
tests (non-pass counts identical; full id-level diff EMPTY, 107 pre-existing offline-lane non-passes on both):
  test_paper_account.py | 1 | 1 (identical ids)
  test_engine_guardrails.py | 1 | 1 (identical ids)
  test_paper_account_nav_qualification.py | 0 | 0
  test_receipt_projection_durability.py | 0 | 0
  test_decision_settlement_reconciliation.py | 2 | 2
  test_cash_yield.py | 0 | 0
  test_decision_availability.py | collection ImportError (ModuleNotFoundError: fastapi) both sides — environment, see not_verified
  test_performance_availability.py | 15 | 15
  test_daily_marks.py | 0 | 0
  test_brain_pending_truth.py | 15 | 15
  test_portfolio_eod_marks.py | 8 | 8
  test_china_book.py | 19 | 19
  test_mw1_guardrails.py | 0 | 0
  test_portfolio_archival.py | 8 | 8
  test_settlement_price_read.py | 30 | 30
  test_selected_price_receipt_integration.py | 6 | 6
  test_pbr_held_pending_change.py | 2 | 2
  test_paper_account_invalid_state.py (new) | 40 passed | n/a on master
blast_radius (no external catcher of PaperTransactionConflict/AccountStateInvalid exists anywhere; no catcher writes account state -> no BLOCKER):
  app/scheduler.py:1292 union want-set | catches Exception, pass — read-only degradation (fewer warmed tickers)
  app/scheduler.py:1349 daily-mark loop | per-book except Exception -> FREEZE _step_failed_event + continue, no write (pre-PR this path silently reset a live book — the exact hazard the PR removes)
  app/web.py:1332-1345 account_preview | except Exception: pass — preview omitted, no write
  app/web.py:2296 history (strict=True) | except Exception -> account_unavailable, no write; strict already raised pre-PR
  bot/settle.py:769 (strict=True) | except Exception -> settlement_finalization_pending, receipt retained, no write; same failure class as pre-PR
  brain/decision_submission.py:250 | except Exception -> DecisionBoundaryFreeze, no write
  portfolio/trade_history.py:87 / safety.py:174 / firm_exposure.py:856 | except Exception -> read-only empty/None aggregates, no write
  bot/phase2.py:1121 (_pa_mark.mark) | except Exception: pass — mark refused internally, no write
  bot/{autonomous,china,hk,etf,heavyweight}.py state0/state/held (~50 sites) | raises-through — build fails loudly (was the silent-reset vector); heavyweight's rebalance try does not wrap its before/after loads
  scripts/{fill_pending_now,check_live_marks,repair_live_books_20260730}.py, brain/*_mcp.py, portfolio/desk_ab.py | raises-through (operator/read paths)
  portfolio/{shadow_books,self_directed}.py | own separate stores/loaders, untouched by the PR
  portfolio/autonomous_migration.py:379 | _load_account patched to a bound snapshot — unaffected
VERDICT: PASS #1747 — every contract clause holds, no fresh-book or overwrite path exists in paper_account.py, all three mutations are caught by shipped tests, regressions are id-identical to master, and no blast-radius catcher writes account state.
commands_run: git rev-parse/log/status; git diff --stat + full diff (paper_account.py, test_engine_guardrails.py) and git show of tests/test_paper_account_invalid_state.py; git grep at HEAD for _load_account/_save_account/_fresh_account/_atomic_write_bytes/_durable_unlink/except-Exception sites and reset_cost_basis (incl. origin/master); git archive 1c6027c85 + origin/master into ~/lanes/tmp/pbr-econ-lr-da1/{head,master}; pytest (venv, -p no:cacheprovider -o addopts="") 16 named files on both trees with id-level diff; new file 40 passed on HEAD; authored+ran 12 adversarial tests (a-f) in scratch; applied 3 mutations in scratch copies (mut1-3) and ran new+adversarial files against each; direct validator probes (negatives/strings/extra keys/purity); sed/awk reads of scheduler/web/settle/phase2/heavyweight/shadow_books/autonomous_migration/decision_submission/trade_history/safety/firm_exposure call sites.
not_verified: tests/test_decision_availability.py could not be executed — fastapi is absent from ~/lanes/venv (identical collection ImportError on HEAD and master, so no regression is possible from this diff, but there is also no pass evidence); live/network-dependent behaviours by design (offline read-only lane — the 107 pre-existing non-passes are identical offline failures on both sides); the external-process TOCTOU window (finding 3) was verified by code reading, not empirically raced.
```
