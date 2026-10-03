# Trend Persistence — Pre-registration B2 (walk-forward comparison and volatility decomposition)

Status: FROZEN 2026-10-03, second freeze. The instrument
(`research/trend_persistence_walkforward.py`) pins this file's sha256 and scores nothing if the
file changes. A first freeze (commit `b20e5f63`) failed an independent review before any real
run was made. §12 says what the review found and what changed.

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

**Order.** On each test date the instrument forms V2's own holdout statistic for each of the
29 tests together with the Q2 statistics. Before any model is fitted, and before anything is
reported or written, it compares V2's statistic with the committed V2 result (mean to 1e-9,
same number of dates; the committed file is read by its pinned hash). If any differs it stops
and reports nothing. Then Q1.

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

Differences are taken per date, A minus B2, and summarised by their mean and the test below.

**The test of a mean.** Every p-value that gates comes from one test. For a series of `n`
per-date values at horizon `h`, whose labels each span `q = ceil(h / 5)` formation dates:

- the long-run variance is the mean of the squares of the first `ν` cosine transforms of the
  series, `Λ_j = sqrt(2 / n) × Σ_t x_t cos(π j (t − ½) / n)`, `j = 1 … ν`;
- `ν = max(4, min(floor(0.4 × n^(2/3)), floor(n / (2 q))))`;
- `t = sqrt(n) × mean / sqrt(variance)`, referred to Student's t with `ν` degrees of freedom.

On the test dates `ν` is 13, 13 and 7 at 5, 20 and 60 sessions. p-values are not rounded.

V2's rule, a Bartlett kernel with `max(4, 2 q)` lags and a normal reference, gates nothing
here. With overlapping labels it rejects a true mean of zero too often (§7). Its t is still
reported beside each mean.

**Q2.** For each confirmed test, on each test date: the correlation, across that date's
stocks, between the label's rank and what is left of the feature's rank after a least-squares
fit on the eleven control ranks, their squares, the rank of the realised volatility of the
label window, and indicators for twenty equal-count bins of that rank. Summarised by its mean
over test dates and the same test.

The residual is not ranked again. V2's statistic does rank it again, and a re-ranked residual
is no longer orthogonal to what was removed: on made-up data, a feature that is nothing but the
label window's volatility plus noise kept 4 to 10 percent of its IC that way (§12). V2's own
statistic is reported beside this one, unchanged.

**The simulated reference.** The same statistics are computed, by the same code, on simulated
panels from the committed benchmark module (`research/trend_persistence_null.py`):
specifications `clustered_leverage` and `clustered_leverage_jumps`. Q2 is computed on seeds 11
to 110 of each, two hundred runs. Q1 is computed as well on seeds 11 to 30 of each, forty runs.
A further hundred runs of each, seeds 111 to 210, compute Q2 only and set no threshold: they
measure how often the rule of §7 gives a volatility-only market the label.
Each run has 1,500 names, all members throughout, on 3,770 sessions from 2012-01-02 to
2026-06-12, with the same blocks and the same 29 feature-horizon pairs. The calendar starts in
2012 so that the first block trains on about as many stock-dates as the real one. The
generator takes a specification and a seed and reads no prices.

The reference is produced after this file is frozen and before the real run. It records one
hash over the code a result depends on: the walk-forward, panel, simulated-market and substrate
modules. The instrument refuses to score real data unless the reference's file hash, this
file's hash, the design constants and that code hash all match.

**One run.** The real run is made once, from a committed tree, and writes to one fixed path,
`research/data/trend_persistence_b2_result.json`. It takes no other output path. Before it
reads real prices it records the attempt (time, commit, code hash) in
`research/data/trend_persistence_b2_attempt.json`. It refuses to run if the result exists. If
an attempt is on record and no result is, another attempt needs a stated reason; the reason is
kept in the result and reported as a deviation. Nothing computed on the test dates is printed
or written before the result file is.

## 7. Gates

Q1 is evaluated at 20 and at 60 sessions. The 5-session horizon is reported and does not gate.

