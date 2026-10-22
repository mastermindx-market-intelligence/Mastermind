# A12 — benchmark ledger: findings and bounded plan (ECON, 2026-10-22)

Scope: `brain/benchmark_ledger.py` (ECON family) and its readers. Evidence is the read-only capture
`/Volumes/Mastermind/evidence/pbr/econ-capture-20261022T073119Z/live-data/benchmark/` (79 top-level
`*.json`, 76 under `hk/`, 76 under `china/`; not committed) read against `origin/master` d31aade9.
No bot code was run against live data. Verdict classes are kept separate: **operational
correctness** (does the code do what it says), **economic qualification** (is the number a valid
comparison), **investment value** (not claimed anywhere in this note).

## Findings

| # | Finding | Status | Evidence |
|---|---------|--------|----------|
| F1 | `latest()` selects a sidecar, not a ledger | **OBSERVED** on live since about 2026-07-26 | `benchmark_ledger.py:315-321` is `sorted(_BENCH_DIR.glob("*.json"))[-1]`; in the capture the last three names sort as `2026-10-21.json`, `_series.json`, `_series_meta.json`, so `latest()` returns `_series_meta.json` (a `{SYM:{date:source}}` map with no `bogeys` / `leaderboard`). `_series_meta.json` mtime 2026-07-26T04:21Z. |
| F2 | US bogeys are renormalized per basket, not on one common window | **LATENT** | `build()` calls `renorm_basket(series,[SPY])` and `renorm_basket(series, DEFENSIVE_BASKET)` (`:180-181`); each picks its own `_common_inception` (`:72-91`). All 77 dated US ledgers (2026-07-03..10-21) show the same inception (2026-06-18) for `spy` / `defensive` / `regime_max`: 0 ledgers differ. The #1433 false deficit therefore has not occurred in the stored data; it occurs as soon as one constituent's history starts later than the others. |
| F3 | Regional bogey window is not the book's window | **OBSERVED** in data, **LATENT** in effect | HK and CN: 17 ledgers (07-06..07-30) are the FXI proxy with inception 2026-06-18; 59 ledgers (07-31..10-21) are the native index (`^HSI` / `000300.SS`) with inception **2024-07-31**. Latest regional `return_pct`: HK 37.6091, CN 19.4607, i.e. two-year index returns, not returns since the books started (2026-06-18). Every regional leaderboard is `['regional']` only, because the scheduler passes no `book_curves` (`app/scheduler.py:1477` for US, `~1482` for `build_regional`). |
| F4 | Regional review history differences a cumulative return additively | **LATENT** (out of ECON family) | `brain/book_lifecycle.py:708-764` `_regional_review_history` takes `inc = cr - prev` and uses the first cumulative as the first increment. (The US `history_from_ledgers`, `:254-299`, does the same and documents it as a first-order approximation; with US book and bogeys on one 2026-06-18 window and cumulatives near 3-6% the error is small and symmetric. The regional case is neither.) For a cumulative based at 2024-07-31 the true period return is `(1+C_t)/(1+C_{t-1}) - 1`; the additive form overstates it by the factor `(1+C_{t-1})`, about 1.38x for HK and 1.19x for CN at current levels, and books the whole two-year 37.6% / 19.5% as one review period. No grade is affected today because no ledger carries a book row (`_active_series`, `:228-241`, skips rows missing the book); the US leaderboards likewise hold only `defensive` / `regime_max` / `spy`. |

Consumers of `latest()` (F1), each of which has received the sidecar on live:

- `app/web.py:1569-1580` — Self-Directed `vs_spy` / `vs_defensive`: absent.
- `brain/improvement_agenda.py:390-396` — benchmark leaderboard rows: absent.
- `brain/attribution.py:430-443` — spy / defensive window returns: `None` (status "building").
- `portfolio/firm_allocator.py:151-160` `_latest_benchmark()` — a **separate** sorted-glob reader
  with the same defect; not fixed by #1432; outside ECON family.

Not verified: the capture holds no `self_directed` directory, so the window a repaired Self-Directed
comparison would use is unverified.

## Consequence for #1432 and #1434

- #1432 (draft/HOLD, `sol/c2-benchmark-latest-ledger-20261013` @ 9dda10f1) fixes the selector only.
  Its body says there is no production incidence; the capture shows OBSERVED incidence (F1). Merged
  alone it would **re-activate** three consumers on per-basket-normalized curves (F2) and on
  two-year regional returns (F3). Recommendation: **hold #1432 standalone**; fold its selector into
  the A12 build below (seat ruling, because consumer semantics change either way).
- #1434 (draft/HOLD, `fix/1433-descriptive-benchmark-comparison` @ d5fec1eb) already has an
  independent PASS for its common-point comparison arithmetic (`brain/benchmark_comparison.py`). The
  A12 build reuses that arithmetic rather than writing a second one.

## Bounded plan

1. **ECON build (one PR, `brain/benchmark_ledger.py` + tests only).**
   a. `latest()` reads only canonical `YYYY-MM-DD.json` names (the #1432 selector).
   b. US bogeys share one inception: the latest of the per-basket common inceptions, so `spy`,
      `defensive` and `regime_max` start at 1.00 on the same day (and `do_nothing` when supplied).
      No-op on today's data (F2: 0 differing); changes only the divergent case.
   c. `build_regional(..., inception=None)` accepts an explicit window start. Default `None` keeps
      today's output byte-identical; a supplied inception renormalizes the native index there.
   d. Falsifiers: the #1433 synthetic case (SPY 100→200→180 from Oct 1; defensive from Oct 2
      100→110) must report SPY −10% and defensive +10% over the common window, not +80% vs +10%;
      a sidecar-only directory must make `latest()` return `{}`; the regional default must be
      byte-identical to master on a fixture.
2. **Out of family, routed by the seat:**
   - `brain/book_lifecycle.py` `_regional_review_history`: geometric linking
     (`(1+C_t)/(1+C_{t-1}) - 1`) and no first-row full-cumulative increment (F4).
   - `portfolio/firm_allocator.py:151-160`: the same date-name filter as 1a.
   - RUNTIME request: `app/scheduler.py:1477` / `~1482` pass `book_curves` (book NAV curves and
     the `do_nothing` carry) and the regional book inception, so the ledgers carry book rows.
3. **Merge:** a seat ruling. 1a-1c change what three consumers display once wired; ECON does not
   merge it on its own authority.

Economic qualification today: the stored US bogey curves are internally consistent (F2 latent); the
stored regional bogey curves are valid index returns but **not** a qualified comparison window for
the CN / HK books (F3). No statement is made about whether any book beat or lagged its benchmark.
