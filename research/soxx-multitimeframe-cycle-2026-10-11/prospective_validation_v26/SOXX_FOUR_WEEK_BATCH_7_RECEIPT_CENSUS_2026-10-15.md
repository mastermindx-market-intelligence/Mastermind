# SOXX four-week BOATS acquisition and seven-receipt source census

**Observed October 15, 2026 UTC. Evidence class: ORIGINAL SOURCE INSPECTION, NOT PIT BACKTEST, EXECUTABLE PRICE, OR LIVE TRADING.**

The original human operator ran the previously frozen SOXX boats-bars 1m OHLCV acquisition for August 31–September 27 in one bounded four-request operation. It returned **4 attempted, 4 HTTP200 OK, 4 new, 0 failures, 8,075 hinted rows, 862,256 raw bytes**. These four original sources were independently located on the original M2 4 TB drive and verified by the existing Macro Data OS receiver, receipt validator, materializer, and research reader. The assistant made **zero** new authenticated vendor calls.

## 1. Exact original receipts and L1 evidence

| Original request period | Verified original rows | Raw SHA256 | Original receipt ID |
|---|---:|---|---|
| Aug 31–Sep 6 | 2,047 | cb9445702f8bd2ddf23c76b58fb0223af2897650bf7eb78dce045895a609a79b | e3b72d7d321be9bd07e84672d1f943a3d99f78106bcdaed07a62173f8ca606b9 |
| Sep 7–13 | 1,898 | f71d2228017a210ce3fffd9e9b4c9548efb12b1f28d6a0c5181cf82e6c6611d2 | ab84c447d13565c0f67282853d36213f9ac6817df12190ecd7e29c3c639a99f6 |
| Sep 14–20 | 2,130 | c2bab8702ed3a6b061427fbff4b96b54e042016e2617b9366eafb7268da815c2 | 82031eb55d1cdc0fae71c26268f7e85c5d350591643048298c8744e074bbe548 |
| Sep 21–27 | 2,000 | ba80ee49d175b5c66ea0330897b5a9f65a56226e2eb85a8f677a6a89597f2850 | 596fce5e565dcb7acb071e630a4dfffb1c0a148c83e2544b9f6fe39eca5ba766 |

Captured October 15 UTC between **07:55:37.357813** and **07:55:43.244794**. Original producer git SHA: **2a08250fe61aa59ad3e1581149f0b93e9d5a17cf**. All four source receipts were unique, authentic to the existing archive receiver and returned original HTTP 200. Exactly four materializer dry-runs returned WOULD_WRITE with no existing L1 targets. The **same original materialize_one writer** then created each Parquet/manifest ONCE, sequentially, and the original **read_research_view** independently reverified L0 raw source, receipt identity, Parquet digest and raw-to-view row equivalence.

| Original request | Materialized Parquet SHA256 | Manifest SHA256 |
|---|---|---|
| Aug 31–Sep 6 | 63b052183edad5375ba5f88674b45d147ef76e200e41986c35902f7b880f89df | 26d005fbc732249b270fffce5cf29a312e61b8d2059b26036dac7c01fd594a17 |
| Sep 7–13 | e158dac8390edfe9b8ace78e333db92a1256587e23188bb52cb11aa1002bc36d | 5d22b16d72c025435220c32050c34b4467914633b125dfa93762da58feeb10b3 |
| Sep 14–20 | b8b8a460a74863d32fd24576ae42b28c0ad1e7dbf973dcb184aafa9df701abb3 | cece4f64cc74dba2833c33ee3e9b062ba598fec96a2af9e166c17e3e49fd86bf |
| Sep 21–27 | 40b4206fc4cd2e2dc96f6f003575c2c97ff5c5dd69e177954300da5ef499e279 | ae1dd4b424ea8c885c36f27bbb0b2d9ae63092e40a4b0324b0aa3b2806ab03f4 |

All four source manifests correctly retain **pit_backtest_eligible=false**, **dataos_identity_admitted=false**, and **redistribution_admitted=false**. Single-venue BOATS OHLC is neither consolidated national best bid/ask nor a broker-executable trade replay. Original price rows, licensed raw payloads, API keys, order instructions and user account identifiers remain PRIVATE.

