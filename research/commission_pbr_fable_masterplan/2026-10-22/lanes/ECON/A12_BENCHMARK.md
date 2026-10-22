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
| F3 | Regional bogey window is not the book's window | **OBSERVED** in data, **LATENT** in effect | HK and CN: 17 ledgers (07-06..07-30) are the FXI proxy with inception 2026-06-18; 59 ledgers (07-31..10-21) are the native index (`^HSI` / `000300.SS`) with inception **2024-07-31**. Latest regional `return_pct`: HK 37.6091, CN 19.4607, i.e. two-year index returns, not returns since the books started (2026-06-18). Every regional leaderboard is `['regional']` only, because the scheduler passes no `book_curves` (`app/scheduler.py:1477` for US, `~1482` for `build_regional`). The persisted curve is long enough to rebase at read time: on the 2026-10-21 ledger the HK curve goes 1.379381 (2026-06-18) → 1.376091 (−0.24 %) and the CN curve 1.435644 → 1.194607 (−16.79 %), against persisted `return_pct` 37.61 / 19.46. These are index returns over the books' window; nothing here says how any book did against them. |
| F4 | Regional review history differences a cumulative return additively | **LATENT** (out of ECON family) | `brain/book_lifecycle.py:708-764` `_regional_review_history` takes `inc = cr - prev` and uses the first cumulative as the first increment. (The US `history_from_ledgers`, `:254-299`, does the same and documents it as a first-order approximation; with US book and bogeys on one 2026-06-18 window and cumulatives near 3-6% the error is small and symmetric. The regional case is neither.) For a cumulative based at 2024-07-31 the true period return is `(1+C_t)/(1+C_{t-1}) - 1`; the additive form overstates it by the factor `(1+C_{t-1})`, about 1.38x for HK and 1.19x for CN at current levels, and books the whole two-year 37.6% / 19.5% as one review period. No grade is affected today because no ledger carries a book row (`_active_series`, `:228-241`, skips rows missing the book); the US leaderboards likewise hold only `defensive` / `regime_max` / `spy`. |

Consumers of `latest()` (F1), each of which has received the sidecar on live:

- `app/web.py:1569-1580` — Self-Directed `vs_spy` / `vs_defensive`: absent.
- `brain/improvement_agenda.py:390-396` — benchmark leaderboard rows: absent.
- `brain/attribution.py:430-443` — spy / defensive window returns: `None` (status "building").
- `portfolio/firm_allocator.py:151-160` `_latest_benchmark()` — a **separate** sorted-glob reader
  with the same defect; not fixed by #1432; outside ECON family.

Not verified: the capture holds no `self_directed` directory, so the window a repaired Self-Directed
comparison would use is unverified.

## Consequence for #1432 and #1434 (aligned to CONTRACTS.md §(d))

`CONTRACTS.md` §(d) (#1699, reviewed PASS in `reviews/lr-docs-r2.md`) is the A12 architecture and
this note does not replace it:

- the comparison is done **at read time** by the #1434 helper (`brain/benchmark_comparison.py`
  `compare_curves`: explicit cohort and asof, actual common endpoints, `C(end)/C(start) − 1`, no
  forward-fill, `unavailable` instead of a number);
- **persisted cumulative leaderboard returns are not replaced**, so `build()` and
  `build_regional()` are not renormalized (an earlier draft of this note proposed a common US
  inception in `build()` and an `inception` keyword on `build_regional()`; both are withdrawn: the
  helper aligns the window when it reads, and F3 shows the persisted curves already hold the
  points needed);
- CN and HK keep their native lineage (`000300.SS`, `^HSI`); a consumer rebases the persisted
  curve at the book's window;
- the scheduler is not re-ordered: consumers read `nav_history` (with A02 `nav_status`) and the
  ledgers after the mark loop. The earlier idea of a RUNTIME request for `book_curves` is withdrawn
  for the same reason.

**One amendment, from new evidence: the #1432 merge trigger.** §(d)1 lets ECON merge #1432 after
green checks plus an independent PASS. F1 changes what that merge does on live. The three `latest()`
consumers have received the `_series_meta.json` sidecar since about 2026-07-26, so they have been
showing nothing. Merging the selector alone turns them back on, and one of them is not window-safe:
`app/web.py:1569-1580` computes Self-Directed `vs_spy_pct = total_return_pct − spy.return_pct`,
i.e. the book's return since its own inception minus SPY's return since 2026-06-18. That is the
#1433 mismatch whenever the two inceptions differ, and the Self-Directed inception is not in the
capture (unverified). #1432's own body keeps it on HOLD for the same reason ("Root is preparing the
bounded Self-Directed withholding gate"). The amended trigger is therefore:

- **#1432** merges after green checks, an independent PASS, **and** either the web consumer goes
  through the helper (or withholds `vs_spy_pct` / `vs_defensive_pct` when the windows differ), or
  a seat ruling accepts turning the three consumers back on as they are. ECON does not merge it on
  §(d)1 alone.
- **#1434** is unchanged from §(d)2: a pure helper with no consumer wired. Merging it changes no
  output and is the prerequisite for every consumer PR. It needs green checks plus an independent
  PASS recorded under `reviews/`; the PASS described in its body is not one ECON can cite.

## Bounded plan

1. **#1434** (helper): independent review lane, then merge (ECON family: `brain/benchmark*`).
2. **#1432** (selector): independent review lane now; merge on the amended trigger above.
3. **Consumers**, each calling `compare_curves` and withholding an unsupported delta (§(d)3), routed
   to their owners with ECON review:
   - `app/web.py:1569-1580` Self-Directed `vs_spy` / `vs_defensive` (PRODUCT; request E8 in
     PRODUCT `CONTRACT_REQUESTS.md` is this consumer);
   - `brain/improvement_agenda.py:390-396` benchmark rows (RESEARCH / seat);
   - `brain/attribution.py:430-443` stays `building` with no score until its window is aligned;
   - `brain/book_lifecycle.py:708-764` `_regional_review_history` (F4): geometric linking
     `(1+C_t)/(1+C_{t-1}) − 1`, no first-row full-cumulative increment, and a regional window that
     starts at the book's window, not 2024-07-31 (out of ECON family);
   - `portfolio/firm_allocator.py:151-160` `_latest_benchmark()`: the same ISO-date filter as #1432
     (out of ECON family).
4. **Falsifiers the consumer PRs must carry:** the #1433 synthetic case (SPY 100→200→180 from
   Oct 1, defensive 100→110 from Oct 2) reports SPY −10 % and defensive +10 % over the common window,
   not +80 % vs +10 %; a sidecar-only directory makes `latest()` return `{}`; a WITHHELD date is
   never an endpoint and a PROVISIONAL endpoint carries its label (§(d)4).

Economic qualification today: the stored US bogey curves are internally consistent (F2 latent); the
stored regional bogey curves are valid index returns but **not** a qualified comparison window for
the CN / HK books until a consumer rebases them (F3). No statement is made about whether any book
beat or lagged its benchmark.
