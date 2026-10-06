# C11/C15 — immutable capture and honest market-data grain

Partial MAS-266 dossier. Verdict: **qualify incumbent capture/replay and measurement grain before expanding crowding or microstructure use**. MAS-276 and MAS-279 retain their P0 health prerequisites.

## Immutable originals and retained value

- [C11, Macro #8421](https://github.com/mastermindx-market-intelligence/macro/tree/74d3b6fb9f45cf35625eeac2fb208fc584acd9cb/research/short_side/commission_11/2026-10-04-hardening), head `74d3b6fb9f45cf35625eeac2fb208fc584acd9cb`, especially `REPORT.md` and `ACCEPTANCE_CASEBOOK.md`: distinguish short activity, reported short positions and broker borrow quotes; first qualify immutable capture, censoring and replay.
- [C15, Macro #8424](https://github.com/mastermindx-market-intelligence/macro/tree/a09f0aa8aa133a985f9235b0c719172fbc79005c/research/market_microstructure/commission15), head `a09f0aa8aa133a985f9235b0c719172fbc79005c`, especially `COMMISSION_15_HARDENED_REPORT.md` and `VALIDATION_PROTOCOL.md`: source grain determines what can be measured; trade-attached quote observations do not establish continuous-book state or participant identity.

Keep both originals and their acceptance casebooks. This source-only review does not rerun their experiments or reverify every external/source-rights claim.

## Current C11 producer and reader seams

Macro pin: `9201f1602bfe47e05a63d61802fbed6f7f55a19d`.

| Surface | Observed boundary |
|---|---|
| [`collectors/finra_short_volume.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/finra_short_volume.py) → `engine/short_volume.py` | Daily short-sale activity ratio is not a short-position stock. Latest-session replacement/deduplication is not immutable correction-generation retention. |
| [`collectors/finra.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/finra.py) → `engine/short_pressure.py` | Source explicitly describes latest-known-per-settlement short-interest history and replacement on restatement. Reader requires knowable-date semantics; settlement date alone cannot be the availability join. |
| [`collectors/ibkr_borrow.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/ibkr_borrow.py) → `engine/short_pressure.load_borrow_panel` / `_latest_borrow` | Broker-specific indicative fee/availability, censored `>10000000` representation and universe/HTB-tail coverage. Same-date reruns replace date/ticker rows; prior-day protection is not immutable intraday generation history. |

Missing, parsing failure, no broker message, observed zero and a censored/lower-bound availability indication are different facts. Broker availability is not market-wide lendable supply, utilization or shares on loan. The source's `avail_unlimited` label must not become an exact share count or a zero. Current reader existence is not actual consumer-generation evidence.

## Current C15 source grain and reader

[`engine/thetadata_store.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/thetadata_store.py) is the incumbent options resolver. Preserve its prior-OI timing law; file presence is not content freshness or proof that prior-session OI was actually available at a particular cutoff.

[`collectors/thetadata.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/collectors/thetadata.py) retains trade/quote times, sequence, conditions, prices/sizes and quote fields from the trade-quote source. [`engine/live_flow.py`](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/engine/live_flow.py) consumes injected poll batches and emits soft quote-location labels. Price versus quote location is not identified buyer/seller intent. Batch/contract coalescing is not an atomic print, parent order or options-package identity.

The existing [`options.trade_nbbo_microstructure.v1` schema](https://github.com/mastermindx-market-intelligence/macro/blob/9201f1602bfe47e05a63d61802fbed6f7f55a19d/contracts/options/options.trade_nbbo_microstructure.v1.schema.json) binds a research receipt to an existing event and its source/clocks/coverage. Its presence does not manufacture dealer/customer/aggressor labels. `engine/options_focused_quote.py` is a narrower snapshot bid/ask projection and cannot be silently substituted for a continuous consolidated quote feed.

Terminal Quote Plane remains a separate shared quote owner; its current-quote interface is not automatically retained event history. Terminal's exact live code/binding and source rights were not independently recertified here. Root independently inspected the borrow/short-interest source policies, live-flow source and receipt schema after the helper review. No quote/borrow files, live provider, market outcomes or production runtime were read.

## Dispositions and exact next scopes

| Disposition | Ruling |
|---|---|
| **RETAIN** | C11-F1 immutable capture/replay and C15-R0 input qualification within the existing producers, resolvers, Flow and Quote Plane owners. |
| **CORRECT** | Same-date replacement or latest-known settlement history cannot support original intraday/vintage replay. A source-observable timestamp is not proof of actual system possession. |
| **CORRECT** | Sparse trade-attached quotes support bounded execution-location measurements; they do not support continuous OFI, time-weighted liquidity, dealer inventory or customer identification. |
| **REJECT** | Daily short volume as outstanding short position, broker availability as market-wide supply, censored availability as exact quantity, a fused crowding score/store or new quote/replay plane. |
| **SUPERSEDE: none for the original acceptance catalogues** | Source presence advances the starting census only. Capture integrity, semantic qualification, consumer proof and empirical obligations remain intact. |

After the relevant P0 and exact writer/custody gates clear, C11's bounded seam is original/normalized generation retention and append-only corrections at the incumbent producers, preserving their legacy convenience views. C15's is source-mode/license/clock/grain qualification and a real measured-block receipt through the existing consumer. First reconcile existing candidates and semantic repairs; do not modify shared capture, Flow or quote interfaces based on an old owner label.

## Discriminating acceptance and falsifiers

- Exact repeated source bytes produce a deduplication receipt; same-date correction/retraction appends a new generation. Original history remains addressable and incomplete files/pages stay incomplete.
- Separate source publication/stamp, actual receipt, persistence and validation clocks. Source-as-known and actual-system replay have distinct admissibility requirements.
- Borrow observed zero, absent message, parse failure, censoring/lower bound and entitlement/outage have separate results; coverage/universe filtering stays visible.
- Same symbol on different listing/identity cannot join without a lawful binding.
- Post-trade/late quotes cannot leak into an earlier measurement; sequence resets do not invent identity. Atomic, coalesced and episode grains remain explicit.
- Prior-session OI joins require its actual availability. Sparse trade BBO fails a continuous-OFI requirement rather than filling missing intervals.
- Corrections preserve earlier recorded receipts; unknown rights refuse the requested new use. A quote-concordance test cannot prove participant identity or predictive value.
- Actual consumer/import tests must show no added rank/gate/size authority; a descriptive schema alone is insufficient.

Falsifier: an accepted retained original/correction capture with exact source clocks, identity, rights and real consumer receipt could discharge the relevant bounded replay requirement. An accepted richer source could support a different measurement grain, but it must be separately admitted. A blocked/unqualified result with exact evidence is valid; never infer a successful historical series from today's convenience file.

## Procurement, unknowns and supersession

No borrow vendor, tape or quote feed was purchased/contacted; no new acquisition occurred. Current entitlements, retention/redistribution/model-use rights, delivered historical grains, complete coverage, costs and incremental value remain **UNKNOWN/NOT_TESTED**. No current FINRA/SLATE launch date is asserted by this addendum. A future purchase requires a named estimand/consumer, missing grain/history, source rights and sample value against the cheapest adequate incumbent baseline.

Preserve both reports unchanged. These findings do not close C11/C15, MAS-266, MAS-276 or MAS-279, or turn display/source qualification into portfolio authority.
