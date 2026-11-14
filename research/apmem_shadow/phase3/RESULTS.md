# Functional entry, momentum and risk engine: phase 3

## Decision

A useful research framework is implemented and tested, but a reliable all-objective trading winner is NOT established. The strongest new insight is a separation of informational jobs: the conditional model improved prediction of movement versus stagnation, not favorable direction. The largest return changes came from the holding/exit contract and rare large winners, not from replacing a simple risk estimate with a more elaborate one.

Retain canonical T1/T2 as one timing representation; retain simple alternatives as controls and instrument-specific challengers. Keep EWMA alongside the newer fixed-power MEM rather than crowning the newer model. Retain the longer-hold T2/union variants as concentrated, higher-risk research candidates, not production promotions. Keep volatility and conditional-path estimates as read-only context until prospectively qualified. Do not convert lower stop frequency, lower forecast loss, or a source merge into automatic capital authority.

This is original research and implementation, not a faithful copy of the external creator's private strategy. No certified live head-to-head superiority is claimed.

## What the components must do

The objective is a favorable distribution of executable net wealth changes under the user's loss, liquidity and concentration constraints. A component must earn a specific job:

| Component | Actual job | What it cannot substitute for |
|---|---|---|
| Opportunity evidence | Explain why expected compensation is attractive versus alternatives | An oscillator or low volatility does not establish mispricing |
| Momentum representation | Detect persistent repricing or an entry-state change at a known time | More indicators do not create independent information |
| Volatility forecast | Estimate the scale and horizon of uncertain price movement | Direction, expected return, or a guaranteed loss bound |
| Conditional path model | Describe stop/target/timeout probabilities under one explicit contract | A model for a 21-session race cannot grade a 63-session trend position |
| Portfolio construction | Respect scarce cash, concentration and correlated risk | Signal quality does not make an oversized book safe |
| Execution | Capture the opportunity at attainable prices and costs | An ideal stop price is not executable through a gap |
| Exit policy | End the opportunity when its price/thesis/time contract expires | A mechanically high win rate can remove the valuable right tail |

The public institutional research reviewed supports this decomposition, not a universal secret formula. Garleanu/Pedersen jointly consider expected-return evolution, signal decay, risks/correlations and trading costs. Moskowitz/Ooi/Pedersen motivate a persistent-trend comparator. Kaminski/Lo show that stop rules can add or subtract value depending on the process and policy. Bessembinder's stock-return skew motivates checking rare-winner dependence and foregone upside. Cederburg and coauthors motivate testing the actual real-time robustness of volatility management. These are primary-source summaries/abstracts and methodological motivations; no full reproduction or access to proprietary institutional systems is claimed. Exact source links and narrower qualifications are in FUNCTIONAL_DESIGN.md.

The present panel does not contain a qualified per-event earnings-revision, valuation, catalyst or fundamental cash-flow dataset. Those mechanisms are not invented from chart patterns. The opportunity-evidence gap remains distinct from the now-tested risk and timing components.

## Scope, protocols and limitations

The stock panel was selected before payoff inspection by a fixed SHA256 ordering of identifiers within available local price-file and historical-membership coverage. Sixty-four were selected; WOR, EBAY, REZI and CTVA were quarantined for action-basis uncertainty and were not replaced. Sixty remained. Only 1,373 of 2,589 historical member identifiers had local discovery price files, so membership filtering is NOT proof of complete delisted coverage or a survivor-free universe. Membership admission stops at the recorded June 2, 2026 snapshot boundary. Current price vintages do not prove historical first availability.

Stock inputs were captured from the existing approved single-provider Tiingo EOD route. Actual distributions and ordinary split-ratio assumptions are explicit. A detailed corporate-action endpoint returned HTTP403 and was not retried or evaded. Payment dates were not fabricated. The primary simulation marks earned cash-distribution entitlements as non-interest-bearing, unspendable receivables through the account end. Ex-date-spendable and no-split-instrument sensitivities are retained; neither claims actual historical cash settlement. Nonordinary factors and unexplained adjustment discontinuities were quarantined before outcomes.

