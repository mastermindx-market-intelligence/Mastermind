# Trend Persistence — Development readout

Wave B, stock level. Development sample only (formation dates 2003–2021).

**Where this stands.** Nothing is promoted. Every feature in this family is still
`DESCRIPTIVE`. The holdout (2022 onward) has not been scored. One claim — downside risk — is
queued for a single confirmatory holdout run under `TREND_PERSISTENCE_PREREG_V2.md`.

## 1. Results in one view

| Question | Design | Tests | Survive development | Reading |
| --- | --- | --- | --- | --- |
| Do these features say anything about forward return vs SPY beyond momentum, volatility and beta? | V1 | 72 | **0** | Null. Closed for these constructions, this universe, these horizons. |
| Do they say anything about forward maximum drawdown beyond momentum, one volatility window and beta? | V1 | 72 | 34 | Not usable as evidence: volatility was under-controlled (§4). |
| Same, with volatility at four spans, downside volatility and the quoted-price mask? | V2 | 72 | **29** | A filter, not evidence. These 29 go to the holdout. |

A survivor here has passed pre-registered development gates. It has not been confirmed
out of sample, and development alone cannot confirm it: the development universe is tilted
toward survivors (§5) and the sample was inspected before V2 was written.

## 2. V1 — forward return relative to SPY: null

| Family | Endpoint | Tests | Survive | Largest abs mean IC | Largest abs HAC t |
| --- | --- | --- | --- | --- | --- |
| path quality | `forward_rel` | 36 | 0 | 0.0143 | 2.86 |
| path quality | `forward_max_drawdown` | 36 | 11 | 0.0249 | 9.06 |
| gain retention | `forward_rel` | 9 | 0 | 0.0138 | 2.82 |
| gain retention | `forward_max_drawdown` | 9 | 1 | 0.0200 | 5.94 |
| drawdown shape | `forward_rel` | 27 | 0 | 0.0084 | 2.75 |
| drawdown shape | `forward_max_drawdown` | 27 | 22 | 0.0965 | 24.03 |

No test of forward relative return clears the gates. 11 of 72 pass the false-discovery
step, but only 2 of the 72 reach an absolute mean IC of 0.010, and both fail the
non-overlapping check. The strongest, `signed_efficiency_120d` at 60 sessions, has mean IC
−0.014 (HAC t −2.9): a *cleaner* advance is followed by slightly *worse* relative return,
the opposite of a continuation claim, and it does not hold across eras. The full per-test
table is in Appendix B.

## 3. V1 — forward maximum drawdown: 34 survive, and why that is not used

Drawdown shape accounts for 22 of the 34. The largest is `max_drawdown_120d` at 60
sessions: mean IC +0.096 — stocks with a shallow past drawdown go on to have a shallow
forward drawdown. Appendix C has every test.

That reads like volatility persistence, and V1 controls volatility with a single 60-session
window. An exploratory rerun on the development sample (not pre-registered, labelled as
such) added volatility at 20, 120 and 252 sessions and downside volatility. The drawdown
ICs fell by about half and the gain-retention and signed-efficiency survivors disappeared.
V1's drawdown result is therefore mostly a statement about its control set. V2 fixes the
control set and tests the claim again.

## 4. Independent review of the instrument

An independent read-only review attacked the V1 instrument before any holdout use. Labels,
judge parity, inference, gate logic and feature arithmetic passed. It found:

| # | Finding | Severity | What was done |
| --- | --- | --- | --- |
| F1 | The audited sanitizer fills gaps inside a name's life; whether a day is inside depends on later prices. Eligibility and feature windows could rest on a filled price. 506 of 504,883 eligible stock-dates before 2022. | blocker, small | V2 uses a quoted-price mask. Measured on V1: survivors 34 → 35, largest change in any mean IC 0.0013. |
| F2 | `build_panel` took the holdout boundary as an argument, so a caller could score 2022+ as "development". | blocker (fence) | Boundaries are module constants; the argument is gone. The V1 run used the default and is unaffected. |
| F3 | The pre-registration hash was read from a relocatable path and never pinned; the survivor list for a holdout run was caller-supplied. | major | Hash pinned in code; nothing scores on a mismatch. A holdout run re-derives the survivors itself. |
| F4 | 864 of 2,249 pre-2022 member tickers have no price column, and the result did not say so. | major | Coverage is stamped on every result (§5). Repaired for the holdout window. |
| F5 | A holdout run computed and emitted coverage for horizons with no survivor. | minor | Horizons without a survivor are not touched. |
| F6 | The judge rounds p to four decimals before the false-discovery step. | minor | Kept and declared in V2 §5. |
| F7 | A test without a p-value dropped out of the false-discovery family. | minor | Such a test now enters as p = 1. None occurred in V1 (144 of 144 had a p-value). |
| F8 | Several small rules were implemented but not written down. | minor | Written into V2 §5–§6. |

**V1's holdout is closed.** With F1 and the volatility finding, a V1 holdout run would test
a design already known to be wrong. The instrument now refuses it.

## 5. Substrate: what the universe actually is

Members by the membership file, and how many have a price, on the first session of the
year:

