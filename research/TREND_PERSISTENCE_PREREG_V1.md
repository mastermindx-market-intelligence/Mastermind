# Trend Persistence — Pre-registration V1

Wave B, stock level: does path quality, gain retention or drawdown shape say anything about
the next 5–60 sessions that trailing momentum, volatility and beta do not already say?

**Authority:** advisory research. Every feature in this family is `DESCRIPTIVE` today. Nothing
here ranks, sizes, gates, buys or sells, and no result of this test changes that by itself.

**Instrument:** `research/trend_persistence_panel.py`. Feature definitions:
`brain/trend_persistence.py`. Charter: `research/TREND_PERSISTENCE_PROTOCOL.md`.

## 0. How this document binds

- It is frozen before any statistic of this family is computed on the real panel. As of this
  freeze no such statistic exists: the earlier harness in this pull request has no recorded
  execution on real data, and the instrument below has been run only on synthetic test panels.
- The instrument refuses to score the holdout unless it is handed the sha256 of this file, and
  it stamps that hash on every result. Editing this file changes the hash, so it is never
  edited after the freeze. A changed design is a new file (`…_PREREG_V2.md`) with its own
  holdout budget decision.
- Anything done differently from this document is recorded as a deviation in the readout,
  with the reason, next to the result it affects.

## 1. Question and claim under test

For a stock that is a point-in-time S&P 1500 member, at a formation date *t*:

> After removing what trailing 20/60/120/252-session returns, 60-session volatility and
> 252-session beta explain, does feature *f* measured at *t* still order stocks by
> (a) forward return relative to SPY and (b) forward maximum drawdown?

The test is two-sided in development. The sign found in development is then the only sign
that can be confirmed in the holdout.

## 2. Substrate

- Prices: the audited deep + delisted close panel, cleaned by
  `loop.factor_experiment.sanitize_panel`, loaded through `loop.factor_experiment.load_panel`
  unchanged. Benchmark: SPY from the same loader.
- Universe: point-in-time S&P 1500 membership, same predicate as
  `loop.factor_experiment.members_asof` (member at *t* iff `start <= t` and `end` is null or
  `end > t`).
- Input file digests, the panel's date range and the hygiene counters are stamped on every
  result under `provenance`.

## 3. Design

**Formation calendar.** One global calendar: every 5th session of the panel starting at
session index 252. Every stock is measured on the same dates.

**Eligibility at *t*.** Point-in-time member, a price on *t*, and that price at least $5.
Eligibility uses nothing after *t*.

**Features (24).** Eight definitions at 20, 60 and 120 sessions, each computed from the
closes in the window ending at *t*; a window containing a missing price yields no value.

| Family | Feature | Definition |
| --- | --- | --- |
| path quality | `signed_efficiency` | net log move ÷ sum of absolute daily log moves, in [−1, 1] |
| path quality | `efficiency` | absolute value of the above, in [0, 1] |
| path quality | `positive_day_fraction` | share of sessions with a positive return |
| path quality | `directional_consistency` | share of sessions moving in the window's net direction |
| gain retention | `retained` | net return ÷ compounded return of the up days alone |
| drawdown shape | `max_drawdown` | worst peak-to-trough decline inside the window |
| drawdown shape | `distance_to_high` | last close ÷ window high − 1 |
| drawdown shape | `sessions_since_high` | sessions since the window high was last touched |

**Controls (6).** `ret_20d`, `ret_60d`, `ret_120d`, `ret_252d` (simple trailing returns),
`vol_60d` (standard deviation of daily log returns), `beta_252d` (covariance with SPY daily
log returns ÷ SPY variance).

**Labels.** For each horizon *h* in {5, 20, 60} sessions, entry is the close of *t*+1 and exit
the close of *t*+1+*h*:

- `forward_return` — exit ÷ entry − 1;
- `forward_rel` — `forward_return` minus SPY's return over the same sessions;
- `forward_max_drawdown` — worst peak-to-trough decline from entry to exit (≤ 0).

A stock that stops trading inside the window keeps its last traded price to the exit and is
flagged. It is never dropped for failing to survive, because dropping it would condition the
cross-section on the future. A label whose exit lies beyond the end of the panel does not exist.

**Samples.**

- *Development:* formation dates whose label exit falls before the first session on or after
  2022-01-01. No development label touches a holdout price.
- *Holdout:* formation dates on or after 2022-01-01, to the end of the panel.

**Cross-section per date.** Eligible stocks with every feature, every control and both
endpoint labels present. A date needs at least 100 such stocks.

## 4. Statistic

Per date, per feature: rank-transform the feature and the six controls across the
cross-section; regress the feature ranks on an intercept and the standardised control ranks;
take the Spearman correlation between the residual and the label. This is
`engine.validation.incremental_ic` (`cross_sectional_resid`, then `rank_ic`) applied to
rank-transformed inputs — a semi-partial rank IC. The primary statistic is the mean of that
per-date series.

Primary tests: 24 features × 3 horizons × 2 endpoints (`forward_rel`,
`forward_max_drawdown`) = **144**.

## 5. Inference

- HAC: `engine.validation.newey_west_tstat` on the per-date series, lags =
  max(4, 2 × ⌈*h* ÷ 5⌉), i.e. 4 / 8 / 24 for the three horizons.
- Non-overlapping check: every ⌈(*h* + 1) ÷ 5⌉-th date (2 / 5 / 13), HAC with 2 lags.
- Multiplicity: `engine.validation.benjamini_hochberg` at α = 0.10 across all 144 tests.

