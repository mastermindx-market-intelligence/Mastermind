# Trend Persistence — Pre-registration V2

**Revision 2**, frozen 2026-10-03 before any holdout run. Revision 1 (sha256 `e63d49eb…d24c`)
is superseded; §0 says what changed and why.

Wave B, stock level, one claim: do path quality, gain retention and drawdown shape describe a
stock's **downside risk** over the next 5–60 sessions beyond what trailing momentum, realized
volatility at four spans, downside volatility and beta already describe?

**Authority:** advisory research. Every feature in this family is `DESCRIPTIVE` today. Nothing
here ranks, sizes, gates, buys or sells, and no result of this test changes that by itself.

**Instrument:** `research/trend_persistence_panel.py`, design `v2`. Substrate:
`research/trend_persistence_substrate.py`. Feature definitions: `brain/trend_persistence.py`.
Charter: `research/TREND_PERSISTENCE_PROTOCOL.md`. Predecessor:
`research/TREND_PERSISTENCE_PREREG_V1.md`.

## 0. What is already known, and how this document binds

**V1 is spent in development and closed in the holdout.** V1's development sample (2003–2021)
was scored: forward return relative to SPY, 0 of 72 tests survive; forward maximum drawdown,
34 of 72 survive. V1's holdout was never scored and never will be — the instrument refuses.
Two things closed it:

- an independent review of the instrument found that V1 lets the audited price cleaner decide
  eligibility. The cleaner fills gaps inside a name's life, and whether a day is inside
  depends on whether the name trades again later. That is a look-ahead, small (about 0.1% of
  eligible stock-dates) but real;
- an exploratory look at the development sample showed V1 under-controls volatility. With
  volatility measured at several spans the drawdown results shrink by roughly half and the
  gain-retention and signed-efficiency results disappear.

**The development sample is not fresh for V2.** This design was written after reading V1's
development result and that exploratory look. In V2, development gates are a filter that
decides which tests are worth a holdout look. They are not evidence. The only evidence V2 can
produce is the holdout.

**The holdout is unspent.** No statistic relating any feature to any label has been computed
for any formation date on or after 2022-01-01. Price-only work has been done on that window
and is declared: validating the split reference against the audited panel, counting gaps,
comparing printed with adjusted prices, and counting how many index members have a price,
clear the price floors and have every feature and control on each formation date.

**Revision 2.** §7 requires an independent review of the instrument before the holdout is
run. The review of revision 1 reproduced the development result, found the statistics and the
survivor-only path correct, and required three repairs before any holdout run. This revision
makes them.

- *The price floors looked ahead.* Revision 1 tested the $1 and $5 floors on adjusted prices.
  An adjusted price is divided by every later split, and the audited cleaner's rebuilt level
  can drift far from the price that printed, so something after a holdout date could decide
  who was eligible on it. The floors are now tested on the close as it printed, wherever the
  store prints one (§2, §3). On holdout formation dates that makes about 1,100 stock-dates
  eligible that were not and removes about 300 that were, of about 294,000.
- *A holdout run was not tied to its inputs.* It now is (Binding, below).
- *The holdout run printed statistics this document did not list.* It now forms and prints
  only what §7 and §9 list.

Eligibility changed, so development is scored again under this revision and its survivors
derived again. Revision 1's development result (29 of 72 survive) is superseded; the readout
keeps it as a record. Nothing about the holdout was learned between the two freezes.

**Binding.**

- The instrument pins the sha256 of this file in code. If the file on disk does not hash to
  the pin, nothing is scored, development included.
- The sample boundaries are constants in the instrument. No argument moves them.
- A holdout run needs the hash from the caller and the committed development result. The
  instrument then re-derives the development survivors itself on the same panel, refuses if
  they differ from the committed ones, and scores those tests and nothing else. Horizons with
  no survivor are not touched.
- A holdout run is bound to its inputs. Every result carries a digest of the panel it was
  scored on: the sessions, the cleaned prices, the benchmark, the membership, the quoted-price
  mask, the prices the floor was tested on, the names and the calendar constants. A holdout
  run refuses unless its panel has exactly the digest stamped on the committed development
  result. A panel built on another formation step, entry lag or horizon set is refused for
  either sample.