| Gate | Requirement |
| --- | --- |
| W1 | mean difference in rank IC above zero, one-sided p ≤ 0.025 (the test of §6) |
| W2 | mean difference in rank IC above zero in at least 4 of the 5 blocks |
| W3 | mean difference in capture of at least 1.0 percentage point |
| W4 | A's calibration slope between 0.80 and 1.25, and A's mean Brier score no worse than B2's |

W1's 0.025 is 0.05 split across the two gated horizons. W3 is a materiality bar, chosen before
the run: below one point of capture a reader could not tell the two risk rankings apart in use.

**W1 and W2 alone do not separate the features from volatility.** In the forty simulated runs
that carry Q1 (§6), A beats B2 by a rank IC of −0.00008 to +0.00079 at the gated horizons, and
both W1 and W2 pass at one of them in 25 runs of 40: the features carry a trace of information
about future volatility that no finite set of descriptors removes. W3 is what the simulated
market does not reach. Its capture difference is between −0.19 and +0.19 points over all three
horizons, and W3 passes in 0 of the 40 runs at any horizon. None of the 40 passes all four
gates at a gated horizon.

W4 hardly discriminates in the simulated market: it passes in 115 of 120 run-horizons, with
A's slope between 0.92 and 1.06. It guards against a probability that cannot be shown as one.
It is not evidence for the family.

**How often the test of a mean rejects when there is nothing to find.** Each simulated run's
volatility-controlled series (Q2, every confirmed test) was centred at the mean of the other
runs of its specification and tested. The share rejected:

| Specification | Horizon | Series | This test, stated 2.5% | stated 5% | V2's rule, stated 2.5% | stated 5% |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `clustered_leverage` | 5 | 1,000 | 2.2% | 3.8% | 2.8% | 5.1% |
| `clustered_leverage` | 20 | 1,100 | 2.6% | 5.2% | 4.1% | 6.5% |
| `clustered_leverage` | 60 | 800 | 2.5% | 5.4% | 5.5% | 9.0% |
| `clustered_leverage_jumps` | 5 | 1,000 | 2.4% | 4.1% | 2.5% | 4.0% |
| `clustered_leverage_jumps` | 20 | 1,100 | 3.4% | 5.7% | 4.9% | 8.2% |
| `clustered_leverage_jumps` | 60 | 800 | 2.9% | 5.6% | 5.8% | 9.2% |

The series of one run are not independent of each other, so these shares are less precise than
their counts suggest. The test of §6 stays near its stated level. At the gated horizons V2's
rule rejects 1.6 to 2.3 times as often as its stated 2.5%, which is why it gates nothing here.
The same exercise on the Q1 difference is recorded in the reference and is not a measure of
the test: each run fits its own models, whose true difference differs from run to run.

Q2, per confirmed test. A test's leftover is **beyond simulated volatility** when all five
hold on the test dates:

| Gate | Requirement |
| --- | --- |
| K1 | the mean has the development sign |
| K2 | one-sided p ≤ 0.05 in the development direction (the test of §6) |
| K3 | false-discovery q ≤ 0.10 across the 29 (Benjamini–Hochberg on those p-values) |
| K4 | absolute mean at least 0.005 |
| K5 | the mean stands clear of both simulated markets, all 29 tests considered together |

**K5.** For one simulated specification, each of its 100 runs gives the statistic for all 29
tests, signed by the development sign. For a test, those runs have a mean `m` and a standard
deviation `s`, and a value `x` has **excess** `(x − m) / s`. Each run's excess is taken test by
test against the other 99 runs, and the largest of its 29 excesses is kept: one draw of how far
the best-looking test of a volatility-only market stands out. The specification's
**threshold** is the 95th smallest of those 100 draws. A real test passes K5 when its excess,
against the mean and standard deviation of all 100 runs, is above the threshold for **both**
specifications.

The simulated calendar has every weekday, so a simulated run has more test dates than the real
panel: 205, 202 and 194 against 197, 194 and 186 (§3). A mean over fewer dates spreads more.
Before a real test's excess is formed, the simulated standard deviation is multiplied by
`sqrt(simulated dates / real dates)`, about 1.02.