## 6. Development gates

A test survives development only if all six hold.

| Gate | Requirement |
| --- | --- |
| G1 | Benjamini–Hochberg q ≤ 0.10 across the 144 tests |
| G2 | absolute mean IC ≥ 0.010 |
| G3 | non-overlapping series: same sign and absolute t ≥ 2.0 |
| G4 | same sign in at least 4 of the 5 eras 2003–06, 2007–10, 2011–14, 2015–18, 2019–21 (an era needs 8 dates) |
| G5 | same sign in at least 4 of 5 momentum quintiles (equal-count groups by the mean rank of the four trailing returns; a group needs 20 stocks) |
| G6 | with every label-window delisting removed instead of carried: same sign and absolute mean IC ≥ 0.010 |

## 7. Holdout confirmation

Run once, after the development result and this document are committed and an independent
review of the instrument has passed. Only development survivors are scored; if there are
none the holdout is not run and stays unspent. Holdout statistics for any other test are
discarded unread.

A survivor is confirmed only if all four hold.

| Gate | Requirement |
| --- | --- |
| H1 | holdout mean IC has the development sign |
| H2 | one-sided HAC p ≤ 0.05 in that direction |
| H3 | Benjamini–Hochberg q ≤ 0.10 across the survivors, on the one-sided p-values |
| H4 | absolute mean IC ≥ 0.005 |

## 8. Decision rule

Per family and endpoint:

- At least one member passes G1–G6 and H1–H4 → the family is `RESEARCH_PREDICTIVE` for that
  endpoint, on the confirmed members only. That earns a walk-forward comparison against a
  momentum-only model (Wave B2). It earns no advisory use.
- Survivors in development, none confirmed → the family stays `DESCRIPTIVE`; the failed
  confirmation is printed.
- No development survivor → the family stays `DESCRIPTIVE`; the null is printed. This closes
  these constructions on this universe and these horizons, not the idea.

## 9. Reported but not gating

Raw rank IC; semi-partial rank IC with the four momentum controls only (to show what
volatility and beta absorb); label means by quintile of the control-neutral feature rank;
coverage (dates, median names, share of labels carried through a delisting, share of eligible
stocks lost to incomplete cases).

## 10. Known limits of this test

- **Terminal losses are understated.** The panel has no delisting returns, and the sanitizer
  treats sub-$1 prints as missing, so a stock that collapses and delists exits at its last
  price of $1 or more. G6 measures how much the result leans on those labels; it does not
  repair them.
- **Sanitized prices.** Daily moves beyond ±60% are clamped by the audited sanitizer, so price
  levels after a clamp are reconstructed, not quoted.
- **Membership vintage.** Point-in-time membership is only as good as the membership file;
  its digest is stamped on the result.
- **Not a strategy.** An IC ignores costs, capacity and turnover. Nothing here is a backtest.
- **Correlated tests.** The 24 features share windows and inputs. Benjamini–Hochberg is valid
  under positive dependence, but the 144 tests are far fewer than 144 independent ideas.
- **One universe, three horizons.** Large and mid/small-cap US stocks, 5–60 sessions. Group
  persistence (sectors, industries, themes) is a separate test (Wave C).

## 11. What this does not license

No composite score, no fitted threshold, no live advisory field, no binding use. Those need
their own evidence and an explicit promotion.

## 12. Frozen constants

The instrument's `frozen_design()` must equal this block; a test enforces it.

```json
{
  "windows": [20, 60, 120],
  "momentum_windows": [20, 60, 120, 252],
  "horizons": [5, 20, 60],
  "formation_step": 5,
  "entry_lag": 1,
  "min_history": 252,
  "vol_window": 60,
  "beta_window": 252,
  "select_floor": 5.0,
  "min_names_per_date": 100,
  "min_names_per_bucket": 20,
  "n_buckets": 5,
  "holdout_start": "2022-01-01",
  "dev_eras": [
    ["2003-01-01", "2006-12-31"],
    ["2007-01-01", "2010-12-31"],
    ["2011-01-01", "2014-12-31"],
    ["2015-01-01", "2018-12-31"],
    ["2019-01-01", "2021-12-31"]
  ],
  "min_dates_per_era": 8,
  "bh_alpha": 0.10,
  "ic_floor_dev": 0.010,
  "ic_floor_holdout": 0.005,
  "thinned_t_min": 2.0,
  "era_agree_min": 4,
  "bucket_agree_min": 4,
  "holdout_p_one_sided": 0.05,
  "controls": ["ret_20d", "ret_60d", "ret_120d", "ret_252d", "vol_60d", "beta_252d"],
  "endpoints": ["forward_rel", "forward_max_drawdown"],
  "features": [
    "efficiency_20d", "efficiency_60d", "efficiency_120d",
    "signed_efficiency_20d", "signed_efficiency_60d", "signed_efficiency_120d",
    "positive_day_fraction_20d", "positive_day_fraction_60d", "positive_day_fraction_120d",
    "directional_consistency_20d", "directional_consistency_60d", "directional_consistency_120d",
    "retained_20d", "retained_60d", "retained_120d",
    "max_drawdown_20d", "max_drawdown_60d", "max_drawdown_120d",
    "distance_to_high_20d", "distance_to_high_60d", "distance_to_high_120d",
    "sessions_since_high_20d", "sessions_since_high_60d", "sessions_since_high_120d"
  ]
}
```
