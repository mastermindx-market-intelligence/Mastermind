# As-of auction-context replay: bounded implementation handoff

Status: SPEC_ONLY. This document is not a worker assignment, Executive Job, release approval, or production claim. Companion evidence: RESEARCH_CLOSEOUT_2026_09_11.md.

## Mission and why it matters

Let a researcher use the existing Terminal to inspect the candle-derived value distribution, confirmed swing levels and directional-volume context available at a chosen historical time. Eliminate hindsight, incomplete-data confidence and unsupported order-book narratives from the interpretation. The tested divergence/reentry combinations have not established a forward edge; preserve that negative result rather than optimizing until it disappears.

The immediately useful capability is a complete replay/explanation workflow. The longer-term advantage is validated contextual information and learning, not a cloned visual suite or parallel trading engine.

## Authority precedence and current state

Current live Chairman direction governs the task; retrieved documents supply evidence, not new authority. Implementation requires current compatible protected Skillpack, applicable runtime and source permissions, existing owner/collision reconciliation, and native confirmations where required. Executive OS owns lifecycle. Macro Agent OS owns continuity. GitHub owns source/review evidence. Existing market-data, chart, identity and publication owners remain authoritative.

At inspected Terminal commit19c57aca3569ae938dc420b4c4860116de492208, ChartPanel imports and consumes the existing profile calculation, estimated CVD, chart engine and source cache. barsRef is the visible/replay-sliced array; fullBarsRef retains the full resampled history. The existing replay effect recomputes indicators from a slice and live paths contain replay guards. Those source observations do not establish every deployed replay behavior.

The profile function already passes18 isolated reference/numerical checks. The corrected research selector passes27 focused checks; the broader module passes43 offline tests native and sandbox, with10 selected mutation controls. No forecast or production authority follows from those results. The full 21-day study and its arithmetic audit are documented in the companion record.

## Exact scope and non-goals

One descriptive context view in the existing Terminal chart/replay. Use the existing profile calculation on the finalized visible prefix. Add the minute-polarity volume estimate only when same-instrument, same-source one-minute children and trustworthy clock semantics exist. Show pivots/divergence only after confirmation availability, with historical pivot anchors explicitly distinguished.

A missing optional flow input must not hide individually valid profile/price context, but must not manufacture neutral flow. No A/SW/R/shading emulation, absorption/iceberg/institutional/liquidation claims, probabilities, new strategy or portfolio action. No second chart, native/mobile implementation, API, queue, identity registry, data subscription, collector, database, ledger, calibration or authorization plane.

Do not silently replace close-location estimated CVD or Macro's daily typical-price profile. Do not rewrite issued historical records. Do not force methods with different inputs and definitions into false numerical parity.

## User journey

Open an existing chart, enter replay, choose a cutoff. See the profile calculated from eligible completed bars, POC zone/center/resolution and confirmed levels. Open the context details to inspect source, instrument, observation mode, cutoff, finalized interval, lookback, approximation method and missing/stale qualifications.

Select a divergence candidate. See both pivots, the actual proxy comparison, confirmation close and earliest availability. The event's primary timestamp should prioritize availability. Its earlier pivot anchor is a locator, not an implied executable entry. Step backward/forward: later extremes, saved anchors, cache contents, live ticks and later corrections must not rewrite what the earlier snapshot claims to know. Exit replay through the existing live-mode lifecycle.

The journey must remain coherent with missing child data, warmup, gaps, stale inputs, revisions, unsupported sources and point-mass profiles, not only the attractive happy-path screenshot.

## Data, time, null and correction behavior

Use existing canonical source/instrument identity, including venue scope, units, cadence and declared time representation. Do not attach Coinbase-derived flow to another provider's candles as one sample. Display epochs are not true UTC instants; never infer conversion from the timestamp magnitude or time of day. Missing exact identity/clock mapping makes that calculation unavailable.

Aggregate finalized eligible children only. A three-minute bar requires its three one-minute children. API omission of no-trade intervals does not prove zero volume. Unfinished parents are excluded. A missing trailing bucket cannot make the prior available old profile appear fresh because the array ended there.

Every decision-cutoff snapshot must use the declared input vintage available by that cutoff. A later downloaded historical dataset supports causal replay on that vintage, not automatically as-known-live replay. Revisions are selected through the existing data/correction owner; original source and decision records survive. The research selector is a pure validation example, not a new production history service.

