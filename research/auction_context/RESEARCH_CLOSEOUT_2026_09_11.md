# Auction-context reconstruction: audited research closeout

Operation: `auction-context-research-closeout-20260911-sol-006`.

## Decision and capability boundary

Use the reconstructed primitives for descriptive chart context, causal replay, and research. Do not promote the tested divergence or value-area reentry combinations into entry, ranking, sizing, or exit authority. Do not automatically invert a negative finding into a new strategy. The attractive reconstructed annotations did not establish a forward trading edge in the evaluated 21-day sample.

This is a research closeout and implementation handoff, not a production release. Exact private A/SW/R, shading, and complete private-script timing remain unresolved. No proprietary code was obtained. No product source, portfolio policy, calibration, runtime lifecycle, or market ledger was changed by these experiments. A records-only merge would preserve knowledge, not install an indicator or complete a Terminal release.

## Original job

Reverse-engineer a Coinbase BTC-USDC three-minute TradingView screenshot: the profile/POC, remembered shelves, normalized flow pane and event markers. Then test the reconstruction, remove hindsight and data-quality traps, and determine which existing Mastermind surfaces should reuse the information.

The researcher must distinguish location, participation proxies and confirmed response using only information actually available at the selected decision time. The machine must receive source-consistent descriptive measurements, not unsupported claims about institutions, hidden orders, actual aggressor volume or liquidations. The longer-term value is trusted research and an evaluable event dataset, not another trading/control engine.

## Leading reconstruction

The histogram is consistent with one-minute candle-polarity volume inside each displayed three-minute candle: `100 * sum(signed_volume) / sum(volume)`. Direction is close minus open; a doji uses previous close and then prior direction when available. Missing intrabars and unknown polarity are not zero pressure. The fast line's candidate is EMA3; the white line's candidate is a 20-bar volume-weighted directional balance, not an unweighted average of percentages.

The reference profile uses 99 completed three-minute candles, 24 bins, volume allocated by high-low overlap, and widths rounded to a maximum of 30 chart-bar units. POC ties prefer the lower bin and value-area ties are explicit. These are strong in-sample numerical matches, not unique recovery of private source.

Price pivots use five bars left and two right, latest-on-equal plateau handling. Price higher-high/proxy-CVD lower-high and the symmetric low case define the candidate divergence. Availability is the confirmation close: nine minutes after the pivot bar opens, six minutes after that bar closes. The one-bar delayed entry adds another three minutes. This is the research candidate's contract, not proof of the private author's timing or repainting.

## Verified profile component

The existing Terminal `calculateFixedRangeVolumeProfile` was executed in isolation: 18/18 checks passed, including all 24 rounded screenshot widths, clipping, exact edges, zero range/volume, order, scaling and ties.

| Measurement | Result |
|---|---:|
| POC center | 79,467.33041666666 |
| Value-area low | 79,298.66833333333 |
| Value-area high | 79,513.32916666666 |
| Represented window volume, BTC | 476.5644041199928 |
| Approximate bin width | 30.67 |

The POC center represents a zone, not a price measured accurately to the cent. OHLCV does not uniquely identify the actual volume-at-price distribution. Rolling-window expiration and moving bin boundaries can move a POC without proving newly accepted value. Reuse the existing profile implementation; do not rebuild it.

## Twenty-one-day retrospective study

Source: Coinbase Exchange public BTC-USD one-minute candles, 2026-08-17 00:00 UTC through 2026-09-07 00:00 UTC, end exclusive. The capture contains 30,240 unique consecutive minutes, 10,080 three-minute bars, and 1,794 eligible confirmed pivots after profile warmup.

This is explicitly post-capture exploratory work, not preregistered, independent author-label replication, or prospective validation. The reference profile is finalized strictly before the pivot candle opens. A touch is the pivot extreme exceeding the corresponding value boundary. Reentry means the confirmation close is inside that frozen value area; it is not a same-candle sweep or decoded private SW label. CVD is continuous through file/day boundaries.

