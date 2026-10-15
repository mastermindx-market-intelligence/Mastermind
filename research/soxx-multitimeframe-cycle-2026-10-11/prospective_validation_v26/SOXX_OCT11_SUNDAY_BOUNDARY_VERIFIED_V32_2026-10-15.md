# V32 — second verified Sunday-night BOATS historical date-boundary recovery

**October 15, 2026 UTC — Original, human-operated Tiingo historical SOXX REST response.**
Status: EXACT ORIGINAL RECEIPT AND L1 VERIFIED; WHOLE OVERNIGHT MINUTE CLOCK FOR OCT11 VERIFIED; OVERLAPPING OHLCV MATCHED; PIT/QUOTE EXECUTION NOT VERIFIED. Research INSPECTION only. This report does not publish licensed market price rows, API keys, order instructions, private account IDs, altered source data or a fitted trading policy.

## 1. One original source request was completed, once

The user executed the existing original Macro Tiingo collector for the explicitly planned SOXX boats-bars request **2026-10-11 through 2026-10-12**, with one-minute open/high/low/close/volume, maximum one request and the existing 1.25-second pacing. Original terminal outcome: **attempted=1, ok=1, new=1, failed=0, row_hints=480, bytes=51,401, errors=[]**.

Original accepted producer provenance:

| Exact original evidence | Value |
|---|---|
| Source receipt capture time | 2026-10-15T10:25:28.017190+00:00 |
| Original historical HTTP status | 200 |
| Original source SHA256 | eea3d5109dd92ce5e93aa2de91e7635615a12d9f035e4836a316465eae8b879e |
| Original receipt identity | c92b2b1a039980237fd2a421b6a2cd5405f06d50e31338975e01d7c50ee3c2cf |
| Original REST source byte count | 51,401 |
| Original existing Data OS L1 Parquet SHA256 | 35f2bcbc0d04b9d5ae5c8a73ed9b42a182ab1441606859b55acb644b1a5b2d83 |
| L1 original Parquet file size | 16,984 bytes |
| Original L1 manifest SHA256 | 6e3b5ea61517e591b448c83e90699bad474e6f534ab0d3435eb22d0fadbf30e1 |
| Exact original source and normalized row count | 480 |

The same incumbent original materializer checked the original raw body, original receipt identity and BOTH absent target paths, returned WOULD_WRITE (480), then executed exactly ONE WRITTEN source materialization. Original Data OS read_research_view(boats-bars,2026-10-15,source_sha,purpose=INSPECTION) independently reverified raw source/receipt, materialized Parquet/manifest digests, and all 480 original-to-view rows. Existing flags remain pit_backtest_eligible=false, redistribution_admitted=false, dataos_identity_admitted=false; BOATS is a single ATS, not national best bid/ask. This session issued ZERO additional vendor requests. This original acquisition and L1 write are now DO_NOT_REDO.

## 2. Sunday October 11 source availability: full 480-minute overnight lattice recovered

Compare the original accepted Monday Oct12–Tuesday Oct13 request (raw SHA ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e) with the NEW Sunday Oct11–Monday Oct12 request (raw SHA eea3d5109dd92ce5e93aa2de91e7635615a12d9f035e4836a316465eae8b879e).

| Local ET source night | Previous weekly request | New targeted Sunday-start request |
|---|---:|---:|
| Sunday Oct11 20:00–23:59 | 0 / 240 | **240 / 240** |
| Monday Oct12 00:00–03:59 | 240 / 240 | **240 / 240** |
| Entire overnight session | 240 / 480 | **480 / 480** |

The original v13 session-clock consumer and V29/V30 research-only source checks independently confirm **16/16 complete 30m**, **4/4 complete 2H**, **2/2 complete 3H** and **2/2 complete 4H** *overnight-only source-input windows* for this previously incomplete Sunday night. This is not the frozen strategy's three observed regular-trading-session hours, not a MACD/Stoch RSI backtest, and not automatically an executable trading price.

**Trade-volume qualifier:** among these 480 original source bars, **276 positive reported venue volume**, **204 zero reported volume**, **193 zero-volume with nonflat OHLC**, and **188 zero-volume with a changed open-to-close price**. All 16 strict 30m buckets and ALL completed 2H/3H/4H input windows include some zero-volume constituent source minutes. Even full source-minute clock coverage does not qualify source-price construction, marketability at size or a historical quote-backed order fill.

## 3. Independent ORIGINAL original-vintage overlap proved clean, without splicing

