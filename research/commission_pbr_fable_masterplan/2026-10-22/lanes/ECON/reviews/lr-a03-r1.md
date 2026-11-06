# Review record — lr-a03-r1 (PR #1709 A03 PIT marks; PR #1708 repair delta)

Lane: pool `ubuntu0`, model glm-5.3 (pool glm-frontier), class review C2_COMPLEX_BOUNDED, run-id `pbr-econ-lr-a03-r1`, 2026-10-22T08:57Z–09:13Z, rc=0.
Reviewed heads: #1709 74bb3eb3; #1708 delta 3120c30b..8ed3fe1b.
Verdicts: FAIL #1709 (1 BLOCKER, 2 MINOR). PASS #1708-delta (no findings).

ECON disposition:
- #1709 finding 1 (BLOCKER). The parent confirmed the root cause: the folded #728 same-day guard combined with two test_desk_ab tests that priced historical dates only through the mocked undated accessor. Integration miss: test_desk_ab was not re-run after folding #726-#728. Fixed in b4426142 (tests only; they now seed the historical build-day prices through the dated `prices=` input). The PR body's 'pre-existing' label was corrected. Re-review: lr-a03-r2 at b4426142.
- #1709 finding 2 (MINOR, host-local `date.today()` same-day bound). Accepted as a disclosed caveat (fallback-only path). Returned to the seat with #1709.
- #1709 finding 3 (MINOR, unpinned clock at test_portfolio_marks_point_in_time.py:101). Not repaired: it fails only on a host whose clock reads before 2026-06-01. Recorded.
- #1708: together with lr-a02-r1 (PASS at 3120c30b) this covers head 8ed3fe1b. #1708 is reserved for the seat.

---

All verification complete. Here is the review.

---

# Independent review — LR-A03: PR #1709 (A03 point-in-time marks) + #1708 repair delta

## Part A — PR #1709 (`origin/master...origin/pbr/econ-a03-pit-marks`, head `74bb3eb3`)

### Item 1 — Contract (b): row shape on every priced path ✅
All source-row paths emit exactly `{source, price, stale_days, observed_asof, retrieved_at, basis, time_kind, close_qualified}` (`portfolio/marks.py:481-485`), plus `adjusted_through` only on real-path yahoo rows (`marks.py:422-423, 306-309`):
- polygon-eod historical `marks.py:222-223` (raw, session_close, **True**); settled current-session `:232-233` (raw, **True**); intraday `:239-240` (**False**); prevday `:243-245` (**False**, basis unknown); yahoo `:306-309` (**True** iff observed == newest parquet row); legacy-float injection `:358-359` (**False**, fail-closed); carry `:466-471` (**False**, `retrieved_at` = stored clock or None for legacy); seed `:442-443` (**False**); unpriced row `:475-477` (all keys, None/False). Pinned by `test_source_row_shape` and my adversarial suite. No path emits a wrong `close_qualified`.

### Item 2 — historical raw-aggregate / snapshot discipline ✅
Historical (`day < today_et`) reads **only** `daily_closes(sym, day, day, cache=True, adjusted=False)` (`marks.py:217-224`); snapshot is read only for the current ET session pre-settle (`:228-240`), labelled `polygon-intraday`/`polygon-prevday`, `close_qualified: false`, never carry-refreshed (refresh tuple at `:492` excludes both labels — adversarial A2). After close+20 min (`_CLOSE_SETTLE_MINUTES`, `:74`) a missing official bar returns `(None, True)` → `polygon_close_bar_missing` increments and the row degrades to yahoo/carry (`:449-451`; adversarial A1/A7). Weekend/holiday today: no source at all (`:226-227`).

### Item 3 — `data_layer/polygon.py` default path byte-identical ✅ (disclosed hunk)
Default `adjusted=True`: request params `{"adjusted": "true", "sort": "asc", "limit": 50000, ...}` — identical string to master; cache name `{t}_{start}_{end}.json` (`''` suffix) — identical. Raw: `"adjusted": "false"`, `{t}_{start}_{end}_raw.json`; cache bases never share an entry (adversarial A4b). `cdir` moved into `_aggs_cache_dir()` — same per-call path computation, now injectable. Callers of `daily_closes` in the tree: `brain/outcomes.py:58` (default — unchanged), `portfolio/safety.py:274` (default — unchanged), `portfolio/marks.py:219,229` (raw — the intended change), plus tests. No other caller changes behaviour.

