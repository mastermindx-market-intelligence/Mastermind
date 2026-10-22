# Review record — lr-a12b-r1 (PR #1752, A12 one-window bogey comparison)

**Lane:** pool `ubuntu0`, model glm-5.3, class review C2_COMPLEX_BOUNDED, run-id `pbr-econ-lr-a12b-r1`, 2026-10-22T13:58Z–14:14Z, rc=0.

**Reviewed head:** #1752 e25a7c6f175b43272455eac59e81b07405a155aa (base 3a6d165f).

**Verdict: FAIL #1752** — 1 BLOCKER and 3 MINOR findings.
- The BLOCKER is a missing test, not a production defect: mutation (iv), which puts the attribution book term back on the stored `return_pct`, was caught by no test.
- The production code conforms on every clause the lane executed or read.
- Adversarial cases (a)–(g) all pass.

## ECON disposition
- **BLOCKER 1: repaired** in 3ccee19804002500e44bb953584a1638d48fed46, a test-only commit. It adds `test_attribution_book_term_is_window_return_not_stored_return_pct`, whose fixture diverges: the stored return is −50% and the window return is +5%.
  - Parent self-check on ubuntu1: the mutant fails exactly that test (1 failed, 44 passed), and the pristine tree gives 45 passed.
  - The independent scoped re-review is `lr-a12b2-r1.md`.
- **MINOR 2** (`brain/posture_governor.py:193-206`, `_gap_from_ledger` still subtracts stored per-inception leaderboard returns): not repaired.
  - It is outside A12's four named consumers, and it is pre-existing and latent: the scheduler builds ledgers with no `book_curves`, `multiplier()` has no production caller, and the output only reaches display or a disarmed path.
  - Follow-up candidate for the seat. It is not in the ECON family.