- The fence binds the instrument's entry points. It cannot bind code written to go around it:
  calling the instrument's private functions, altering a panel between building and scoring,
  or feeding real prices to the older generic harness
  (`research/trend_persistence_experiment.py`, which holds no data and no fence) can compute
  what this document forbids. That would be a breach of this pre-registration, not a result
  under it.
- This file is never edited after the holdout is scored. A change before that is a new freeze
  with a new pin, recorded in the readout with its reason.
- Anything done differently from this document is recorded as a deviation in the readout,
  next to the result it affects.

## 1. Claim under test

For a stock that is a point-in-time index member, at a formation date *t*:

> After removing what trailing 20/60/120/252-session returns, 20/60/120/252-session realized
> volatility, 60/252-session downside volatility and 252-session beta explain, does feature
> *f* measured at *t* still order stocks by forward maximum drawdown?

Primary tests: 24 features × 3 horizons × 1 endpoint = **72**. Two-sided in development; the
sign found in development is the only sign that can be confirmed in the holdout.

Continuation (forward return relative to SPY) is not carried forward. V1 closed it as a
development null: these constructions, this universe, these horizons.

## 2. Substrate

**Audited part.** The deep + delisted close panel, cleaned by
`loop.factor_experiment.sanitize_panel`, loaded by `loop.factor_experiment.load_panel`
unchanged. Benchmark: SPY from the same loader.

**Repair.** For index members the audited panel has no column for and whose membership
reaches past 2021-07-06, closes come from the whole-market daily store (raw, unadjusted, first
session 2021-07-06):

1. drop non-positive prices and duplicate dates;
2. back-adjust for splits from the committed vendor reference
   `research/data/trend_persistence_split_reference.csv`: every price before an execution
   date is multiplied by `split_from ÷ split_to`;
3. if the symbol's prices fall into runs separated by more than 30 calendar days, keep the one
   run with the most sessions inside the membership spans (the later run on a tie) — a symbol
   reused by another company is not the member;
4. put the block on the audited panel's sessions and clean it with the same audited sanitizer.

Audited columns are not touched; the repaired panel's audited columns equal the audited
loader's output exactly. Today the repair adds 410 names; 2 members have no store file.

**Printed closes.** For every member whose membership reaches past 2021-07-06 and that has a
store file — audited or store-sourced, 1,918 names — the unadjusted close is read from the
store by symbol and day. Printed closes are used for the two price floors and for nothing
else: features, controls and labels come from the cleaned, adjusted prices. Four audited
names have no store file under their symbol (BF-B, BRK-B, CWEN-A, MOG-A).

**Quoted-price mask.** A cell is *quoted* when the inputs hold a real close of at least $1
for that day — in the raw audited files for audited columns, in the split-adjusted store
closes for store columns — and, where the store prints a close for that symbol that day, the
printed close is at least $1 too. Cleaned prices that are gap fills are not quoted.

**Universe.** Point-in-time membership from the membership file, same predicate as
`loop.factor_experiment.members_asof`. The file is not a constant S&P 1500: it lists about 500
names until 2012, about 920 from 2013 and about 1,520 from 2020.

**How much of that universe has a price** (first session of the year; prices and membership
only). *Eligible price* means quoted and at or above the $5 floor of §3.

| Year | Members | Audited panel, quoted | Repaired, quoted | Repaired, eligible price |
| --- | --- | --- | --- | --- |
| 2004 | 494 | 268 | 268 | 256 |
| 2008 | 497 | 314 | 314 | 306 |
| 2012 | 497 | 346 | 346 | 331 |
| 2013 | 920 | 593 | 593 | 577 |
| 2016 | 920 | 647 | 647 | 642 |
| 2019 | 913 | 726 | 726 | 721 |
| 2020 | 1,521 | 1,085 | 1,085 | 1,074 |
| 2021 | 1,521 | 1,125 | 1,125 | 1,113 |
| 2022 | 1,516 | 1,167 | 1,501 | 1,492 |
| 2023 | 1,514 | 1,222 | 1,507 | 1,489 |
| 2024 | 1,510 | 1,314 | 1,506 | 1,498 |
| 2025 | 1,507 | 1,385 | 1,504 | 1,498 |
| 2026 | 1,506 | 1,458 | 1,505 | 1,496 |

