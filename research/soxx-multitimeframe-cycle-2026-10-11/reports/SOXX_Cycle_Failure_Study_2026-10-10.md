# SOXX: defining cycle failure without cutting intact recoveries

**Research date:** October 10, 2026  
**Requested evaluation period:** October 9, 2025–October 8, 2026  
**Earlier comparison period:** December 16, 2024–October 8, 2025  
**Status:** retrospective hypothesis testing; no production admission, live trading, or true overnight feed.

## Executive finding

The right design objective is to close a position when its recovery thesis no longer justifies the remaining risk, rather than mechanically selling because a fixed percentage target or an overbought reading was reached. That does not make any particular cycle-failure detector a proven improvement.

This round implemented explicit, causal definitions of failed launch, failed reclaim, absent follow-through, momentum reset, and mature swing-structure failure. It then measured both losses avoided and profits surrendered against the same-entry holding control. The main full-position test deliberately had **no fixed profit target or scheduled partial sale**. Parallel tests retained a 25% sale at +2% to compare with preceding research.

The conclusions are:

* Momentum-only weakness is too indiscriminate in this sample: it helped three losing trades but harmed two substantial winners. Across the ten full-position comparisons, it added or preserved 9.32 percentage points of trade returns while surrendering 25.58 points elsewhere.
* Strong price-and-parent-momentum confirmation usually came after the existing 1.5% emergency stop, or did not fire at all. Waiting for certainty cannot provide an earlier protective exit in those cases.
* The original local pivot associated with six of ten entries was farther below the purchase price than the fixed stop. Two other purchases were already below that pivot. This makes an entry-thesis audit necessary before interpreting every stop as proof of cycle failure.
* A young-impulse detector was also not a reliable solution. It helped two trades but cut the September recovery while its original pivot low remained intact.
* No newly tested failure rule is accepted as superior. A structured distinction between warning, trade invalidation, and parent-cycle failure is a useful research result, not a validated predictive classifier.

## 1. Define the object that can fail

Here, “cycle” is an operational recovery sequence, not a claim of a deterministic periodic market rhythm. It is the observed progression from a larger-timeframe downside extreme into a smaller-timeframe reversal, follow-through, pullback, and continuation.

Three separate boundaries are necessary:

| Boundary | Meaning | Appropriate interpretation |
|---|---|---|
| Larger 2H/3H/4H recovery context | The original selloff may be exhausting | Permission to investigate an entry, not a promise that price must rise immediately |
| Local 15/30/60-minute entry thesis | A specific pivot/reclaim should hold or improve | A local invalidation can justify exiting this position even while the larger opportunity remains possible |
| Position risk limit | The maximum planned risk is no longer acceptable | Exit or reduce under the precommitted risk rule without pretending that the larger market cycle is proven dead |

A valid large recovery context does not justify moving an existing tight stop farther away after the position deteriorates. Conversely, the fact that a tight stop is hit does not establish that the larger cycle has failed.

The useful question is: **what observation would contradict the reason for entering at this price, on this timeframe, with this risk budget?**

## 2. A proposed operational state model

The following is a research framework. The exact numerical examples tested below are not universal validated thresholds.

### Armed but unconfirmed

The larger chart has a dramatic negative MACD histogram extension and recent low Stoch RSI. A smaller chart forms a confirmed pivot. Record the pivot price, the known confirmation/reclaim level, and the indicator state when the order becomes actionable.

Remaining negative MACD is not itself failure. The relevant distinction is whether downside momentum is contracting or re-expanding. A negative histogram that is moving toward zero can be consistent with recovery; a positive histogram that is falling can be consistent with deceleration.

### Recovering

Price regains the known confirmation level, or produces meaningful positive progress, but a structurally defended higher low has not yet been established. A drop below the regained level is a warning. Persistent loss of that level, a failed reclaim, and renewed downside momentum provide stronger local-invalidation evidence.

### Established recovery

In the prototype, a higher low was not immediately promoted into the defended level. It first had to be confirmed using already completed bars, then be followed by a later closing high beyond the prior closing peak. Only then did the implementation treat that low as a defended continuation level.

