# Real event-level continuation: what is now measured, built and still unproven

## Decision

The work has progressed beyond daily-bar conjecture into a real, fully framed historical exchange capture and an executable research prototype. **The new repeated-order execution-history candidate failed its positive forecast gate. The stronger quote-recovery/fatigue hypothesis remains untested on real book data; it was not relabeled as the failed execution-only experiment.**

This continuation remains research-only under the original commission. No purchases, live source changes, production schemas, ranking, alerts, sizing, trades or deployment were made. All prior negative pilots and their original data/results remain unchanged.

## 1. Actual source qualification

The existing IEX HIST DEEP+ archive is `20261005_IEXTP1_DPLS1.0.pcap.gz`, acquired October 7. Its 9,875,890,058 compressed bytes were rehashed and exactly match the retained receipt:

`2e41ba84c2a24ccd541d079c2bb05a6da38e988790d8e97a19c1527b1195b0dd`.

The original C++ scanner reads gzip -> PCAPNG -> Ethernet -> IPv4 -> UDP -> IEX-TP version 1/protocol 0x8005. It checked block trailers, packet lengths, message framing, stream sequence and byte offsets, and read the compressed stream to its checked end.

| Observation | Actual result |
|---|---:|
| Captured packets | 275,447,873 |
| Framed exchange messages | 351,610,550 |
| First/last sequence | 1 / 351,610,550 |
| Detected sequence gaps | 0 |
| Duplicate messages | 0 |
| Backward source-send timestamps | 0 |
| Uncompressed bytes consumed | 44,183,218,988 |
| Raw selected-symbol messages retained privately | 6,576,677 |
| Selected displayed execution (`L`) messages | 39,763 |

The fixed cohort is AAPL, MSFT, NVDA, AMD, MU, INTC, SPY and XLV. This is an intentionally limited cohort, not a representative market sample.

**Framing the full archive is not the same as semantically reconstructing its full order book.** Only previously retrieved, documented `L` fields were interpreted. An independent Python parser matched every one of the 39,763 extracted L records, including nanosecond timestamps and large order/trade identifiers. Other selected messages remain raw for a later qualified replay.

IEX describes DEEP+ as order-by-order displayed liquidity. Hidden orders, hidden reserve portions and other venues are outside that observed book. An L order reference identifies the displayed resting order affected by an execution, not an institution or an aggressive parent metaorder. First observed execution time is not order-entry time. The capture's source-send clock is not a proof of Mastermind's historical ingestion/decision availability.

Source references: IEX market-data documentation, the DEEP+ specification page, and the IEX-TP specification page. Downloaded document hashes and the exact previously retrieved field ranges are in `QUALIFICATION.json`. The old IEX-TP URL now returns a relocation notice. Current source pages are:

- https://www.iex.io/products/market-data-connectivity
- https://www.iex.io/documents/iex-deep-plus-specification
- https://www.iex.io/documents/iex-transport-specification

## 2. The real experiment: LP-EVENT-03A

The protocol was committed at `e5981d709` and the study implementation at `a314e91bf` before outcomes. The experiment asks whether histories of repeated executions against the same observed displayed order add information beyond execution-price, volume and cadence features.

This is **not** a signed-flow, hidden-inventory or reconstructed bid/ask recovery test. It makes a useful narrower comparison using fields already supported by the retrieved documentation.

Only sale-condition flag 0 records were used for the empirical model: the documented standard continuous-execution example. The conservative filter and single-venue scope leave thin samples in some securities. No unverified flag or aggressor-side interpretation was filled in.

At an eligible execution after the history warmup, the decision uses only records disseminated so far. The target compares the median of the next five eligible execution prices, starting at least one second later, with the median of the most recent five. DOWN, SAME and UP all remain distinct classes. All five future prints must arrive within fifteen minutes and the study's session window. Missing suffixes are missing—not unchanged prices.

