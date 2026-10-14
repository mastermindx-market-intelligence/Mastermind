# V27 — false-exit information hurdle and prospective-sample feasibility

**Status: algebraic feasibility diagnostic, NOT strategy validation, prediction, or a minimum powered sample.** This memo consumes the previously published v23 *inspected-development* conditional means without rerunning or changing a single v2–v24 event or threshold. It is secondary to the frozen prospective analysis contract.

## What the observed payoff asymmetry implies

The old thirty-minute intervention-only hindsight classification found mean benefit **1.54447 percentage points** of an original position for a helpful exit, versus mean harm **10.28901 percentage points** when a winning continuation was surrendered. Those are historical conditional payoffs, not future predictions; the classification uses eventual outcomes. The sample is small, correlated and selection-sensitive.

In an **idealized fixed-payoff** action model, let \`p\` be the chance that a contemplated discretionary sale is truly beneficial (among sales the future policy elects to make). Let \`b\` be the fixed benefit of a correct sale, \`h\` the fixed harm of a wrong sale and \`c\` the additional adverse execution cost **per elected sale**, on original-position percentage-point basis:

\`expected incremental utility per sale = p*b - (1-p)*h - c\`

Strictly positive hypothetical action utility requires \`p > (h+c)/(h+b)\`, assuming \`c < b\`. **This is an intervention-conditional break-even identity, not an accuracy target for all parent entries or an admissible classifier.** It does not justify a mandatory trade when uncertainty is high.

The following deliberately simplifies the new cost to \`c = (0.75 remaining original-position fraction) * (1.00 sale/entry ratio) * adverse_bps / 100\` pp. Neither 0.75 nor 1.00 has been independently established as the actual fraction/price of future sales. Baseline fees, spread, gaps, partial/no fills, latency and rejected orders can add cost; no execution price is authenticated by this algebra.

| Hypothetical added adverse sell cost | Assumed cost per elected sale (pp) | Conditional break-even correct-sale fraction | Minimum all-correct *independent* sales for a one-sided 97.5% binomial lower bound above that fraction |
|---:|---:|---:|---:|
| 0 bp | 0.0000 | 86.9483% | 27 |
| 10 bp | 0.0750 | 87.5821% | 28 |
| 25 bp | 0.1875 | 88.5328% | 31 |
| 50 bp | 0.3750 | 90.1173% | 36 |
| 100 bp | 0.7500 | 93.2863% | 54 |

The last column is a **best-case information calculation, not a promised power or GO test**. Under fictitiously independent, identical Bernoulli interventions with all \`n\` decisions correct, the exact one-sided Clopper–Pearson lower bound is \`L = 0.025 ** (1/n)\`. For each row, the displayed \`n\` is the first integer satisfying \`L > p_break_even\`. The 0.025 tail is chosen solely to illustrate the preregistered familywise 5% across two checkpoint claims. At least one wrong sale, variable or heavy-tailed benefit/harm, unknown payoff estimation, adverse fees or dependence can invalidate this count as evidence or demand more information. These idealized assumptions are **not accepted** for Mastermind.

## The real bottleneck is SOXX decisions, not synthetic test counts

The preserved historical SOXX 3H-parent-only design yielded only about **11 original SOXX parent arms** in the inspected year; the 91-episode combined cohort includes correlated other stocks. A six-month prospective horizon therefore cannot be assumed to supply anywhere near **27 discretionary SOXX sales**, even in the optimistically all-correct hypothetical case. In fact, many valid parent entries close before the 30-minute or 3-hour checkpoint and many surviving positions should never receive an additional sale. More semiconductor symbols do not manufacture independent SOXX decisions, and repeated delay/slippage/checkpoint views reuse the same episodes.

This *does not* imply that there is a rigorous universal 27-event minimum, or that success follows from observing 27 correct sales. The actual estimand is **mean original-cohort economic delta**, not action accuracy. Regime dependence, overlapping exposure, tail losses, unequal payoffs, outcome censoring and the selected historical v23 payoffs make the binomial illustration non-confirmatory. Positive 2025–26 development statistics cannot validate a strategy after window selection.

**Operational consequence:** keep the preregistered 2026-10-14 through 2027-04-13 prospective source/entry protocol as a valuable independent observation exercise, but do not promise a powered six-month success verdict. Prioritize incumbent Macro Data OS's answer on the **earliest genuinely served historical SOXX BOATS date** and other legally available *untouched* SOXX multi-regime time windows, then qualify true candle/calendar/adjustment vintages and separately quote marketability before using any of them for frozen hold-versus-sale economics. Do not backfill or stitch unqualified sources, retune the inspected year, instantiate another data collector or buy/admit vendor access by inference.

This note makes no new vendor call or price observation. The prior v24 simulated 50-bp adverse scenario already turned the naive 30-minute strategy mean negative, but that separate historical stress result is **not** a future price/fill guarantee.

## Public source-design facts (not a provider-access claim)

Tiingo's current official BOATS REST documentation includes a **2026-07-22** example \`startDate\` for overnight historical intraday bars; Tiingo announced its retail BOATS API on **July 22, 2026**. This establishes **neither** the first stored BOATS trading day **nor** the earliest date that a licensed account actually serves historical **SOXX**. The original owner's question about earliest authenticated SOXX coverage is therefore material and must be answered from a qualified original receipt, not an example or API launch date. Sources: https://www.tiingo.com/documentation/boats and https://www.tiingo.com/blog/?p=662 .

Alpaca's official 24/5 and historical-stock-data documentation independently names \`feed=boats\` for **historical bars, quotes and trades**, subject to plan/access and actual served coverage. That is a *possible alternate licensed source requirement for the incumbent Data OS owner to assess*, not permission for a new collector, provider request, account reuse or retry of previously denied probes. Historical venue bids/asks are distinct from SIP/NBBO and actual order fills, and the oldest source-qualified SOXX night is unknown there too. Sources: https://docs.alpaca.markets/us/docs/245-trading-for-trading-api and https://docs.alpaca.markets/us/reference/stockquotes-1 .

Under the illustrative fixed 1.54447-pp benefit / 10.28901-pp harm model, one wrong sale among ten decisions leaves \`9*1.54447 - 10.28901 = +3.61122 pp\` total before added costs, but with the illustrative 0.375 pp **per sale** at 50bp leaves \`3.61122 - 10*0.375 = -0.13878 pp\`. These are **conditional hypothetical action sums**, not a 10-trade SOXX result or original-cohort mean; the calculation shows why seemingly high classification success may still lose money after adverse execution.