Group membership is available at confirmation close. Delay zero uses next-bar open at that timestamp, an optimistic zero-latency convention. Delay one waits one further three-minute bar. Horizons are 15, 30 and 60 minutes after entry. Outcomes are directional price observations, not actual executions, short borrowing, fees, fill probability, latency or capacity models. Groups overlap.

### Thirty-minute outcomes

| Group | Observed n | Mean gross, delay 0 (bp) | Mean gross, delay 1 (bp) | Delay 1 after illustrative 5 bp cost |
|---|---:|---:|---:|---:|
| All eligible pivots | 1,792 | -0.61 | -0.13 | -5.13 |
| Divergence | 311 | -3.02 | -3.33 | -8.33 |
| Value-edge touch | 737 | -0.60 | -0.36 | -5.36 |
| Value-edge reentry | 290 | -1.82 | -0.41 | -5.41 |
| Reentry plus divergence | 67 | -5.55 | -6.34 | -11.34 |

One basis point is 0.01%. Costs are sensitivity assumptions, not account fee claims. Two all-pivot outcomes and one touch outcome are right-censored at 30 minutes. All 30 tested group/horizon/delay cells have negative full-sample mean gross return. They are not 30 independent tests. Greedy non-overlap subsets do not establish independence or a strategy.

### Availability versus screenshot impression

For the same 67 combined events and delayed-entry 30-minute exits, an unavailable hindsight entry at the exact pivot extreme would show +15.55 bp mean; the proper delayed-entry return is -6.34 bp. The mean directional move from extreme to entry was +21.88 bp. Pivot extremes structurally benefit from confirmation selection and are not executable signal prices.

In 29/67 cases the frozen POC was touched after the pivot bar and through confirmation, before signal availability. Only 46/67 had that POC still ahead in the proposed direction at the delayed entry. These are range-touch observations, not fills or first-passage profits.

### Uncertainty and disjoint controls

A 6,000-draw, fixed-seed circular three-UTC-day-block bootstrap was applied without tuning features. Delay-one/30-minute exploratory 95% intervals: divergence [-7.19, +0.62] bp; combined reentry/divergence [-12.59, +0.27] bp; all reentries [-3.16, +2.02] bp. These are not multiple-testing-adjusted or proof of a large independent sample.

The disjoint non-divergent pivot control had 1,481 observations and +0.54 bp mean. The 223 non-divergent reentries averaged +1.37 bp versus -6.34 bp for the 67 divergent reentries; the difference's exploratory interval crosses zero. This is insufficient support for adding divergence, not a universal causal claim that it worsens returns. Divergence and combined-group means were negative in each weekly partition. More independent periods and forward evidence are required before predictive authority.

## Hardening and discrimination

The old version selector checked ambiguity only against its currently selected winner. Conflicting same-version records could be hidden by visiting a newer winner first. The corrected selector checks all eligible version identities before selecting the latest, rejects conflicts in every input order, keeps exact duplicates idempotent, respects observation cutoffs, validates clocks and values, and returns detached copies. Only `choose_vintage` changed. No persistence owner was added.

| Evidence | Result and scope |
|---|---|
| Terminal profile function | 18/18 isolated checks; not a browser result |
| Native correction selector | 27/27 focused checks plus unchanged-reference parity |
| Broader replay contract | 43/43, zero failures/errors/skips, native and sandbox with identical JSON hash |
| Mutation controls | 10/10 deliberately faulty mechanics caught by intended assertions, with passing controls |
| Availability/arithmetic audit | All 30 stored result cells re-calculated to matching counts and means |

The 43 cases cover parsing, doji/gaps, incomplete bars, flow reset/weighting, pivot timing/ties, prefix invariance, profile conservation/clipping/availability, retained levels, gap-versus-breach interpretation, delay/cost/censoring, target freezing and correction selection. Mutants cover future-profile leakage, unfinished parents, doji carry across gaps, wrong weighting, backdated pivots, ignored delay, future targets, unbound clocks, ignored costs and mislabeled gaps. This is offline calculation evidence, not full feed, application, entitlement, browser, forecast or deployment proof.

## Integration ruling

