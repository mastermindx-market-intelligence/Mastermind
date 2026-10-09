# W-LIQ.3 independently executable quant foundation

**Issue:** Mastermind #120
**Control board:** #123
**Architecture:** draft PR #117
**Producer dependency:** #118 / W-LIQ.1
**Authority:** research and shadow evidence only; zero portfolio, candidacy, Market View vote, sizing, or execution authority

## 1. Delivered boundary

This foundation implements only the portions that are executable before W-LIQ.1 freezes and publishes its canonical state semantics:

1. a closed adapter envelope for externally computed `global_liquidity_transmission.v1` observations;
2. deterministic shock episode eventization under an explicitly supplied, versioned policy;
3. an append-only keep-first shock registry with append-only amendments;
4. the precommitted target and horizon registries;
5. conservative point-in-time forward-return panel construction;
6. a hierarchical/shrunk full response-curve estimator interface;
7. non-overlapping episode effective-N;
8. horizon-purged expanding walk-forward splits with a separately returned untouched holdout;
9. an executable train-only/validation-only curve runner and paired incremental-error scorer;
10. bridges to the existing Macro HAC and BH-FDR judges rather than second statistical implementations;
11. an inert deterministic relation-lifecycle substrate with no built-in promotion thresholds;
12. a keep-first forward forecast/grade ledger; and
13. a BTC→China/HK protocol fixture whose chronology remains explicitly empty until exact point-in-time timestamps are supplied.

The implementation is under `brain/liquidity_lab/`. It is not imported by a portfolio, scheduler, API, Market View, or deployment path.

## 2. W-LIQ.1 seam — no duplicate liquidity state

`SourceStateRef` is deliberately **not** a parser for the raw producer artifact. It is the output of a future adapter that W-LIQ.1/W-LIQ.2 can implement only after #118 freezes field semantics.

The envelope copies, without recomputing:

- producer schema and exact source snapshot hash;
- source observation/release time and first-known time;
- producer model and data versions;
- producer-named state family and shock/source type;
- supplied direction and magnitude;
- breadth, quality, confidence, coverage, and freshness;
- supplied compact conditions, regional-gate snapshot, and component snapshot.

The lab contains no central-bank, money, credit, TGA, RRP, dollar, funding, FX, z-score, orthogonalisation, breadth, or source-quality calculation. It cannot silently become a second GLT producer.

### Adapter obligations after #118

The future adapter must:

- map only frozen W-LIQ.1 fields;
- preserve `observed_at` separately from `known_at`;
- pass the canonical content/source hash and version identifiers;
- degrade stale, unknown, missing, or revised data exactly as the producer declares;
- refuse unknown schema versions and ambiguous timestamps; and
- add golden tests against a real W-LIQ.1 sample artifact.

It must not translate missing data into zero, infer a supportive direction, or derive a fallback liquidity score in Mastermind.

## 3. Episode law

Eventization operates over producer-supplied state points sorted by `known_at`.

- A shock begins at the first eligible material threshold crossing.
- Continued material observations do not revise its first-known record.
- An explicit reset, a sign flip, or a long observation gap closes the active episode.
- A policy-supplied refractory window suppresses rapid same-direction remints.
- Only `fresh` observations with policy-sufficient coverage and confidence can mint an episode.
- Stale, unknown, or low-coverage observations neither mint a shock nor fabricate a reset.
- Thresholds have no module-level production defaults. The caller must supply them, and Sol must ratify any production research policy after #118 freezes semantics.

`shock_id` is stable over first-known time, state family, direction, and model/data versions. It excludes revised magnitude and component payloads. Revisions therefore append amendments to the same first-known record instead of manufacturing a new historical truth.

## 4. Ledger law

Both JSONL ledgers are append-only and use an exclusive file lock plus `fsync` for each append.

### Shock registry

- identity: `shock_id`;
- exact retry: no-op (`duplicate`);
- conflicting reuse: fail closed (`KeepFirstConflict`);
- correction: append `shock_amendment`; never rewrite the original row;
- malformed existing JSONL: fail closed; no row is silently dropped.

### Forward ledger

- identity: `shock_id × target × horizon × model_version`;
- exact retry: no-op;
- conflicting forecast: fail closed;
- first realized grade: append once;
- conflicting re-grade: fail closed and require a future explicit amendment contract.

Forecast rows accept only `discovered`, `shadow`, `demoted`, or `dead`. This foundation cannot emit `advisory` or `validated`. An `insufficient` cell must contain no expected return or probability.

## 5. Target and horizon registry

The fixed horizons are:

`1 / 5 / 10 / 20 / 40 / 60 / 90 / 120` business sessions.

The initial compact target set covers:

- BTC;
- SPY, QQQ, semis, software, and small caps;
- duration, HY, and IG credit;
- gold, silver, broad commodities, oil, and copper;
- DM ex-US and EM;
- FXI, MCHI, KWEB; and
- BABA as a separately identified thin single-name target.

Registry membership precommits a research measurement. It does **not** grant trading eligibility.

## 6. Point-in-time outcome alignment

`build_forward_return_panel` accepts already sampled business-session close series and an evaluation `as_of` date.

- It discards all closes after `as_of`.
- It never forward-fills across calendars.
- It anchors at the first supplied close **strictly after** the shock's first-detection calendar date. This conservative rule avoids using a same-day close that may not have existed when an intraday or after-close state became known.
- A horizon is omitted until the full number of target sessions has printed.
- It never accesses the holdout or a later outcome merely because that value exists on disk.

