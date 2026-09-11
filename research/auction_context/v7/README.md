# Auction context: verified integration spike, not a shipped indicator

**State:** the research adapter is built and tested offline; Terminal integration and production proof are not complete. No trading authority is granted.

## What changed in this continuation

The former final-response claims that the correction-selector and 21-day pivot study were still pending were stale. The existing GitHub research carrier, Mastermind PR #565 at head 03072cebd01f7862e6c8f8579bd2a790ed6b55c3 before this continuation, already records the completed reports and their hashes. It remains the same carrier; no replacement research PR or worker was created.

The recorded 21-day results are not a new run in this continuation. At one-bar delay and a 30-minute horizon, the recorded mean directional price return was -3.33 basis points for 311 divergent pivots, -0.41for 290 value-area reentries, and -6.34for 67 combined events. These are retrospective, overlapping, single-venue observations, not executable trade returns. Do not promote or invert them into trading rules.

This continuation adds a small TypeScript calculation adapter, `auctionContext.ts`, that **imports the existing Terminal volume-profile function unchanged**. It returns a profile zone and an optional one-minute candle-polarity volume estimate for an explicitly declared historical cutoff and analysis construction. It does not contain a new volume-profile algorithm, feed, store, cache, event queue, correction owner, or trading system.

## Executed evidence

