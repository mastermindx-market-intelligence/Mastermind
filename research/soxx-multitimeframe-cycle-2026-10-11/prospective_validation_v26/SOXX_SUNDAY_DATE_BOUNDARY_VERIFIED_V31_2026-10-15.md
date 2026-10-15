# V31 — Sunday BOATS date-boundary falsifier: verified recovery of the missing first half

**2026-10-15 UTC | Actual licensed-original-source evidence, research INSPECTION only.** No new vendor calls by the research assistant, trading actions, historical price rows, API credentials or originally closed source writers were published. This records the human operator's ONE new Sunday–Monday Tiingo BOATS SOXX historical request and its original M2 receipt/Parquet readback.

## 1. Original human call, original receipt and exact L1 validation

The human operator used the existing original Tiingo collector (on the mounted 4 TB source drive) for SOXX one-minute overnight OHLCV, **Sunday September 27–Monday September 28, 2026**, with max-requests 1 and 1.25-second pacing. Its reported effect was **1 attempted, 1 HTTP200 OK, 1 NEW original receipt, 0 errors, 479 rows, 51,200 bytes**.

| Original custody/effect | Verified fact |
|---|---|
| Original raw source SHA256 | b1a6d6d7796b5d472dfc75cfbd65ded3dc7af148330af158640757e187de685c |
| Original receipt identity | e813dc9b4bb547c4d9b66064dfe870ed5341cf4f75903fd5a15b7e8e130479e8 |
| Capture clock (UTC) | 2026-10-15T09:00:39.144128Z |
| Historical request range | 2026-09-27 through 2026-09-28, one-minute open/high/low/close/volume |
| Original raw payload byte count | 51,200 |
| Original canonical materialized Parquet SHA256 | 458bd1924b7a8af17922b7113a22488368c8d3dbd00c8f117ea317ef0a584aaa |
| Canonical Parquet bytes | 17,686 |
| Original manifest SHA256 | 7b763acbafc35fca6c4bd19646e8b4bbada8e7de401c70547123f89ed162a868 |
| Original receipt L1 rows | 479 |

The original materializer produced **WOULD_WRITE 479** after checking that both output targets were absent, then executed **WRITTEN ONCE** for this receipt; both Parquet and manifest postimages were independently SHA-verified. The incumbent source reader, read_research_view(source=boats-bars, capture_day=2026-10-15, raw_sha, purpose=INSPECTION), independently reverified the original raw hash, receipt identity, source context and all 479 original-to-L1 rows. Original PIT backtest eligibility, canonical price identity, redistribution and executable historical bid/ask marketability remain **FALSE / NOT PROVEN**. No old raw source or L1 file was overwritten.

## 2. High-value conclusion: the Sunday first-half omission is a request-date boundary issue, not proof the venue was silent

The existing earlier **Monday September 28–Sunday October 4** seven-day REST request lacked all Sunday September 27 **20:00–23:59 ET** rows, but included **240 Monday September 28 00:00–03:59 ET** rows. The NEW targeted **Sunday September 27–Monday September 28** request returned:

| Actual New York overnight window | Prior weekly REST context | New targeted REST context |
|---|---:|---:|
| Sunday Sep 27 20:00–23:59 ET | **0/240** | **239/240** |
| Monday Sep 28 00:00–03:59 ET | **240/240** | **240/240** |
| Whole Sep 27 overnight session | **240/480** | **479/480** |

The exact one missing new minute is **Sunday September 27 at 22:28 ET**. The new 479-row original source contains **387 minutes with positive reported BOATS volume, 92 with zero reported volume, 71 zero-volume bars with nonflat high–low**. The existing original v13 whole-night resampler returned **15 strict complete 30-minute timestamp windows / 1 withheld**. Existing V29/V30 reported 3/4 overnight-local 2H, 1/2 overnight-local 3H, 1/2 overnight-local 4H full 1m input windows, each with some zero-volume source minutes and **zero** full HTF windows with all-positive constituent volume.

**The key falsifier is decisive about source availability:** real, vendor-archived Sunday September 27 20:00–23:59 SOXX minute history IS SERVED when the request begins on Sunday. A claim that the original 0/240 from Monday–Sunday weekly requests proved no Sunday evening BOATS activity is therefore false. The observed pattern strongly supports **REST date-filter alignment**: a Sunday-start request recovers the missed first half while retaining the Monday 00:00–04:00 second half. Tiingo's official BOATS documentation establishes the 20:00–03:59 ET venue window but does not explicitly document the date-only endDate normalization rule; this is **experimental evidence for these exact request contexts**, not a global server implementation guarantee. https://www.tiingo.com/documentation/boats

## 3. Exact private original-vintage overlap comparison — no mixing or price leak

The new request intentionally overlaps the old Sept 28–Oct 4 raw source (SHA256 f01d2d4ada743310eacc1b0b557342371e62351584d388dbf813d1543a4415e6, original receipt caaa9e4ab4cf1f040dd2bb972e25959bce60bc9716058dd8b9edb0eb3f429822) on precisely **240 Monday 00:00–03:59 ET minute timestamps**.

