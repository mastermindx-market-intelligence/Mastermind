# SOXX — Beyond the 2% target
## Upper-momentum exits, delayed rollovers and partial-profit runners

**Research date:** October 9, 2026  
**Requested evaluation window:** October 9, 2025–October 8, 2026  
**Earlier comparison:** December 16, 2024–October 8, 2025  
**State:** Completed retrospective exit experiment; not a validated trading system. Regular-session observations only. BOATS data was not used.

## Executive finding

A fixed 2% target often truncated the largest recoveries in the captured SOXX sample. But simply raising that target was not uniformly helpful: a 4% target underperformed the 2% target on the common entry cohort, because some early winners subsequently stopped out.

The most useful balanced candidate from this experiment is **sell half at +2%, and manage the remaining position with a 3H upper-momentum rollover rule while keeping the original 1.5% stop**. Its common-cohort mean was **+3.42% per trade**, compared with **+1.00%** for selling everything at +2%. Its win rate was lower—**62.5% versus 75.0%**—and its measured maximum drawdown was larger—**4.48% versus 2.94%**. Thus, this is a return/risk tradeoff, not a free improvement in every metric.

The candidate's earlier-period mean remained positive after removing its best trade, unlike some automatic-breakeven variants. However, only eight recent-year and five earlier-period trades support the main comparison. The paired bootstrap interval for its incremental return includes zero. No claim of a perfect combination, a statistically established edge, or production readiness is justified.

An especially important control is that **keeping the hard stop and using a ten-session time exit without a profit target produced an even larger recent-year return** than the highlighted indicator exits. Therefore, much of the gain from lifting the 2% cap can be explained by allowing strong rebounds more time, not necessarily by identifying a top.

## 1. Data and comparison discipline

### Fixed entries and a common observable horizon

The main entry definition was not re-optimized in this exit study. It is the previous 3H extreme-context / 1H confirmed-pivot candidate. The prior report contained ten recent-year entries. This experiment compares exits lasting as long as **65 regular-session hours**, approximately ten normal daytime sessions. It requires a complete observed intraday path over that common maximum horizon for every candidate rule.

Two previous +1.899% winners were excluded because missing source bars occurred later in their maximum comparison windows: **November 5, 2025 at 10:30 a.m. ET**, and **February 2, 2026 at 9:30 a.m. ET**. All headline rows therefore use the **same eight retained entries**, not the original ten.

This is retrospective data-quality cohort selection. It is **not a tradable rule known at entry**, and it must not be used to remove inconvenient future trades in production. Missing observations were not forward-filled or invented. A shorter, rule-specific completeness sensitivity retained nine entries for several shorter-horizon rules; these results were recorded separately and were not mixed into the eight-entry headline table.

### Captured inputs

The annual data source contains 3,473 valid regular-session hourly candles from October 9, 2024 through October 8, 2026, with the earlier portion used for warmup and comparison. The 15-minute snapshot contains 1,534 retained regular-session candles after excluding October 9, 2026. Its matched recent evaluation starts August 17, 2026 after warmup and ends October 8, 2026.

The shorter data window contains only one shared completed long recovery episode under the relevant extreme/reclaim rules. It cannot establish which subhourly exit is best. The archived source is Yahoo Finance chart data; neither broker-quality historical quotes nor an independent exchange tape was available. Cached daily/hourly checks from the preceding study identified occasional source differences, so individual fills remain research estimates.

Frozen input SHA-256 digests:

- `rth_original.json`: `ce4c6ae05c29f92a3903b2148f7a0595d10baf0b226b82dec2f7b73528e34720`
- `15m_60d.json`: `f3fd82f86b6264625e1263e4f46fdae08141aceaa1f5fe8e3699c778943c0426`

The original data are retained in the complete private mini4 archive. The downloadable conversation ZIP contains source code, tests and selected evidence, not the full raw snapshots or full grid.

## 2. Entry retained from the previous study