The native T1/T2 gate was replayed on observed daily prefixes at immutable Macro source, without the unavailable historical peer-washout waiver. T1 confirmation/provisional state, event date, observation date and next-open fill are separate. The fast historical tier stream was not substituted for the production gate. The last-marker projection matched the untouched gate on 63 initial real prefixes, 195 expanded real prefixes, and 100 deterministic positive prefixes (50 each T1/T2). Sixty-four synthetic prefixes also matched, but had no eligible primary states and therefore do not replace positive-case evidence. No mismatch appeared in those sampled checks of 36 decision fields.

All model preprocessing and outcome labels are chronological. The classifier uses only fully matured 21-session labels; minimum training and class counts, fixed ridge strength, fit cadence and failed-refresh abstention are enforced. The volatility model uses the already declared common positive variance target and fixed fit schedule. No individual threshold was tuned to maximize the displayed returns.

The original event study contains 11,689 overlapping family rows, 1,427 union events and 49,610 path variants. Conditional predictions cover 970 common events across four model types. The main economic run contains 95 accounts and 34 registered contrasts. Later disclosed work includes all 72 factorial cells (15 original accounts reused, 57 new), 12 persistent controls, 12 accounts on eleven correlated ETFs, and 128 date/count-matched placebos. These are highly dependent experiments, not hundreds of independent confirmations.

## Main economic results

The primary account window is January 2, 2020 through June 2, 2026. It is long/cash, unlevered, with ten slots, up to 8% new allocation per name and an 80% decision-open gross cap. The common opportunity population is held fixed for sizing comparisons. Entries use the next regular-session open, costs are five basis points per side, cash return is zero, actual gap-through-stop losses are retained, and same-bar ambiguous barriers are stop-first. Intraday sale proceeds cannot finance earlier opening purchases. Maximum drawdown is close-marked, not a continuous intraday loss bound.

| Policy | CAGR | Sharpe | Max close drawdown | Mean worst-5% day | Mean opening exposure |
|---|---|---|---|---|---|
| union | 3.83% | 0.529 | -11.57% | -1.05% | 41.02% |
| union_ewma | 4.04% | 0.651 | -8.71% | -0.89% | 36.53% |
| union_mem | 3.56% | 0.588 | -8.33% | -0.89% | 36.01% |
| union_time21 | 9.42% | 0.761 | -18.76% | -1.83% | 57.48% |
| union_stop21 | 4.70% | 0.524 | -17.05% | -1.35% | 47.60% |
| union_trail63 | 12.36% | 0.834 | -21.26% | -2.00% | 65.42% |
| union_trail63_mem | 5.86% | 0.608 | -17.41% | -1.45% | 53.84% |

The barrier contract is a 5% stop, 8% target and 21-session timeout. The time21 arm removes both barriers; stop21 retains the stop but removes the target. The trail63 arm removes BOTH fixed barriers, extends the maximum hold and uses a confirmed 20-session-low break for next-open exit. Its higher return cannot be attributed solely to a different profit target. Risk reduction also changes exposure and may remove profitable high-volatility rebounds.

The simple EWMA-sized account was competitive with, and on some economic measures better than, the new MEM-sized account. Both reduced severe daily losses on unchanged opportunities. None of the original net-return contrasts survived the full 34-comparison Holm correction. A subset of tail-loss contrasts and the price-model versus frequency-model probability improvements did survive that correction. These approximate calendar-block diagnostics preserve same-date cross-name dependence but do not eliminate current-vintage data limits, strategy-design selection or nonstationarity.

At 20bp per side, union barrier CAGR falls to 0.88%; union trailing CAGR is 10.57%. With one additional session of delay, those figures are 2.24% and 10.69%. Full cost, latency, cash, intrabar-order, no-split and exposure-control results are retained, including unfavorable cases.