| Test family | Observed result | Scope |
|---|---:|---|
| Strict TypeScript compilation | PASS | Node 22.16.0 / TypeScript 5.8.3 |
| Named behavior contracts |76/76| Synthetic input, data quality, timing, source and construction |
| Fixed-seed randomized scenarios |250/250;1,750 assertions| Synthetic properties, not market samples |
| Targeted mutations |12/12 detected| Intended assertions caught deliberately broken mechanics |
| Fresh portable-runner reproduction | PASS | Same source and dependency in a newly created directory |
| Local browser diagnostic | BLOCKED | Navigation returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` |
| Native research-file access this continuation | Unavailable | Mini ping worked; file/process tools returned `Not connected` |

No browser acceptance is claimed. The denied local navigation was not rerouted through another URL scheme or a disabled policy. The offline runner does not attempt a browser, network access or dependency installation.

The first behavior run exposed one malformed synthetic fixture, corrected before the accepted run. The first mutation run caught 10/12 targeted mutants; the two misses led to stronger fixtures, not weaker assertions or hidden skips. The companion archive retains those earlier receipts separately. The final code and test hashes are in `VERIFIED_RESULTS.json`.

## What the adapter can calculate

`computeAsOfAuctionContext(request, parentFeed, optionalMinuteFeed)` returns independently qualified profile and flow components. Valid parent candles can produce a usable profile even when optional one-minute flow is unavailable. The profile includes a POC price zone, representative center, value area, bin width, represented volume and POC-volume share. The flow output includes the latest signed-volume percentage and a volume-weighted rolling balance; both are explicitly candle-derived proxies.

The adapter is deliberately limited to declared true-UTC, 24/7 instruments for this research slice. Unsupported display-epoch or equity-session contracts are refused instead of silently shifted. It does not yet implement EMA/CVD histories, pivot/divergence rendering, private A/SW/R labels or an interactive Terminal card.

The existing source owner supplies provider, instrument, venue scope, price/volume units, selected-vintage identity and observation semantics. These are inputs to the adapter, not identities invented by it. Parent OHLCV must reconcile with its same-source one-minute children before flow is accepted. Minor volume roundoff is tolerated, but flow percentages use the child totals, avoiding a tolerated parent rounding error producing a percentage outside its intended bounds.

## Availability and replay contracts

The reference window ends at the last fully closed analysis interval at the requested cutoff. It does not silently slide back to the last data row. A missing trailing interval therefore cannot make an old profile look current.

`selected_historical_vintage` means causal replay on the supplied historical revision. `observed_by_cutoff` additionally requires eligible observations to have valid supplied observation clocks. Neither mode proves that the selected data is the original live feed: `claimsOriginalLiveFeed` remains false. The production data/correction owner, not this helper, must establish provenance and select a consistent vintage.

Null volume, zero volume, missing intervals, incomplete windows, unknown initial doji polarity, conflicting selected bars, mismatched sources, arithmetic overflow and a point-mass distribution have explicit non-ready states. Missing volume does not become zero, missing flow does not become neutral, and malformed parent candles are not repaired by swapping prices.

`analysisSeconds` is separate from display presentation. The profile allocation method can change when underlying candles are aggregated, so the UI cannot change a frozen analysis merely because the chart display timeframe changed. `snapshotMatchesRequest` compares the complete supplied source/vintage, cutoff, method parameters and evidence mode. It is a pure predicate for the **existing** renderer/request owner; it does not create a second stale-response coordinator. Reusing a vintage label for different data would violate the upstream contract.

## Freshly verified integration gap

Terminal commit `a4be9a3f4b51246200cb1b7c4f1d44730066a9a9` was inspected. These are source facts, not claims about a live endpoint:

- `terminal/app/api/intraday/route.ts`, blob `894b31aaf54defde517f0656599a47367b74ee2e`, internally keys the cache by provider and basis, but the normal successful minute response is constructed as `{t, tf, bars}`. Optional source fields exist in the type, yet that normal branch does not populate them. It does not carry per-bar observation/vintage clocks. Error fallbacks may return a retained cache entry. Existing authentication-before-cache and rate limiting must be preserved.
- `terminal/lib/intradayStore.ts`, blob `53a6c7f786899a00f7f01b46d12ed2138714cc3e`, has no 1m/2m/3m pre-store. Its deep-history path is for US-equity 5m/hourly data; crypto returns the live window unchanged. A long history on an hourly chart therefore does not establish deep one-minute BTC history.
- `terminal/lib/intradaySources.ts`, blob `e41fea7de70d43e7430baf2f7e34c61e83fc8fdb`, emits actual UTC epochs for crypto, but market-local display epochs for other markets. Crypto normally requests the requested aggregate, not automatically a retained child-minute series.
- `terminal/lib/drawing-engine/analytics.ts` remains blob `dd6abc4e177ff4870d2b64b927c73d7ea430e2a3`. The tested lab dependency matches this blob byte-for-byte.

Therefore the next production slice is **existing intraday owner metadata/coverage plus the actual chart/replay consumer**, not another profile engine, another API, a new database or a generic "wire the indicator" change. Use the existing permissible one-minute route/window where available, preserve the source and entitlement policy, and visibly report unavailability outside supported history. Do not synthesize minutes from coarser bars. Missing original observation clocks require honest selected-vintage replay rather than a claim of as-known-live history.

## Reproduce offline

Prerequisites: Python 3.9+, Node.js and TypeScript already installed. Recorded compiler: 5.8.3. The named mutations intentionally fail closed if a different compiler changes their exact anchors.

From this directory, supply the **existing** Terminal source file:

```bash
python3 run_verification.py \
  --terminal-source /path/to/terminal/lib/drawing-engine/analytics.ts \
  --out /path/to/new-private-verification-directory
```

The output directory must not already exist. The runner verifies the dependency Git-blob hash and adapter SHA256, copies them to a private verification layout, compiles and runs all three test families. It performs no network calls, package installation, browser navigation, product writes or deployment. On failure, inspect the result and logs before another run; do not treat a process exit as semantic success.

The downloadable archive also contains `source/terminal_analytics_pinned.ts` solely for reproducibility, with its exact existing-source hash. That fixture is not a production implementation to copy into another service. The research GitHub directory omits the dependency file intentionally: the runner accepts it from its existing Terminal owner.

## Exact next action and completion gate

Keep PR #565 as the research carrier. Review these artifacts without treating its initial records-only body or a later docs merge as product completion. In the existing Terminal/data source ownership, add truthful source/basis/coverage selection and the descriptive as-of consumer together. Preserve current estimated CVD and daily profile semantics. Verify valid, missing, stale, mismatched and corrected states in the actual chart using the established dark/light, EN/ZH and responsive browser matrix before any production acceptance.

This prototype has no calibrated forecast, probability, ranking, position size or entry verdict. The recorded negative studies remain visible. Decoding private labels is a separate research question, not a prerequisite to delivering a useful, honest descriptive workflow.