In development 52–79% of the members are eligible, tilted toward names that survived. In the
holdout 99% or more of the members have a quoted price and 98–99% are eligible; the gap
between the two is names that print under $5. That asymmetry is the reason development is
only a filter here.

Input digests (audited files, store block, printed closes, split reference), the panel
digest, the panel's date range, the hygiene counters and this coverage table are stamped on
every result.

## 3. Design

**Formation calendar.** One global calendar: every 5th session of the panel starting at
session index 252.

**Eligibility at *t*.** Point-in-time member, a quoted price on *t*, and a close of at least
$5 on *t*. The $5 test, like the $1 test inside the quoted-price mask, reads the close as it
printed that day wherever the store prints one. Where it prints none — every date before
2021-07-06, and after it a symbol the store does not carry that day — both tests fall back on
the adjusted, cleaned price.

A printed close holds nothing from after *t*. The fallback does: an adjusted price is divided
by later splits and, for audited names, sits on the level the cleaner rebuilt. On the 197
holdout formation dates that have a 5-session label (2022-07-06 to 2026-06-02), 294,058
stock-dates are eligible; 290,240 of them (98.7%) were tested on a printed close and 3,818
(1.3%, about 50 names: the four class-share symbols and symbols the store starts carrying
only after a ticker change) on the fallback. Of the 290,276 member stock-dates that print $5
or more, 36 are not eligible, all for want of an audited price that day (SBNY 35, KNF 1).
Development dates before 2021-07-06 are on the fallback entirely (§10).

**Features (24).** As V1: eight definitions at 20, 60 and 120 sessions, from the closes in the
window ending at *t*. A window holding any unquoted cell yields no value.

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

**Controls (11).** Computed from quoted prices only, like the features.

- `ret_20d`, `ret_60d`, `ret_120d`, `ret_252d` — simple trailing returns;
- `vol_20d`, `vol_60d`, `vol_120d`, `vol_252d` — standard deviation of daily log returns;
- `downvol_60d`, `downvol_252d` — square root of the mean squared negative daily log return
  (a positive return counts as zero);
- `beta_252d` — covariance with SPY daily log returns ÷ SPY variance.

**Label.** For each horizon *h* in {5, 20, 60} sessions, entry is the close of *t*+1 and exit
the close of *t*+1+*h*; `forward_max_drawdown` is the worst peak-to-trough decline of the
cleaned price from entry to exit (≤ 0). A stock that stops trading inside the window keeps its
last price to the exit and is flagged; it is never dropped for failing to survive. A label
whose exit lies beyond the end of the panel does not exist.

**Samples.**

- *Development:* formation dates whose label exit falls before the first session on or after
  2022-01-01 — V1's development sample, on the quoted-price mask and V2's controls.
  Store-sourced names have less than 252 sessions of history there and drop out as incomplete
  cases, so the development cross-section is the audited names.
- *Holdout:* formation dates on or after **2022-07-06**, the first formation date on which a
  store-sourced name has the 252 sessions of history the controls need, to the end of the
  panel.
- *Quarantine:* formation dates from 2022-01-01 to 2022-07-05 are scored by nobody. On those
  dates the universe could not be repaired.

**Cross-section per date.** Eligible stocks with every feature, every control and the label
present. A date needs at least 100 such stocks.

## 4. Statistic

Per date, per feature: rank-transform the feature and the eleven controls across the
cross-section; regress the feature ranks on an intercept and the standardised control ranks;
take the Spearman correlation between the rank of that residual and the label. This is
`engine.validation.incremental_ic` applied to rank-transformed inputs — a semi-partial rank
IC. The primary statistic is the mean of the per-date series.

## 5. Inference

- HAC: `engine.validation.newey_west_tstat` on the per-date series, lags =
  max(4, 2 × ⌈*h* ÷ 5⌉), i.e. 4 / 8 / 24.
- Non-overlapping check: every ⌈(*h* + 1) ÷ 5⌉-th date of the series (2 / 5 / 13), starting
  from its first date, HAC with 2 lags.