This is deliberately stricter than ratcheting to every small pullback. The hypothesis is to tolerate oscillator resets while the continuation structure holds, and become more defensive when that structure fails.

### Warning versus confirmed failure

A weakening fast histogram, RSI losing its midrange, or a lower high is a warning. It is not automatically a full-position liquidation.

Evidence of failure can include loss of the entry/defended pivot; inability to regain a previously accepted breakout level; a fast momentum recovery that resets bearish while price loses that level; or adverse lack of follow-through coupled to renewed selling. Requiring more confirmation reduces false exits but delays action. The emergency stop remains active throughout.

A strong adverse break should not be held indefinitely waiting for a later confirmation candle. Confirmation is an information/risk tradeoff, not permission to exceed the position's risk limit.

## 3. Exact tested definitions

The entry rules, observation window and original emergency stop were frozen. The main local monitor used **1H MACD 5/13/4 and conventional RSI(14)**. The main larger context used **3H MACD 8/21/5**; the wider-entry cohort used the corresponding 2H/3H/4H parent profile. All higher-timeframe features were the last completed available observation.

ATR in the new failure conditions was frozen from the known entry signal. A 0.1-ATR price buffer was a fixed test choice, not an optimized volatility tolerance.

### First experiment: stronger confirmation

**Fast weakness control:** two consecutive declines in the local histogram and RSI below 45. No structure prerequisite. This is intentionally a naive control.

**Launch/pivot failure:** a completed close below the recorded local pivot minus 0.1 ATR, with the same fast weakness.

**Failed reclaim:** price first closes above the entry-confirmation high plus 0.1 ATR with RSI at least 50; it subsequently closes below that level minus 0.1 ATR for two monitored bars, with fast weakness and larger-timeframe weakness.

**Parent weakness:** the parent histogram declines twice with parent RSI below 50, or it had become positive after entry and subsequently becomes negative with parent RSI below 50.

**No ignition:** after two nominal parent-candle durations, the best closing progress is below 0.5 ATR, the latest close is at least 0.25 ATR below entry, and both fast and parent weakness are present.

**Mature structure failure:** the defended post-entry higher low is lost by more than the buffer, with fast and parent weakness.

**Structural composite:** any of the above launch, reclaim, no-ignition or mature failures. A separate sequential version required another distinct completed bar with continuing price weakness; that extra delay produced no requested-year change before the original stop/time exit.

**Momentum reset:** the fast histogram has become positive after entry, subsequently becomes negative with two declines and RSI below 45, price is below EMA10, and a relevant pivot has broken or a regained level has been lost for at least two closes.

Controls included a plain 52-RTH-hour time exit, the preceding slow 3H upper-range rollover, and the preceding finite early guard. Both full-position and 25%-partial versions were evaluated. Cycle decisions and timers execute at the next recorded open. The original hard stop and gaps remain operative.

### Second experiment: faster, phase-aware failure

This hypothesis was specified after examining the first experiment; it is not an untouched test.

A young, unestablished recovery was considered to have made an initial impulse after at least 0.5 ATR of closing-price progress, but less than 2 ATR. A loss of more than half that progress, a close below the previous two bars' lows minus the price buffer, RSI below 50, close below EMA10, and falling local histogram triggered the early-impulse failure candidate.

The broader phase rule added adverse no-ignition and a mature defended-low break accompanied by local and parent histogram deterioration. A separate version sold only half the remaining shares on initial-impulse failure and retained stronger exits for the remainder.

## 4. Full-position results: no preset profit cap

The following requested-year rows use the same ten entry opportunities, a 1.5% initial emergency stop, no scheduled partial sale, no price target, and a maximum 52 observed RTH hours followed by next-open execution. Costs are five basis points per side.

| Rule | Average net trade | Win rate | Illustrative compounded return | OHLC-route drawdown magnitude |
|---|---:|---:|---:|---:|
| Time exit only | 4.54% | 40% | 50.60% | 11.35% |
| Slow 3H rollover | 4.34% | 40% | 48.02% | 11.77% |
| Previous finite early guard plus slow exit | 5.19% | 60% | 61.33% | 6.93% |
| Fast weakness alone | 2.92% | 50% | 30.67% | 5.80% |
| Strict structural cycle failure | 4.65% | 40% | 52.25% | 11.35% |
| Momentum reset plus price evidence | 4.82% | 50% | 54.91% | 11.35% |
| Phase-aware initial/mature failure | 3.44% | 40% | 36.01% | 9.78% |