The thresholds are 2.952 (`clustered_leverage`) and 2.870 (`clustered_leverage_jumps`). In the
statistic's own units, at the real numbers of dates, that puts the bar for a real test between
+0.0047 and +0.0153:

| Feature | Horizon | `clustered_leverage` mean | sd | `clustered_leverage_jumps` mean | sd | Bar: signed mean above |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `distance_to_high_120d` | 5 | +0.0011 | 0.0015 | +0.0018 | 0.0012 | +0.0057 |
| `distance_to_high_20d` | 5 | +0.0013 | 0.0015 | +0.0025 | 0.0015 | +0.0068 |
| `distance_to_high_60d` | 5 | +0.0012 | 0.0014 | +0.0025 | 0.0013 | +0.0064 |
| `efficiency_20d` | 5 | +0.0012 | 0.0014 | +0.0040 | 0.0015 | +0.0084 |
| `max_drawdown_120d` | 5 | +0.0005 | 0.0014 | +0.0020 | 0.0014 | +0.0060 |
| `max_drawdown_20d` | 5 | +0.0012 | 0.0015 | +0.0039 | 0.0016 | +0.0085 |
| `max_drawdown_60d` | 5 | +0.0006 | 0.0014 | +0.0024 | 0.0015 | +0.0066 |
| `positive_day_fraction_120d` | 5 | +0.0002 | 0.0014 | +0.0020 | 0.0017 | +0.0069 |
| `positive_day_fraction_20d` | 5 | +0.0002 | 0.0016 | +0.0014 | 0.0015 | +0.0060 |
| `positive_day_fraction_60d` | 5 | +0.0002 | 0.0013 | +0.0022 | 0.0015 | +0.0066 |
| `distance_to_high_120d` | 20 | -0.0003 | 0.0021 | +0.0020 | 0.0021 | +0.0080 |
| `distance_to_high_20d` | 20 | -0.0007 | 0.0014 | +0.0028 | 0.0015 | +0.0073 |
| `distance_to_high_60d` | 20 | -0.0002 | 0.0019 | +0.0027 | 0.0018 | +0.0081 |
| `efficiency_20d` | 20 | +0.0004 | 0.0014 | +0.0044 | 0.0018 | +0.0097 |
| `max_drawdown_120d` | 20 | +0.0002 | 0.0024 | +0.0027 | 0.0027 | +0.0105 |
| `max_drawdown_20d` | 20 | -0.0006 | 0.0020 | +0.0041 | 0.0021 | +0.0102 |
| `max_drawdown_60d` | 20 | +0.0001 | 0.0022 | +0.0028 | 0.0024 | +0.0099 |
| `positive_day_fraction_120d` | 20 | -0.0006 | 0.0022 | +0.0031 | 0.0027 | +0.0109 |
| `positive_day_fraction_60d` | 20 | -0.0008 | 0.0019 | +0.0032 | 0.0024 | +0.0101 |
| `sessions_since_high_120d` | 20 | +0.0001 | 0.0020 | -0.0016 | 0.0022 | +0.0060 |
| `sessions_since_high_60d` | 20 | +0.0001 | 0.0015 | -0.0018 | 0.0020 | +0.0047 |
| `distance_to_high_120d` | 60 | -0.0023 | 0.0024 | +0.0005 | 0.0027 | +0.0083 |
| `distance_to_high_20d` | 60 | -0.0026 | 0.0015 | +0.0015 | 0.0015 | +0.0057 |
| `distance_to_high_60d` | 60 | -0.0027 | 0.0020 | +0.0011 | 0.0021 | +0.0074 |
| `max_drawdown_120d` | 60 | -0.0009 | 0.0035 | +0.0030 | 0.0040 | +0.0147 |
| `max_drawdown_20d` | 60 | -0.0030 | 0.0018 | +0.0039 | 0.0023 | +0.0106 |
| `max_drawdown_60d` | 60 | -0.0011 | 0.0028 | +0.0029 | 0.0034 | +0.0130 |
| `positive_day_fraction_60d` | 60 | -0.0021 | 0.0029 | +0.0039 | 0.0039 | +0.0153 |
| `sessions_since_high_120d` | 60 | +0.0000 | 0.0027 | +0.0002 | 0.0028 | +0.0086 |

