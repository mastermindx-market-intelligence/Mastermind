# Commodity pivot research: known-support risk assessment

**As of October 13, 2026. Research result, not a production trading rule.**

## Decision
The nested developing/confirmed weekly-biweekly setup has now been evaluated with a single, preregistered price-structure invalidation rule. It materially reduced the worst historical losses in this fixed sample, but did not establish a general return advantage. The modest primary mean benefit reversed when the single USO March 2020 event was excluded as an influence check. The original event stays in the study; it is not silently dropped.

This is NOT the best intraday-timeframe experiment. The input is final-vintage daily OHLC from the already captured Yahoo/Tiingo pairs, with unchanged identity/rights/PIT flags. No orders, position sizing, new subscriptions, source capture, runtime repair or production strategy change occurred.

## Exact frozen rule
Population: the 346 completed low-side original events across eight source pairs and both biweekly alignments in `developing_entry_economics_20261013/event_ledger.csv`, SHA256 `7f4df4ac4514926fece6876638caad82996c5c594794f1e84a4c2c4aff64d66c`. Primary sample: Tiingo, alignment 0, 86 opportunities; 24 developing-only and 62 already confirmed.

At the original daily signal close, support is the minimum observed daily low from the beginning of that exact biweekly calendar group through the signal, inclusive. No future pivot, ATR multiple, buffer or target was optimized. The initial stop remains fixed. EARLY buys at the original next open; WAIT buys at the original post-confirmation open if confirmation occurs by the group end. Both keep the original endpoint: the close ten cash sessions after that group end.

The protected variants cancel a pending entry if support was breached in an intervening completed bar. They abstain when the actual entry open is at/below support. After entry, a later opening through support exits at that adverse opening price. An intraday touch otherwise assumes an un-slipped fill at support—an optimistic daily-bar model, not proof of executable liquidity. No entry means zero cost and contribution. All entered trades assume 0.40% round-trip cost, with the inherited 1.00% sensitivity.

## Primary outcome: all 86 original opportunities
| Policy | Entered | Mean net/event | Median net/event | Worst-decile mean | Worst net/event |
|---|---:|---:|---:|---:|---:|
| EARLY reference | 86 | 1.7710% | 2.1601% | -19.4291% | -54.8343% |
| EARLY + known support | 85 | 2.1445% | 0.0384% | -8.0564% | -11.2108% |
| WAIT reference | 81 | 1.5865% | 1.7961% | -19.3296% | -54.8343% |
| WAIT + known support | 77 | 2.0878% | 0.0000% | -7.7018% | -11.2108% |

EARLY_SUPPORT had 28 intraday stop assumptions, six opening-gap stops and one opening-price abstention. Ten reference winners became losses; no reference loser became a positive trade. Mean nominal entry-to-support distance was 6.10%. Mean holding time fell from 14.59 to 9.82 sessions, but capital recycling is not modeled. Worst exposed adverse excursion remained about -19.19%; the stop is not a universal low-risk entry guarantee.

The primary paired mean gain was **+0.3735 percentage points**, with a diagnostic two-quarter block interval **[-1.3866,+2.2243] points**. These are overlapping/correlated retrospective events, not annualized returns, a financed portfolio or a new independent holdout.

## Influence and dependence checks
| Comparison | N | EARLY mean | Protected EARLY mean | Difference |
|---|---:|---:|---:|---:|
| Primary all | 86 | 1.7710% | 2.1445% | +0.3735 pp |
| Primary nonoverlapping original windows | 78 | 2.0315% | 2.5408% | +0.5093 pp |
| Primary excluding USO March 2020, influence only | 85 | 2.4370% | 2.2428% | -0.1941 pp |
| Alternate alignment all | 87 | 1.0301% | 1.0339% | +0.0038 pp |
| Alternate nonoverlapping original windows | 81 | 1.9007% | 1.4209% | -0.4797 pp |

The common-window nonoverlap gate uses original scheduled endpoints and signal dates, not realized returns or each policy's exit time. It is a dependence sensitivity, not a portfolio simulation.

For the original USO signal on March 4, 2020 (entry March 5), the protected replay exited at the March 6 opening gap for **-6.2104% net** rather than the reference endpoint's **-54.8343%**. The intended support distance was approximately **2.7523%**; the actual price loss was **5.8104% before cost**. The stop overshoot was **3.0581 percentage points**. This directly demonstrates why a nominal stop is not a guaranteed maximum loss.

## Constituents are not interchangeable
Primary mean protected-minus-reference effects were approximately: AEM +1.6252 pp, COP +0.8087, COPX -3.5235, FCX -4.0580, GLD +1.0730, PAAS +0.2939, SLV +2.0411, USO +4.7818. Cells have only 7–13 observations. These are not instrument recommendations or optimized rules. Copper-producer pullbacks often lost recovery value under this exact unbuffered support rule.

The 24 developing-only primary opportunities remained positive in mean under both policies: EARLY_SUPPORT 2.9350%, WAIT_SUPPORT contribution 2.7319%. The paired difference does not establish which is better; both alternative calendar alignment and small effective sample require caution.

## Verification
- 18 new causal/support/stop-accounting tests and six independent accounting/dependence tests passed.
- All 692 original EARLY/WAIT returns and all 346 original EARLY maximum-adverse excursions reproduced.
- All 1,384 policy records passed independent return arithmetic and reported-bar feasibility checks.
- Across 692 corresponding cross-vendor policy comparisons: zero admission, exit-date or exit-reason disagreements. Numerical returns differ slightly with adjustment histories. This is not independent exchange-tape certification.
- Source and output hashes below identify full-precision original evidence retained on M2. No licensed raw price rows are published here.

## Reproducibility identities
Original source directory: `/Volumes/Mastermind/research/commodity_pivot_census_20261009_web/structural_risk_20261013`.

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
The requested 2h/3h/4h comparison still needs qualified commodity/venue-specific intraday histories. The original 24-request diagnostic packet remains NOT_DISPATCHED by this mission. The existing Tiingo/Data OS collector owns collection; no parallel collector or namespace bypass is created. Current research has no evidence clearing the earlier Data&Lab runtime-integrity failure, and the source workstream continues to retain rights, identity, knowledge-time and publication gates.

Publication of this report is not merge, approval, source admission, strategy selection, installation or live proof. All earlier action-scoped denials and original source-custody fences are preserved. The actual parent mission remains incomplete.

## Primary execution references
SEC/Investor.gov, Stop, Stop-Limit and Trailing Stop Orders: https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/alerts-bulletins-15
FINRA, Understanding Order Types: https://syndication.finra.org/content/understanding-order-types-can-save-time-and-money

The stop trigger is not a guaranteed execution price. A stop-limit can refuse the bad price but may fail to execute; this research does not model a stop-limit replacement.