The full-position time and slow controls are intentionally different from earlier 25%- or 50%-partial results. They must not be compared as though only one failure condition changed.

Compounding assumes full unlevered hypothetical notional in each non-overlapping position and cash otherwise. It is not recommended position sizing. Drawdown uses assumed open-low-high-close intermediate values and recorded executions; it is not verified tick-level or overnight drawdown.

The fast control lowered drawdown but harmed return and cut major winners. It could represent a different risk tradeoff; it is not a demonstrated way to retain the same winners while discarding the losers.

## 5. Losses saved must be compared with profits sacrificed

Against the same full-position 52-hour time control:

| Detector | Improved trades | Harmed trades | Sum of positive trade-return differences | Sum of negative trade-return differences | Average difference per trade |
|---|---:|---:|---:|---:|---:|
| Fast weakness | 3 | 2 | 9.32 pp | 25.58 pp | -1.63 pp |
| Strict structure | 1 | 0 | 1.08 pp | 0.00 pp | +0.11 pp |
| Momentum reset with price evidence | 1 | 0 | 2.81 pp | 0.00 pp | +0.28 pp |
| Phase-aware failure | 2 | 1 | 2.82 pp | 13.83 pp | -1.10 pp |

These are sums of paired percentage-point differences across trade episodes, not portfolio returns or amounts of account capital. “Improved” and “harmed” are retrospective outcome labels used for evaluation, never inputs to the live decision.

The strict and reset detectors had fewer false exits in the requested year, but had worse earlier-period known outcomes. They do not establish a stable improvement merely because one recent trade was helped.

The parallel quarter-partial comparison is in `comparison.csv` and `failure_attribution.csv`. It reaches the same qualitative conclusion.

## 6. The September false failure

The September 15, 2026 entry was approximately **$501.83**. Its recorded original local pivot was approximately **$496.73**.

On September 16 at 3:30 p.m. ET, a completed observation had close **$499.00**, local RSI approximately **38.48**, and a negative, deteriorating fast histogram. It had also broken a smaller recent low. The young-impulse rule declared failure.

But $499.00 was still above the original $496.73 pivot. The rule had detected a failed small impulse while treating it as failure of the larger trade thesis.

In the quarter-partial comparison, that action produced **-0.68%** versus **+10.34%** for the same-entry 52-hour control. This is not proof that the next recovery could have been predicted. It is direct evidence of the cost of the false exit in that episode.

I did not remove the episode, change the threshold until it disappeared, or label the later outcome a signal available at the decision time.

## 7. Cycle failure requires a coherent entry contract

The recorded local pivot is a candidate structural invalidation level. It was not an enforced admission condition in every earlier entry rule.

The audit found:

* **Two of ten entries opened below that recorded pivot.** February 2 opened near $342.26 versus a $343.71 pivot; May 19 opened near $484.24 versus a $486.94 pivot. If holding that pivot is made a required premise, the premise must be revalidated at the actual order/fill boundary. One of these was later a large winner, so rejecting stale-pivot entries must not be advertised as a free historical improvement.
* **Six of ten pivots were more than 1.5% below the recorded entry.** For example, the June 8 pivot was roughly 5.17% below entry. The existing 1.5% stop therefore fires before a definitive break of that pivot. It is logically impossible for that particular structural break to act as the earlier exit on those paths.
* The other two were above their pivot and within 1.5% before adding a volatility buffer. Adding the tested 0.1-ATR buffer can change that relationship.

This is a mismatch among entry, structural invalidation and permitted risk—not a reason to widen stops after a position goes wrong. A fresh smaller-timeframe setup might provide closer invalidation, but the annual 15/30-minute evidence required to test it is not available here.

## 8. What a useful mature-cycle rule would protect

Consider a hypothetical entry at 100 with a valid local pivot at 99.30. Price rises to 102, pulls back to 101, then closes above 102 and extends to 104. Under the proposed structural definition, the confirmed 101 higher low can become the defended continuation level after that later closing high.

