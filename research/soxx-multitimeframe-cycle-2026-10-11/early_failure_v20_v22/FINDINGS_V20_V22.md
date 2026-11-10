# SOXX cycle failure: economically avoidable loss and chronological decision value (v20–v22)

**2026-10-12 ET · retrospective research, not a trading signal or accepted strategy.** Source: previously archived private SOXX/SMH/QQQ/AMD/NVDA/MU/INTC/AMAT/LRCX/KLAC/XLV/XLE regular-session Terminal 5-minute bars plus frozen 3H MACD/1H-15m entries. Original evaluation window **2025-10-09–2026-10-08**; the entire period was repeatedly inspected during prior research. Source price adjustment, known-at vintages and historical executable bid/ask are **NOT independently verified**. No BOATS overnight 20:00–04:00 SOXX history has been acquired.

## Stable experimental baseline

One eligible opportunity is the **first completed 3H negative but improving MACD(8,21,5) histogram with Stoch RSI rising and K≥D**, after negative extension >=2× previous 80-bar RMS and recent stochastic K≤20. Candidate entry at the next regular-session 15m open. Original emergency stop **1.5%** below modeled fill, partial profit **25% at +2%** if touched, fees **5 basis points each side**, and maximum **52 observed regular-session hours** with signal execution at the next 5m open. The emergency stop has precedence over discretionary exits. Same 91 eligible parent arms retained across 12 correlated assets; KLAC's seven missing 5m source intervals were excluded from any path they intersect rather than imputed.

## v20: previously computed 3-hour perfect-hindsight upper bound

Of **91 originally qualified episodes**, only **56 were alive** when a 3-RTH-hour decision was possible; **35 had already stopped or closed**. A hindsight oracle choosing each time between forced sale and continued holding could have improved return by at most **+0.542694 percentage points per original episode** at that checkpoint. This **cannot be turned into a trading rule**: the oracle knows the future and is included only as a ceiling on the benefit of additional information.

The initial v19 rule (exit if close below entry at that exact 3h check) changed the combined 91-trade average by **−0.015013 percentage points**, with broad clustered uncertainty. It did not justify installation. Six additional semiconductors had 47 trades: seven original losers improved but one previous winner sacrificed an **11.64-percentage-point** continuation; that one false positive outweighed all six new names' aggregate helped-loss savings.

## v21: six predefined intervention-time gates

v21 froze intervention at **15m, 30m, 1h, 2h, 3h or 6h** after entry. Three separate policies were compared at each time: forced sale of all remaining exposure, sale only if completed 5m close is below entry, and a predefined half-giveback rule. Any sale request acts **next observed 5m open**. Positions already stopped cannot be rescued. The oracle column is max(0, realized early-exit advantage) after observing the entire future and is **not** a tradable policy.

| Checkpoint | Positions still alive of 91 | Oracle maximum return gain per original episode | Ordinary below-entry-rule return change |
|---|---:|---:|---:|
| 0.25 RTH h | 78 | +0.8572 pp | **−0.3711 pp** |
| 0.5 RTH h | 76 | +0.8826 pp | **+0.1414 pp** |
| 1 RTH h | 65 | +0.6423 pp | −0.3278 pp |
| 2 RTH h | 60 | +0.6553 pp | −0.0802 pp |
| 3 RTH h | 56 | +0.5427 pp | −0.0150 pp |
| 6 RTH h | 34 | +0.2260 pp | −0.3461 pp |

The 30-minute below-entry version had a week-block bootstrap **[−0.2535,+0.4774] pp**; it **does not prove a positive edge**. It improved the 47 additional-semiconductor cohort **+0.2577 pp per original episode** but was negative for the ten XLV/XLE controls. Selecting the 30m checkpoint because it looked best on these same inspected observations would add selection bias.

The 3-hour oracle and eligibility results **reproduced v20 exactly**, including cohort partitions and source-path censoring.

## v22: fixed six-feature earlier-week economic prediction failed

v22 fixed a **single regularized linear regression** before evaluating it. Inputs from completed 5m bars only: price change since entry, last three 5m close momentum, highest favorable price excursion, lowest adverse excursion, closing location within the observed range and average prior-12-bar range as a price fraction. The response is **actual net incremental return of next-open exit minus continued hold**, clipped to ±10 pp **for training only**. Standardization and fitting use **strictly earlier calendar weeks**, never another asset in the same test week; ridge feature penalty is fixed at 12, with intercept unpenalized.

A model could act only after at least **20 previously observed eligible trades across 6 distinct earlier market weeks**. The policy exits if modeled remaining incremental advantage exceeds **+0.25 pp**; otherwise it holds. This is a **chronological retrospective replay**, not a pristine holdout or a live learned model.

| Forecast checkpoint | Later eligible observations | Model exits | Model economic lift versus holding | Predefined below-entry control on same observations |
|---|---:|---:|---:|---:|
| 30 minutes | 56 | 17 | **−0.1512 pp** | +0.0568 pp |
| 3 hours | 34 | 6 | **−0.1980 pp** | +0.0407 pp |

Week-block exploratory intervals for the model: 30m **[−1.0103,+0.4578] pp**, 3h **[−0.6317,+0.1052] pp**, both include zero and negative values. No learned exit is accepted. The model underperformed *holding* and the simpler fixed control despite using more causal features.

## Verification and interpretation

- v21 produced **1,638 matched policy/checkpoint/event records** (91×6×3); **1,092** separate rule-to-force accounting checks passed.
- v22 produced **182 event/checkpoint records**; **90** were forecast-eligible on later market weeks. There were **23 actual model interventions** across both predeclared times. All remaining original opportunities retained no-action status.
- Aggregated means, action thresholds, source eligibility, v20 3h parity and model test-label arithmetic were independently recomputed and verified. See `VALIDATION_V21_V22.json`.
- Conditional performance is not equivalent to portfolio returns, return on risk, fair bid/ask execution, or trading capacity. The study never validates an options contract, broker stop, partial-fill price or the 20:00–04:00 BOATS venue.

## Decision

**Do not promote a 5m-cycle exit simply because it rescues some losers.** The economically available rescue ceiling decreases quickly after the stop has already acted, and a false exit can surrender vastly more than the loss it avoids. The fixed six-feature walk-forward score did not demonstrate improvement. Preserve parent 3H-cycle state and original stop as comparators; do not select a 'best' checkpoint from this reused market year.

For genuine acceptance, an untouched future sample and coherent source/PIT vintage are needed, then separately a BOATS 24h licensed historical source and quote marketability proof through the **existing Macro Data OS** rather than a new collector or credentials path. See the parent research [PR #1338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1338).

This folder intentionally contains no vendor raw prices or credentials.