The new Sunday-start receipt deliberately overlaps exactly **240** original Monday Oct12 00:00–03:59 UTC-equivalent minutes from the older Oct12–13 original source (raw source SHA256 ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e; original receipt a90016abfd49a712215bdea2d08a8fe81bb8c4f398e803472082d8289534c8df).

Both original sources were read independently by incumbent Data OS reader and converted with unchanged original v13 l1_to_bars. Existing V31 audit_receipt_overlap verified:

- **240** original minute timestamps overlap between source receipts.
- All **240/240** original overlap rows match EXACTLY for open/high/low/close/volume, with **ZERO** mismatched fields or changed volume.
- The targeted new source contributes **240 genuinely new** previously absent Sunday 20:00–23:59 minute timestamps.
- For the compared pair: 720 old + 480 new - 240 overlapping = **960 distinct** timestamps; source vintages stay separate, and no joined price series is constructed.

The prior independently accepted Sep27–28 Sunday boundary repair recovered 239 new Sunday-evening minutes and had 240 matching overlapping Monday rows, with its sole missing minute at Sep27 22:28 ET. These TWO source-recovery observations strongly support date-alignment affecting the original Monday–Sunday historic REST request population; **the universal vendor implementation/date-filter guarantee is still UNKNOWN**.

The union of ALL accepted historical original SOXX REST receipts now contains **NINE original receipt contexts** with **14,038 source rows across receipts**, **480 timestamp overlaps**, and **13,558 DISTINCT original UTC minute starts**. These raw records are neither 14,038 independent price observations nor new strategy entries. The original archival receipt SHA identities, source capture vintages, price values and rights are preserved separately.

## 4. Coverage consequences, retained uncertainty and next source work

The original 25 Mon–Thu near-full/full overnight nights retain the already accepted **11,666/12,000** minute-slot clock, **334 gaps**, 291/400 strictly complete 30m source windows, and 39/100, 12/50, 12/50 overnight-only complete 2H/3H/4H source windows. They are unchanged by this Sunday-only request. The two independently source-recovered Sunday night clocks now add Sep27 **479/480** and Oct11 **480/480** (959/960 total across these two nonweekday starts). Thus 27 inspected normal nightly starts have **12,625/12,960** source-minute slots, including **335 missing**. These are source clocks, not independent SOXX 3H parent-turn events, marketable fills, or completed 52-RTH-hour outcomes.

Known OTHER nonholiday Sunday first-halves still missing in the seven original Monday–Sunday week receipts: **Aug30, Sep13, Sep20, Oct4**. **Sep6 evening was OFFICIALLY CLOSED on Blue Ocean's 2026 Labor Day holiday schedule**, so its zero rows are not a missing trading night. The original venue holiday proof is external; weekday-only source classifiers cannot certify all other holiday exceptions. Existing original device/source controls and all 9 accepted request/receipt/L1 effects must remain the one archival authority.

**Next efficient source action:** use the original one-task source planner for **SOXX Sunday Oct4–Monday Oct5**, source plan digest **cc523faefb25fda12ec558c2087cc66aba0768cea000044ba7eb52d0c3d5bf7c** (previously prepared offline). It is a new deliberately overlapping original request context and requires current operator credential/quota/source rights/writer admission. On an actual new response, materialize only once, independently read its original L0/L1, compare overlapping old Monday OHLCV PRIVATELY via V31, quarantine mismatches, and report genuinely new Sunday clock minutes. No automatic source splice.

For NEW EARLIER, completely uncollected months, the original planner's **Sunday–Saturday 2026-08-02 to 2026-08-29** four-week source request batch has offline digest **adce4ddf294f52be94445019f5a3fc0ad33ecf3455b9deedeac2f8ce5a4d74c5**. It remains NOT EXECUTED; historical source depth, first served date and previous year coverage are not established by the existence of this plan.

**End-state now proven:** original Sunday first-half historical SOXX data CAN be recovered by targeted Sunday-start REST source contexts, with unchanged original overlapping Monday 1m OHLCV for both tested source dates. **NOT proven:** PIT market price vintages, legitimate historical bid/ask/size, true every-minute trade liquidity, original RTH-aligned strategy input/followthrough or independent prospective SOXX economic utility. No trading actions, live orders, price-level signals, collector replacement or merger are authorized by this report.

Result: V32_ORIGINAL_SUNDAY_NIGHT_SOURCE_480_OF_480 / NEW_ORIGINAL_MINUTE_TIMES_240 / V31_OVERLAP_240_OF_240_EQUAL / NINE_RECEIPTS_13558_UNIQUE / RESEARCH_INSPECTION_ONLY.
