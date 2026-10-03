# Trend Persistence — Pre-registration B2 (walk-forward comparison and volatility decomposition)

Status: FROZEN 2026-10-03. The instrument (`research/trend_persistence_walkforward.py`) pins
this file's sha256 and scores nothing if the file changes.

Wave B2, stock level. This document fixes, before any model is fitted on the test years, how
the confirmed features are compared against a volatility-aware model, how what they carry is
split into volatility and everything else, and what both have to show for the family to move
up.

## 0. What is already known

- V1: no feature in the family says anything about forward return relative to SPY beyond
  momentum, volatility and beta (0 of 72). That question is closed for these constructions.
- V2: 29 tests of forward maximum drawdown passed development and the four holdout gates on
  formation dates from 2022-07-06 to 2026-06-02 (readout §10).
- The effect is small: mean IC 0.007 to 0.051 after eleven controls; 0.03 to 1.2 points of
  forward maximum drawdown between the end fifths.
- **V2's gates do not separate these features from volatility.** A simulated market with no
  drift and no return autocorrelation, only volatility that differs across stocks and clusters
  in time, passes the same gates on most of the 29 (readout §10, committed benchmark).
- **Every year in the sample has now been looked at.** B2 cannot confirm anything a second
  time. It measures two things that have not been computed on the test years.

What was looked at while this document was written, and what was not, is in §12.

## 1. Questions

**Q1, value.** Does adding the confirmed features to a model built from momentum, beta and a
full set of price-only volatility descriptors improve its out-of-sample ranking of which stocks
draw down most, by enough to justify carrying a separate estimate?

**Q2, kind.** Once the realised volatility of the label's own window is known, do the
confirmed features say anything more about the drawdown in that window than they do in a
simulated market that has only volatility?

Q1 decides whether anything is built. Q2 decides what it may be called.

## 2. Substrate, universe, labels

Exactly V2's: the repaired panel, the quoted-price mask, floors on printed closes, the
point-in-time S&P 1500 membership, the same formation calendar (every fifth session), entry
lag of one session, and forward maximum drawdown at 5, 20 and 60 sessions. The panel is built
by the V2 instrument's own loader and builder and must carry V2's panel digest
(`48cb5e76…ef178`); the instrument refuses any other panel.

A stock-date is a complete case exactly as in V2: eligible under V2 §3, with the label, all
eleven controls and all 24 features. A date needs 100 complete cases. The added volatility
descriptors (§4) use windows no longer than the features', on the same quoted prices, so they
exist on every complete case; the instrument stops if one does not. A price-only count run
before this freeze found none missing (§3).

Confirmed features, by horizon (readout §10; the instrument checks this list against the
committed V2 holdout result):

| Horizon | Drawdown shape | Path quality |
| ---: | --- | --- |
| 5 | `distance_to_high` 20/60/120, `max_drawdown` 20/60/120 | `efficiency_20d`, `positive_day_fraction` 20/60/120 |
| 20 | `distance_to_high` 20/60/120, `max_drawdown` 20/60/120, `sessions_since_high` 60/120 | `efficiency_20d`, `positive_day_fraction` 60/120 |
| 60 | `distance_to_high` 20/60/120, `max_drawdown` 20/60/120, `sessions_since_high_120d` | `positive_day_fraction_60d` |

## 3. Test blocks and training

The test dates are exactly the dates V2's holdout scored. They are split into five blocks by
formation date:

| Block | Formation dates |
| --- | --- |
| T1 | 2022-07-06 to 2022-12-31 |
| T2 | 2023 |
| T3 | 2024 |
| T4 | 2025 |
| T5 | 2026-01-01 to the last date with a complete label |

For each block and horizon, every model is fitted once, on every formation date whose label
ends before the block's first test date. That includes the dates in the first half of 2022
that V2 scored in neither sample. Nothing inside or after a block is used to fit the model
that is scored on it.

Training data before mid-2022 is survivor-conditioned (V2 §2). That biases the fit, not the
test.

Sample sizes, from a count of complete cases that compares no feature with any label:

| Horizon | Test dates | T1 | T2 | T3 | T4 | T5 | Training stock-dates, T1 → T5 |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 5 | 197 | 25 | 50 | 51 | 50 | 21 | 525,918 → 786,171 |
| 20 | 194 | 25 | 50 | 51 | 50 | 18 | 522,401 → 781,706 |
| 60 | 186 | 25 | 50 | 51 | 50 | 10 | 513,056 → 769,791 |