How often a volatility-only market is given the label:

| Runs | Specification | K5 passes on some test | All five gates pass on some test | …at a gated horizon |
| --- | --- | ---: | ---: | ---: |
| the 100 the thresholds were set on, each left out in turn | `clustered_leverage` | 1 | 0 | 0 |
| | `clustered_leverage_jumps` | 4 | 4 | 4 |
| 100 further runs that set no threshold (seeds 111 to 210) | `clustered_leverage` | 0 | 0 | 0 |
| | `clustered_leverage_jumps` | 4 | 4 | 1 |

In the first pair of rows the construction caps the K5 count at 5. Nothing forces the second
pair: the further runs go through the same code as real data, and their counts are the
measured rate at which this rule mislabels these two markets.

K4's floor is low against V2's ICs of 0.007 to 0.051. The statistic is what is left after a
strong control, so it is smaller than an IC by construction. K4 only keeps a leftover that is
detectable and negligible from being called more. For every test but one K5's bar is the
higher of the two.

## 8. Decision rule

- W1–W4 all pass at a horizon → a walk-forward event probability from model A, with its
  reliability table, is eligible for `CALIBRATED_PROFILE` at that horizon and for a shadow
  snapshot through the existing signal and outcome owners (Wave D), display tier only.
  - If at least one confirmed test at that horizon passes K1–K5, the profile is recorded as
    `beyond_simulated_volatility`: the features say more about the drawdown than they do in
    either simulated market. That is a statement about those two markets. It is not proof of
    path information (§10).
  - If none does, it is a volatility-type risk estimate. It is named that way, and it is not
    evidence of persistence.
- No horizon passes all four, and W1, W2 and W3 pass at one → material and not calibrated.
  No profile is built under this pre-registration. A recalibrated model would need its own.
- Neither of the above, and W1 and W2 pass at a gated horizon → detectable and immaterial.
  This is what the simulated market produces in 25 runs of 40 (§7); it is not evidence for the
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
beside the smallest and largest of the forty simulated runs; V2's t beside every mean; each
test's excess against each simulated specification.

## 10. Known limits

- The years are seen. A pass here is a measurement, not a confirmation.
- One period of four years for the gated blocks. T5 is a partial year.
- The event is cross-sectional. It says which stocks draw down most on a date, not when the
  market draws down.
- The simulated market is one calibration by the author, at two specifications, with a fixed
  universe. Real volatility has structure it lacks, so a test that clears K5 is not proof of
  anything beyond volatility; a test that does not is not distinguished from volatility.
- K5's thresholds are each estimated from 100 runs. A 95th percentile read off 100 draws is
  exceeded by 5.9% of new draws on average, and by anything from about 2% to 11%; §7 gives
  the rate measured on fresh runs.
- The simulated spread is taken to the real number of dates by a square-root rule (§7). With
  overlapping labels that rule is approximate. The correction is about 2%.