First destination: descriptive as-of context in the existing Terminal chart/replay. Reuse current profile, chart, source/cache, indicator and theme owners. Distinguish current versus historical distributions, approximate versus measured order flow, and each component's availability. Keep the existing estimated CVD and Macro daily profile semantics intact. No private A/SW/R emulation, liquidation quantities, probability claims or trading actions in the first slice.

Research Foundry should compare these features with simple price/intrabar baselines. Treat histogram, smoothing and cumulative balance as a related family, not three independent votes. Market Ontology can retain observed episodes, not inferred hidden participants. Do not disguise intraday events as portfolio theses to reuse a differently scoped outcome ledger.

## Immutable source and evidence

Procedure: Mastermind `068dcc1533776672844b36ffcde30fad68a4317f`, INDEX/COLD_START/RECONCILE_STATE/CLOSEOUT, compatible Skillpack1.0.1/bootstrap1. The publication branch is records-only and does not alter the protected branch or require a runtime Job.

Terminal inspection: `19c57aca3569ae938dc420b4c4860116de492208`; profile blob `dd6abc4e177ff4870d2b64b927c73d7ea430e2a3`, ChartPanel blob `4488d0170ad798611196511e20cc593863be0f5e`, intradaySources blob `e41fea7de70d43e7430baf2f7e34c61e83fc8fdb`. These are immutable inspection pins, not perpetual current-deployment claims.

| Artifact | SHA256 |
|---|---|
| Original module | `dd1e34b84aa5650cb4f8ced431c76d2289bd6b5c62fff4dff5a79fbc1afb6866` |
| Corrected module | `0c0057f0638f34092c42a0b84dda57e1a2889c8038cb1f6cd38d89e76fa7bb4a` |
| 27-case native report | `eb4f6edee70a54949d3a2fbba98238d813189c22160a18be39fb9f6cc9050536` |
| Full larger study result | `0f6725e81a66206c20a3b9b1af160f1029288043751dea77c8a0711f6157ce43` |
| Larger study script | `3454c3376f52d45aa1029fde9b6015321a5d5dbcbfd7e15e4e613ba601cd8b86` |
| Capture receipts | `e5ac29f93223622ed97ad36db2e73f85fd7d031fb671c4121a39011ef83e5c3e` |
| Capture freeze | `8b25ba594829f15c8ad3d7d4a6ad173798c6279667f64be9daaf2d7a7902d00a` |
| 43-case native/sandbox report | `73f0ff954badcd6bec883bfc1cc8899cb0ce80e72d0abf04ec7b51b452efaee4` |
| Availability audit script | `0acf45bb70929d0b3655b2a7766e8e402e7bf125af6996c720f0aabc71250818` |
| Audited event rows | `68a86a0f4ca52b4fc387605fb1d9bff8abb7846d8b6443c8cd52e96efa703030` |
| 18-case profile report | `f11b87d00b87edbf052dfe90337f4a4a46c1b331929d28349983201f31a582b3` |

Native lab: `/tmp/mmx-auction-hardening-20260910-sol-002/` on authorized Mini `37db60bd-f84d-4521-ae9e-47c575d9ba86`; results under continuation_v5/ and continuation_v6/. Research scratch is not a product worktree. The companion downloadable package preserves exact modules, executable contracts and inspected receipts; it does not embed the large raw capture. A later raw-reference export was tool-blocked and was not retried or rerouted. That optional export was not required for completed proofs.

Official method documentation: TradingView Volume Delta support (`https://www.tradingview.com/support/solutions/43000725057-volume-delta/`) and Coinbase product candles (`https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles`). These establish the method/data family, not the private indicator's source identity.

## Exact continuation

The former pending files have been recovered; do not rerun those terminal operations or redo the completed capture. Reconcile existing Terminal/data owners and current path collisions, then implement the companion descriptive as-of replay slice. Its real-source applicability, actual consumer/browser proof, exact-head review/CI and production release remain separate open gates. Unknown private labels remain a separate research question; they are not permission to invent those labels or delay a useful descriptive workflow indefinitely.