A test date holds about 1,470 to 1,490 complete cases. T5 is short, ten dates at 60 sessions.
It counts as a block all the same.

## 4. Variables

On each date, among that date's complete cases, every control, descriptor, feature and label
is replaced by its percentile rank minus one half (ties share their average rank). A higher
label rank is a shallower forward drawdown.

The **event** is a stock whose forward maximum drawdown is in the deepest tenth of that date's
complete cases: the `floor(n / 10)` deepest, ties broken by panel order.

**Added volatility descriptors**, from daily log returns of quoted prices at or before the
formation date, eleven in all. A window that holds an unquoted price gives no value.

| Descriptor | Definition |
| --- | --- |
| `ewma_vol_3`, `_10`, `_30` | square root of the exponentially weighted mean squared return over the last 120 sessions, half-life 3, 10, 30 sessions |
| `mean_abs_20`, `_60`, `_120` | mean absolute return over the last 20, 60, 120 sessions |
| `max_abs_20`, `_60`, `_120` | largest absolute return over the last 20, 60, 120 sessions |
| `downvol_20`, `_120` | square root of the mean squared negative return over the last 20, 120 sessions |

**Realised volatility of the label window** (Q2 only): the square root of the mean squared
daily log return over the label's own `h` sessions, on the same carried-forward prices the
label uses. It is not known at formation. It is used to split what a feature says, never to
predict.

## 5. Models (Q1)

Two fits per model, pooled over training stock-dates, each stock-date weighted equally, each
with an intercept:

- ordinary least squares of the label rank on the regressors. Its fitted value is the model's
  **score**.
- unpenalised logistic regression of the event on the regressors, by Newton's method. Its
  fitted value is the model's **event probability**. If it does not converge the instrument
  stops.

| Model | Regressors |
| --- | --- |
| B0 | the eleven V2 controls |
| B1 | B0 plus the square of each control |
| B2, volatility-aware baseline | B1, plus the eleven descriptors and their squares, plus six products: trailing return × volatility and squared trailing return × volatility at 20, 60 and 120 sessions |
| A, augmented | B2 plus the features confirmed at the horizon |
| A-dd, A-pq | B2 plus one family's confirmed features (ablation) |

All regressors are the centred ranks of §4; squares and products are taken of those ranks.

The comparison that gates is **A against B2**. B2 is the baseline because V2 removed
volatility rank-linearly from four spans, and the benchmark shows that is not enough: a model
of drawdown has to be allowed short memory, large single moves, curvature and the dependence of
volatility on recent direction before anything is credited to another feature.

No hyperparameter is tuned. No feature is selected inside B2. No composite is formed outside
these fits.

## 6. What is measured

**Order.** The instrument first recomputes V2's own holdout statistic for each of the 29 tests
on the test dates and compares it with the committed V2 result (mean to 1e-9, same number of
dates). If any differs it stops and reports nothing. Then Q2, then Q1.

**Q1.** On each test date:

- **Rank IC** between a model's score and the realised forward drawdown rank.
- **Capture**: of the tenth of stocks with the highest event probability, the share that are
  events. Chance is 10%.
- **Brier score** of the event probability.
- **Realised drawdown of the flagged tenth**: mean forward maximum drawdown of the tenth with
  the highest event probability.

Pooled over all test dates, per model: a reliability table (ten equal-count bins of event
probability, mean prediction against observed event rate) and the calibration slope and
intercept (logistic regression of the event on the logit of the probability).

Differences are taken per date, A minus B2, and summarised by their mean and a HAC t with V2's
lag rule (`max(4, 2 × ceil(h / 5))` lags).

**Q2.** For each confirmed test, on each test date: the correlation, across that date's
stocks, between the label's rank and what is left of the feature's rank after a least-squares
fit on the eleven control ranks, their squares, the rank of the realised volatility of the
label window, and indicators for twenty equal-count bins of that rank. Summarised by its mean
over test dates and a HAC t with V2's lag rule.

The residual is not ranked again. V2's statistic does rank it again, and a re-ranked residual
is no longer orthogonal to what was removed: on made-up data, a feature that is nothing but the
label window's volatility plus noise kept 4 to 10 percent of its IC that way (§12). V2's own
statistic is reported beside this one, unchanged.