The 3H setup uses **MACD 8/21/5** and **Stoch RSI 14/14/3/3**. It requires a negative MACD histogram whose magnitude is at least twice the RMS magnitude of its preceding 80 bars, and Stoch RSI K at or below 20 in the latest three bars. The current bar is excluded from its own reference scale. This is an RMS magnitude normalization, not a conventional centered z-score.

A single original downside episode can arm one setup, which expires after 26 observed regular-session hours. Within the setup, the 1H entry uses a confirmed local price low: below the two preceding lows, with one following bar that does not undercut it. That following candle must close before the pivot is available. RSI(14) must be improving after a reading at or below 45 near the pivot, the lower MACD histogram must improve, and Stoch K must be at or above D. The principal lower parameters are MACD 5/13/4 and Stoch RSI 7/7/3/3. Entry occurs at the next available hourly open.

This remains an earlier local entry inside a larger extreme, not a guarantee that the larger downtrend has ended. Other previously defined entry families were assessed independently. They were not silently substituted into the main result.

## 3. What was varied at exit

The exit experiment compared fixed targets at 2%, 3%, 4%, 6% and 8%; no-target time exits; conventional RSI(14) levels 60/65/70/75; Stoch RSI K levels 80/90/95; bearish K/D rollovers; positive MACD-histogram extension and contraction; confirmed price tops; and higher-timeframe upper conditions followed by a lower-timeframe rollover. Exit panels used MACD 12/26/9 or 8/21/5 and Stoch RSI 14/14/3/3.

Annual exits used 1H, 2H, 3H and 4H panels. The common recent study additionally used 15-, 30- and 45-minute panels constructed from actual 15-minute input. Maximum holds were 19.5, 32.5 and 65 observed RTH hours. Partial-profit variants sold 25% or 50% at +2%, retaining the original stop or applying delayed breakeven/ATR/profit-giveback protection.

The primary grid contained **11,844 configuration rows** and **41,594 configuration-trade records**. There were 2,668 annual and 9,176 recent configurations; supplemental runner tests added 640 configuration rows and targeted joint-rule checks. These are highly dependent scenarios, **not independent market observations**.

### First upper reading versus exhaustion

RSI at 70 identifies a traditionally overbought reading; it does not guarantee that price has topped. RSI can remain elevated during strong trends [1]. This is why the experiment separately measures an immediate upper-zone exit and a later loss-of-momentum exit.

The highlighted **3H joint-rollover rule** is precise:

1. After entry, a completed 3H candle has both **Stoch RSI K ≥80 and RSI(14) ≥65**. This arms the exit watch.
2. Subsequently, K crosses from at/above D to below D while the 3H **MACD 12/26/9 histogram is falling**.
3. Sell the remaining position at the **next recorded regular-session source-bar open**.

The upper-zone condition is latched once observed; it does not have to remain true on the exact rollover candle. A bearish histogram slope is required, not necessarily a negative histogram. Any stop or maximum holding time can end the trade earlier. A partial at +2% executes only if that price is reached; the oscillator rule can otherwise liquidate whatever quantity is still held.

## 4. Main results on identical retained entries

| Exit | Trades | Win rate | Mean net trade | Compounded return | Measured max drawdown |
|---|---:|---:|---:|---:|---:|
| Sell all at +2% | 8 | 75.0% | +1.00% | +8.22% | -2.94% |
| Sell all at +4% | 8 | 50.0% | +0.65% | +4.79% | -9.07% |
| Sell all at +8% | 8 | 50.0% | +2.64% | +21.87% | -9.07% |
| Sell all at 3H RSI(14) ≥70 | 8 | 50.0% | +4.89% | +43.12% | -9.07% |
| Sell all at 3H joint momentum rollover | 8 | 50.0% | +5.83% | +52.87% | -9.40% |
| Half at +2%; remainder at 3H joint rollover | 8 | 62.5% | +3.42% | +29.65% | -4.48% |
| Half at +2%; breakeven remainder + 3H joint rollover | 8 | 75.0% | +2.83% | +24.15% | -2.51% |

