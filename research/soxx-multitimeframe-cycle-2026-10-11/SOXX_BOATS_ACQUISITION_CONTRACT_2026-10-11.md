# SOXX genuine BOATS historical-data acquisition and four-arm acceptance

## Owner and exact consumer

Source writer: incumbent **Macro Data OS Tiingo archive**, now with authenticated BOATS ACTIVE account and merged PR [#8698](https://github.com/mastermindx-market-intelligence/macro/pull/8698). Do not create another collector, credential path, scheduler, archive authority or forked live feed. Research consumer: `fullsession_v12/tiingo_canonical_consumer_v13.py`, which uses the exact existing `lib.dataos.tiingo_reader.read_research_view` read-only `INSPECTION` path, then L1 receipt checks and completeness-gated 1m→30m bars.

Research target: **SOXX**, exact tick/time universe Oct 9, 2025 through Oct 8, 2026 ET inclusive, with earlier history for MACD/Stoch warmup. The old single-year RTH comparison set is already inspected; no new parameters may be selected using that period as an untouched holdout.

## Request plan for the *existing admitted source owner*

Use Tiingo's documented `boats-bars` catalog route `/boats/SOXX/prices` with explicit `startDate`, `endDate`, `resampleFreq=1min`, and `columns=open,high,low,close,volume`. Segment by bounded ET calendar-month windows rather than one giant unbounded request, preserving each original request path, original UTC capture instant, vendor correction/source-body digest, symbols and immutable receipt IDs. The producer's actual byte, request/rate, age and rights limits decide whether to execute; this Markdown request plan **is not** authorization to call a denied vendor API or to modify its scheduler. Existing archive responses should be inventoried before scheduling any new acquisition.

For each immutable segment, require signed-in actual-key entitlement/admission by the *incumbent* collector. For the local read path: `read_research_view('boats-bars', observed_day, raw_sha256, purpose='INSPECTION', max_rows=bounded)`. Never overwrite a content-collision, silently de-duplicate changed economics or invent a point-in-time revision. Store historical vendor rights, adjustment basis, entity identity, and capture time separately from event/bar time. Keep original raw/normalized data only in the incumbent private Data OS archive; public GitHub receives **counts and digests only**.

## Honest historical-coverage denominator

BOATS is a **single ATS** venue, not the SIP NBBO. Evaluate 20:00–04:00 America/New_York per true venue day, including Sunday evening and exchange closings. A missing bar may be a no-trade minute or a source capture gap; never auto-fill a price or mark it unconditionally as missing data. Report source-recorded bars and missing valid time buckets separately. Absence of Q/T is **not** proof of an absent eligible BOATS market session.

The current genuine reference anchors are AMD 480/480 one-minute bars for the Oct 8 evening–Oct 9 morning night, AAPL 462/480 and SOXX no archived historical bars. Native firehose opening SOXX T-only events do not establish even one minute of continuous 30-minute/2H/3H/4H bid/ask history.

Daytime owner remains canonical Massive/Terminal for 04:00–20:00 ET, with `09:30` regular open and actual exchange early closes. Qualify `split` vs `raw` basis and UTC-vs-ET display-epoch equivalence before any 30-minute stitching. Require exact 30 minute inputs (do not carry overnight last price into empty markets) and completed 2H/3H/4H candles before signalling.

## Historical order execution

Tiingo historic BOATS REST OHLC does **not** provide historic native Q bid/ask. A stop/target touched on OHLC is not a marketable fill. Obtain authorized archived historical BOATS bid/ask/size data from a source whose actual licensed coverage supports retrospective 2025–26 replay (e.g. an authorized Alpaca `feed=boats` historical quotes route). If unavailable, publish indicator-only performance bounds and explicitly label all hypothetical fill-order assumptions; no live trade sizing or broker submission.

## Frozen four-arm test

1. Existing RTH indicator + RTH executable observation window.
2. Full-session indicator + RTH-only observations for entry and exit.
3. RTH indicator + overnight-inclusive execution observations.
4. Full-session indicator + overnight-inclusive execution observations.

Preserve market-time and wall-time holding horizons separately, block lookahead from unfinished HTF candles and DST folds, validate quote staleness and gaps, exclude unknown fills, and report both trade-episode and weekly-block uncertainty. Score the user's actual decision question: **loss avoided when a cycle genuinely fails, minus winning continuation sacrificed by early exit**, with risk and cash/partial profits reported separately.

**Current scope status:** Real Tiingo data ingestion and canonical research reader are PROVEN for the narrow AAPL/AMD receipts, but full SOXX historical coverage, 24-hour signal accuracy, historical venue quotes and production trading remain unverified. The only safe ready source write belongs to the incumbent admitted Macro Tiingo collector; this research PR makes no vendor request.