| Year | Members | Audited panel | Repaired, quoted |
| --- | --- | --- | --- |
| 2004 | 494 | 270 | 268 |
| 2008 | 497 | 317 | 314 |
| 2012 | 497 | 346 | 346 |
| 2013 | 920 | 593 | 593 |
| 2016 | 920 | 647 | 647 |
| 2019 | 913 | 726 | 726 |
| 2020 | 1,521 | 1,085 | 1,085 |
| 2021 | 1,521 | 1,125 | 1,125 |
| 2022 | 1,516 | 1,167 | 1,501 |
| 2023 | 1,514 | 1,222 | 1,507 |
| 2024 | 1,510 | 1,314 | 1,506 |
| 2025 | 1,507 | 1,385 | 1,504 |
| 2026 | 1,506 | 1,458 | 1,505 |

Two things follow.

- **The membership file is not a constant S&P 1500.** It lists about 500 names until 2012,
  about 920 from 2013 and about 1,520 from 2020.
- **The audited panel is survivor-tilted.** It prices 55–80% of members in development,
  mostly names that are still listed. `loop/factor_experiment.py` calls the panel
  "survivorship-safe"; for this universe that overstates it. Every development number in
  this readout carries that tilt.

For 2022 onward the gap is repaired from the whole-market daily store (410 names, split
adjustment from a committed vendor reference, validated against the audited panel on names
both sources hold: 91 of 91 real splits matched, no false adjustment). The repaired panel
prices more than 99% of members. Names that left before mid-2021 cannot be repaired.

## 6. V2 — development result

Controls: four trailing returns, volatility at 20/60/120/252 sessions, downside volatility at
60/252, beta. Quoted-price mask. Seven gates, the seventh requiring the same sign in at least
four of five volatility quintiles. 72 tests.

| Family | Tests | Survive |
| --- | --- | --- |
| drawdown shape | 27 | 21 |
| path quality | 36 | 8 |
| gain retention | 9 | 0 |

- **Drawdown shape.** `max_drawdown` and `distance_to_high` survive at every window and
  horizon, all positive: shallower past drawdown, shallower forward drawdown. Mean ICs run
  from +0.010 to +0.056 — about half of what V1's control set showed. `sessions_since_high`
  survives in 3 of 9.
- **Path quality.** `positive_day_fraction` survives in 6 of 9 and `efficiency_20d` in 2 of
  3, with mean ICs of +0.011 to +0.017. `directional_consistency` and `signed_efficiency`
  do not survive.
- **Gain retention.** Null under V2's controls. The single V1 survivor does not survive them.

These are small effects. The largest mean IC is 0.056.