All rows retain the original **1.5% initial stop**. A stop is not a guaranteed maximum loss when the next observed opening price gaps through it. The 65-RTH-hour limit is a research ceiling, not a requirement to hold every trade that long.

Compounding assumes an unlevered, full-notional allocation to one trade at a time, reinvesting after exits and holding cash otherwise. Partial-sale proceeds remain cash until the remaining position is closed. These are not personal account returns or a recommendation to use that allocation. Cash yield, tax, dividends and actual bid/ask spread dynamics are not included.

Drawdown is computed from observed source-bar closing marks and recorded exit fills; it is **not tick-level, full intrabar, or overnight maximum drawdown**. The lower subhourly study has finer marks, but not a full-year sample.

### A higher numeric target is not enough

The 4% target reduced the win rate from 75% to 50% and the average return from +1.00% to +0.65%. Two trades that previously reached +2% stopped out before the more ambitious objective. At an 8% target, the average increased to +2.64%, but those failed recoveries remained. The benefit is asymmetric: some extended winners become much larger, while some early winners become losses.

## 5. Which exit timeframe and upper range?

Conventional RSI(14) first reaching 70, with the full position held until the next opening fill:

| Exit timeframe | Earlier-period mean | Requested-year mean | Indicator exits | Time exits | Stops |
|---|---:|---:|---:|---:|---:|
| 1H | +2.26% | +2.83% | 4 | 0 | 4 |
| 2H | +3.11% | +5.16% | 4 | 0 | 4 |
| 3H | +3.42% | +4.89% | 4 | 0 | 4 |
| 4H | +2.62% | +5.44% | 3 | 1 | 4 |

The 3H RSI-70 rule ranked best on the **earlier-period mean after removing its best trade** among the screened classic/no-protection rules. That is a transparent historical selection criterion, not an untouched validation sample: the entire strategy development process has already inspected this year.

The 4H RSI-70 row had one time-limit exit. At 4H RSI-75, three of the four surviving positions exited at the timer and only one at the actual indicator signal. Its larger average therefore cannot be described as four successful top calls.

The indicators also behave differently at the same nominally upper setting. At 3H, selling the full position on the first Stoch K≥90 averaged **+1.42%**, compared with **+4.89%** at RSI≥70 and **+5.83%** on the joint rollover. Stoch RSI is a different transformation from conventional RSI; neither threshold should be treated as interchangeable with the other. The study tested their behavior rather than assuming that all upper-zone readings mean the same thing.

Positive MACD extension followed by contraction was another plausible exit. The 3H +2-RMS/fade rule with half sold at +2% averaged **+3.39%**, close to +3.42% for the joint runner, but one surviving position used the timer. The analogous 4H rule averaged +3.97%, but had only two actual indicator exits and two timer exits. That is insufficient evidence to rank 4H as the superior top detector.

## 6. How much additional movement was captured?

These are the actual retained entry episodes, not hypothetical chart maxima. Returns are percentages of the original position's entry notional, after modeled costs.

| Entry date | All at +2% | All at 3H joint rollover | Half at +2%, remainder joint rollover | Same half-rule with breakeven protection |
|---|---:|---:|---:|---:|
| 2025-10-13 | -1.60% | -1.60% | -1.60% | -1.60% |
| 2025-10-22 | +1.90% | +9.30% | +5.60% | +5.60% |
| 2025-12-15 | -1.76% | -1.76% | -1.76% | -1.76% |
| 2026-03-31 | +1.90% | +20.27% | +11.09% | +11.09% |
| 2026-05-19 | +1.90% | +15.71% | +8.80% | +0.66% |
| 2026-06-08 | +1.90% | -1.60% | +0.15% | +0.90% |
| 2026-07-06 | +1.90% | -5.47% | -1.78% | +0.90% |
| 2026-09-15 | +1.90% | +11.77% | +6.83% | +6.83% |

