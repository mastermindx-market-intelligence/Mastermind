# Trend Persistence Engine — empirical protocol v0

**Status:** pre-registered research protocol for PR #1155. No production authority.

## Core falsifiable claim

Conditional on vanilla trailing momentum, point-in-time path-quality and gain-retention features
contain incremental information about future continuation and/or downside path risk.

The null is important: if the added features do not improve genuinely out-of-sample prediction
after costs and factor controls, the engine stays a descriptive lens and must not become a gate.

## First experiment

Universe: the same liquid, survivorship-safe equity universe used by the existing outcome/shadow
research path. Use only observations whose price history and benchmark history existed at the
decision timestamp.

Formation features:
- baseline: 20d, 60d, 120d and 252d trailing return; existing RS where available;
- incremental: 20d/60d/120d path efficiency, positive-day fraction, gain retention,
  max/current drawdown and sessions-since-high;
- benchmark-relative 20d/60d/120d/252d return.

Forward labels, measured independently at 5d, 20d and 60d:
- forward total return and benchmark-relative return;
- continuation indicator: positive forward benchmark-relative return;
- forward maximum drawdown;
- failure indicator: drawdown breaches a pre-registered percentile threshold.

## Tests

1. Report univariate Spearman rank IC and monotonic decile curves for every feature.
2. Compare baseline momentum-only models with baseline + persistence features using walk-forward
   folds. Never tune on the final fold.
3. Report incremental rank IC, calibration/Brier score for continuation probability, and changes
   in forward-drawdown discrimination.
4. Neutralize/condition on sector, size, beta and volatility where data are available.
5. Repeat within momentum quintiles. The thesis requires discrimination among names with similar
   past returns, not merely rediscovery of momentum.
6. Run ablations by feature family. A composite is prohibited until individual families earn
   incremental information.
7. Apply realistic rebalance lag and transaction-cost assumptions before translating prediction
   into any portfolio result.

## Advancement gates

A feature family may advance from descriptive -> shadow-advisory only if its direction is stable
across walk-forward folds and at least one economically relevant horizon, with no single sector or
episode explaining the result.

Shadow-advisory -> candidate binding logic requires a separate pre-registered test and review.
No threshold in this document is permission to trade.

## Kill criteria

Kill or demote a feature family when:
- apparent edge disappears after controlling for trailing momentum;
- sign flips materially across adjacent walk-forward eras without an ex-ante regime explanation;
- performance is concentrated in a tiny number of names/themes;
- turnover/cost erases the translated edge;
- point-in-time reconstruction cannot be proven leakage-free.

## Next hierarchy experiment

Only after the stock-level baseline is measured, add group persistence:
industry/static basket first, then dynamic theme/network clusters. Compare:
(a) stock-only momentum/persistence;
(b) group persistence only;
(c) group persistence + stock selection;
(d) interaction terms.

The key falsifier for the "theme first, stock second" hypothesis is failure of group persistence to
add out-of-sample information beyond member-level momentum.

## Research integrity

Do not retrofit thresholds to anecdotes. Preserve failed hypotheses. Report missing data and
coverage explicitly. Separate FACT (replicated result), INTERPRETATION, HYPOTHESIS and SPECULATION
in every research readout.