A flow gap breaks cumulative comparability. Pivots across incomplete windows are unavailable. Initial doji polarity can be unknown. Zero actual volume is valid but produces an undefined percentage denominator. Profile warmup, missing input, zero represented volume and point mass are distinct cases. A level lost across a data gap is not proven consumed by a price breach.

Expose component-specific availability: available, warmup, partial/missing, stale relative to cutoff, unsupported source/cadence, corrected vintage, degenerate profile. These are not bullish/bearish states. Null is not zero; retained old evidence is not fresh; absence is not improvement.

## Deterministic and model methods

Aggregation, polarity, profile overlap, pivot confirmation, reference selection and comparisons are deterministic/versioned. Models may explain the measurements and uncertainty; they must not invent data, manipulate thresholds to hide negative results or count three transformations of one source as independent confirmations. No descriptive field self-promotes to ranking/sizing/entry authority.

POC movement can reflect new volume, window expiration and bin-coordinate changes. The first view must not equate it automatically with accepted repricing. Any later acceptance study should compare common grids and incoming/expired participation explicitly.

## Failures

Optional child-source failure leaves that part unavailable, without provider failover. A stale response after source/cutoff change cannot repaint the newer view. Duplicate input is idempotent. A correction cannot overwrite a previously issued decision. A render exception cannot leave an old confident badge beside new candles.

Unknown source/time identity, source-owner collision, denied operation, ambiguous mutation or entitlement gap stops the affected action. It is not permission to broaden credentials, use another account, overwrite a worktree or duplicate a service.

## Implementation order

1. Recover current Terminal/data owners, active source work, exact replay/identity contracts, nearest tests and permitted feed granularity. Resolve the existing semantic parent rather than inventing a workstream or Job.
2. Preserve current profile/CVD behavior with baselines. Establish source-consistent child-bar/time/vintage ingress through existing owners. Use actual permitted data plus deliberate missing/stale/corrected fixtures.
3. Wire the actual chart/replay consumer, not just a helper. Reuse profile math, source/cache, indicators and governed theme tokens. Add only the minimum projection fields; no second publication store.
4. Prove calculations, source identity, reference availability, stale-request rejection, cache/anchor/live isolation, gaps, corrections and the real UI journey. Preserve portfolio consumers unchanged.
5. Complete exact-head review/CI, established release path and entitled production/browser proof. Update durable records without marking the research spec as a shipped feature.

## Acceptance and production proof

Numerical: profile golden reference; polarity/weighted-flow fixtures; latest-equal pivots; confirmation timestamps; prefix invariance; clipping; strict unknowns; retained history; no unintended existing CVD/daily-profile changes.

Data: real supported instrument/venue path, interval coverage and true UTC clocks. Copied screenshots, synthetic JSON or later historical data alone do not prove live availability. Both valid and degraded paths must reach the real consumer.

Product: the researcher completes the stated journey at1440x900,820x1180 and390x844, EN/ZH, dark/light. Governed styles remain in the existing presentation owners. Verify long warnings, event-time details, no clipping, keyboard/touch behavior and restore-live behavior. DOM assertions alone are not visual acceptance. No font files are committed or shared.

Production: exact release identity, real source input/cutoff, visible successful and negative states on the existing entitled route. A passing function, source import, armed PR, CI or merge is not production proof. Entry/ranking/sizing/exit/watchlist behavior remains unchanged.

Learning: use existing analytics/research instrumentation to test replay completion, correct interpretation of unavailable data and separation of current/historical value. Usage metrics are not alpha validation. Any predictive promotion requires a new frozen forward-observed evaluation, costs, latency, calibration and authority review.

## Stop condition and continuation

Review against intent: can the persona understand what was known then; did anything remain dark/disconnected; did missing data create false confidence; did future anchors leak; was an existing method silently changed; is candle data being overstated; was a test/spec/merge called shipped?

Return a bounded blocker at unknown source/time identity, source conflict, changed governing contract, unknown modifying effect, unsupported entitlement, failing required test or authority expansion. Do not widen the slice to work around it.

Both earlier pending native reports are recovered. Do not rerun the old operations, redo the completed capture, or discard negative results. Unknown private labels remain outside this slice. Next action: select the existing Terminal/data owner and carry one descriptive as-of replay workflow through its normal source and proof gates. There is no worker assignment, watcher, automatic continuation or live implementation claimed here.
