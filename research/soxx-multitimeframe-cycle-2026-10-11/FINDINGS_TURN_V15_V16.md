# SOXX Multi-Timeframe Confluence Falsification: Parent Turn Versus Extra Pivot (v15/v16)

**Study date:** 2026-10-11 ET. **Status:** exploratory retrospective RTH research; **not** an accepted trading strategy, untouched holdout, true overnight backtest, or verified executable fill. The same market year was inspected repeatedly while these algorithms were developed.

## The critical denominator change

Two different experiments must **not** be compared as if they had the same opportunity universe:

- **v15**: starts from *lower-pivot-armed* opportunities after an earlier 3H dramatic histogram extension; compares ordinary lower pivot versus requiring the completed 3H momentum to be turning at the same event.
- **v16**: starts from **every original 3H dramatic-extreme episode**, whether or not any lower pivot appears; compares the first completed 3H momentum turn by itself, combined with a 15/30m pivot, and fixed delays of 1,2,4,8 observed regular-session hours. Skipped/never-triggered arms are **cash with zero opportunity return**; unresolved return paths are unknown.

The pre-outcome rule specifications, executed research scripts and aggregate ledgers reside under `turn_confluence_v15_v16/`. Original Terminal source OHLCV is retained on mini4 and never copied into this repository.

## v15: requiring 3H turn *helps within an already-pivoted 30m selection*

For the fixed 3H MACD(8,21,5) + Stoch RSI(14) histogram-extreme setup, when a completed 3H candle still has a negative but improving histogram and a rising, K≥D stochastic, and a confirmed 30m price pivot is present:

| Instrument | Initial 30m pivot signals | Both turning signals | Average net per original *30m pivot* opportunity, without 3H requirement | Average net per original *30m pivot* opportunity, with 3H requirement |
|---|---:|---:|---:|---:|
| SOXX | 8 | 5 | −0.2128% | +3.1125% |
| SMH | 7 | 4 | +0.0028% | +1.0898% |
| QQQ | 7 | 4 | +0.3471% | +1.2656% |
| AMD | 5 | 3 | −1.5340% | −0.9596% |

These values are not out-of-sample; requiring the later parent confirmation changed both entry prices and which earlier setups were skipped.

## v16: the additional lower pivot is *not* reliably valuable beyond the completed 3H turn

| Instrument | Original 3H extreme episodes | 3H turn-only eligible trades | Average net per **3H arm**: turn alone | Average net per **3H arm**: turn + 30m pivot |
|---|---:|---:|---:|---:|
| SOXX | 11 | 11 | +4.5135% | +2.2637% |
| SMH | 8 | 8 | +3.0599% | +0.9536% |
| QQQ | 7 | 7 | +0.3992% | +1.2656% |
| AMD | 8 | 8 | +7.4204% | −0.5997% |

**The 3H turn is a candidate gate; a second 30m pivot is not a demonstrated mandatory entry filter.**

SOXX parent-turn-only had 5 positive trades / 11, +4.5135% mean, and +3.2792% mean after removing its largest winner; **win probability remains uncertain**. On 16 identical parent episodes across four instruments where both approaches entered, 30m confluence changed trade returns by −0.433 percentage points on average, helped four failing trades but cut four previously winning outcomes. A week-clustered bootstrap interval was **[−4.1089, +2.4851] percentage points**; it includes zero. This is weak evidence, not a proof that lower confirmation is universally harmful.

The parent-only entry required a **completed** 3H negative-yet-rising histogram and rising Stoch K≥D, **not** a MACD crossing its absolute zero line. The subsequent position was bought at the next observed 15m regular-session opening. It does *not* use a still-open 3H candle.

## v16 explicit time-delay controls

Simply delaying the 3H turn-only entry by a fixed 1, 2, 4 or 8 *observed regular-session hours* did not systematically improve it:

| SOXX entry after completed 3H turn | Trades | Average modeled net return |
|---|---:|---:|
| No additional delay | 11 | +4.5135% |
| +1 RTH hour | 11 | +2.9408% |
| +2 RTH hours | 11 | +2.8535% |
| +4 RTH hours | 11 | +2.0035% |
| +8 RTH hours | 11 | +3.0367% |

QQQ showed some benefit at 2/4 hours, but SMH and SOXX did not; AMD had a highly variable outcome. Fixed delays are diagnostic controls, **not a strategy to optimize by taking the best-looking historical delay**.

## Implementation/quantitative verification

- **34 independently replayed parent-turn positions** matched the separate OHLC route for net return, including a stop-first versus high-first stress with zero divergent outcomes on that cohort.
- **164 aligned parent/confluence/delay episode-return pairs** passed return-difference arithmetic and entry-order chronology.
- Strict 15m→30m OHLCV parity passed previously for all **4,298 observed SOXX 30m RTH bars**.
- Studies used an identical hypothetical **1.5% initial stop, sale of 25% at +2%, five basis points fees each side**, conservative OHLC stop ordering and **52 observed regular-session hours** maximum holding. No notion of quote-executable bid/ask, unobservable intrabar tick path, SIP NBBO, past correction vintage or point-in-time availability is verified.
- Source contains public Terminal `market_local_display_epoch` timestamps; before aggregation, those were converted to aware America/New_York instants. It holds mostly stored-5m bars plus a separate live tail; source adjustments and known-at history are explicitly **not verified**.
- All four assets are correlated with common macro/AI/semiconductor shocks; calendar-week block resampling reduces the most obvious pseudo-replication but does not create independent market eras.

## Research decision

Keep three **unranked** frozen comparators for next genuinely new observations: (A) first completed 3H turn alone, (B) completed 3H turn + first confirmed 30m pivot, and (C) the original 3H extreme + 1H confirmed pivot. Compare **per-original-parent-episode** results, loss avoided versus profitable continuation sacrificed, unmatched opportunity count, entry slippage, 3H timing and raw adjusted basis. No candidate is accepted until it survives realistic execution plus new untouched sessions.

Other unresolved work: full-year actual SOXX BOATS 20:00–04:00 historical bars/quotes and license/PIT qualification through **incumbent Macro Data OS**, not another collector. See `SOXX_BOATS_ACQUISITION_CONTRACT_2026-10-11.md` and prior [Macro #8698](https://github.com/mastermindx-market-intelligence/macro/pull/8698).

Methodological reference: Bailey et al., [The Probability of Backtest Overfitting](https://escholarship.org/uc/item/4w1110bb) (2017). We do not assert CSCV-derived PBO from this small, selected cohort.