Training is the morning window with every training label finished before noon. Evaluation begins at 13:00 and ends at 15:30, with eligible suffixes finished by 15:45. This is a same-calendar-day chronological split, **not multi-day out-of-sample validation**. The variable event-clock horizon is itself a limitation: evaluation median 84.14 seconds; 90th percentile 304.25 seconds. Sparse AMD cases have much longer horizons and only fourteen evaluation observations.

The baseline contains price/momentum/range/volatility, executed volume, event duration, interarrival timing, median size, clock and ticker indicators. The candidate adds repeated-order volume share, order-volume concentration, previously observed order references, time since first observed fill and a frozen interaction with observed recent price change. Both use fixed ridge-softmax models and train-only standardization. No model/window tuning followed results.

| Three-class forecast | Training observations | Evaluation observations | Brier loss, lower is better | Log loss | Accuracy |
|---|---:|---:|---:|---:|---:|
| Training-class constant | 2,206 | 2,295 | 0.548416 | 0.864113 | 39.91% |
| Price/volume/cadence baseline | 2,206 | 2,295 | **0.527829** | **0.849491** | 55.86% |
| Baseline plus repeated-order history | 2,206 | 2,295 | 0.539244 | 0.869037 | 56.38% |

The candidate's small accuracy increase is **not** a successful probability forecast. Its Brier and log losses are worse. It primarily shifts more weight toward the prevalent UP outcome while reducing DOWN recall; neither fitted model selects the SAME class as its maximum-probability forecast. Accuracy alone would give a misleadingly favorable summary.

Paired mean Brier gain, baseline minus candidate: **−0.011415**. The originally specified five-minute-block interval is **[−0.022241,+0.000220]** over thirty within-day blocks. This is not a population confidence claim: outcome windows and serial features cross block boundaries, and all blocks share one day. A post-result dependence qualification, with no refits or candidate changes, uses fifteen- and thirty-minute blocks. These remain negative in this sample but have only ten and five blocks respectively. They do not create independent days or justify universal significance.

Only MSFT, NVDA and XLV have positive point gains; five other names are negative. The candidate fails the frozen overall-gain and cross-name gate. A fixed shuffled-order-ID diagnostic also worsens the baseline, with gain −0.012586. The secondary simple recent-direction carry rule, omitted from the frozen primary output, was computed explicitly after results as a diagnostic: 49.19% accuracy, not calibrated probabilities. It changes no candidate or acceptance gate; POST_RESULT_CHECKS.json records this deviation. One shuffle is a control, not a full randomization significance test, and it is explicitly not a deployable construction.

**Conclusion:** reject promotion of these particular execution-history features. Do not infer that actual quote recovery, resistance fatigue or source-backed event-response mechanisms have been disproven. Displayed execution messages make up only about 0.60% of selected messages in this capture; the richer order-book history is not represented in the execution-only features.

## 3. Recovery engine implemented without future leakage

`book_recovery.py` is an original research engine for explicitly normalized synthetic ADD, MODIFY, DELETE and EXECUTE events. It maintains displayed quantity, detects an execution shock against a best displayed level and follows what happens afterward.

It separates:

- PENDING response: elapsed time is observed, eventual recovery time is unknown.
- RECOVERED: the original displayed depth has returned, at a known later event.
- LEVEL_DEPLETED: displayed quantity at the defended level has reached zero. This is **not** automatically a trade-price breakdown or proof of aggressive selling.
- HORIZON_ENDED_UNRECOVERED / SOURCE_GAP_CENSORED: unresolved duration is censored, not converted to an invented completed recovery.

Events that already deplete a level at the proposed decision cannot be credited as forecasts of a later failure. Bid and ask histories remain separate. Duplicate/unknown orders, impossible executions, out-of-order observations and noninteger identity/time fields are rejected. A source gap invalidates continuing inference. A historical snapshot requires replay of the original prefix; a future state cannot answer a past query.

The engine has **18 passing focused tests**. The included synthetic demonstration shows a pending response at a cutoff before recovery, then a completed seven-unit recovery duration only after the later replenishment event arrives. This proves the implementation's temporal behavior under its explicit fixture contract. It is not a market backtest, evidence of institutional sponsorship or a calibrated forecast.