A move from 104 to 103 with a declining Stoch RSI is not, by itself, structural failure. A loss of 101, failure to regain that level, and renewed downside momentum provide materially different evidence. The trader need not wait for the original 99.30 cycle origin to break before recognizing failure of the now-established continuation structure.

This illustration is a design explanation, not a tested trade or claimed predictive edge. A precommitted risk stop can require exit earlier than structural confirmation, and market gaps can execute beyond the stop price.

## 9. Decision quality, rather than a perfect label

The ideal comparison is the expected value and risk of continuing from the current observable state versus exiting at an executable price. Symbolically, a simple two-outcome approximation is:

`continuation value = p(recovery | available evidence) × remaining upside − p(failure | available evidence) × remaining downside − incremental friction`.

This is a decision framework, not a calibrated probability model. The current ten inspected trades cannot provide credible state-by-state estimates of those probabilities. Risk constraints may require exit even when the expected return estimate remains positive.

A good classifier must measure the economic severity of false exits, not just the count of losing trades rescued. It must also be judged against a constant-risk holding control, retain unknown paths as unknown, count overlapping episodes honestly, and reserve genuine later observations for evaluation. “Cycle failed” must not be defined retrospectively as “this exit happened to save money.”

## 10. Evidence quality and scope

All main requested-year ten outcomes are observed in the accepted frozen hourly source under the vendor-session audit. One earlier runner holding path remains unresolved because of a missing early-close tail. Prior averages of known outcomes are not a complete five-trade portfolio return; comparisons can involve different known counts when a faster policy exits before the missing interval.

SMH transfer and the wider SOXX entry stream were also run unchanged. The transfer observations are correlated and not independent replications. Wider-entry endpoint censoring remains explicit. None of the tests is an untouched out-of-sample result; the first experiment follows extensive inspection of this year, and the second follows the first experiment.

Software verification:

* 32 local unit tests passed; failure-then-pass receipts are preserved for the two new modules.
* Five new source files matched the remote execution copies by SHA-256.
* 630 comparisons between the independent OHLC replay and inherited execution engine had zero return difference. These include repeated controls and are not 630 independent trades.
* 45,200 feature-prefix positions matched under truncated histories.
* 135 truncated action replays reproduced 601 available decision records.
* No live trades, authentication changes, production changes, or overnight feed were used.

SOXX source SHA-256: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`.

## 11. Deliverables and current disposition

The research implementations and their falsifiers are complete for this round. They are not accepted replacements for a trading policy. The economic evidence does not yet demonstrate a cycle-failure rule that reliably cuts the losers while preserving the same winners.

The important retained design change is to separate **warning, trade invalidation, parent-cycle failure and hard risk stop**. The next empirical requirement is to evaluate a consistent order-time entry/invalidation contract on authentic smaller-timeframe observations, rather than repeatedly optimizing the same ten trades. BOATS remains pending and no 24-hour performance is asserted.

The conversation evidence package includes selected results, exact code, tests and verification metadata. The complete original-carrier archive contains raw snapshots, all tested cohort outputs, state-by-state observations and full counterfactual ledgers.

## External methodological references

These references support indicator/execution background; they do not validate the proposed SOXX strategy.

1. Fidelity, Relative Strength Index: RSI can remain extreme in trends; trend-dependent ranges and failure swings. https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI
2. Fidelity, MACD: trend-momentum construction and whipsaws in ranges. https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd
3. TradingView Pine documentation, Repainting: last-confirmed higher-timeframe values versus changing unconfirmed observations. https://www.tradingview.com/pine-script-docs/concepts/repainting/
4. SEC Investor.gov, Stop, Stop-Limit, and Trailing Stop Orders: trigger price does not guarantee execution price; stop-limit orders can remain unfilled. https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15
5. Kaminski and Lo, When Do Stop-Loss Rules Stop Losses?, Journal of Financial Markets 18 (2014), 234–254: stop-loss value depends on the return process and risk tradeoff, not merely the existence of a stop. https://www.sciencedirect.com/science/article/pii/S138641811300030X