The March 31 entry illustrates the potential: +1.90% under the fixed target versus +20.27% when the full position survived to the joint rollover; taking half at +2% retained +11.09% for the original position. The May and September recoveries also extended well beyond the initial target.

The July 6 entry illustrates the opposing risk: +1.90% under the fixed target became **−5.47%** for the full runner because of a subsequent opening gap. Partial profit-taking reduced the loss to −1.78%, but did not eliminate it. This is particularly important before a real overnight execution model is available.

Breakeven protection is also not uniformly beneficial. For the May 19 entry, the half-runner result fell from **+8.80% to +0.66%** because the protected remainder exited during a retracement before the later recovery. “Breakeven” refers to the price stop, not guaranteed zero net loss after costs or gaps. Stop revisions in this simulation become active only on the next source candle.

## 7. Does the balanced runner survive basic stress checks?

For half at +2%, remainder at the 3H joint rollover, original stop retained:

| Check | Result |
|---|---:|
| Requested-year mean | +3.42% |
| Mean with 15bp modeled cost per side | +3.21% |
| Mean after removing best requested-year trade | +2.32% |
| Earlier period: five trades | +1.55% mean |
| Earlier period after removing best trade | +0.93% mean |
| Incremental mean versus the same fixed-2% trades | +2.41 percentage points |
| Paired entry-month bootstrap interval for incremental mean | **−0.41 to +5.43 percentage points** |

The final row matters more than a favorable standalone confidence interval. The observed improvement is not statistically established by this small sample. Bootstrap resamples are not new trades, and the interval is not adjusted for thousands of strategy comparisons. The win-rate interval around five winners in eight trades is approximately 31%–86% even before accounting for model selection.

The half-runner with automatic breakeven protection looked better on recent-year drawdown, but its earlier mean excluding the best trade was **−0.35%**. This prevents calling breakeven an unqualified improvement. The original-stop runner showed the more consistent earlier-period average in this particular comparison.

### Chronological selection check

An expanding retrospective exit-only selection chose among 273 classic/unprotected exit variants using only trades completed before each quarterly decision, requiring at least five completed training trades and ranking by mean after removing the best trade. It carried open positions across boundaries. The aggregate result was eight trades, 50% winners, +5.13% mean and +45.55% compounded return.

This is an additional diagnostic, **not pristine out-of-sample evidence**. Entry selection, candidate construction and repeated experimentation have already used the dataset. Research on backtest overfitting explains why selecting winners from many historical trials requires more than a favorable in-sample or ordinary holdout result [3].

## 8. Control: can simply holding longer explain the gain?

With the same initial stop but **no profit target**, a 65-RTH-hour time exit returned **+7.76% per trade and +73.90% compounded** in the common recent-year cohort. It outperformed the highlighted full-position RSI and joint-rollover rules, while retaining a 50% win rate and roughly 9.07% measured drawdown.

This is not a recommendation to hold every trade for ten sessions. It is a necessary control: the indicator exits have not demonstrated that their timing adds value beyond a longer holding period in this sample. The balanced partial runner sacrificed some of that upside to reduce the observed drawdown. Its purpose is a different tradeoff, not claiming the largest numerical backtest return.

## 9. Actual 30-minute entry / slower-exit illustration

One previously identified reclaim entry occurred on **September 16, 2026 at 9:30 a.m. ET, $507.50**. It used a 30-minute trigger within the 3H recovery and an approximately 2.28% structural stop. This is a separate illustration, not the annual 1.5%-stop cohort.

For an RSI-70 exit with an additional requirement that the signal candle show at least +2% unrealized gain, the results were:

| Exit timeframe | Net result | Observed RTH hours held |
|---|---:|---:|
| 15 minutes | +2.28% | 7.0 |
| 30 minutes | +3.34% | 13.5 |
| 45 minutes | +7.33% | 19.5 |
| 1H | +7.33% | 19.5 |
| 2H | +9.42% | 21.5 |
| 3H | +9.49% | 22.5 |
| 4H | +11.77% | 30.0 |