### Item 4 — monotone carry ✅
Refresh only from `polygon-eod`/`yahoo-parquet`/`seed` (`marks.py:492`), guarded by `stored_d = observed − stored.asof >= 0` (`:494-495`); stamped with the **observed** date (`:496`). Packet-mandated test written and passing (adversarial A3: mark D2 then replay D1 → carry still D2; A3b: seed replay likewise; plus the PR's own `test_carry_store_never_moves_backward_on_replay`, `test_carry_refresh_stores_observed_asof_not_mark_asof`).

### Item 5 — clock ✅
`grep` over the marks.py diff: the only `datetime.now()` is `_clock()` itself (`marks.py:79`, UTC, injectable via `now=` on every entry point; naive `now` treated as UTC, never machine-local `:396-398`). No `date.today()` remains in `portfolio/marks.py`. Audit `ts` = `now_iso` (`:506`), no fresh clock read. ET midnight boundary and DST verified empirically (adversarial A8: 03:59Z → current-session settled bar `cache=False`, 04:01Z → same asof becomes historical `cache=True`; A8b: EDT/EST settle cutoffs). `date.today()` does remain in the adjacent `shadow_books.py` (finding 2 below).

### Item 6 — callers ✅
`prices_for` (`marks.py:520`), `mark_one` (`:513`) unchanged in signature (`mark_symbols` adds keyword-only `now=`); `shadow_books._gather_prices(tickers, seed, asof=None)` — back-compatible optional param; `desk_ab.run` now passes asof (`desk_ab.py:346`); `app/scheduler.py:1300,1406` call sites untouched. What differs from master: scheduler/self-directed now get raw-basis point-in-time prices (historical = that session's raw aggregate, never the live snapshot; after-close = official bar, never an extended-hours `lastTrade`); shadow historical replays no longer borrow the undated `paper_account._current_price`; desk_ab replays get asof-dated prices. Internal `_polygon_eod` gained a required `asof` but has no non-test callers.

### Item 7 — tests HEAD vs master, and the "pre-existing" claim — **see Finding 1**

| file | HEAD | master |
|---|---|---|
| test_marks_observation_basis (new) | 18 P | n/a (29/30 new items fail on master) |
| test_portfolio_marks_point_in_time (new) | 8 P | n/a |
| test_desk_ab_asof_propagation (new) | 1 P | n/a |
| test_shadow_books_price_clock (new) | 3 P | n/a |
| test_marks | 10 P | 10 P |
| test_daily_marks | 27 P | 27 P |
| test_interim_marks | 3 P | 3 P |
| test_portfolio_eod_marks | 8 F / 3 P | 8 F / 3 P (identical ids) |
| test_shadow_books | 23 P | 23 P |
| test_outcomes | 12 P / 1 S | 12 P / 1 S |
| test_settle_open_price | 14 P | 14 P |
| test_cash_yield | 7 P | 7 P |
| **test_desk_ab** | **2 F / 20 P** | **22 P** ← regression |
| test_safety | 2 F / 16 P | 2 F / 16 P (identical) |

Contract-acceptance quartet (`test_marks`, `test_daily_marks`, `test_interim_marks`, `test_shadow_books`) green on HEAD. The `test_safety.py` 2 failures **are** pre-existing (identical on master) — that half of the claim is confirmed; the `test_desk_ab.py` half is refuted (Finding 1). New tests: **30 items** (28 functions); running them against master code: **29 fail, 1 passes** (`test_same_day_shadow_gather_can_use_current_price_as_emergency_fallback` — pins preserved same-day behaviour, passing on master by design). Discrimination holds.

### Item 8 — adversarial tests ✅
16 written in scratch (`~/lanes/tmp/pbr-econ-lr-a03/head/tests/test_adv_lr_a03.py`), **16/16 pass**: after-cutoff snapshot never selected; intraday+prevday never refresh carry; D2-then-D1 carry monotonicity (packet item 4); seed replay cannot move carry backward; split-dated-after-asof uses the raw close not the restated adjusted close; adjusted cache never answers a raw request; unparseable `observed_asof` injected row ineligible; yahoo non-newest row not close-qualified (and newest-on-own-date is); `polygon_close_bar_missing` once per symbol and zero under injection; ET midnight boundary (03:59Z/04:01Z); DST settle cutoffs (Jul vs Dec); no `avg_cost` in marks code (AST-level); unpriced name absent from `prices` and `mark_one` → None; audit `ts` = pinned clock; seed row shape (carry-official, never close-qualified).

### Item 9 — lane interpretations
(i) **ACCEPT** — `_bounded_age` (`marks.py:153-162`) fails closed on missing/unparseable `observed_asof`; `_accept` (`:416-418`) refuses the row and the chain degrades (P2). Proven adversarially. (ii) **ACCEPT** — the counter increments only in the default-path branch (`:449-451`); injected `polygon_fn` cannot set it and `_polygon_observation` discards the flag (`:254`). (iii) **ACCEPT** — audit `ts` is `now_iso` from the pinnable clock (`:393-399, 506`), replacing master's inline `datetime.now()`.

### Item 10 — A02 seam ruling: **CARRIED-ok**
At `8ed3fe1b`, `paper_account.py:1827-1829` classes a `polygon-intraday` row with prior-session `observed_asof` as CARRIED (the `elif (says_carry or (stale_days or 0) > 0 or observed_day < asof_day)` branch does not read `close_qualified`). That is correct: contract (a) step 2 (CONTRACTS.md:58-59) defines CARRIED as "its evidence says carry or `stale_days > 0`"; the `close_qualified is False` → UNATTESTED rule (CONTRACTS.md:54-56) lives inside step 1 (FRESH) and enumerates same-date cases; contract (b) (CONTRACTS.md:229-231) requires only that the snapshot row "never satisfies A02 FRESH-for-close" and explicitly expects a close_qualified-False prior-session row (prevDay) to "class CARRIED with age ≥ 1". Materially, CARRIED and UNATTESTED both yield PROVISIONAL with `nav_qualified: null` — no NAV can qualify that shouldn't (probe `test_lr_b7`). Must-not-be-UNATTESTED is rejected.

### Item 11 — authority ✅
Added lines contain no `reset`/`balanc`/`rewrite`; every `avg_cost` hit is docstring/comment prose ("never touches avg_cost"); every `seed` hit is the pre-existing seed-price mechanism (source label / seed dict), not an account seed or rewrite. No account reset, no balancing fill, no avg_cost-as-mark.

### Findings

1. **[BLOCKER] `tests/test_desk_ab.py:221` and `:286` — two tests fail on HEAD that pass 22/22 on master; the PR's "pre-existing and identical on master" claim is refuted for this pair.**
   Evidence: master `tests/test_desk_ab.py` → 22 passed; HEAD → `test_run_isolates_to_sandbox_and_builds_all_books` (`assert "SMH" in res["books"]["prod"]["holdings"]` → `[]`) and `test_carried_day_empty_inputs_holds_not_liquidates` (`(AME).shares == 0`) fail, reproduced twice. Root cause: `portfolio/shadow_books.py:398` gates the legacy `paper_account._current_price` fallback on `mark_asof == str(date.today())`; both tests replay historical dates (2026-06-21/22) and monkeypatch `_current_price` as their only price feed, which the gate now (contract-correctly, per #728) refuses — and with no Polygon key and no vendored yahoo parquet on this host (`vendor/macro` absent here *and* in the live worktree) nothing else prices the names. The behaviour change is contract-mandated; the defect is that the two existing tests were left unamended (unlike the #726-era tests the carrier did amend) and the regression was misreported as pre-existing. Per the packet's severity table ("a failing test that passes on master") this is a BLOCKER; the repair is to amend the two tests (seed the prices or use a same-day asof).
2. **[MINOR] `portfolio/shadow_books.py:389,398` — the same-day bound uses machine-local `date.today()`, not the ET session date of the marks clock.** Around UTC midnight the emergency `_current_price` fallback can be admitted for a mark date whose ET session has not opened (or vice versa). Fallback-only; historical replays are unaffected.
3. **[MINOR] `tests/test_portfolio_marks_point_in_time.py:101` — `M._polygon_eod("AAPL", "2026-06-01")` runs unpinned against the real machine clock**, contrary to the file's own "every clock is pinned" preamble; breaks if the suite ever runs before 2026-06-01. Fragility only.

## Part B — #1708 repair delta (`3120c30b..8ed3fe1b`)

- **lr-a02-r1 finding 1 (garbage `stale_days` → FRESH/QUALIFIED): FIXED.** `portfolio/paper_account.py:1800-1814` parses via `float()` with a `stale_garbled` flag (bools, NaN/±inf, non-numeric all garbled); FRESH gate requires `not stale_garbled` (`:1819-1820`); garbled + current → UNATTESTED (`:1836-1837`); fractional ages round away from zero; garbled + non-current observed → UNPRICED/WITHHELD. Pinned by 15 new parametrized tests and my probe `test_lr_b1` (`stale_days="not-a-number"` → UNATTESTED, PROVISIONAL — was FRESH/QUALIFIED at `3120c30b`).
- **lr-a02-r1 finding 2 (rejected input persisted as last mark): FIXED.** `paper_account.py:3640-3643` — `if line["class"] == "UNPRICED": continue` in `mark()`'s persistence loop; pinned by `test_mark_does_not_persist_an_unpriced_input` / `test_mark_keeps_the_prior_persisted_mark_when_input_is_unpriced`.
- **Carry age 0 with no `observed_asof`** (`:1833`, `asof − max(stale_days or 0, 0)`): **safe** — a carry-labelled line can never be FRESH (`says_carry` blocks it), so the book is PROVISIONAL at best and age 0 cannot qualify a NAV; contract (a) E3 explicitly documents "0 is possible when the source labels the line a carry but supplies no age" (probe `test_lr_b4`).
- **WITHHELD**: no `nav_history` row written (WITHHELD branch returns at `:3698` before the record is built); `nav_withheld.jsonl` written idempotently per `(date, mark_source)`, exposure in shares, no cost term (probe `test_lr_b6`). **`nav(strict=True)`** raises `NavWithheld` (`:1948-1952`, probe `test_lr_b5`). **No evidence ⇒ PROVISIONAL at best** (UNATTESTED, probe `test_lr_b3`).
- **Tests**: `test_paper_account_nav_qualification.py` 39/39 pass at `8ed3fe1b`; `test_paper_account.py` 30 P / 1 F on both `8ed3fe1b` and master — the single failure is `test_api_performance_route_never_500` (`ModuleNotFoundError: fastapi`), byte-identical on master (environment, also seen in lr-a02-r1).
- **Findings: none.**

---

```
RETURN pbr-econ-lr-a03
PR #1709 findings:
  1. [BLOCKER] tests/test_desk_ab.py:221 & :286 — test_run_isolates_to_sandbox_and_builds_all_books and test_carried_day_empty_inputs_holds_not_liquidates fail on HEAD (2F/20P) but pass 22/22 on origin/master; the PR claim that the test_desk_ab pair is "pre-existing and identical on master" is REFUTED (the test_safety pair IS confirmed pre-existing). Cause: shadow_books.py:398 same-day-only gate on the legacy _current_price fallback (contract-correct per #728) + historical replay dates + no polygon key / no vendored yahoo parquet on this host ⇒ names unpriced; the two existing tests were left unamended. Severity per packet rule "a failing test that passes on master". Remedy: amend the two tests (seed prices or same-day asof), not revert the gate.
  2. [MINOR] portfolio/shadow_books.py:389,398 — same-day fallback bound uses machine-local date.today(), not the ET session date of the marks clock; edge disagreement around UTC midnight; fallback-only.
  3. [MINOR] tests/test_portfolio_marks_point_in_time.py:101 — _polygon_eod called without now= (real machine clock), contrary to the file's pinned-clock preamble; breaks only if run before 2026-06-01.
interpretations: (i) ACCEPT — _bounded_age (marks.py:153-162) fails closed on missing/unparseable observed_asof; row degrades down the chain (adversarial A5). (ii) ACCEPT — counter incremented only on the default Polygon path (marks.py:449-451); injected pfn cannot set it, _polygon_observation discards the flag (:254); counts once per symbol (A7). (iii) ACCEPT — per-asof audit "ts" = now_iso from the pinnable run clock (marks.py:393-399,506; adversarial A11).
a02_seam_ruling: CARRIED-ok — paper_account.py:1827-1829 @8ed3fe1b classes the prior-date polygon-intraday row CARRIED (stale_days>0 branch, close_qualified unread); contract (a) step 2 (CONTRACTS.md:58-59) defines CARRIED by "carry or stale_days > 0", the close_qualified-is-False→UNATTESTED rule lives inside step 1/FRESH (CONTRACTS.md:54-56) and contract (b):229-231 requires only "never satisfies A02 FRESH-for-close" while expecting the close_qualified-False prevDay row to "class CARRIED with age ≥ 1"; CARRIED and UNATTESTED both yield PROVISIONAL/nav_qualified=null, so no unqualified NAV can result (probe test_lr_b7).
tests: file | HEAD | master — test_marks_observation_basis 18P | n/a(new); test_portfolio_marks_point_in_time 8P | n/a(new); test_desk_ab_asof_propagation 1P | n/a(new); test_shadow_books_price_clock 3P | n/a(new); test_marks 10P|10P; test_daily_marks 27P|27P; test_interim_marks 3P|3P; test_portfolio_eod_marks 8F/3P|8F/3P (identical ids, pre-existing); test_shadow_books 23P|23P; test_outcomes 12P/1S|12P/1S; test_settle_open_price 14P|14P; test_cash_yield 7P|7P; test_desk_ab 2F/20P|22P (regression, finding 1); test_safety 2F/16P|2F/16P (identical, pre-existing). New tests: 30 items; on master code 29 fail / 1 passes (same-day-fallback preservation pin) — discrimination holds. Contract quartet (marks/daily/interim/shadow) green on HEAD.
adversarial: 16 written, 16 pass, no failures (~/lanes/tmp/pbr-econ-lr-a03/head/tests/test_adv_lr_a03.py); Part B probes 7 written, 7 pass (a02/tests/test_adv_lr_b.py).
VERDICT: FAIL #1709 — every contract item (b) 4–8 and the polygon default-path invariance are correctly implemented, but two unamended test_desk_ab tests regress HEAD vs master and the PR mislabels that pair pre-existing (BLOCKER per the packet's severity rule).
#1708 delta findings: none — lr-a02-r1 #1 FIXED (paper_account.py:1800-1814,1819-1820,1836-1837 + 15 new tests), #2 FIXED (:3640-3643 + 2 new tests); carry-no-age age 0 is safe (never FRESH ⇒ PROVISIONAL at best; contract (a) E3); WITHHELD writes no nav row + nav_withheld.jsonl (shares, no cost); nav(strict=True) raises NavWithheld (:1948-1952); no evidence ⇒ PROVISIONAL; nav-qualification 39/39, paper_account 30P/1F identical on master (fastapi env-fail).
VERDICT: PASS #1708-delta — both prior findings fixed with pinning tests; no new defect found.
commands_run: git rev-parse/verify refs; git show CONTRACTS.md (§a,§b); git diff origin/master...origin/pbr/econ-a03-pit-marks (marks/polygon/desk_ab/shadow_books + 4 test files); git grep daily_closes/_polygon_eod/_yahoo_parquet/prices_for/mark_one/_gather_prices; git show marks.py+paper_account.py @head/8ed3fe1b; git show lr-a02-r1.md @econ-hk-bridge; git diff 3120c30b..8ed3fe1b; git archive → ~/lanes/tmp/pbr-econ-lr-a03/{head,master,a02}; pytest matrices (14 files HEAD, 10 files master ×2 runs), new-tests-on-master discrimination run, per-file loops ×2, adversarial suites ×3 runs, Part B paper_account/nav suites on 8ed3fe1b+master; authority grep over added lines.
not_verified: live Polygon/yahoo network paths (offline mandate — all feeds injected/monkeypatched); the #1709/#1708 PR descriptions on the forge (only local refs available); root cause of the 8 pre-existing test_portfolio_eod_marks failures (identical on both trees, out of this PR's gate); behaviour on a data-complete host (vendor/macro parquet) where the desk_ab pair may pass — vendor/macro is absent on this host entirely, including the live worktree, and the regression was reproduced deterministically here.
```