The caller remains responsible for corporate-action-safe, survivorship-aware, point-in-time target membership and business-session sampling.

## 7. Response curves and honest N

The initial estimator is a hierarchical mean response skeleton, not a discovered alpha model.

- It returns cells across the complete precommitted horizon family.
- It collapses duplicate rows to one shock episode.
- It thins event dates to non-overlapping windows separately at each horizon.
- Narrow targets may borrow a bounded prior from other targets in the same asset class/shock family.
- The prior excludes the target itself.
- Cells below caller-supplied `min_effective_n` return `insufficient` and no estimate.
- Supported cells remain `discovered`; this estimator cannot promote them.
- It reports raw and shrunk means, uncertainty, sample count, effective episode count, and prior count.

This is an interface and statistical skeleton. It does not establish that a relation is predictive.

## 8. Walk-forward, holdout, and FDR

`build_walk_forward_plan` creates expanding validation folds only from shocks before a caller-frozen `holdout_start`.

- Training shocks whose forward windows can overlap the validation start are purged.
- Holdout shock IDs are returned separately and are never inserted in any development split.
- The plan is horizon-specific; a 120-day relation receives a wider purge than a 5-day relation.

`run_walk_forward_curves` fits an estimator only on each split's purged training shock IDs and emits predictions only for that split's validation IDs. It refuses any malformed split containing an untouched-holdout ID. `score_incremental_predictions` pairs a candidate with one named baseline on the exact same shock/target/horizon outcome, averages cross-sectional rows within each shock, thins by the actual widest anchor/exit interval, and reports squared-error improvement, effective-N, single-episode concentration, and the canonical Macro HAC p-value.

HAC and BH-FDR are delegated to canonical Macro validation functions. Hermetic tests inject compatible frozen judges only because a developer worktree may not contain the gitignored Macro sparse checkout. The production defaults fail loud if `engine.validation` is unavailable.

The BTC→China protocol precommits the leader candidates, targets, horizons, condition families, and all required simple baselines. Incremental predictive value—not raw correlation—is the required comparison.

## 9. Lifecycle substrate

The lifecycle vocabulary is:

`DISCOVERED -> SHADOW -> ADVISORY -> VALIDATED`, with terminal failure paths to `DEMOTED` or `DEAD`.

The code deliberately defines **no numeric production policy**. With `policy=None`, every relation stays in its current state. A caller-supplied policy can advance at most one step and must use effective-N, FDR survival, incremental performance, sign stability, single-episode concentration, and forward-window evidence. This ensures an LLM or an estimator cannot self-promote by merely writing a favorable result.

## 10. BTC→China/HK fixture status

`btc_china_protocol.v1.json` is executable protocol plumbing, not a result.

Verified from #117:

- the motivating chronology is qualitative;
- the visible lag prior is roughly 2–4 months, with 12–14 weeks visually salient;
- exact first-known episode timestamps are not supplied;
- recent arrows must not be the optimization target.

Therefore the fixture keeps `episodes: []`, `holdout.start: null`, and explicit unblock conditions. Inventing dates would create false point-in-time evidence and contaminate the future holdout.

## 11. Required W-LIQ.1 handoff before historical computation

W-LIQ.3 cannot honestly run live/backfill studies until #118 returns:

1. a frozen sample `global_liquidity_transmission.v1` payload;
2. exact field meanings for state family, direction, magnitude, breadth, quality, confidence, coverage, and freshness;
3. `observed_at` / release / first-known clock semantics;
4. canonical source/component hash law;
5. model/data version law;
6. revision and amendment semantics;
7. a point-in-time backfill or explicit per-field vintage limitations; and
8. the exact historical chronology source for the visually identified 2023–2026 episodes, if available.

## 12. Explicitly not delivered

- no liquidity-state producer or fallback state;
- no invented historical GLT backfill;
- no empirical BTC→China/BABA result;
- no fitted 12–14 week lag;
- no ChinaGate implementation;
- no repricing-gap or GapScore;
- no Prophet comparison result;
- no Market View reader/plane;
- no UI;
- no relation acceptance thresholds;
- no advisory/validated promotion;
- no portfolio wiring, sizing, execution, deployment, or live runtime mutation.

## 13. Downstream handoff

### To W-LIQ.1 / #118

Freeze the producer contract and provide the eight receipts in §11. Do not implement the quant ledgers or response curves on the Macro side.

### Back to W-LIQ.3

After #118 freezes semantics:

1. write the sole adapter from the real sample payload to `SourceStateRef`;
2. freeze a Sol-ratified eventization policy version;
3. freeze exact historical episode timestamps and the untouched holdout boundary before inspection;
4. run causal eventization and persist first-known shocks;
5. build point-in-time outcome panels and named baseline panels;
6. execute horizon-specific purged walk-forward studies;
7. apply BH-FDR across the complete searched relation family;
8. publish full curves, uncertainty, effective-N, sign/lag instability, nulls, counterexamples, and dominance checks; and
9. keep every relation research/shadow until a separate Sol-ratified promotion policy and forward evidence exist.

### To W-LIQ.4

Consume response-curve outputs only after the above study exists. W-LIQ.4 owns ChinaGate and repricing-gap semantics; this foundation preserves regional gates as opaque context and does not pre-implement either system.
