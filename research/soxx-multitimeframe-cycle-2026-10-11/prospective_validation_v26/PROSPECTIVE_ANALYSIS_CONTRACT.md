# Prospective cycle-failure analysis contract — V26 supplement

This is a pre-outcome research specification for the existing SOXX consumer, not a collector, scheduled run, licence, model deployment or trading approval. Source/code anchor: Mastermind `524e923d12cd2aeca21e4b9303fb0392d8654288`. The original v2–v24 evidence is not altered or re-estimated.

## 1. Fixed population and comparison

Use the V26 prospective entry window **October 14, 2026–April 13, 2027, America/New_York**, then follow every entry through the complete original horizon. Do not roll the ending date forward until a desirable result appears. If this specification is not publicly committed before the entry window starts, or the dataset was already inspected, it is not a prospective test: establish a new untouched window before examining its outcomes. No capture is scheduled by this document.

Primary instrument: SOXX. Secondary transfer instruments remain the twelve-name original universe with SOXX reported separately. Other stocks and repeated checkpoint views do not manufacture additional independent SOXX time observations.

The primary comparison is two separate fixed policies, each against the original hold/risk-control benchmark: below-entry at a completed 30-minute decision and below-entry at a completed three-RTH-hour decision. They are not combined or selected after observing results. Retain the original 3H parent-turn entry, 1.5% stop, 25% partial at +2%, and 52 observed RTH-hour horizon. No indicator, threshold, delay, stop, risk normalization, new composite, or ridge model is fitted on this sample. The old year's oracle and best checkpoint are not prospective forecasts.

Every original qualifying parent episode appears once in each policy's ledger. Early stop, abstention and verified no-fill are included, not selectively removed. Recording two policies does not turn one parent into two independent trials.

## 2. Source completeness precedes the denominator

The incumbent owner must establish the complete eligible-session and warmup coverage, source versions, adjustment basis, true UTC instants, and completed-candle parent extraction. A missing source session can hide **whole entries**, not just an unknown return for a known entry. Therefore a list of observed IDs is not proof of a complete original population.

If entry-universe coverage is incomplete, `utility.summarize` may describe the supplied observed cohort but its result must not be labelled the full-population effect. No finite whole-population bound is available merely by inserting one unknown row per missing day: the missing episode count is itself unknown. Keep separate (a) verified complete parent population, (b) known episode with uncertain paired outcome, and (c) unknown entry-universe coverage.

The existing source gate owns provenance and rights; this document creates no new calendar, identity registry or collector. Macro #8698 / comment 6137771857 remains the existing BOATS owner request. Reuse the retained 53 seven-day / 67-with-warmup offline plan rather than interpreting an old prose reference to monthly chunks as a new source task. The plan is not request admission. Explicit historical columns already include volume; missing volume is not zero volume.

For BOATS, require the venue's overnight session and original historical receipts. A current quote snapshot and a live firehose are not a historical quote archive. The public Tiingo REST documentation specifies overnight OHLC and a compatibility `afterHours` parameter that does not extend the venue window. Its documentation does not establish a full year of SOXX history. Do not replace actual source coverage with the product's marketing description.

## 3. Actual estimand and execution uncertainty

For each known episode i and fixed policy h, retain baseline and intervention net returns on the **same original-position basis**, with their common entry and unchanged partial/stop controls. Primary descriptive effect:

`theta_h = sum(intervention_net_i,h - baseline_net_i) / N_original`.

Report the exact accounting bridge: loss reduction + profit increase − profit surrender − loss increase. Also show counts and magnitudes of harmed original winners and worsened original losers. Accuracy, win rate, number of stops avoided and conditional return on the remaining sold fraction do not replace theta.

Known no-action/no-fill contributes zero incremental return only with evidence that the same baseline controls and path survived. An unfilled attempt that cancelled a stop, incurred different fees, changed the holding horizon or altered later orders is not automatically equivalent to holding. Uncertain paired outcomes remain bounded or unknown; bounds include the requested stress and every affected control, not just a guessed market-sale price.

**Clarification of the older acquisition contract's phrase “exclude unknown fills”: exclude them from claims of known executable fills, never delete their original episodes from economic accounting.** This supersedes only that ambiguous treatment; it does not alter any frozen historical number.

Preserve the entire original V24 delay grid [1,2,4] five-minute bars and additional sell-slippage grid [0,10,25,50,100] bp as hypothetical diagnostics. Do not pick the best delay or lowest cost after scoring. The 25 bp scenario is a stress assumption, not an empirical spread guarantee. Entry cost, stop-gap execution, auction restrictions, available size, latency and rejected/partial orders require their own source-qualified evidence or unknown bounds. OHLC-only results remain model-price results even when their arithmetic is exact.