## 2. Original overnight source quality

The original fullsession timezone and V29/V30 audit functions were executed against each separate verified receipt, never stitching incompatible historical price vintages or calculating a new trading signal.

| New source nightly start ET | Original source 1m rows / 480 | Complete original 30m timestamp buckets |
|---|---:|---:|
| Aug 31 | 436 | 4 |
| Sep 1 | 469 | 11 |
| Sep 2 | 454 | 7 |
| Sep 3 | 470 | 8 |
| Sep 7 | **480** | **16** |
| Sep 8 | 470 | 10 |
| Sep 9 | 469 | 12 |
| Sep 10 | 479 | 15 |
| Sep 14 | 466 | 9 |
| Sep 15 | 477 | 13 |
| Sep 16 | 470 | 12 |
| Sep 17 | 478 | 14 |
| Sep 21 | 479 | 15 |
| **Sep 22** | **332** | **0** |
| Sep 23 | 479 | 15 |
| Sep 24 | 474 | 12 |

These **16 normally scheduled Mon–Thu overnight starts** have **7,382 of 7,680 original minute timestamps; 298 missing slots**. The four original weekly responses also contain boundary Sunday-night Monday-morning fragments: **Aug 30 218**, **Sep 13 239**, **Sep 20 236** one-minute rows, making **8,075** in total. Empty Sunday **Sep 6** is **NOT a source failure**: the official Blue Ocean ATS 2026 holiday calendar explicitly lists **Sunday September 6 Labor Day closure** at https://boats-pub-website-wordpress-prod.azurewebsites.net/trading-updates/ . This is a source-attributed one-date historical exclusion, not a new holiday/calendar control plane.

Across the **8,075** newly accepted rows: **5,662** reported positive venue volume; **2,413** reported zero volume; **2,106** had both zero reported volume and nonflat OHLC. The existing V29 audit reports **188** timestamp-complete 30m buckets but only **10** containing exclusively positive-volume original 1m inputs. The V30 overnight-only source observer found **23** completed 2H, **7** completed 3H and **7** completed 4H original-source windows including partial Sunday boundaries. Only **one** such 2H block had all constituent minutes with positive reported volume; **none** of the complete 3H/4H blocks did. This **does not** imply all vendor OHLC are bad; price-construction semantics and trade execution remain unknown.

**September 22 is an anomaly:** 332/480 original 1m timestamps, so 148 missing. A separate exact source-clock audit measured **93 distinct missing timestamp runs distributed across all eight overnight hours** (largest 6 minutes), unlike adjacent Sep 21 and Sep 23 (479/480 each). Its original week receipt has exactly 2,000 source rows, but other identical seven-day requests had MORE than 2,000. Therefore **no vendor 2,000-row cap, truncation or venue outage has been proven**; do not invent repairs, missing prices or fake RTH joins.

## 3. Seven historical receipts: current cumulative SOXX source frontier

Prior accepted user-operated SOXX sources contain **2,136 + 2,148 + 720 = 5,004** original minute times from the Sept 28–Oct 13 request periods. These four new sources add **8,075**. Independent exact-source reads confirmed **7 accepted original SOXX receipts, 13,079 distinct UTC minute timestamps, and ZERO duplicate minute timestamps across receipt contexts**.

For the **25 near-full/full Mon–Thu overnight sessions** (Aug31–Sep3, Sep7–10, Sep14–17, Sep21–24, Sep28–Oct1, Oct5–8, Oct12):

| Source evidence | Verified |
|---|---:|
| 1m timestamps present / expected | **11,666 / 12,000**, **334 missing** |
| Full 480-minute source-night timestamp grids | **2 / 25**: Sep 7 and Oct 12 |
| Source minutes with positive reported volume | **8,191** |
| Original 1m bars with zero reported volume | **3,475** |
| Zero-volume 1m bars with nonflat OHLC | **3,067** |
| Original 30m timestamp-complete windows | **291 / 400** |
| Complete 30m windows with ALL underlying 1m volume positive | **17 / 291** |
| Timestamp-complete overnight 2H input windows | **39 / 100** |
| Timestamp-complete overnight 3H input windows | **12 / 50** |
| Timestamp-complete overnight 4H input windows | **12 / 50** |
| Of completed HTF windows, every minute positive venue volume | **2H: 1 / 39; 3H: 0 / 12; 4H: 0 / 12** |