| Feature | h | Mean IC | HAC t | BH q | V1 controls | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0036 | -2.10 | 0.0498 | -0.0030 | +0.0192 | +0.0076 | G2, G4, G5, G6 | no |
| `directional_consistency_20d` | 20 | -0.0057 | -2.93 | 0.0057 | -0.0076 | +0.0225 | +0.0070 | G2, G5, G6 | no |
| `directional_consistency_20d` | 60 | -0.0085 | -3.86 | 0.0002 | -0.0094 | +0.0239 | +0.0044 | G2, G3, G5, G6 | no |
| `directional_consistency_60d` | 5 | -0.0043 | -2.30 | 0.0308 | -0.0094 | +0.0174 | +0.0103 | G2, G5, G6 | no |
| `directional_consistency_60d` | 20 | -0.0103 | -3.58 | 0.0005 | -0.0164 | +0.0203 | +0.0087 | G3, G5 | no |
| `directional_consistency_60d` | 60 | -0.0187 | -4.91 | 0.0000 | -0.0247 | +0.0152 | -0.0024 | G5 | no |
| `directional_consistency_120d` | 5 | -0.0089 | -4.16 | 0.0000 | -0.0086 | +0.0138 | +0.0082 | G2, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0190 | -5.57 | 0.0000 | -0.0177 | +0.0124 | +0.0021 | G5 | no |
| `directional_consistency_120d` | 60 | -0.0272 | -5.83 | 0.0000 | -0.0245 | +0.0097 | -0.0042 | G5 | no |
| `efficiency_20d` | 5 | +0.0172 | +8.55 | 0.0000 | +0.0188 | +0.0516 | +0.0054 | — | yes |
| `efficiency_20d` | 20 | +0.0173 | +6.25 | 0.0000 | +0.0163 | +0.0590 | -0.0008 | — | yes |
| `efficiency_20d` | 60 | +0.0071 | +2.36 | 0.0273 | +0.0059 | +0.0507 | -0.0150 | G2, G3, G5, G6, G7 | no |
| `efficiency_60d` | 5 | +0.0093 | +3.66 | 0.0005 | +0.0128 | +0.0461 | -0.0045 | G2, G6, G7 | no |
| `efficiency_60d` | 20 | +0.0072 | +1.75 | 0.1069 | +0.0101 | +0.0548 | -0.0150 | G1, G2, G6, G7 | no |
| `efficiency_60d` | 60 | -0.0072 | -1.57 | 0.1419 | -0.0057 | +0.0413 | -0.0368 | G1, G2, G5, G6 | no |
| `efficiency_120d` | 5 | +0.0025 | +0.85 | 0.4283 | +0.0061 | +0.0430 | -0.0185 | G1, G2, G3, G6, G7 | no |
| `efficiency_120d` | 20 | -0.0068 | -1.42 | 0.1880 | -0.0014 | +0.0482 | -0.0382 | G1, G2, G3, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0177 | -2.72 | 0.0102 | -0.0139 | +0.0402 | -0.0535 | G5 | no |
| `positive_day_fraction_20d` | 5 | +0.0107 | +5.62 | 0.0000 | +0.0111 | +0.0311 | +0.0526 | — | yes |
| `positive_day_fraction_20d` | 20 | +0.0093 | +3.66 | 0.0005 | +0.0090 | +0.0356 | +0.0607 | G2, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0092 | +3.58 | 0.0005 | +0.0113 | +0.0401 | +0.0570 | G2, G6 | no |
| `positive_day_fraction_60d` | 5 | +0.0139 | +7.27 | 0.0000 | +0.0136 | +0.0436 | +0.0703 | — | yes |
| `positive_day_fraction_60d` | 20 | +0.0150 | +5.07 | 0.0000 | +0.0145 | +0.0552 | +0.0875 | — | yes |
| `positive_day_fraction_60d` | 60 | +0.0117 | +2.93 | 0.0057 | +0.0142 | +0.0590 | +0.0845 | — | yes |
| `positive_day_fraction_120d` | 5 | +0.0136 | +7.71 | 0.0000 | +0.0166 | +0.0518 | +0.0804 | — | yes |
| `positive_day_fraction_120d` | 20 | +0.0149 | +4.99 | 0.0000 | +0.0188 | +0.0672 | +0.1009 | — | yes |
| `positive_day_fraction_120d` | 60 | +0.0108 | +2.41 | 0.0242 | +0.0183 | +0.0719 | +0.1007 | G7 | no |
| `signed_efficiency_20d` | 5 | +0.0072 | +3.83 | 0.0002 | +0.0106 | +0.0516 | +0.0581 | G2, G6 | no |
| `signed_efficiency_20d` | 20 | +0.0057 | +2.35 | 0.0273 | +0.0063 | +0.0635 | +0.0687 | G2, G3, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0023 | +0.71 | 0.5079 | +0.0050 | +0.0677 | +0.0592 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_60d` | 5 | -0.0006 | -0.30 | 0.7664 | +0.0056 | +0.0762 | +0.0756 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_60d` | 20 | -0.0017 | -0.50 | 0.6317 | +0.0049 | +0.1023 | +0.0962 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_60d` | 60 | -0.0082 | -1.60 | 0.1354 | -0.0045 | +0.1095 | +0.0881 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_120d` | 5 | -0.0020 | -0.92 | 0.3983 | +0.0088 | +0.0951 | +0.0879 | G1, G2, G3, G4, G5, G6, G7 | no |
| `signed_efficiency_120d` | 20 | -0.0064 | -1.74 | 0.1079 | +0.0090 | +0.1305 | +0.1111 | G1, G2, G3, G5, G6, G7 | no |
| `signed_efficiency_120d` | 60 | -0.0093 | -2.00 | 0.0611 | +0.0066 | +0.1452 | +0.1102 | G2, G3, G5, G6, G7 | no |
| `retained_20d` | 5 | +0.0083 | +4.35 | 0.0000 | +0.0115 | +0.0524 | +0.0595 | G2, G6 | no |
| `retained_20d` | 20 | +0.0068 | +2.75 | 0.0098 | +0.0072 | +0.0643 | +0.0703 | G2, G3, G6 | no |
| `retained_20d` | 60 | +0.0034 | +1.08 | 0.3271 | +0.0060 | +0.0685 | +0.0608 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 5 | +0.0034 | +1.61 | 0.1354 | +0.0096 | +0.0790 | +0.0804 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 20 | +0.0036 | +1.05 | 0.3305 | +0.0100 | +0.1058 | +0.1023 | G1, G2, G4, G6 | no |
| `retained_60d` | 60 | -0.0024 | -0.46 | 0.6578 | +0.0011 | +0.1131 | +0.0954 | G1, G2, G3, G4, G5, G6, G7 | no |
| `retained_120d` | 5 | +0.0057 | +2.21 | 0.0384 | +0.0167 | +0.0998 | +0.0988 | G2, G3, G5, G6 | no |
| `retained_120d` | 20 | +0.0045 | +1.09 | 0.3260 | +0.0199 | +0.1370 | +0.1279 | G1, G2, G3, G4, G5, G6 | no |
| `retained_120d` | 60 | +0.0039 | +0.71 | 0.5079 | +0.0195 | +0.1529 | +0.1307 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 5 | +0.0100 | +4.75 | 0.0000 | +0.0235 | +0.1360 | +0.1528 | — | yes |
| `distance_to_high_20d` | 20 | +0.0167 | +7.08 | 0.0000 | +0.0291 | +0.1817 | +0.2005 | — | yes |
| `distance_to_high_20d` | 60 | +0.0145 | +6.10 | 0.0000 | +0.0315 | +0.1959 | +0.2026 | — | yes |
| `distance_to_high_60d` | 5 | +0.0164 | +7.59 | 0.0000 | +0.0246 | +0.1734 | +0.1793 | — | yes |
| `distance_to_high_60d` | 20 | +0.0255 | +9.48 | 0.0000 | +0.0354 | +0.2359 | +0.2363 | — | yes |
| `distance_to_high_60d` | 60 | +0.0273 | +9.40 | 0.0000 | +0.0397 | +0.2576 | +0.2423 | — | yes |
| `distance_to_high_120d` | 5 | +0.0216 | +10.49 | 0.0000 | +0.0384 | +0.1932 | +0.1962 | — | yes |
| `distance_to_high_120d` | 20 | +0.0355 | +12.10 | 0.0000 | +0.0587 | +0.2665 | +0.2605 | — | yes |
| `distance_to_high_120d` | 60 | +0.0406 | +10.60 | 0.0000 | +0.0677 | +0.2925 | +0.2693 | — | yes |
| `max_drawdown_20d` | 5 | +0.0185 | +9.72 | 0.0000 | +0.0437 | +0.2174 | +0.2538 | — | yes |
| `max_drawdown_20d` | 20 | +0.0280 | +11.04 | 0.0000 | +0.0503 | +0.2843 | +0.3288 | — | yes |
| `max_drawdown_20d` | 60 | +0.0275 | +9.95 | 0.0000 | +0.0573 | +0.3090 | +0.3440 | — | yes |
| `max_drawdown_60d` | 5 | +0.0246 | +10.78 | 0.0000 | +0.0284 | +0.2321 | +0.2722 | — | yes |
| `max_drawdown_60d` | 20 | +0.0412 | +13.09 | 0.0000 | +0.0465 | +0.3186 | +0.3648 | — | yes |
| `max_drawdown_60d` | 60 | +0.0472 | +13.31 | 0.0000 | +0.0506 | +0.3444 | +0.3856 | — | yes |
| `max_drawdown_120d` | 5 | +0.0268 | +13.03 | 0.0000 | +0.0505 | +0.2397 | +0.2833 | — | yes |
| `max_drawdown_120d` | 20 | +0.0442 | +14.01 | 0.0000 | +0.0803 | +0.3319 | +0.3831 | — | yes |
| `max_drawdown_120d` | 60 | +0.0557 | +12.17 | 0.0000 | +0.0964 | +0.3648 | +0.4133 | — | yes |
| `sessions_since_high_20d` | 5 | -0.0018 | -1.06 | 0.3305 | -0.0037 | -0.0198 | -0.0409 | G1, G2, G3, G4, G5, G6, G7 | no |
| `sessions_since_high_20d` | 20 | -0.0035 | -1.64 | 0.1309 | -0.0048 | -0.0277 | -0.0512 | G1, G2, G3, G4, G6, G7 | no |
| `sessions_since_high_20d` | 60 | -0.0013 | -0.57 | 0.5897 | -0.0033 | -0.0274 | -0.0436 | G1, G2, G3, G4, G5, G6, G7 | no |
| `sessions_since_high_60d` | 5 | -0.0091 | -5.05 | 0.0000 | -0.0077 | -0.0358 | -0.0575 | G2, G6 | no |
| `sessions_since_high_60d` | 20 | -0.0124 | -4.59 | 0.0000 | -0.0121 | -0.0513 | -0.0741 | — | yes |
| `sessions_since_high_60d` | 60 | -0.0086 | -2.74 | 0.0098 | -0.0079 | -0.0518 | -0.0682 | G2, G6 | no |
| `sessions_since_high_120d` | 5 | -0.0075 | -3.96 | 0.0002 | -0.0131 | -0.0428 | -0.0717 | G2, G4, G6 | no |
| `sessions_since_high_120d` | 20 | -0.0164 | -5.89 | 0.0000 | -0.0256 | -0.0673 | -0.0961 | — | yes |
| `sessions_since_high_120d` | 60 | -0.0154 | -4.77 | 0.0000 | -0.0253 | -0.0720 | -0.0950 | — | yes |

