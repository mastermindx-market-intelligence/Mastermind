# V27 — sealed-cohort economics gate (research-only)

This adds a **pure, offline paired-return consumer** to Mastermind PR #1338. It does not collect data, reconstruct market candles, manage sessions, grant data rights, fetch credentials, fit a strategy, calculate an executable broker fill, or enable trading. It imports the previously verified V26 UTC/utility/accounting code without modifying v2–v24 or V26.

## Why this is a useful, bounded prerequisite

The original development sample comprises 91 correlated parent-turn episodes, and its seemingly positive 30-minute fast exit was too sensitive to false exits and execution to establish a live rule. A new source-qualified prospective population, not another fit to the inspected year, is necessary. Before new observations arrive, **V27 now refuses to produce a finite whole-cohort score** if any of the following applies:

- Incumbent-owned historical source/provenance, research rights, adjustment/vintage, warmup, event clock, or **complete entry-universe coverage** is unqualified.
- The registered October 14, 2026–April 13, 2027 Eastern entry window is still open. Interim results may never be scored as a stopping signal.
- Any observed original episode's baseline horizon has not ended. The original 52 observed RTH hours may run beyond April 13; that horizon is supplied by the incumbent source/calendar and is **not recomputed** here.
- Any of six frozen checkpoint × next-5m-open delay arms omits, duplicates, or invents a parent episode, or asserts a different original baseline return for the same episode.
- A resolved return is not known at evaluation time, or an unresolved-fill interval fails to cover a requested adverse-slippage stress.

Empty original populations yield **NO_OBSERVED_PARENT_EPISODES**, not zero estimated profit. No SOXX episodes yields an explicit **NO_PRIMARY_EPISODES** status; semiconductor peers are not allowed to stand in for independent SOXX-time evidence.

## Fixed estimand and test grid

Each original parent episode appears exactly once, even when stopped before the checkpoint, with verified non-action, or with uncertain fill. The **same denominator** applies to every primary comparison. V27 evaluates **both** 30-minute and three-RTH-hour below-entry decisions, all pre-existing 1/2/4 next-five-minute-open delay scenarios and all pre-existing 0/10/25/50/100-bp extra adverse sell costs. That is 30 cells per reported cohort, with separate SOXX-only and all-symbol descriptive strata if SOXX exists. There is no best-arm selection, threshold search, reselection after seeing winner paths, or learned model.

The underlying V26 utility computes:

\`increment = loss reduction + profit improvement - profit surrendered - worsening losses\`

on the original-position basis, including actual fraction sold and price ratio for the additional cost. Reports retain winner harm, tail deterioration, unresolved returns and partial-fill constraints. Positive intervals from input-supplied fill bounds are **not confidence intervals**. Observed per-episode means are neither funded-portfolio P&L nor a valid forecast under unproven sampling, overlap and regime assumptions. Formal claims about the two checkpoints retain the prospective contract's familywise multiplicity requirement and the need for independently defensible inferential assumptions.

## External source truth that this code cannot establish

\`UpstreamSourceClaims\` is **caller-supplied metadata** (manifest digest, incumbent receipt reference and five explicit completeness/rights flags). The code validates its shape and refuses absent gates. It **cannot** authenticate the owner's original receipt, prove that a true SOXX parent event was detected, distinguish valid vs duplicate proprietary raw trades, prove a 52-RTH-hour calendar, prove source adjustment/PIT vintage, attest data rights, or establish historical bid/ask/size marketability. Even a fully filled fixture returns \`STRUCTURAL_ECONOMICS_ONLY\` with \`source_claims_externally_authenticated=false\`, \`execution_marketability_proven=false\`, \`inferential_confidence_claim=false\`, and \`live_trading_accepted=false\`.

Real inputs must be provided and independently qualified by the **incumbent Macro Data OS/Terminal owners**, with private licensed rows retained only under the existing archive/reader. Reuse the single Macro #8698 request at https://github.com/mastermindx-market-intelligence/macro/pull/8698#issuecomment-6137771857 . The last verified historical BOATS source still contained only AAPL/AMD historical REST receipts (zero SOXX). Previously audited nine-minute, 2,000-segment SOXX quote/trade presence is **not** a full night or a fill replay. An earlier broader RTH inventory was explicitly blocked and is not retried by this module.

## Verification performed in the isolated source workspace

\`python3 -m unittest discover -s tests -p 'test_soxx_v27_cohort_grid.py' -q\`

**32 distinct synthetic tests pass.** Two tests first failed against the initial implementation, proving it improperly permitted interim scoring and unfinished original horizons; the focused cutoff/horizon repair made both pass. Fixtures are invented SOXX/AMD returns; there are **zero new market observations**. No unchanged v2–v24 replays or previously accepted V26 suite were rerun. Source compilation passes. The existing V26 clock mutation review is reused, not repeated.

Source: \`prospective_validation_v26/cohort_v27.py\`. Tests: \`tests/test_soxx_v27_cohort_grid.py\`. A published GitHub commit and hosted CI receipt are separately required before declaring this candidate green. **The economic decision remains unaccepted** until genuinely unseen source-qualified SOXX data, whole-universe coverage, defensible fill/no-fill stress and independent performance evidence satisfy the original contract.
