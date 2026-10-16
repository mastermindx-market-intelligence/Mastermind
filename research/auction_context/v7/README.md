# Auction context: tested research adapter, not a shipped indicator

**State:** the TypeScript research adapter is built and tested offline. Terminal integration, real-source acceptance, browser proof and production release remain incomplete. No trading authority is granted.

## Reconciled checkpoint

The previous final replies calling the correction-selector and 21-day study pending were stale. PR #565 already records their completed native reports and hashes. This continuation uses the same research branch, not a replacement PR or worker.

Those historical results were not rerun here. At a one-bar delay and 30-minute horizon, the recorded means were -3.33 basis points for 311 divergent pivots, -0.41 for 290 value-area reentries and -6.34 for 67 combined events. They are retrospective, overlapping, single-venue price observations, not executable returns. Do not promote or automatically invert them into trading rules. The exact private A/SW/R and shading remain unresolved.

## New executable work

`auctionContext.ts` imports the existing Terminal profile function unchanged. It does not add another profile algorithm, collector, API, store, cache, correction owner, queue or trading engine.

`computeAsOfAuctionContext(request, parentFeed, optionalMinuteFeed)` produces separately qualified profile and flow components. The profile includes POC zone and center, value area, bin width, represented volume and POC-volume share. The optional flow component reports the latest one-minute-polarity volume percentage and a volume-weighted rolling balance. These remain candle-derived estimates, not actual bid/ask trade classifications.

The existing source owner must provide matching provider, instrument, venue scope, units, selected-vintage identity and observation semantics. Parents must reconcile with their one-minute children. The research adapter supports declared true-UTC, 24/7 inputs only; it rejects display-epoch and equity-calendar contracts. It does not implement EMA/CVD history, pivots, event rendering or an interactive Terminal card.

The expected window is anchored to the requested cutoff, not the last received row. Missing trailing bars cannot make old data look current. A missing optional flow input leaves a valid profile usable. Missing volume, unknown polarity, conflicting bars, mismatched sources, unfinished intervals, zero volume and point-mass distributions remain explicit states instead of fabricated neutral readings.

`selected_historical_vintage` supports causal replay on supplied historical data. `observed_by_cutoff` also checks supplied observation clocks. Neither proves the original live feed: `claimsOriginalLiveFeed` remains false. The production data/correction owner selects revisions; this adapter refuses conflicting eligible rows rather than inventing a new selector/store.

Analysis construction is separate from display presentation. `snapshotMatchesRequest` checks the supplied immutable source/vintage selection, cutoff, cadence, all construction parameters and evidence mode. It is a predicate for the existing renderer/request owner, not a new concurrency or cache plane. Reusing the same vintage identity for changed data violates the upstream contract.

## Executed evidence

| Test family | Result | Scope |
|---|---:|---|
| Strict TypeScript compilation | PASS | Node 22.16.0 / TypeScript 5.8.3 |
| Named behavior contracts | 78/78 | Synthetic source, time, data-quality and arithmetic cases |
| Fixed-seed randomized scenarios | 250/250 | 1,750 assertions; not market observations |
| Targeted mutants detected | 14/14 | Intended assertions catch deliberately broken mechanics |
| Fresh portable-runner reproduction | PASS | New private directory, same exact dependency and source |
| Browser acceptance | NOT PROVEN | Diagnostic navigation was blocked by administrator policy |

The first mutation pass caught 10/12 selected mutants. Its two misses led to stronger fixtures, not weakened assertions. After the initial 76-case pass, two red-first tests exposed finite inputs producing an infinite POC and requested fractions below the dependency's 0.01 minimum being silently clamped. The adapter now rejects both. It does not change Terminal's profile calculation. Final totals are 78 contracts and 14 targeted mutants; earlier receipts survive in the companion archive.

The browser diagnostic returned `net::ERR_BLOCKED_BY_ADMINISTRATOR` before reaching its page. No alternative URL scheme or policy bypass was attempted. It used the pre-edge source; the final candidate has no browser acceptance. Mini ping succeeded but native file/process reads returned `Not connected`. That transport failure does not undo prior recorded results. The July capture's launch/completion is not established; it was not restarted.

## Current integration gap

Inspected Terminal commit: `a4be9a3f4b51246200cb1b7c4f1d44730066a9a9`. These are repository-source observations, not live-endpoint proof.

- `terminal/app/api/intraday/route.ts`, blob `894b31aaf54defde517f0656599a47367b74ee2e`, knows source/basis internally for caching, but its normal minute success payload is `{t, tf, bars}`. That branch does not populate source/basis or per-bar observation/vintage metadata. Retained-cache fallback needs an honest interpretation. Preserve existing authentication-before-cache and rate limits.
- `terminal/lib/intradayStore.ts`, blob `53a6c7f786899a00f7f01b46d12ed2138714cc3e`, has no 1m/2m/3m pre-store. Its deep-history path is for US-equity 5m/hourly data; crypto returns the live window. A long hourly chart is not proof of deep one-minute BTC coverage.
- `terminal/lib/intradaySources.ts`, blob `e41fea7de70d43e7430baf2f7e34c61e83fc8fdb`, emits true UTC for crypto and display epochs for other markets. Crypto normally requests the requested aggregate rather than retaining all one-minute children automatically.
- The existing analytics dependency remains blob `dd6abc4e177ff4870d2b64b927c73d7ea430e2a3`. The lab copy was verified byte-for-byte against it.

The next product slice must extend the **existing intraday response/data owner and actual chart/replay consumer together**. Use permissible one-minute history where available and report missing coverage elsewhere. Do not synthesize child minutes from coarser bars or invent observation times. Preserve existing CVD and daily-profile method semantics. Missing original vintage clocks require honest selected-vintage replay, not a false as-known-live claim.

## Reproduce offline

Prerequisites: Python 3.9+, Node.js and TypeScript already installed. Recorded compiler: 5.8.3. Mutation anchors fail closed if another compiler changes their shape.

```bash
python3 run_verification.py \
  --terminal-source /path/to/terminal/lib/drawing-engine/analytics.ts \
  --out /path/to/new-private-verification-directory
```

The output directory must not exist. The runner verifies the exact dependency blob and adapter SHA256, creates a private layout, compiles, runs the three test families and writes a hash-linked receipt. It makes no network calls, installation, browser navigation, product writes or deployment. Inspect failure logs before another run.

GitHub intentionally omits a second copy of the profile implementation. Supply it from its existing Terminal owner. The downloadable archive includes the exact pinned dependency only as a reproducibility fixture, never as an alternate production owner.

## Release boundary and next action

All new files remain under `research/auction_context/v7/` in PR #565, which stays draft/HOLD. Merging research artifacts would not install a Terminal capability. The earlier top-level research documents preserve their historical evidence; this v7 directory supersedes only the stale pending-result descriptions and supplies the new adapter proof.

Next: reconcile the existing Terminal/data owners and active paths, then carry truthful source/basis/coverage through the existing route into a descriptive as-of chart consumer. Complete exact-head review, real source tests, EN/ZH dark/light responsive browser evidence and the normal production release before accepting the user workflow. No entry, ranking, sizing, exit, watchlist, probability or calibration authority changes.