## 7. Deviations from the pre-registrations

- **V1 holdout not run.** V1 §7 scheduled it after review. The review and the volatility
  finding closed it instead (§4).
- **V1 development was rerun on the refactored instrument.** Every per-test number, the
  coverage and the survivor set are identical to the first run (commit `9ee79b75`).
- **F1 sensitivity** (§4) scores V1's design with the quoted-price mask. It is a diagnostic
  outside V1's frozen design.
- **The volatility rerun in §3 is exploratory.** It informed V2's design and is the reason
  V2 treats development as a filter.
- **Price-only work on 2022 onward** was done to build and validate the repair: split
  validation, gap counts, member coverage. No feature was related to any label there.

## 8. What happens next

1. Independent review of the V2 instrument, fence and substrate.
2. One holdout run: the 29 survivors, formation dates from 2022-07-06, repaired universe.
3. Per family: confirmed members move to `RESEARCH_PREDICTIVE` for downside-risk
   description and earn a walk-forward comparison; otherwise the family stays `DESCRIPTIVE`
   and the failed confirmation is printed.

No outcome of step 2 creates an advisory field, a score or a gate.

## 9. Reproduce

```
python3 -m research.trend_persistence_panel --design v1 --sample dev \
    --breadth-dir <breadth> --out research/data/trend_persistence_v1_dev.json
python3 -m research.trend_persistence_panel --design v2 --sample dev \
    --breadth-dir <breadth> --store-dir <massive_stock_day> \
    --out research/data/trend_persistence_v2_dev.json
```

`<breadth>` holds `_closes_deep.parquet`, `_closes_delisted.parquet` and
`sp1500_pit_membership.parquet`. Input digests are stamped in each result under
`provenance`.

## Appendix A — gate legend

G1 false-discovery q ≤ 0.10 · G2 absolute mean IC ≥ 0.010 · G3 non-overlapping series, same
sign and absolute t ≥ 2 · G4 same sign in 4 of 5 eras · G5 same sign in 4 of 5 momentum
quintiles · G6 same sign and floor with delisting-carried labels removed · G7 (V2 only) same
sign in 4 of 5 volatility quintiles.