- **MINOR 3** (`brain/book_lifecycle.py:291,755`: first-appearance rows carry each curve's own-window return, and `_active_series` subtracts across windows at `:228`): not repaired. It is pre-existing, starved of data today, and owned outside ECON. Follow-up candidate.
- **MINOR 4** (`app/web.py:1591`: the `vs_benchmark_pct` alias could raise KeyError): not repaired. The lane reports it is unreachable through `compare_curves`.
- **not_verified:** the web Self-Directed block never ran here because fastapi is absent from the ubuntu0 lane venv. The scoped re-review ran mutation (i) on ubuntu1, which has fastapi; see `lr-a12b2-r1.md`.
- **Merge:** #1752 is RESERVED (it touches web, agenda, attribution and firm_allocator), so it returns to the seat for the merge.

---

All checks are complete. Here is the review report.

---

# Independent frontier review — PR #1752 (A12 one-window bogey comparison)

## 1. Contract conformance (diff `origin/master...e25a7c6f`)

**`read_nav_history`** (`brain/benchmark_ledger.py:354`) — conforms. Canonical-date + finite non-bool positive-nav + non-WITHHELD gate; label = `nav_status` or `"UNLABELLED"`; last-row-wins retraction (a later WITHHELD/invalid row pops the date, a later valid row restores it — verified both directions); never raises; missing file → `{curve:{}, status_by_date:{}, skipped:0}`.

**`compare_book_to_ledger`** (`brain/benchmark_ledger.py:405`) — conforms. Whole-body try/except (never raises); no rounding (web's `round(…,4)` is the presentation boundary, as before); no writes (verified byte-identical ledger after repeated calls). Unsupported → `status:"unavailable"` + `reason`, all numbers None. `endpoint_status`: PROVISIONAL dominates; QUALIFIED only when both endpoint labels are exactly `"QUALIFIED"`; absent/unknown/case-differing labels → UNLABELLED.

**`app/web.py:1565-1595`** — conforms. `vs_spy_pct`/`vs_defensive_pct`/`vs_benchmark_pct` set only from a descriptive result; otherwise popped, never 0/old number. `benchmark_window` present on every data path (absent only if the imports themselves raise — environmental). `total_return_pct` untouched.

**`_from_benchmark`** (`brain/improvement_agenda.py:386-452`) — conforms. Gap over the shared window from the book's nav history; evidence carries window, n, endpoint_status; unavailable → no item. Path resolution matches the real writers (`bot/autonomous.py:1025`, `paper_account` per-book `base/nav_history.jsonl`); `self_directed` uses its own `_NAV_PATH`.

**`allocation_attribution`** (`brain/attribution.py:416-507`) — conforms. Scored only from `book_curves`; per-book `window`; top-level `withheld` map; top-level `spy_return`/`defensive_return` stay ledger-wide per-inception (display only — stored values are out of scope).

**`_latest_benchmark`** (`portfolio/firm_allocator.py:149-160`) — delegates to `latest()`; never picks a sidecar.

**Cross-window grep answer:** the four contract consumers are fixed. Everything else is either out of scope (shadow_books:367 and cio.py:269 — same-window co-recorded spy marks; web.py:197 archived perf — co-recorded `spy_nav` over the same base, paper_account-owned; performance_projection:547 — benchmark recomputed from closes over the book's own inception→as_of; forward_evaluation:1247 — paired marks; heavyweight:796 — book-vs-book persona display; lenses:275 / scorer / student — same-lookback factors; run_desk_ab — shadow arms; build() math and stored `return_pct` — declared out of scope) or **still cross-window** (findings 2–3 below, listed in `cross_window_remaining`).

## 2. Existing-test edits in the diff (both quoted in full above)

- `test_allocation_attribution_consumes_benchmark_ledger`: adds `"as_of": "2026-07-01"` (required by the new canonical-asof gate — without it everything is unavailable) and passes an explicit `book_curves` (the new contract scores only supplied curves). Assertions unchanged. Not a weakening — but its fixture is the root cause of finding 1.
- `test_shadow_guarantee_grep` allowlist +1 line: admits only a **test** file whose sole use is a read-only `_latest_benchmark()` call; every production module except `app/web.py` (the GET endpoint) and the module itself remains forbidden. It lets **no** new production reader of shadow output through. The grep proved genuinely strict during this review: it flagged my own scratch test file for merely containing the string.

## 3. Authority

No production write anywhere in the diff (tests write only into conftest-redirected tmp). No NAV/mark/settlement semantics change (`build()` math, `marks.py`, `settle.py`, `paper_account.py` untouched). No new path from a benchmark comparison to sizing/ranking/execution: consumers are the web status row, agenda items, and attribution; `allocation_attribution` confirmed to have **no production caller on master and none added**; `/api/firm_allocator` confirmed a shadow GET endpoint (`app/web.py:3489`) whose import-isolation is grep-enforced.

---

**Findings**

1. **BLOCKER (mutation-coverage gap, per Check 3's rule)** — Mutation (iv) (attribution's book term reverted to the ledger's stored `return_pct`, `brain/attribution.py:478`) is caught by **no test at HEAD**: `tests/test_attribution.py` passes 22/22 on the mutant and the window-consumer attribution tests pass; only the 3 fastapi-env failures remain, identical to pristine HEAD. Both PR fixtures put the book's curve inception exactly at the window start, so stored == window book return (−5 == −5; −10 == −10). The production code is correct — the defect is the missing guard, so a future regression to cross-window scoring would land silently. Proven catchable: my adversarial fixture (stored −50 vs window +5) fails on the mutant (`active_return` −0.60 vs −0.05 expected).
2. **MINOR (still cross-window, pre-existing, outside A12's consumer set)** — `brain/posture_governor.py:193-206` `_gap_from_ledger` still subtracts stored per-inception leaderboard `return_pct` values (book − defensive), undifferenced — the literal #1433 pattern. Latent today: the production daily ledger is built without `book_curves` (`app/scheduler.py:1477`), so persisted ledgers carry no book rows and the gap is None; `multiplier()` has no production caller; consumers are `status()`/`guards()` (display + disarmed arming). Note: its `_bench_history` glob still admits sidecar filenames (harmless — non-ledger JSONs contribute no leaderboard).
3. **MINOR (still cross-window on first-appearance rows, pre-existing)** — `brain/book_lifecycle.py:291` and `:755` (`inc = cr - prev.get(rid, 0.0) if rid in prev else cr`): consecutive-snapshot differencing is same-window, but an id's **first** appearance contributes its full own-window cumulative return, and `_active_series` (`:228`) subtracts book−bogey on those rows cross-window. Also data-starved today; feeds the lifecycle grade card and firm_allocator's advisory fields (shadow surface).
4. **MINOR (fragility)** — `app/web.py:1591` `status["vs_benchmark_pct"] = status["vs_spy_pct"]` would KeyError (swallowed, leaving partial state) if a descriptive result ever lacked the spy delta. Unreachable through `compare_curves` (both delta pairs always present when descriptive).

---

```
RETURN pbr-econ-lr-a12b
head: e25a7c6f175b43272455eac59e81b07405a155aa
findings:
  1. BLOCKER — mutation (iv) uncaught: reverting brain/attribution.py:478 (book_ret = returns_pct[bid]/100.0) to the ledger row's stored return_pct passes the entire repo suite at HEAD (test_attribution.py 22/22 on the mutant; window-consumer attribution tests pass). Both fixtures make stored == window book return (curve inception == window start). Production code is correct; the guard is missing. Catchable — adversarial fixture stored −50 vs window +5 fails on the mutant.
  2. MINOR — brain/posture_governor.py:193-206 still subtracts stored per-inception leaderboard return_pct (book − defensive), undifferenced; pre-existing, outside A12's four consumers, latent (scheduler builds ledgers without book_curves, app/scheduler.py:1477; multiplier() has no production caller; output is status()/guards() display + disarmed arming).
  3. MINOR — brain/book_lifecycle.py:291,755 first-appearance rows carry each curve's full own-window return; _active_series (:228) subtracts cross-window on those rows; pre-existing, data-starved today.
  4. MINOR — app/web.py:1591 KeyError-fragile vs_benchmark_pct aliasing; unreachable via compare_curves.
cross_window_remaining:
  - brain/posture_governor.py:198-206 (_gap_from_ledger — stored per-inception subtraction; latent, no book rows in production ledgers)
  - brain/book_lifecycle.py:291 and :755 (first-appearance rows) consumed at :228-240 (data-starved)
  (all four A12 contract consumers verified fixed; everything else classified out of scope with reasons — co-recorded same-window marks, paper_account-owned, or declared out of scope)
adversarial:
  (a) PASS — book 3 days late: window starts 2026-10-04 (book's first date); spy leg 112/108−1=+3.70%, not stored +12%; book leg +3%.
  (b) helper: unavailable/missing_curve, no numbers. agenda: no item. attribution: scores vs SPY-only cohort (bogey_ids reduced), defensive_return None, window present, active_return −0.05. web: code-read only (fastapi absent) — non-descriptive → pop branch, keys absent, benchmark_window present with reason missing_curve.
  (c) PASS — "2026-10-3", "2026-10-03T00:00", "garbage", None, int 20261003 → all ledger_asof_invalid, numbers None, endpoint_status None.
  (d) PASS — last row WITHHELD: date retracted, skipped=1, window ends 2026-10-02, book leg 104/100 never the withheld 120; duplicate-date last-row-wins verified both directions.
  (e) PASS — QUALIFIED+missing→UNLABELLED; QUALIFIED+"ESTIMATED"→UNLABELLED; QUALIFIED+"qualified"(case)→UNLABELLED; PROVISIONAL+QUALIFIED→PROVISIONAL both orders.
  (f) PASS — with _series.json, _series_meta.json, zzz_cache.json, 2026-10-2.json, 2026-10-02.backup.json, notes.json present, both benchmark_ledger.latest() and firm_allocator._latest_benchmark() return the dated daily ledger.
  (+g) PASS — repeated comparisons write nothing; ledger file bytes and stored return_pct unchanged.
mutations:
  (i)  -> UNCAUGHT by any runnable test in this venv (fastapi absent; the 3 failures on the mutant are the same ModuleNotFoundError as pristine HEAD). Catchers on a fastapi host: test_web_self_directed_vs_spy_on_shared_window (revert yields −80.0 vs asserted +10.0; benchmark_window missing → KeyError) and test_web_self_directed_withholds_unsupported_window[rows0]/[None] (keys present vs asserted absent). Non-web test pinning the same arithmetic: tests/test_benchmark_window_consumers.py::test_falsifier_1433_shared_window_on_helper (shared-window delta, spy −10 not stored +80) — it pins the helper, not the web wiring.
  (ii) -> tests/test_benchmark_window_consumers.py::test_endpoint_status_never_infers_qualified[QUALIFIED-None-UNLABELLED]; ::test_falsifier_1433_shared_window_on_helper
  (iii)-> tests/test_benchmark_window_consumers.py::test_dated_ledger_wins_over_sidecars_for_both_readers
  (iv) -> UNCAUGHT (finding 1)
tests: (file | HEAD | master; all HEAD-only failures are fastapi ModuleNotFoundError, ids identical on shared files — verified by id-set diff)
  test_benchmark_ledger.py             | 21 pass | 21 pass
  test_benchmark_ledger_latest.py      | 23 pass | n/a
  test_benchmark_comparison.py         | 27 pass +51 subtests | same
  test_benchmark_window_consumers.py   | 19 pass, 3 fail (fastapi env) | n/a
  test_attribution.py                  | 22 pass | 22 pass (pre-edit fixture)
  test_firm_allocator.py               | 2 fail (fastapi env), 25 pass | identical
  test_improvement_agenda.py           | 13 pass | 13 pass
  test_improvement_discovery_agenda.py | 6 pass | 6 pass
  test_improvement_discovery_owner.py  | 91 pass | 91 pass
  test_agentos_readiness_agenda.py     | 1 fail (fastapi env), 15 pass | identical
  test_backfill_benchmark.py           | 24 pass | 24 pass
  test_experiment_maturity.py          | 43 pass | 43 pass
  test_experiment_registry.py          | 52 pass | 52 pass
  test_performance_projection.py       | 79 pass | 79 pass
  test_scheduler_governance.py         | 27 pass, 2 skip | same
  test_self_directed.py                | 31 pass | 31 pass
  test_portfolio_archival.py           | 8 fail (env), 12 pass | identical
  test_book_lifecycle.py               | 3 fail (env), 17 pass | identical
  failure_injection/test_m7_drill.py   | 3 fail (env), 22 pass, 1 skip | identical
authority:
  - writes in diff (ledger/book state/nav_history/account) | NONE in production; test writes go to conftest-redirected tmp (tests/conftest.py:416-441)
  - NAV/mark/settlement semantics | unchanged — build() math, marks.py, settle.py, paper_account.py untouched; read_nav_history only filters comparison inputs, rewrites nothing
  - benchmark comparison → sizing/ranking/execution | no new path: web status row + agenda items + attribution; allocation_attribution has NO production caller on master (confirmed; none added); /api/firm_allocator confirmed shadow GET (app/web.py:3489), import-isolation grep-enforced
  - test_firm_allocator.py allowlist +1 | admits a test file only (read-only _latest_benchmark call); no new production reader of shadow output
VERDICT: FAIL #1752 — production code conforms on every executed and read clause, but mutation (iv) (attribution book term → stored return_pct) is caught by no test at HEAD; add a fixture whose stored ≠ window book return (e.g. stored −50 vs window +5) before merge.
commands_run: git log/status/diff (origin/master...e25a7c6f, per-file); git archive HEAD+master → ~/lanes/tmp/pbr-econ-lr-a12b/{head,master}; grep sweeps (return_pct, vs_spy, vs_defensive, spy_return, defensive_return, firm_allocator, allocation_attribution, writes); pytest per-file on head/master + 4 mutation copies; 16 adversarial tests (test_a12b_adversarial.py, scratch-only, removed from tree after evidence capture); failure-id set diff HEAD vs master.
not_verified: app/web.py Self-Directed block never executed (fastapi absent from ~/lanes/venv) — verified by code-read + helper-level tests; the three web tests fail environmentally here and are the identified catchers for mutation (i) on a fastapi host. Production host's live data/benchmark contents unobservable (repo copy empty) — posture_governor/book_lifecycle "latent" status rests on the scheduler code path, not on live artifacts. Repo-wide gate known-red, not run (per packet).
```
