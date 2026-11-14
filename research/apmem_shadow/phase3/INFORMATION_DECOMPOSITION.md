# Information decomposition and matched-retention diagnostics

Exploratory, recorded after the original study and full factorial outputs were inspected. No new fit, threshold, indicator, input history or best-arm selection is introduced. The question is the actual informational job of each component, not whether a more complex model can claim a lower loss.

## Exact likelihood decomposition

For the registered stop/target/timeout classifier, let a=p_stop+p_target be the probability that either barrier is reached, and q=p_target/(p_stop+p_target) be the conditional upper-barrier probability. The multiclass log loss decomposes exactly into binary activity loss plus the realized-active indicator times conditional direction loss. Timeout events contribute only activity loss. Verify the numerical identity per event before interpreting the averages.

Compute this decomposition for the four unchanged chronological prediction streams on identical events. Report activity Brier/log loss, active-event conditional-direction Brier/log loss, active-event sample count, and each component's contribution to the original total log-loss improvement. Conditioning on the realized active outcome is an evaluation decomposition, never an input or a tradable look-ahead selector. A model that predicts movement/timeout well has not necessarily predicted which direction pays. A uniform 8%/5% barrier has a driftless continuous-price eventual-hit reference q=5/13 only under the ideal assumptions in FUNCTIONAL_DESIGN.md; do not assign it as an empirical equity probability.

## Exact-date, count-matched retention control

For the existing positive-relative-strength filter and the unchanged risk-classifier positive-net-payoff filter, preserve the exact number of admitted opportunities on each origin date, but randomize their identities within that date's same available parent opportunity set. Use 64 fixed seeds starting 2026111400, no optimization. Evaluate the identical next-open barrier account, costs, capital caps and unspendable-dividend convention. Retain all 64 controls, the tested arm's rank, and the fraction of opportunities in actually exchangeable dates. A one-event date with a one-event retention count has no randomization power; report that rather than counting it as a separate randomized trial. These are descriptive placebo controls after model development, not randomized market interventions or confirmatory p-values.

The relative-strength control uses the full risk-available T1/T2 union; the classifier control uses exactly the all-four-model common-event set. The randomness changes only which contemporaneous candidate is retained, not the retained count, signal date, quote, cost or future outcome. Shared capital can still make executed trades differ, which is measured rather than assumed away.

## Failure-cluster and benchmark read

Retain year/era breakdowns, gaps, stop-then-recovery cases and the largest contribution episodes. Verify the biggest long-hold contributor's native entry against the untouched gate on its actual historical prefix and independently reconcile its raw source action/price path. An outcome-selected case study is a diagnostic, not a representative sample or a signal rule. The three-largest-name removal remains explicitly selected after outcomes; a positive-skew strategy may legitimately depend on uncommon winners, but that dependence raises uncertainty about a small-sample return claim.