Without the +2% signal-profit guard, the 15-minute oscillator exited almost immediately at −0.29%. A very fast oscillator could already be elevated near entry and was not necessarily measuring completion of the larger rebound. The guard only applies at the completed signal candle; the next opening execution can differ.

This single example supports testing **fast entry / slower exit**, but not ranking seven exit timeframes on one market event. A different first-pivot variant in the same recent window stopped out before the upper exits, further emphasizing entry and stop dependence. Longer real subhourly history remains necessary.

## 10. Execution assumptions, verification and provenance

The engine uses no future higher-candle values. Every indicator decision is associated with a completed candle; execution follows at the next available source-bar open. Fixed limits are conservatively filled at their limit even if an opening gap is more favorable. Stops are filled at the worse observed open if gapped through. If an already active stop and target are both touched within an unresolved bar, the stop is assumed first. This differs from some platform emulators but makes the assumption explicit. OHLC-based execution cannot recover the actual tick path [2].

A regression check caught and corrected partial-limit ordering: when a partial sell is executable at the opening price, it must be processed before a later intrabar stop. Revision 2 is the authoritative output; the previous grid is superseded. It did not alter the headline selected annual rows, but affected other scenario rows.

Verification completed:

- **29 local unit tests** passed for exit accounting, event alignment and ordering, including a red/green partial-opening regression.
- **879 actual-data fixed-exit regression cases** matched the previous engine's exit index and net return.
- **64 prefix/truncation experiments**, comparing **109,664 timestamp positions**, found the tested signal flags unchanged when future bars were withheld.
- Selected exported CSVs were read back from the remote host and byte-verified against SHA-256 receipts.

These tests validate specified implementation behavior, not investment profitability. They do not validate missing data, unobserved quotes, real liquidity, overnight stop fills or statistical generalization.

Protected Mastermind procedure pin: `326c8469a21d7f50fc9ecb1848196bf1c6e66685`. All work was restricted to research artifacts. No trades, credential changes, production deployment or repository changes were performed.

Authoritative current code and results:

- Exit engine SHA-256: `109ae1c1eeee7b455086f90ca10b3a7711346f8eb0b50fb7dcbe2769de4bf4dc`
- Corrected main grid SHA-256: `5d022bd44c55d55acda05d431d27370e1eb89de68e9f49b28116cbd6b14d40f3`
- Validation JSON SHA-256: `582d7d0831b470ec1133b144675adcfdb8b894fbbbcc525bef9d55b110b0d661`

## Conclusion and continuation boundary

The research now supports a concrete hypothesis: **use the small pivot to enter, take only partial early profits, and use the larger momentum cycle to manage the remaining position**. In the common sample, the half-at-2% / 3H-joint-rollover rule offered a more balanced outcome than either capping every trade at 2% or holding the entire position for maximum extension.

That hypothesis remains unproven. It is not the universally highest-return rule, it did not dominate on every risk measure, and its apparent incremental benefit has a wide uncertainty interval. The definitions and source snapshots should remain frozen for the pending full-session comparison. BOATS and longer true subhourly data must be validated for session boundaries, quotes, execution rights, indicator memory and comparable elapsed holding periods. No continuous or background execution is claimed.

## Primary external references

[1] Fidelity, *Relative Strength Index (RSI)*, official indicator guide. Used only for the conventional 70/30 interpretation and persistence of overbought states, not the reported SOXX returns. https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI

[2] TradingView, *Strategies — Broker emulator*, official documentation. Used for the general limitation that OHLC simulation requires intrabar assumptions; this experiment uses its own Python engine, not TradingView. https://www.tradingview.com/pine-script-docs/concepts/strategies/

[3] Bailey, Borwein, López de Prado and Zhu, *The Probability of Backtest Overfitting*, 2015, author-posted paper abstract. Used for the model-selection/overfitting warning; no PBO estimate was computed here. https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253

All numerical results are this experiment's computations on the frozen snapshots, supported by the accompanying evidence files; the external references do not substantiate those returns.