## What the classifier actually learned

Let a be the probability of either barrier being reached and q be the upper-barrier probability conditional on a barrier hit. The multiclass log loss decomposes exactly into activity-versus-timeout loss plus the realized-active indicator times conditional-direction loss. This is an evaluation identity, not a look-ahead input.

| Model | Activity log loss | Direction loss on active outcomes | Total log loss |
|---|---|---|---|
| frequency | 0.537229 | 0.672500 | 1.068990 |
| interaction | 0.415512 | 0.685495 | 0.957548 |
| price | 0.426517 | 0.686539 | 0.969378 |
| risk | 0.413605 | 0.686322 | 0.956294 |

Lower is better. On these 970 common events, including 767 barrier hits, the entire improvement relative to the rolling-frequency baseline comes from predicting movement versus stagnation. The directional component is worse, offsetting some of that gain. Adding forecast-risk features to the price/tier baseline did not establish an incremental improvement after the registered statistical tests. This model must not be sold as a demonstrated favorable-direction selector merely because its aggregate loss is lower.

A useful first-principles check: for an ideal continuous driftless price martingale with eventual absorption at +8% or -5%, no fees and no jumps, the upper-hit probability is 5/13 and the lower-hit probability 8/13. More than half of such trades stop out despite zero gross expectancy. Finite timeouts, equity risk premia, gaps and costs change that reference. It is not an empirical market forecast. The lesson is to score payoff and time, not demand a cosmetically high win rate.

## Holding horizon, concentration and exposure

The exploratory full factorial lets the same entry representations use four payoff contracts and three fixed risk policies. It retains every cell rather than selecting the best configuration as proven. A notable candidate is T2 with the uncapped 63-session trailing/time contract:

| Entry-risk sizing | CAGR | Sharpe | Max close drawdown | Mean opening exposure |
|---|---|---|---|---|
| none | 13.05% | 0.873 | -23.01% | 63.09% |
| ewma | 6.67% | 0.669 | -19.72% | 52.62% |
| mem | 6.96% | 0.715 | -18.21% | 51.32% |

That is an objective tradeoff, not a universal winner. The long-hold arm is materially more exposed and can suffer much larger losses. A union-trailing static-size account matched in hindsight to the union-barrier opening exposure still earned about 7.91% annualized, versus 3.83% for the barrier account, but had a deeper drawdown. The exposure match is a diagnostic, not a deployable learned size rule or equal-downside-risk comparison.

Closed-lot cash/receivable P&L reconciles exactly to unchanged original account equity. Three names account for about 64% of union-trailing net gain; the largest name, DDD, accounts for about 36%. Removing DDD after seeing the result lowers CAGR to about 7.27%; removing the top three lowers it to about 3.84%. Those are outcome-selected fragility tests, not new investable universes.

The largest DDD episode was rechecked with the untouched native gate and independent arithmetic. Its native T2 was observable on November 10, 2020; the next-open entry was 7.38 on November 11. Its 63-session timeout exit was 49.94 on February 11, 2021. The full-path net return was 576.02%, while the shared-capital account lot earned 562.54% on committed cash after the common portfolio actions. The path first suffered approximately -6.64% adverse excursion. A fixed 5% stop therefore removes this later large winner. This is a selected explanatory case, not a reason to hold every losing stock or proof of future repeatability. A second stored price series closely agrees over the episode, but its historical first-publication provenance is not independently certified.

## Persistent opportunity and transfer tests

Simply staying in relative-strength leaders did not automatically create a superior system. Monthly relative-momentum constituents with daily MEM risk scaling earned about 5.14% annualized with Sharpe .386 and maximum drawdown around -35.52%. Daily constituent reselection increased turnover substantially; its high-cost version lost money. A fixed initial 50/50 core/tactical mixture earned about 4.37%, compared with 2.73% for core/cash, but also had a somewhat worse drawdown and adverse-tail loss. No mixture weight was optimized and the two-sleeve account can hold more names than the ten-slot primary book.