A paired-episode mean is **not portfolio P&L**: overlapping entries can require more capital and correlated risk than a funded portfolio permits. Do not annualize it, quote a portfolio Sharpe/drawdown, or introduce model-originated sizing. Without an accepted funded allocation path, report per-episode tail losses, worst deterioration, overlap components and source/fill limitations separately.

## 4. Causal learning and the tail objective

No learned model is a primary arm in this test. Before a later learned extension, record the feature-availability instant and when BOTH paired outcomes and their source evidence became available. A model fit may consume a label only strictly afterward. An earlier entry week alone is not sufficient. Corrections arriving later remain later vintages; they cannot rewrite what a prior decision knew.

Symmetric clipping of training labels is not economically neutral when false exits destroy rare large continuations. A **synthetic, not market-observed** example: nineteen interventions improve returns by 1.5 pp each, while one sacrifices 40 pp. True mean utility is (19×1.5−40)/20 = **−0.575 pp**. Clipping the negative training label at −10 changes the mean to **+0.925 pp**. This is an algebraic counterexample, not evidence that the old v22 model actually made those trades. Its test returns were not clipped; its negative historical result stays unchanged. Any later robust estimator must state whether it estimates true utility, a transformed utility, or a bound with explicit tail correction.

## 5. Dependence, multiplicity and stopping

The fixed-window realised effect and explicit execution envelope are the first result. An envelope of possible fills is not a sampling-confidence interval. SOXX exposure intervals can span entry weeks, and many semiconductor names can share the same rebound. Preserve complete cross-symbol time blocks, empty eligible sessions and overlapping horizons in any inferential resampling; do not resample trade rows or signals as independent Bernoulli trials.

There are two prospective checkpoint claims. Any formal directional superiority claim must use a method valid for the admitted sampling assumptions and control this two-claim family at 5% (for example, each valid one-sided bound at 97.5%). Cost and delay sensitivity tables are not additional chances to find a winning arm. Any selected secondary-instrument, regime, learned-model or stress-grid claim is exploratory unless a separate multiplicity plan was registered before its outcomes.

No repeated “stop when positive” testing is permitted. Interim checks may verify source integrity, pre-outcome decisions, missingness and operational safety; they do not promote a profitability result. At the fixed cutoff, unresolved outcomes remain unresolved; do not selectively extend only losing or winning cases. Complete the original follow-through when possible and separately report unavailable outcomes.

A stationary block bootstrap is an **approximation under weak-dependence/stationarity assumptions**, not a certificate that a six-month, regime-changing sample is sufficient. An anytime-valid heavy-tail confidence sequence also needs its paper's assumptions, such as an admitted variance/moment bound; an empirical estimate from the same small correlated sample is not that bound. Neither assumption set has been established for this project. Consequently this contract does not promise a confidence interval, minimum powered sample, or confirmatory GO merely because a routine library can print one. If the inferential assumptions cannot be defended independently, publish the complete finite-cohort effect and sensitivity as limited evidence and withhold a future-performance claim. Do not invent a forty-event rule or drop large harms to make a confidence interval narrow.

## 6. Acceptance boundaries

Source-qualified independent-time **descriptive evidence**, defensible generalisation, practical execution and trading acceptance are four distinct outcomes. A negative or indeterminate independent result is useful and must be retained. Positive synthetic tests, source publication, CI and independent code review establish none of the last three. No live signal, order, sizing, collector or scheduled acquisition is enabled.

### Primary references consulted (public documentation, not account admission)

- Tiingo, BOATS REST documentation, checked October 13, 2026: https://www.tiingo.com/documentation/boats . Historical OHLC and current snapshots are distinct; historical bars are overnight only.
- Tiingo, BOATS WebSocket documentation: https://www.tiingo.com/documentation/websockets/boats . Venue-native quote/trade updates are distinct from retrospective quote coverage.
- Politis and Romano (1994), *The Stationary Bootstrap*, JASA 89(428), 1303–1313, DOI 10.1080/01621459.1994.10476870. The publisher's abstract describes weakly dependent stationary observations; the full paper was not used for a theorem claim here.
- Wang and Ramdas, *Catoni-style confidence sequences for heavy-tailed mean estimation*, arXiv:2202.01250v6 / DOI 10.1016/j.spa.2023.05.007. The abstract specifies the variance-bound premise; no theorem or implementation is claimed to apply to this project without its conditions.