These are **source observations, NOT 25 independent original SOXX parent-turn trades**. The original frozen strategy's **3 observed RTH-hour decision** is not a 3H overnight time window. Historical source adjustment/PIT vintage, executable bid/ask order sizes, zero-volume OHLC construction, original 52-RTH-hour return maturity and live trading rights remain **UNPROVEN**.

## 4. Critical weekly-source boundary: no Sunday 20:00–23:59 ET data

The exact union of seven original source receipts has the following original BOATS Sunday overnight starts:

| Sunday ET | Sunday 20:00–23:59 source minutes | Monday 00:00–03:59 source minutes | Interpretation |
|---|---:|---:|---|
| Aug 30 | 0 | 218 | Partial source night |
| Sep 6 | 0 | 0 | **Official venue holiday closure** |
| Sep 13 | 0 | 239 | Partial source night |
| Sep 20 | 0 | 236 | Partial source night |
| Sep 27 | 0 | 240 | Partial source night |
| Oct 4 | 0 | 240 | Partial source night |
| Oct 11 | 0 | 240 | Partial source night |

The six non-holiday eligible Sunday evening starts all have **zero archive minutes before midnight ET**, despite most of their Monday early-morning halves being present. This is a systematic **four-hour historical acquisition/response coverage hole at every ordinary weekly boundary**. It might relate to REST date selection/venue date filtering, provider historical availability or another cause; the exact explanation is **NOT PROVEN**. Do **not** present Sunday 00:00 as the true 20:00 opening or infer that the ATS was closed in these six cases.

### Targeted, independent one-request falsifier BEFORE scaling further

The already installed original pure Tiingo planner generated a distinct, bounded **SOXX Sunday Sep 27–Monday Sep 28 historical 1min REST** request with original plan SHA256:

**186eee89dee9e3ecec666a22cde909785ba345df63bf1896ae15cdfde59aacd0**

This is **NOT YET DISPATCHED**. Unlike another identical seven-day call, it is a deliberate source-date-boundary diagnostic: see if this newly specified source request includes Sunday Sep27 20:00–23:59. Because Sep28 portions intentionally overlap the previously accepted Sept28–Oct4 source, preserve the new response as a **separate original receipt and observed vintage**, and compare overlapping timestamps/economic values **privately through the original receipt-bound research reader**. Any disagreement must remain quarantined, not silently spliced or certified PIT. If the new request does not recover the four-hour first half, no missing bars or vendor explanation should be invented.

The original pure planner separately generated a four-request **Aug 3–30 SOXX** backfill (Aug3–9, Aug10–16, Aug17–23, Aug24–30), SHA256 **b7b786b19d5870fdce89aac2f164586b96d0595608f5e9d35d3db71551469415**, which is ALSO NOT DISPATCHED. Consider that source expansion after the Sunday boundary question is reconciled, not in parallel on another host or account.

## 5. Effects / carry-forward

**DONE:** four new original human-operated source receipts verified; four canonical original one-time L1 writes completed, hashes and readback accepted; V29/V30 nightly audits; seven original receipt timestamp union; official Sep6 holiday exclusion; 93-run Sept22 gap audit; Sunday four-hour per-week source hole established; two original offline future request plans retained. **DO_NOT_REDO ALL SEVEN accepted vendor requests and their L1 source writes.**

**Remaining:** original source rights/PIT price-vintage admission, normal-holiday special calendar proof, true source-marketability and zero-volume OHLC semantics, meaningful full 24-hour sessions and subsequent unseen strategy return/fill outcomes. The frozen 91-episode inspected development data and unresolved original accounting-review worker are untouched. No new assistant provider calls, trading, model sizing, new collector, duplicate reader or production deployment.

**Result:** SEVEN_REAL_SOXX_BOATS_REST_RECEIPTS / 13079_ORIGINAL_MINUTE_TIMES / 25_CORE_NIGHTS_WITH_334_SOURCE_GAPS / SUNDAY_EVENING_BOUNDS_UNQUALIFIED / NO_PIT_QUOTE_OR_TRADING_ACCEPTANCE.