**The simulated reference.** The same Q1 and Q2 statistics are computed, by the same code, on
simulated panels from the committed benchmark module (`research/trend_persistence_null.py`):
specifications `clustered_leverage` and `clustered_leverage_jumps`, seeds 11 to 15, ten runs.
Each has 1,500 names, all members throughout, on 3,770 sessions from 2012-01-02 to 2026-06-12,
with the same blocks and the same 29 feature-horizon pairs. The calendar starts in 2012 so
that the first block trains on about as many stock-dates as the real one. The generator takes
a specification and a seed and reads no prices. For a statistic, the **simulated range** is
the interval from the smallest to the largest of the ten run means.

The reference is produced after this file is frozen and before the real run. Its file hash is
pinned in the instrument, and the instrument refuses to score real data without it.

**One run.** The real run is made once. The instrument refuses to run if its output file
exists.

## 7. Gates

Q1 is evaluated at 20 and at 60 sessions. The 5-session horizon is reported and does not gate.

| Gate | Requirement |
| --- | --- |
| W1 | mean difference in rank IC above zero, one-sided HAC p ≤ 0.025 |
| W2 | mean difference in rank IC above zero in at least 4 of the 5 blocks |
| W3 | mean difference in capture of at least 1.0 percentage point |
| W4 | A's calibration slope between 0.80 and 1.25, and A's mean Brier score no worse than B2's |

W1's 0.025 is 0.05 split across the two gated horizons. W3 is a materiality bar, chosen before
the run: below one point of capture a reader could not tell the two risk rankings apart in use.

**W1 and W2 alone do not separate the features from volatility.** In the ten simulated runs
(§6), A beats B2 by a rank IC of +0.00004 to +0.0006 at the gated horizons, and both W1 and W2
pass at one of them in 8 runs of 10: the features carry a trace of information about future
volatility that no finite set of descriptors removes. W3 is what the simulated market does not
reach. Its capture difference at the gated horizons is between −0.10 and +0.14 points, and W3
passes in none of the 30 run-horizons.

Q2, per confirmed test. A test **carries more than volatility** when all five hold on the test
dates:

| Gate | Requirement |
| --- | --- |
| K1 | the mean has the development sign |
| K2 | one-sided HAC p ≤ 0.05 |
| K3 | false-discovery q ≤ 0.10 across the 29 (Benjamini–Hochberg on the one-sided p-values) |
| K4 | absolute mean at least 0.005 |
| K5 | the mean, signed by the development sign, lies above the top of the simulated range for that test |

## 8. Decision rule

- W1–W4 all pass at a horizon → a walk-forward event probability from model A, with its
  reliability table, is eligible for `CALIBRATED_PROFILE` at that horizon and for a shadow
  snapshot through the existing signal and outcome owners (Wave D), display tier only.
  - If at least one confirmed test at that horizon carries more than volatility, the profile
    may be described as drawing on path information.
  - If none does, it is a volatility-type risk estimate. It is named that way, and it is not
    evidence of persistence.
- No horizon passes all four, and W1, W2 and W3 pass at one → material and not calibrated.
  No profile is built under this pre-registration. A recalibrated model would need its own.
- Neither of the above, and W1 and W2 pass at a gated horizon → detectable and immaterial.
  This is what the simulated market produces in 8 runs of 10 (§7); it is not evidence for the
  family. No profile and no field are built. The features stay available as descriptive
  fields.
- Otherwise → the null on model value is printed. No profile and no field are built.

In the last two cases the family stops at Wave B for these constructions. Q2 is still printed:
it records what kind of information the confirmed tests carried.

No outcome gives sizing, ranking or gating authority.

## 9. Reported but not gating

A against B1 and B0, B2 against B1 and B1 against B0 (what each layer of the baseline buys);
the two ablations; every metric at 5 sessions; the rank IC difference on audited names only;
the same comparison of B0, B2 and A on annual blocks from 2009 to 2021, scored on V2's
development dates, which are survivor-conditioned; Q2's statistic with the controls and their
squares alone, with the eleven descriptors and their squares added, and with both those and
the label window's volatility; Q1 and Q2 on the simulated runs one by one; each Q1 difference
beside the simulated range.

## 10. Known limits

- The years are seen. A pass here is a measurement, not a confirmation.
- One period of four years for the gated blocks. T5 is a partial year.
- The event is cross-sectional. It says which stocks draw down most on a date, not when the
  market draws down.