The real DEEP+ order adapter deliberately raises `DEEPPLUS_BOOK_FIELDS_UNVERIFIED`. It does not guess the add-side flags, modify/delete quantity semantics, order-priority/repricing behavior, reset events or atomic update boundaries.

## 4. A real read-only research consumer now works

`research_snapshot.py` produces a historical, cutoff-aware observation for all eight securities from the qualified execution extraction. It exposes observed order concentration, previously seen fills, recent print direction, last source sequence and print age at the requested cutoff.

It explicitly returns null for inferred pressure direction, hidden inventory, quote recovery and forecast probability. Rotation-call writes, live alerts, ranks and sizing all remain false. The sample at 14:00 New York on the capture date was executed and checked; all eight records preserve those limits.

This is a reusable research read path through the already authorized Studio filesystem/process service—not a second production schema, runtime owner or live deployment. It allows a user or machine to inspect what the selected data actually support without presenting a failed candidate as a signal.

## 5. Verification and repairs

The decoder fixture suite initially passed fourteen tests. Two additional adversarial tests exposed acceptance of a negative signed price and an execution timestamp after the packet's send time. Both were repaired and now fail closed. Raw retained records are serialized explicitly little-endian rather than relying on the observed M2 architecture, and a packet limit now also bounds heartbeat-only input.

A further red fixture exposed a UDP datagram extending beyond the declared IPv4 packet length, and another exposed invalid JSON for unknown message-type bytes. Both were repaired, along with checked report writes. This changed a material framing predicate, so one stricter full-archive replay was necessary. It produced byte-identical raw selected messages, compressed execution CSV and scan metadata. The original forecasts were reused without refitting; see REQUALIFICATION.json.

Test suites at this stage: 19 decoder fixtures, 18 synthetic recovery tests and 7 event-study tests—**44 passing tests**. Additional real checks include all-record independent L parsing, exact source-hash agreement, causal-prefix feature equality and training-label purging. Tests are not predictive acceptance.

The framing audit `lp-event03-framing-review` returned and was adjudicated. It alleged a compile typo absent from the exact packet and contradicted its own malformed-input findings. It is NOT accepted as overall approval. Useful negative-price, byte-order and JSON observations were independently checked; the parent found and repaired additional framing issues. REVIEW_ADJUDICATION.json records the exact returned-byte hash and disposition. The child is terminal with no outstanding obligation. No independent market-alpha review or replication is claimed.

## 6. Exact remaining constraint and next action

A selected PDF read/render request was explicitly blocked by the platform before dispatch. That action was not retried or routed through another tool. The continuation proceeded with the already retrieved IEX-TP and L-message fields, the independent archive scan, real execution-only study, research consumer and synthetic recovery engine.

**The remaining critical step is a permitted, verified mapping of the full DEEP+ book events and reset/update boundaries.** Then bind the guarded adapter, reconcile every selected order transition against the retained raw stream, and test ordered recovery/fatigue at matched false-alarm rates with independent days and realistic observation latency. Neither an assumed side bit nor an apparently plausible reconstructed book is sufficient.

Until then, the real quote-recovery hypothesis remains **BUILT AS A GUARDED RESEARCH PROTOTYPE, NOT REAL-DATA VALIDATED**. Its production and trading boundaries remain closed. More executions or additional paid feeds would not repair a missing semantic qualification, and more tests of the failed execution-only candidate would not answer the stronger hypothesis.

## Attribution and source limits

Data provided for free by IEX. By accessing or using IEX Historical Data, you agree to the IEX Historical Data Terms of Use: https://www.iex.io/legal/hist-data-terms

IEX historical data represent IEX rather than all trading venues and are supplied as reference information. Private source captures and full per-event/per-forecast series are not republished here; only code, qualified aggregate results, hashes and bounded research examples are included. No inference of broader source rights, original historical end-user availability, real-time operation or actionable market advantage is made.
