# Commodity pivot research: known-support risk assessment

**Research result; not a production trading rule. Original market-history cutoff: October 8, 2026.**

## Decision
A single, preregistered price-structure stop materially reduced the worst losses in the frozen nested-state sample, but did not establish a general return advantage. Removing one USO March 2020 observation as an influence check reversed the modest mean benefit. The original event remains in the actual study; it was not deleted or replaced.

This is not the requested best-intraday-timeframe test. Inputs are final-vintage daily OHLC from previously captured Yahoo/Tiingo pairs, with unchanged rights, identity and PIT-admission flags. No new trade, position sizing, subscription, vendor request, capture, runtime repair or production strategy change occurred.

## Frozen definition
The parent is `developing_entry_economics_20261013/event_ledger.csv`, SHA256 `7f4df4ac4514926fece6876638caad82996c5c594794f1e84a4c2c4aff64d66c`. Its 346 completed low-side events cover eight securities, two source vendors and two biweekly calendar alignments. Primary sample: Tiingo phase 0, 86 opportunities, of which 24 were developing-only and 62 already had both long states confirmed.

At the original daily signal close, support is the minimum daily low from the start of that exact biweekly group through the signal, inclusive. No future pivot, ATR multiplier, discretionary buffer or target was optimized. Original EARLY and WAIT entry dates and the common endpoint remain fixed: close of the tenth cash session after that group ends.

Protected policies cancel an entry if the original support was breached before entry, and abstain if the entry opening price is at/below support. After entry, a later opening through support exits at the adverse opening price. Otherwise a support touch assumes an un-slipped stop fill at that level: an optimistic daily-bar assumption, not executable-liquidity proof. No re-entry, upside target or trailing stop is used. Entered trades assume 0.40% round-trip costs; no-entry contribution and cost are zero. The inherited 1.00% cost stress is also retained.

## Primary result: same 86 original opportunities
| Policy | Entries | Mean net/event | Median | Worst-decile mean | Worst net/event |
|---|---:|---:|---:|---:|---:|
| EARLY | 86 | 1.7710% | 2.1601% | -19.4291% | -54.8343% |
| EARLY with support | 85 | 2.1445% | 0.0384% | -8.0564% | -11.2108% |
| WAIT | 81 | 1.5865% | 1.7961% | -19.3296% | -54.8343% |
| WAIT with support | 77 | 2.0878% | 0.0000% | -7.7018% | -11.2108% |

EARLY_SUPPORT recorded 28 intraday-stop assumptions, six opening-gap stops and one opening-price abstention. Ten reference winners became losses; no reference loser became a positive trade. Mean nominal entry-to-support distance was 6.10%. Mean holding duration fell from 14.59 to 9.82 sessions. Capital recycling was not modeled; these are not funded portfolio returns.

The mean protection effect was +0.3735 percentage points per original opportunity, with a descriptive two-quarter-block 95% interval of [-1.3866,+2.2243] points. Worst exposed adverse excursion still reached about -19.19%; this is not proof of precise low-risk bottom entries.

## Influence and dependency tests
| Comparison | N | EARLY | Protected EARLY | Difference |
|---|---:|---:|---:|---:|
| Primary all | 86 | 1.7710% | 2.1445% | +0.3735 pp |
| Primary nonoverlapping original windows | 78 | 2.0315% | 2.5408% | +0.5093 pp |
| Primary excluding the USO March 2020 event, influence only | 85 | 2.4370% | 2.2428% | -0.1941 pp |
| Alternate alignment all | 87 | 1.0301% | 1.0339% | +0.0038 pp |
| Alternate nonoverlapping original windows | 81 | 1.9007% | 1.4209% | -0.4797 pp |

Nonoverlap selection uses original signal dates and already-known planned endpoints, never outcomes or each policy's actual exit. It is a sensitivity check, not a portfolio backtest or a rule chosen for performance.