## Appendix B — V1, forward return relative to SPY, every test

| Feature | h | Mean IC | HAC t | BH q | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0002 | -0.09 | 0.9432 | -0.0012 | -0.0014 | G1, G2, G3, G4, G6 | no |
| `directional_consistency_20d` | 20 | +0.0015 | +0.67 | 0.6449 | -0.0010 | -0.0024 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_20d` | 60 | +0.0038 | +1.49 | 0.2272 | +0.0024 | +0.0024 | G1, G2, G3, G6 | no |
| `directional_consistency_60d` | 5 | +0.0045 | +2.54 | 0.0264 | +0.0045 | +0.0065 | G2, G3, G5, G6 | no |
| `directional_consistency_60d` | 20 | +0.0056 | +1.79 | 0.1368 | +0.0051 | +0.0084 | G1, G2, G3, G6 | no |
| `directional_consistency_60d` | 60 | -0.0025 | -0.64 | 0.6480 | -0.0036 | -0.0011 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_120d` | 5 | +0.0001 | +0.04 | 0.9686 | -0.0007 | +0.0031 | G1, G2, G3, G4, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0019 | -0.59 | 0.6796 | -0.0038 | -0.0012 | G1, G2, G3, G4, G6 | no |
| `directional_consistency_120d` | 60 | -0.0074 | -1.74 | 0.1471 | -0.0084 | -0.0064 | G1, G2, G3, G6 | no |
| `efficiency_20d` | 5 | -0.0011 | -0.54 | 0.7075 | -0.0014 | -0.0046 | G1, G2, G3, G5, G6 | no |
| `efficiency_20d` | 20 | -0.0024 | -0.84 | 0.5296 | -0.0049 | -0.0089 | G1, G2, G3, G6 | no |
| `efficiency_20d` | 60 | -0.0014 | -0.44 | 0.7687 | -0.0034 | -0.0045 | G1, G2, G3, G4, G6 | no |
| `efficiency_60d` | 5 | +0.0043 | +2.01 | 0.0884 | +0.0032 | +0.0049 | G2, G3, G5, G6 | no |
| `efficiency_60d` | 20 | +0.0044 | +1.22 | 0.3226 | +0.0029 | +0.0055 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_60d` | 60 | -0.0034 | -0.78 | 0.5678 | -0.0059 | -0.0018 | G1, G2, G3, G6 | no |
| `efficiency_120d` | 5 | +0.0028 | +1.35 | 0.2755 | +0.0005 | +0.0058 | G1, G2, G3, G5, G6 | no |
| `efficiency_120d` | 20 | +0.0011 | +0.36 | 0.8160 | -0.0005 | +0.0034 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0060 | -1.29 | 0.2962 | -0.0049 | +0.0012 | G1, G2, G3, G4, G6 | no |
| `positive_day_fraction_20d` | 5 | +0.0006 | +0.38 | 0.8090 | +0.0007 | -0.0018 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_20d` | 20 | -0.0030 | -1.03 | 0.4208 | -0.0036 | -0.0113 | G1, G2, G3, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0048 | +1.39 | 0.2652 | +0.0036 | -0.0058 | G1, G2, G6 | no |
| `positive_day_fraction_60d` | 5 | +0.0019 | +0.94 | 0.4733 | +0.0017 | +0.0019 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_60d` | 20 | +0.0039 | +1.08 | 0.3939 | +0.0028 | -0.0024 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_60d` | 60 | +0.0043 | +0.77 | 0.5708 | +0.0009 | -0.0058 | G1, G2, G3, G4, G6 | no |
| `positive_day_fraction_120d` | 5 | +0.0018 | +0.88 | 0.5063 | +0.0012 | +0.0052 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_120d` | 20 | +0.0013 | +0.34 | 0.8187 | -0.0002 | -0.0020 | G1, G2, G3, G4, G5, G6 | no |
| `positive_day_fraction_120d` | 60 | +0.0010 | +0.20 | 0.8933 | -0.0008 | -0.0060 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 5 | +0.0010 | +0.48 | 0.7462 | -0.0002 | -0.0060 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 20 | +0.0005 | +0.18 | 0.8988 | -0.0015 | -0.0161 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0008 | +0.24 | 0.8778 | +0.0006 | -0.0150 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_60d` | 5 | -0.0026 | -1.23 | 0.3226 | -0.0032 | -0.0030 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_60d` | 20 | -0.0024 | -0.69 | 0.6304 | -0.0049 | -0.0104 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_60d` | 60 | -0.0091 | -1.83 | 0.1269 | -0.0111 | -0.0159 | G1, G2, G3, G4, G6 | no |
| `signed_efficiency_120d` | 5 | -0.0054 | -2.59 | 0.0242 | -0.0055 | +0.0028 | G2, G6 | no |
| `signed_efficiency_120d` | 20 | -0.0082 | -2.37 | 0.0409 | -0.0108 | -0.0073 | G2, G3, G6 | no |
| `signed_efficiency_120d` | 60 | -0.0143 | -2.86 | 0.0119 | -0.0157 | -0.0132 | G3, G4 | no |
| `retained_20d` | 5 | +0.0011 | +0.53 | 0.7075 | -0.0002 | -0.0059 | G1, G2, G3, G4, G6 | no |
| `retained_20d` | 20 | +0.0003 | +0.10 | 0.9432 | -0.0019 | -0.0163 | G1, G2, G3, G4, G5, G6 | no |
| `retained_20d` | 60 | +0.0007 | +0.20 | 0.8933 | +0.0002 | -0.0152 | G1, G2, G3, G4, G6 | no |
| `retained_60d` | 5 | -0.0024 | -1.09 | 0.3912 | -0.0030 | -0.0020 | G1, G2, G3, G4, G5, G6 | no |
| `retained_60d` | 20 | -0.0021 | -0.57 | 0.6924 | -0.0049 | -0.0089 | G1, G2, G3, G4, G5, G6 | no |
| `retained_60d` | 60 | -0.0093 | -1.80 | 0.1346 | -0.0118 | -0.0173 | G1, G2, G3, G4, G6 | no |
| `retained_120d` | 5 | -0.0062 | -2.81 | 0.0136 | -0.0060 | +0.0021 | G2, G6 | no |
| `retained_120d` | 20 | -0.0080 | -2.23 | 0.0565 | -0.0107 | -0.0065 | G2, G3, G6 | no |
| `retained_120d` | 60 | -0.0138 | -2.82 | 0.0133 | -0.0156 | -0.0106 | G3 | no |
| `distance_to_high_20d` | 5 | +0.0010 | +0.40 | 0.7908 | +0.0015 | -0.0066 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 20 | +0.0009 | +0.33 | 0.8208 | +0.0018 | -0.0119 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_20d` | 60 | +0.0036 | +1.37 | 0.2749 | +0.0030 | -0.0144 | G1, G2, G6 | no |
| `distance_to_high_60d` | 5 | -0.0003 | -0.12 | 0.9369 | +0.0012 | -0.0054 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_60d` | 20 | -0.0004 | -0.14 | 0.9257 | -0.0002 | -0.0142 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_60d` | 60 | +0.0038 | +0.97 | 0.4578 | +0.0029 | -0.0163 | G1, G2, G3, G4, G6 | no |
| `distance_to_high_120d` | 5 | -0.0005 | -0.23 | 0.8778 | +0.0012 | -0.0013 | G1, G2, G3, G4, G5, G6 | no |
| `distance_to_high_120d` | 20 | +0.0021 | +0.64 | 0.6480 | +0.0009 | -0.0103 | G1, G2, G3, G4, G6 | no |
| `distance_to_high_120d` | 60 | +0.0083 | +1.89 | 0.1156 | +0.0053 | -0.0136 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_20d` | 5 | +0.0030 | +1.31 | 0.2915 | +0.0041 | -0.0007 | G1, G2, G3, G5, G6 | no |
| `max_drawdown_20d` | 20 | +0.0036 | +1.17 | 0.3480 | +0.0021 | -0.0114 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_20d` | 60 | +0.0072 | +1.77 | 0.1404 | +0.0049 | -0.0146 | G1, G2, G6 | no |
| `max_drawdown_60d` | 5 | +0.0001 | +0.04 | 0.9686 | +0.0029 | +0.0005 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_60d` | 20 | +0.0051 | +1.46 | 0.2369 | +0.0038 | -0.0075 | G1, G2, G3, G4, G6 | no |
| `max_drawdown_60d` | 60 | +0.0023 | +0.54 | 0.7075 | +0.0003 | -0.0164 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_120d` | 5 | -0.0007 | -0.31 | 0.8300 | +0.0018 | +0.0032 | G1, G2, G3, G4, G5, G6 | no |
| `max_drawdown_120d` | 20 | +0.0015 | +0.44 | 0.7687 | -0.0008 | -0.0065 | G1, G2, G3, G6 | no |
| `max_drawdown_120d` | 60 | +0.0045 | +0.90 | 0.4928 | +0.0006 | -0.0124 | G1, G2, G3, G6 | no |
| `sessions_since_high_20d` | 5 | +0.0028 | +1.55 | 0.2088 | +0.0030 | +0.0072 | G1, G2, G3, G4, G5, G6 | no |
| `sessions_since_high_20d` | 20 | +0.0045 | +1.85 | 0.1219 | +0.0043 | +0.0142 | G1, G2, G3, G6 | no |
| `sessions_since_high_20d` | 60 | +0.0037 | +1.49 | 0.2272 | +0.0047 | +0.0126 | G1, G2, G3, G4, G6 | no |
| `sessions_since_high_60d` | 5 | +0.0048 | +2.75 | 0.0160 | +0.0055 | +0.0064 | G2, G3, G6 | no |
| `sessions_since_high_60d` | 20 | +0.0082 | +2.72 | 0.0170 | +0.0099 | +0.0152 | G2, G3, G6 | no |
| `sessions_since_high_60d` | 60 | +0.0084 | +2.28 | 0.0506 | +0.0104 | +0.0159 | G2, G3, G4, G6 | no |
| `sessions_since_high_120d` | 5 | +0.0029 | +1.59 | 0.1945 | +0.0036 | -0.0020 | G1, G2, G3, G6 | no |
| `sessions_since_high_120d` | 20 | +0.0019 | +0.64 | 0.6480 | +0.0037 | +0.0052 | G1, G2, G3, G4, G6 | no |
| `sessions_since_high_120d` | 60 | +0.0010 | +0.27 | 0.8559 | +0.0022 | +0.0049 | G1, G2, G3, G4, G5, G6 | no |

## Appendix C — V1, forward maximum drawdown, every test

| Feature | h | Mean IC | HAC t | BH q | Momentum only | Raw | Gates failed | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `directional_consistency_20d` | 5 | -0.0043 | -2.50 | 0.0295 | +0.0168 | +0.0043 | G2, G4, G5, G6 | no |
| `directional_consistency_20d` | 20 | -0.0082 | -3.95 | 0.0003 | +0.0205 | +0.0038 | G2, G6 | no |
| `directional_consistency_20d` | 60 | -0.0096 | -4.03 | 0.0003 | +0.0222 | +0.0013 | G2, G3, G6 | no |
| `directional_consistency_60d` | 5 | -0.0107 | -5.37 | 0.0000 | +0.0150 | +0.0071 | G5 | no |
| `directional_consistency_60d` | 20 | -0.0169 | -5.52 | 0.0000 | +0.0184 | +0.0056 | G5 | no |
| `directional_consistency_60d` | 60 | -0.0249 | -5.97 | 0.0000 | +0.0134 | -0.0053 | G5 | no |
| `directional_consistency_120d` | 5 | -0.0099 | -4.39 | 0.0000 | +0.0114 | +0.0051 | G2, G5, G6 | no |
| `directional_consistency_120d` | 20 | -0.0181 | -5.15 | 0.0000 | +0.0107 | -0.0007 | G5 | no |
| `directional_consistency_120d` | 60 | -0.0246 | -5.20 | 0.0000 | +0.0081 | -0.0068 | G5 | no |
| `efficiency_20d` | 5 | +0.0190 | +9.06 | 0.0000 | +0.0520 | +0.0064 | — | yes |
| `efficiency_20d` | 20 | +0.0160 | +5.29 | 0.0000 | +0.0592 | -0.0002 | — | yes |
| `efficiency_20d` | 60 | +0.0056 | +1.70 | 0.1593 | +0.0507 | -0.0144 | G1, G2, G3, G6 | no |
| `efficiency_60d` | 5 | +0.0130 | +4.75 | 0.0000 | +0.0468 | -0.0035 | — | yes |
| `efficiency_60d` | 20 | +0.0096 | +2.23 | 0.0565 | +0.0549 | -0.0146 | G2, G6 | no |
| `efficiency_60d` | 60 | -0.0064 | -1.40 | 0.2652 | +0.0414 | -0.0362 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 5 | +0.0064 | +1.99 | 0.0917 | +0.0441 | -0.0168 | G2, G3, G6 | no |
| `efficiency_120d` | 20 | -0.0018 | -0.34 | 0.8187 | +0.0488 | -0.0370 | G1, G2, G3, G4, G5, G6 | no |
| `efficiency_120d` | 60 | -0.0145 | -2.07 | 0.0810 | +0.0407 | -0.0524 | G3, G5 | no |
| `positive_day_fraction_20d` | 5 | +0.0099 | +5.00 | 0.0000 | +0.0287 | +0.0490 | G2, G6 | no |
| `positive_day_fraction_20d` | 20 | +0.0087 | +3.12 | 0.0052 | +0.0338 | +0.0571 | G2, G3, G6 | no |
| `positive_day_fraction_20d` | 60 | +0.0113 | +3.72 | 0.0006 | +0.0384 | +0.0536 | — | yes |
| `positive_day_fraction_60d` | 5 | +0.0125 | +5.80 | 0.0000 | +0.0412 | +0.0664 | — | yes |
| `positive_day_fraction_60d` | 20 | +0.0145 | +4.31 | 0.0000 | +0.0536 | +0.0839 | — | yes |
| `positive_day_fraction_60d` | 60 | +0.0145 | +3.17 | 0.0045 | +0.0574 | +0.0810 | — | yes |
| `positive_day_fraction_120d` | 5 | +0.0156 | +7.55 | 0.0000 | +0.0494 | +0.0765 | — | yes |
| `positive_day_fraction_120d` | 20 | +0.0190 | +5.51 | 0.0000 | +0.0656 | +0.0973 | — | yes |
| `positive_day_fraction_120d` | 60 | +0.0188 | +3.61 | 0.0009 | +0.0704 | +0.0972 | — | yes |
| `signed_efficiency_20d` | 5 | +0.0102 | +4.83 | 0.0000 | +0.0519 | +0.0581 | — | yes |
| `signed_efficiency_20d` | 20 | +0.0059 | +2.21 | 0.0580 | +0.0636 | +0.0684 | G2, G3, G6 | no |
| `signed_efficiency_20d` | 60 | +0.0043 | +1.28 | 0.2962 | +0.0678 | +0.0588 | G1, G2, G3, G6 | no |
| `signed_efficiency_60d` | 5 | +0.0056 | +2.58 | 0.0242 | +0.0768 | +0.0758 | G2, G3, G5, G6 | no |
| `signed_efficiency_60d` | 20 | +0.0044 | +1.30 | 0.2925 | +0.1027 | +0.0959 | G1, G2, G4, G5, G6 | no |
| `signed_efficiency_60d` | 60 | -0.0053 | -1.03 | 0.4208 | +0.1096 | +0.0877 | G1, G2, G3, G4, G5, G6 | no |
| `signed_efficiency_120d` | 5 | +0.0091 | +3.90 | 0.0003 | +0.0960 | +0.0882 | G2, G5, G6 | no |
| `signed_efficiency_120d` | 20 | +0.0089 | +2.39 | 0.0388 | +0.1311 | +0.1109 | G2, G4, G5, G6 | no |
| `signed_efficiency_120d` | 60 | +0.0063 | +1.36 | 0.2755 | +0.1456 | +0.1100 | G1, G2, G3, G4, G5, G6 | no |
| `retained_20d` | 5 | +0.0112 | +5.25 | 0.0000 | +0.0526 | +0.0594 | — | yes |
| `retained_20d` | 20 | +0.0070 | +2.58 | 0.0242 | +0.0644 | +0.0699 | G2, G3, G6 | no |
| `retained_20d` | 60 | +0.0055 | +1.63 | 0.1814 | +0.0686 | +0.0604 | G1, G2, G3, G6 | no |
| `retained_60d` | 5 | +0.0097 | +4.13 | 0.0000 | +0.0796 | +0.0808 | G2, G5, G6 | no |
| `retained_60d` | 20 | +0.0097 | +2.70 | 0.0180 | +0.1062 | +0.1022 | G2, G5, G6 | no |
| `retained_60d` | 60 | +0.0005 | +0.09 | 0.9432 | +0.1132 | +0.0951 | G1, G2, G3, G4, G5, G6 | no |
| `retained_120d` | 5 | +0.0172 | +5.94 | 0.0000 | +0.1009 | +0.0996 | G5 | no |
| `retained_120d` | 20 | +0.0200 | +4.29 | 0.0000 | +0.1378 | +0.1283 | G5 | no |
| `retained_120d` | 60 | +0.0194 | +3.14 | 0.0050 | +0.1534 | +0.1309 | G5 | no |
| `distance_to_high_20d` | 5 | +0.0240 | +10.42 | 0.0000 | +0.1371 | +0.1534 | — | yes |
| `distance_to_high_20d` | 20 | +0.0296 | +11.05 | 0.0000 | +0.1830 | +0.2010 | — | yes |
| `distance_to_high_20d` | 60 | +0.0319 | +11.52 | 0.0000 | +0.1970 | +0.2030 | — | yes |
| `distance_to_high_60d` | 5 | +0.0244 | +10.46 | 0.0000 | +0.1742 | +0.1797 | — | yes |
| `distance_to_high_60d` | 20 | +0.0351 | +11.67 | 0.0000 | +0.2368 | +0.2365 | — | yes |
| `distance_to_high_60d` | 60 | +0.0394 | +10.95 | 0.0000 | +0.2584 | +0.2422 | — | yes |
| `distance_to_high_120d` | 5 | +0.0379 | +16.82 | 0.0000 | +0.1936 | +0.1963 | — | yes |
| `distance_to_high_120d` | 20 | +0.0580 | +17.42 | 0.0000 | +0.2670 | +0.2603 | — | yes |
| `distance_to_high_120d` | 60 | +0.0672 | +14.48 | 0.0000 | +0.2929 | +0.2689 | — | yes |
| `max_drawdown_20d` | 5 | +0.0447 | +17.74 | 0.0000 | +0.2190 | +0.2552 | — | yes |
| `max_drawdown_20d` | 20 | +0.0513 | +14.57 | 0.0000 | +0.2860 | +0.3301 | — | yes |
| `max_drawdown_20d` | 60 | +0.0579 | +14.93 | 0.0000 | +0.3103 | +0.3450 | — | yes |
| `max_drawdown_60d` | 5 | +0.0288 | +11.56 | 0.0000 | +0.2334 | +0.2735 | — | yes |
| `max_drawdown_60d` | 20 | +0.0466 | +13.40 | 0.0000 | +0.3198 | +0.3657 | — | yes |
| `max_drawdown_60d` | 60 | +0.0503 | +12.59 | 0.0000 | +0.3453 | +0.3860 | — | yes |
| `max_drawdown_120d` | 5 | +0.0504 | +21.60 | 0.0000 | +0.2407 | +0.2842 | — | yes |
| `max_drawdown_120d` | 20 | +0.0801 | +24.03 | 0.0000 | +0.3327 | +0.3836 | — | yes |
| `max_drawdown_120d` | 60 | +0.0965 | +18.50 | 0.0000 | +0.3654 | +0.4137 | — | yes |
| `sessions_since_high_20d` | 5 | -0.0037 | -2.04 | 0.0846 | -0.0201 | -0.0411 | G2, G3, G5, G6 | no |
| `sessions_since_high_20d` | 20 | -0.0049 | -2.21 | 0.0576 | -0.0281 | -0.0513 | G2, G3, G6 | no |
| `sessions_since_high_20d` | 60 | -0.0032 | -1.33 | 0.2823 | -0.0277 | -0.0436 | G1, G2, G3, G4, G5, G6 | no |
| `sessions_since_high_60d` | 5 | -0.0074 | -3.90 | 0.0003 | -0.0358 | -0.0573 | G2, G6 | no |
| `sessions_since_high_60d` | 20 | -0.0118 | -4.11 | 0.0000 | -0.0513 | -0.0736 | — | yes |
| `sessions_since_high_60d` | 60 | -0.0073 | -2.06 | 0.0817 | -0.0516 | -0.0674 | G2, G6 | no |
| `sessions_since_high_120d` | 5 | -0.0128 | -6.20 | 0.0000 | -0.0426 | -0.0715 | — | yes |
| `sessions_since_high_120d` | 20 | -0.0250 | -8.21 | 0.0000 | -0.0670 | -0.0956 | — | yes |
| `sessions_since_high_120d` | 60 | -0.0248 | -6.80 | 0.0000 | -0.0716 | -0.0943 | — | yes |