- The test of a mean was checked on simulated series (§7) and on made-up noise (§12). Its
  behaviour on real series is not known. At 60 sessions it has seven degrees of freedom and
  little power; a real effect there can be missed.
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
| Test of a mean | equal-weighted cosine variance; `ν = max(4, min(floor(0.4 n^(2/3)), floor(n / (2 ceil(h / 5)))))`; Student t with `ν` degrees of freedom; one-sided; unrounded |
| W1 | one-sided p ≤ 0.025 |
| W2 | at least 4 of 5 blocks positive |
| W3 | at least 0.010 of capture |
| W4 | slope in [0.80, 1.25]; Brier no worse than B2 |
| K2, K3, K4 | p ≤ 0.05; q ≤ 0.10; absolute mean ≥ 0.005 |
| K5 | per specification, the 95th smallest of 100 leave-one-out largest excesses over the 29 tests; simulated spread × `sqrt(simulated dates / real dates)`; a test must exceed both |
| Bins of the label window's volatility | 20, equal count |
| Reproduction tolerance | 1e-9 on each of V2's 29 holdout means |
| V2 holdout result | `research/data/trend_persistence_v2_holdout.json`, sha256 `ff928d6c22168b4a674f63a319efd45d984f0b2a9c4095bfda8790cb6dceff41` |
| Simulated reference | `clustered_leverage`, `clustered_leverage_jumps`; Q2 on seeds 11–110; Q1 on seeds 11–30; fresh check on seeds 111–210; 1,500 names; 3,770 sessions from 2012-01-02; models B0, B1, B2, A |
| Code pinned by the reference | `trend_persistence_walkforward.py` (its two pin lines excepted), `trend_persistence_panel.py`, `trend_persistence_null.py`, `trend_persistence_substrate.py` |
| Result, attempt record | `research/data/trend_persistence_b2_result.json`, `research/data/trend_persistence_b2_attempt.json` |

The sha256 of this file is pinned in the instrument as `PREREG_SHA256`; the sha256 of the
simulated reference as `REFERENCE_SHA256`. The loader the substrate module calls
(`loop/factor_experiment`) is outside the code pin; the panel digest covers what it returns.

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
- **A first freeze of this design, and its independent review.** Commit `b20e5f63` froze an
  earlier version of this file (sha256 `75bf31d8…7972b`) with a ten-run reference. An
  independent reviewer, working only on simulated data and before any real run, failed it:
  1. K5 compared each test with the largest of ten simulated run means, one test at a time,
     and a horizon took the label if any one test passed. Leaving one simulated run out, every
     `clustered_leverage_jumps` run was given the label.
  2. V2's HAC rule, which W1 and K2 used, rejected a true mean of zero 4.8% and 6.8% of the
     time at a stated 2.5%, at 20 and 60 sessions, in the reviewer's simulation.
  3. The reference was not tied to the code that produced it.
  4. The one-run guard could be passed by naming another output file, and a crash left no
     record.
  Changed in this freeze: the test of a mean (§6), K5 and its reference (§6, §7), the name of
  the label (§8, once "path information"), the code pin, the pinned V2 result file and the
  attempt record (§6). Not changed: the questions, the substrate, the blocks, the variables,
  the models, W2, W3, W4, K1, K4, the levels of W1, K2 and K3, and the four outcomes.
  **No real B2 run was made under the first freeze.**
- The test of a mean was chosen on made-up noise: sums of overlapping shocks of the kind 20-
  and 60-session labels induce, the same with persistent shocks, and the same with heavy tails
  and clustered variance; 20,000 series of each at the real numbers of dates. At a stated
  2.5%, V2's rule rejected a true zero 2.8% to 7.1% of the time. Cosine variances with three
  caps on the number of terms (`n / 2q`, `n / 3q`, `n / 4q`) rejected 2.4% to 2.9%. The widest
  cap was taken because it keeps the most degrees of freedom. At 60 sessions it is also the
  one furthest above its stated level: 2.7% to 2.9% at 2.5%, and 5.4% to 5.9% at 5%. No real
  data was involved.
- The simulated reference, built under drafts of this file: once with ten runs (first
  freeze), then with the runs of §6. From the first: Q2's volatility-controlled statistic and
  the Q1 differences on simulated runs; seeing them changed the outcome once drafted as
  "confirmed and immaterial" to "detectable and immaterial". From the second: every number in
  §7. Across the 200 runs the volatility-controlled statistic lies between −0.0105 and
  +0.0172. K5's level (5%) and form were fixed before its thresholds were computed, and no
  threshold was changed after seeing them. Two things were added after the first 200 runs
  were seen: the 100 further runs per specification, and the scaling of the simulated spread
  to the real number of dates, which raises every bar by about 2%. Neither changed a
  threshold. The reference is rebuilt from this frozen file.
- A price-only count of complete cases on the real panel (§3).

Not looked at: any model of §5 fitted on real data, in any year; Q2's volatility-controlled
statistic on any formation date from 2022 onward.