- Multiplicity: `engine.validation.benjamini_hochberg` at α = 0.10 across all 72 tests.
- p-values are used exactly as the judge returns them (rounded to four decimals).
- A series shorter than 8 dates has no mean and no p-value. Such a test stays in the family
  and enters the multiplicity step as p = 1.

## 6. Development gates

A test survives development only if all seven hold. A group, era or series without a value
counts as disagreeing.

| Gate | Requirement |
| --- | --- |
| G1 | Benjamini–Hochberg q ≤ 0.10 across the 72 tests |
| G2 | absolute mean IC ≥ 0.010 |
| G3 | non-overlapping series: same sign and absolute t ≥ 2.0 |
| G4 | same sign in at least 4 of the 5 eras 2003–06, 2007–10, 2011–14, 2015–18, 2019–21 (an era needs 8 dates) |
| G5 | same sign in at least 4 of 5 momentum quintiles |
| G6 | with every label carried through a delisting removed: same sign and absolute mean IC ≥ 0.010 |
| G7 | same sign in at least 4 of 5 volatility quintiles |

Quintiles (G5, G7) are equal-count groups of the date's cross-section, by the mean rank of the
four trailing returns (G5) or of the six volatility and downside-volatility controls (G7);
ties go by column order. Inside a group the whole statistic is recomputed on that group's
stocks — ranks, residualisation on all eleven controls, correlation. A group needs 20 stocks
on a date, and a group's mean needs 8 dates. G6 recomputes the statistic per date on the
stocks whose label was not carried; a date needs 100 of them and the mean needs 8 dates.

## 7. Holdout confirmation

Run once, after this document, the instrument and the development result are committed and an
independent review of the V2 instrument and fence has passed. For this revision that means
the review of revision 1 plus a re-review of the changes it required. Only development
survivors are scored. If there are none the holdout is not run and stays unspent.

A survivor is confirmed only if all four hold, on the full repaired universe.

| Gate | Requirement |
| --- | --- |
| H1 | holdout mean IC has the development sign |
| H2 | one-sided HAC p ≤ 0.05 in that direction (p ÷ 2 when the sign matches, 1 − p ÷ 2 when it does not) |
| H3 | Benjamini–Hochberg q ≤ 0.10 across the survivors, on the one-sided p-values (a survivor without a p-value enters as 1) |
| H4 | absolute mean IC ≥ 0.005 |

For each survivor the holdout run forms and prints the per-date series' length, mean, HAC t,
p and lag count; the one-sided p; the four gates; and the non-gating numbers of §9. It forms
nothing else. The quintile-group, era and non-overlapping statistics of §6 and the share of
positive dates gate or describe development only and are not computed on holdout dates. A
survivor with no usable holdout date is printed as unconfirmed, with no statistic.

## 8. Decision rule

Per family, for forward maximum drawdown:

- At least one member passes G1–G7 and H1–H4 → the family is `RESEARCH_PREDICTIVE` for
  downside-risk description, on the confirmed members only. That earns a walk-forward
  comparison against a momentum-and-volatility model (Wave B2). It earns no advisory use.
- Survivors in development, none confirmed → the family stays `DESCRIPTIVE`; the failed
  confirmation is printed.
- No development survivor → the family stays `DESCRIPTIVE`; the null is printed.

A kill closes these constructions on this universe and these horizons, not the idea.

## 9. Reported but not gating

Raw rank IC; semi-partial rank IC with the four momentum controls only and with V1's six
controls (to show what the added volatility controls absorb); label means by quintile of the
control-neutral feature rank; coverage (dates, first and last date, median names, share of
labels carried through a delisting, share of eligible stocks lost to incomplete cases, share
of store-sourced stocks, share of stocks whose floor was tested on a printed close).

For each holdout survivor two brackets are printed beside the gated number: the mean IC with
carried labels removed, and the mean IC on audited-panel names only. They show how much a
confirmation leans on carried prices or on the repaired names; they do not gate.

## 10. Known limits of this test

- **Development is survivor-conditioned** (§2). Its gates can pass a test that the full
  universe would not, or drop one it would keep. Only the second error is uncorrected.
- **Store-sourced names are adjusted for splits only.** Dividends are not added back, and a
  spin-off, liquidating distribution or bankruptcy share exchange reads as a price drop (three
  seen so far). Audited names come adjusted. The audited-only bracket shows the effect.
