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

## Repository census and viable integration path (2026-10-03)

The build should compose with existing owners rather than create a parallel research stack:

- **Price/PIT substrate:** `portfolio.predictions._load_panel()` already exposes the local deep + delisted breadth panel and SPY benchmark with survivorship-safe, vectorized forward grading. Reuse it.
- **Inference discipline:** `portfolio.predictions` already treats entry dates as the independent unit, thins overlapping forward windows, and uses rank IC/HAC statistics. Persistence experiments should follow that contract rather than count thousands of same-day names as independent observations.
- **Decision-time history:** `brain.signal_history` is KEEP-FIRST PIT history for what the engine actually saw. Once persistence earns price-only incremental value, attach the feature snapshot there rather than inventing another production memory ledger.
- **Outcome/calibration:** `brain.outcome_ledger`, `brain.outcomes`, shadow books, and `portfolio.predictions` already own realized grading. Do not invent a new outcome definition.
- **Group/rotation evidence:** `brain.rotation_tensor`, sector cycles, sector pulse, basket membership, and theme context already expose sector/theme leadership and breadth concepts. The next group-persistence wave should derive from those contracts; it should not create a competing market-regime plane.
- **Theme identity gap:** Mastermind has basket/theme membership and GICS sector identity, but no clearly canonical fine-grained dynamic subtheme taxonomy in this repository. Therefore v1 should test static GICS/basket cohorts first. Dynamic subtheme/network clusters should consume the Macro/theme-graph owner only after a stable PIT membership contract is available.
- **Fundamental-revision gap:** portfolio-v3 architecture names `fundamental_revisions` / `earnings_expectations` as an evidence family, but the current Mastermind census does not expose a mature historical revisions series suitable for this experiment. Treat revisions persistence as a later lane; do not synthesize it from current fundamentals.

### Build sequence

1. **Wave A — stock-level empirical harness (initiated in this PR).** `research/trend_persistence_experiment.py` reconstructs PIT features from the existing breadth panel, creates independent 5/20/60-session forward labels, reports raw IC, and residualizes candidate features against 20/60/120/252-session momentum before conditional IC. This is the first kill test.
2. **Wave B — statistical hardening.** Add sector/size/beta/vol controls where PIT-safe data exists, monotonic buckets, forward-drawdown discrimination, bootstrap/HAC uncertainty, era/regime splits, and family ablations. Pre-register advancement thresholds before looking at final-fold results.
3. **Wave C — group persistence.** Start with GICS sector + existing basket membership. Measure group RS persistence, breadth participation, member hit-rate, leader retention, and within-group dispersion. Test group-only, stock-only, additive, and interaction models. The key claim must fail if group features add no OOS information beyond member momentum.
4. **Wave D — shadow advisory integration.** Only surviving features become namespaced PIT fields in existing signal/prediction records and a dashboard/research readout. Still no sizing/gating authority.
5. **Wave E — fundamental revision persistence.** Only after a canonical PIT revisions history exists, test revision breadth, magnitude, acceleration, and duration as a separate evidence family.
6. **Wave F — candidate binding logic.** Requires a separate pre-registered experiment, transaction-cost/turnover analysis, failure-mode review, and explicit promotion. No composite score is allowed to skip these gates.

### What not to build

Do not create a second outcome ledger, second market-regime engine, second theme authority, or a monolithic opaque “persistence score” now. The viable product is a **research-tested evidence family that plugs into Mastermind's existing PIT → prediction → outcome → calibration loop**. Its first useful output is explanatory/advisory: distinguish a high-return name whose gains persist cleanly from one whose identical trailing return is mostly churn and giveback, then prove whether that distinction forecasts continuation or drawdown.