- The simulated market is one calibration by the author, at two specifications, with a fixed
  universe. Its range is the spread of ten runs, not the distribution of a known null. Real
  volatility has structure it lacks, so a statistic above the range is not proof of anything
  beyond volatility; a statistic inside it is not distinguished from volatility.
- The label window's realised volatility and the label's drawdown come from the same prices.
  Removing one from the other is a decomposition, not a causal control: a feature that predicts
  a drawdown which itself raises realised volatility loses credit for it.
- No sector or size control; point-in-time sector history does not exist for former members.
- Rank models. A different functional form could give a different size.
- No costs, turnover or capacity. Nothing here is a strategy.
- V2's substrate limits carry over (V2 §10).

## 11. Frozen constants

| Constant | Value |
| --- | --- |
| Panel | V2's; digest `48cb5e76269b3a503d2973aecdd04733a2d8b88434db06de8367a224ba4ef178` |
| Label | forward maximum drawdown; horizons 5, 20, 60; gated horizons 20, 60 |
| Blocks | T1 2022-07-06..2022-12-31; T2 2023; T3 2024; T4 2025; T5 2026 |
| Early blocks (reported) | calendar years 2009 to 2021, development dates only |
| Minimum training dates | 100 |
| Minimum complete cases per date | 100 |
| Event fraction, flagged fraction | 0.10, 0.10 |
| Reliability bins | 10 |
| Descriptors | EWMA half-lives 3, 10, 30 over 120 sessions; mean and max absolute return over 20, 60, 120; downside volatility over 20, 120 |
| Products | return × volatility and return² × volatility at 20, 60, 120 |
| Logistic fit | Newton; at most 60 steps; largest step below 1e-8 |
| W1 | one-sided p ≤ 0.025 |
| W2 | at least 4 of 5 blocks positive |
| W3 | at least 0.010 of capture |
| W4 | slope in [0.80, 1.25]; Brier no worse than B2 |
| K2, K3, K4 | p ≤ 0.05; q ≤ 0.10; absolute mean ≥ 0.005 |
| Bins of the label window's volatility | 20, equal count |
| Reproduction tolerance | 1e-9 on each of V2's 29 holdout means |
| Simulated reference | `clustered_leverage`, `clustered_leverage_jumps`; seeds 11–15; 1,500 names; 3,770 sessions from 2012-01-02; models B0, B1, B2, A |

The sha256 of this file is pinned in the instrument as `PREREG_SHA256`; the sha256 of the
simulated reference as `REFERENCE_SHA256`.

## 12. What was looked at before this freeze

- V2's development and holdout results, including the IC of each of the 29 tests on the test
  dates. Q2's first reported series repeats that statistic; it is not new.
- Exploratory, real data, development sample only (labels ending before 2022), not committed
  as a result: adding more volatility descriptors to the controls removes about a quarter of
  the strongest ICs, and adding the realised volatility of the label's own window removes most
  of the rest: all nine `distance_to_high` tests fall to about zero, and `max_drawdown` keeps
  +0.004 to +0.02. The simulated market behaves the same way under both. This is why Q2 is
  asked, and it shaped the descriptors in §4.
- This instrument on one simulated panel of 250 names: the augmented model did not beat the
  volatility-aware baseline (rank IC difference −0.0005 to +0.0002).
- Made-up panels with a planted answer, used to test the instrument. On two of them, a
  feature equal to the label window's volatility plus noise had an IC of −0.31 to −0.55 by V2's
  statistic. With that volatility removed as a rank and its square, and the residual ranked
  again, −0.02 to −0.04 was left (t −6 to −10). Without re-ranking, a rank and its square left
  −0.011 to +0.001, and a rank and twenty bins left −0.003 to +0.005 (|t| under 1.6). Q2's form
  in §6 was chosen from this.
- The simulated reference itself, built once under an earlier draft of this file. Q2's
  volatility-controlled statistic on the simulated runs lies between −0.006 and +0.011 across
  the 29 tests; Q1 is in §7. Seeing it changed two things: the outcome in §8 once drafted as
  "confirmed and immaterial" is now "detectable and immaterial", and §7 says why. No gate, no
  threshold and no model changed. The reference is rebuilt from this frozen file.
- A price-only count of complete cases on the real panel (§3).

Not looked at: any model of §5 fitted on real data, in any year; Q2's volatility-controlled
statistic on any formation date from 2022 onward.