The original USO March 4, 2020 signal entered March 5. Protection exited at the March 6 opening gap for -6.2104% net instead of the reference endpoint's -54.8343%. Nominal support distance was 2.7523%, but actual simulated price loss was 5.8104% before costs: a 3.0581-point overshoot. A nominal stop did not bound the loss.

## Per-instrument interpretation
Protected-minus-reference mean effects, primary alignment: AEM +1.6252 pp; COP +0.8087; COPX -3.5235; FCX -4.0580; GLD +1.0730; PAAS +0.2939; SLV +2.0411; USO +4.7818. Each cell has only 7–13 opportunities. These are not per-stock strategy recommendations. The exact unbuffered setup-low rule often surrendered copper-producer recoveries.

The developing-only subset stayed positive in mean: EARLY_SUPPORT 2.9350%, WAIT_SUPPORT contribution 2.7319%, across the same 24 opportunities. Their paired difference did not establish dominance. Sparse correlated events, inspected history and alignment sensitivity remain material.

## Verification
Eighteen new risk/accounting tests and six review/dependence tests passed. All 692 original EARLY/WAIT returns and 346 original EARLY adverse-excursion values were reproduced. All 1,384 policy records passed independent return arithmetic and reported-bar feasibility checks. All 692 corresponding cross-vendor policy comparisons agreed on admission, exit date and exit reason. Returns differ slightly under vendor adjustment histories. None of these checks authenticates actual bid/ask fills or provides an untouched validation period.

Full-precision original evidence remains at `/Volumes/Mastermind/research/commodity_pivot_census_20261009_web/structural_risk_20261013`. Licensed raw price rows are not published here.

| Object | SHA256 |
|---|---|
| SPEC.md | e27591585414c00cbfb8d6ebb2dbb99644a42987a52242b7a5cc4bf637c01f55 |
| risk.py | db5d3390756317a096e0e315b1c13935c0e6b430c6265be73e695c000bb460f5 |
| review.py | 32dcdf6b46f986fee9a9ea71e9422db16ecb872542aa7e01225939b6e88432a1 |
| verification.json | cec5dfd402500fe7908225e41988cf832b71f3f6450a8ca2a6f3480c0317eb2f |
| review_receipt.json | c9bf90a3f2349365c9530003421d9147289f9e88508abe9787e20390d0c6d9aa |
| policy_summary.csv | e000aa4cb1a5f79d8e11165301b75cf93765f70856b75cf1ed89e00daa4d7f49 |
| paired_contrasts.csv | ab083cf419af8ec2b19f454d25522af1ac222ca2a748977d78390b83fe3759d3 |
| dependence_and_crisis_checks.csv | 3bf4630884074cc77e0e447f292d2c4c7460365d0eb8a35100d6a315eb2789a3 |
| primary_instruments.csv | 1c75f375d61b506a9076e45dc0261be019184b4369ce58444bc930b94d2f08fd |
| source_reproduction.csv | 7e1cfa6992783604c130e830049aeb23ce4f3c06947ea287ca7c183fe9fa01a2 |

## Unfinished consumer dependency
Qualified commodity/venue-specific intraday histories are still required for the requested 2h/3h/4h comparison. The original 24-request diagnostic packet remains NOT_DISPATCHED by this mission. The incumbent Tiingo/Data OS collector owns ingestion. Existing rights, identity, knowledge-time, actual execution and publication gates remain intact. See the companion data-dependency record for bounded adapter recovery evidence; availability is not qualification.

Publication is not approval, protected-master merge, strategy selection, installation, or live proof. All earlier action-scoped denials and source-custody fences remain preserved. The parent mission is incomplete.

## Primary execution references
SEC/Investor.gov, Stop, Stop-Limit and Trailing Stop Orders: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins-15
FINRA, Understanding Order Types: https://syndication.finra.org/content/understanding-order-types-can-save-time-and-money

Stops become market orders when triggered, and the fill price is not guaranteed. Stop-limits may not execute. The present daily-bar model does not demonstrate live order performance.