All **240/240** overlapping original records have EXACT EQUALITY for ALL **five** OHLCV fields (open/high/low/close/volume). **Zero price, zero volume or mixed-field conflicts** were detected. The new source contributes **239 genuinely new UTC minute starts**. Across these TWO original source contexts, total raw rows **2,615** minus **240** exact overlapping minutes = **2,375 unique minute instants**. The remaining old-source-only minute starts are **1,896**. Both immutable original receipts retain their own capture clocks and price vintages; no synthetic merged price series, source overwrite, chosen winner or adjusted transaction price was created.

The old seven SOXX receipts total **13,079 distinct source minutes**. This eighth, 479-row source overlaps previously accepted original data by 240 and contributes 239 new time instants. Thus there are now **8 original SOXX REST receipts / 13,558 raw source rows across receipt contexts / 13,318 DISTINCT UTC one-minute starts**, not 13,558 independent market observations.

## 4. Reusable V31 read-only source conflict checker

Added the pure research module boats_source_overlap_v31.py plus tests/test_soxx_v31_boats_overlap.py. The source function consumes ONLY original fullsession.Bar objects, after each original view separately passes read_research_view and tiingo_l1_v13.l1_to_bars using its immutable SHA/receipt/capture cutoff. It verifies input type, symbol, 1m clock alignment, order, duplicates, original raw basis and distinct lowercase digest identifiers; compares overlapping original UTC timestamps and exact OHLCV fields; returns only counts, conflict status and false acceptance flags. It outputs **NO licensed OHLC price values, no rows, no joined series and no automatic source permission**.

- Exact overlapping original values: SOURCE_TIME_OVERLAP_EXACT_NO_PRICE_CONFLICT.
- Any changed high/low/open/close/volume: QUARANTINE_CONFLICTING_HISTORICAL_VINTAGES; exact changed-field COUNT only, no market price leaked and no automatic source selection.
- Fully disjoint: DISJOINT_ORIGINAL_SOURCE_TIMESTAMPS_NO_VINTAGE_COMPARISON (no invented equality proof).
- Even a perfect 240/240 match does **not** grant point-in-time source availability, historical top-of-book/order size, legal redistribution, independent strategy results or production trading authority.

**16 targeted synthetic tests PASSED** plus exact **real** old/new original-source L0/L1 → v13 overlap replay PASSED, with 240 identical OHLCV collision rows, 0 mismatches and 239 genuinely new timestamps. The previously accepted V29, V30 and 2025–26 historical strategy code are untouched; no old v2–v24 replays, model fitting or execution-size assumptions.

## 5. Correct future request alignment and the next original operation

**Design consequence:** For FUTURE UNCOLLECTED historical data, prefer original **Sunday–Saturday** seven-day calendar-date requests (e.g. Aug 2–8, Aug 9–15, Aug 16–22, Aug 23–29, 2026) rather than naive Monday–Sunday chunks, whose observed first Sunday night is incomplete. The ORIGINAL offline Tiingo planner has validated a four-request disjoint **Aug 2–Aug 29** Sunday-aligned range, digest **adce4ddf294f52be94445019f5a3fc0ad33ecf3455b9deedeac2f8ce5a4d74c5**. This is NOT a new ingestion scheduler or automatic permission to fetch. Actual provider responses would need original receipt/rights/clock/volume checks, because one experiment does not ensure all older Sundays are complete.

For the FIVE already archived but still missing normal Sunday first halves **Aug 30, Sep 13, Sep 20, Oct 4, Oct 11**, use distinct original Sunday–Monday targeted two-day requests ONLY if original operator entitlement, current quota and source writer admission permit. The **next single** recommended source-boundary recovery is **Oct 11–Oct 12 SOXX BOATS historical 1m OHLCV**, original offline plan SHA256 **a1adfb0186c501f749640353896a6e8009b1715630574cfc78062d0b8cb6e61d**. It will intentionally overlap Monday Oct 12 00:00–03:59 rows from the previously accepted Oct 12–13 receipt: retain as separate source vintage and compare via V31; quarantine any conflict. The official Sep 6 Labor Day night is CLOSED and remains excluded from missing trading history. For historical Sunday Sep 27, this target source effect is ACCEPTED — **never repeat**.

**Not complete:** earlier untouched SOXX overnight seasons, RTH+BOATS continuous causal 2H/3H/4H indicators, original frozen 30m/3RTH-hour early-exit economics, true PIT/corporate-action adjustments, historical executable quotes/book/size and fully matured independent prospective 52-observed-RTH-hour outcomes. No live order, protected merge, source retrofit or trading policy accepted.

**Status:** SUNDAY_REQUEST_DATE_GAP_EXPLAINED_FOR_SEP27 / 479_REAL_SOURCE_ROWS_ACCEPTED / OVERLAP_240_OF_240_EXACT_OHLCV / 239_GENUINELY_NEW_TIMESTAMPS / NEXT_OPERATOR_REQUEST_NOT_DISPATCHED.