- **Ticker changes are not linked.** The old symbol stops and is carried at its last price;
  the new symbol starts.
- **Terminal losses are understated.** No delisting returns; sub-$1 prints are treated as
  missing, so a collapse exits at its last price of $1 or more.
- **Clamped prices.** Daily moves beyond ±60% are clamped by the audited sanitizer, so price
  levels after a clamp are reconstructed, not quoted.
- **Floors before the store begins.** Before 2021-07-06 no printed close exists, so the $1 and
  $5 floors are tested on adjusted, cleaned prices and a later split or the cleaner's rebuilt
  level can decide eligibility. That covers development up to its last half-year. It is one
  more reason development is a filter and not evidence.
- **Floors on the fallback in the holdout.** 1.3% of eligible holdout stock-dates have no
  printed close and are tested on the adjusted, cleaned price (§3).
- **The quote test keeps one adjusted leg.** A cleaned price must exist, and the audited
  cleaner drops adjusted prints under $1. From 2021-07-06 that leg removed no member cell
  that printed $1 or more.
- **Store prints are taken as they are.** A wrong print in the store moves a floor test, and
  a wrong or missing split in the reference moves a store-sourced price. Large single-day
  moves that remain in store-sourced names after cleaning are counted in the readout beside
  the audited-only bracket.
- **The fence has an edge.** It binds the instrument's entry points, not code written to go
  around it (§0).
- **Members that left before mid-2021 stay unpriced.** The store cannot reach them.
- **Short holdout.** About four years: one rate cycle, one regional-bank failure wave. At 60
  sessions there are roughly fifteen non-overlapping windows.
- **Not a strategy.** An IC ignores costs, capacity and turnover. Nothing here is a backtest.
- **Correlated tests.** The 24 features share windows and inputs; 72 tests are far fewer than
  72 independent ideas.

## 11. What this does not license

No composite score, no fitted threshold, no live advisory field, no binding use. Those need
their own evidence and an explicit promotion.

## 12. Frozen constants

The instrument's `frozen_design("v2")` must equal this block; a test enforces it.

```json
{
  "windows": [20, 60, 120],
  "momentum_windows": [20, 60, 120, 252],
  "horizons": [5, 20, 60],
  "formation_step": 5,
  "entry_lag": 1,
  "min_history": 252,
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
  "bh_alpha": 0.1,
  "ic_floor_dev": 0.01,
  "ic_floor_holdout": 0.005,
  "thinned_t_min": 2.0,
  "era_agree_min": 4,
  "bucket_agree_min": 4,
  "holdout_p_one_sided": 0.05,
  "controls": ["ret_20d", "ret_60d", "ret_120d", "ret_252d", "vol_20d", "vol_60d", "vol_120d", "vol_252d", "downvol_60d", "downvol_252d", "beta_252d"],
  "endpoints": ["forward_max_drawdown"],
  "features": [
    "efficiency_20d", "efficiency_60d", "efficiency_120d",
    "signed_efficiency_20d", "signed_efficiency_60d", "signed_efficiency_120d",
    "positive_day_fraction_20d", "positive_day_fraction_60d", "positive_day_fraction_120d",
    "directional_consistency_20d", "directional_consistency_60d", "directional_consistency_120d",
    "retained_20d", "retained_60d", "retained_120d",
    "max_drawdown_20d", "max_drawdown_60d", "max_drawdown_120d",
    "distance_to_high_20d", "distance_to_high_60d", "distance_to_high_120d",
    "sessions_since_high_20d", "sessions_since_high_60d", "sessions_since_high_120d"
  ],
  "design": "v2",
  "risk_windows": [20, 60, 120, 252],
  "downside_windows": [60, 252],
  "risk_controls": ["vol_20d", "vol_60d", "vol_120d", "vol_252d", "downvol_60d", "downvol_252d"],
  "holdout_formation_start": "2022-07-06",
  "observed_mask": true,
  "printed_floor": true,
  "risk_bucket_gate": true,
  "substrate": "repaired",
  "n_bins": 5,
  "min_dates_for_mean": 8,
  "thinning_phase": 0
}
```