On the eleven-ETF transfer panel, the T1/T2 union risk overlay reduced drawdown, while a simple breakout20 barrier control had higher return and Sharpe at substantially greater exposure. The stock long-hold result did not transfer cleanly to ETFs. This is evidence against one universal momentum representation and one universal exit contract. The ETF forecasts were reused from phase2 without refitting; exact prepared-price hashes, date alignment and target equality were verified. Correlated ETFs are not eleven independent tests or a fully diversified portfolio.

The exact-date/count-retention placebos also challenge filter claims. The positive-relative-strength and risk-EV filters beat their median placebo in this sample, but many dates had no exchangeable alternatives and some controls matched or exceeded the tested policy. These are descriptive post-development placebos, not confirmatory randomized trials. Complete distributions and exchangeability coverage are retained.

## Implementation and actual consumer boundary

The code implements raw-action adapters, source-bound native replay, interchangeable fixed entry representations, executable barrier/exit labels, stock-specific forecasts, matured-label conditional models, a self-financing shared-capital evaluator, continuous controls, dependence-aware diagnostics, read-only context attachment, and a source-bound future-outcome grader.

The existing canonical entry assessor is called with explicit price/native inputs and defaults disabled. The adapter adds a research context without altering its buyability, verdict, score or held-position behavior. It distinguishes activity probability from conditional direction, refuses a 21-session probability for a different horizon/exit contract, checks source identity and clocks, and cannot claim ranking/sizing/trading authority. This is a demonstrated research call path, not a deployed production strategy or a complete live sector/fundamental/holdings assessment.

A deterministic prefix digest now hashes economic date/value pairs rather than pandas metadata, preventing an index-name change from falsely appearing to be a vendor revision. The failure and repair are disclosed in the qualification record; the new regression test is retained. The original failed stdout was not separately archived. True historical price revisions cause the future grader to abstain for explicit adjudication rather than rewrite the frozen record.

## Retain, hold and reject

Retain the component-separated evaluation framework, simple EWMA and MEM risk comparisons, native T1/T2 timing representation, per-instrument momentum challengers and the exact activity/direction decomposition. Hold the long-hold T2/union candidate as concentrated and riskier; do not promote it on its attractive CAGR. Reject the inference that the new risk model has already demonstrated directional alpha or that more confluence votes create independent confidence.

The next scientific obligation is opportunity evidence that can discriminate favorable direction/payoff beyond activity, without duplicating price momentum or using future fundamental vintages. Contemporary expectations revisions, identifiable catalysts and cash-flow/valuation mechanisms are examples of hypotheses, not features implemented or validated in this panel. Their eventual addition must earn incremental performance against the existing controls on their own point-in-time sources. Forward performance, portfolio covariance, broader historical-security coverage and production acceptance remain separate obligations.

All actual source release, forward-publication and test receipts are provided separately below; source acceptance never constitutes investment-performance acceptance.


## Fresh consumer and forward observation

All sixty fixed-panel instruments produced an actual current research observation from newly captured complete single-provider data through November13,2026. The immutable source-bound implementation generated360 forecast values (sixty instruments x two models x three horizons). All future outcomes are NOT_MATURED at issuance. Every actual existing-entry-assessor verdict, score and buyability field was preserved; no strong authority flag was enabled. The old conditional classifier was not laundered into a fresh fit and remained unavailable for this new observation. Current SP1500 membership, missing opportunity/sector/holdings context and production qualification are not asserted. The separate publication receipt establishes pre-outcome persistence when committed. No recurring service was installed.

One hundred twenty hermetic tests passed in the actual numerical runtime. All 29 owned Python/test files were hash-matched to GitHub scientific source df0106cf5c5717fa40c6de207643696b3e0656d7. This is source/mechanics qualification, not independent review, principal-container execution, hosted-CI acceptance or investment validation.
