# Third real SOXX BOATS historical week — Sept 28 to Oct 4, 2026

**Research-only source acceptance**, October 15, 2026. This records the original human-operated ONE-REQUEST Tiingo historical BOATS acquisition on the existing mounted M2 4 TB drive and the independently reconciled original source. No vendor request was made by the research assistant, no private OHLC price/trade rows were published, no collector/calendar/price authority was duplicated, no trading occurred, and no inspected v2–v24 strategy/backtest was rerun.

## 1. Exact source receipt and immutable original L0 → L1 readback

The original collector command was:

\`python3 -m scripts.tiingo_ingest collect --sources boats-bars --symbols SOXX --start 2026-09-28 --end 2026-10-04 --max-requests 1 --pause-seconds 1.25\`

User's original successful result: **attempted 1; ok 1; new 1; failed 0; row_hints 2,136; bytes 228,741; errors []**. The independently retrieved original Tiingo receipt is **HTTP 200**, observed at **2026-10-15T07:29:32.102009Z**, explicitly bound to \`/boats/SOXX/prices?columns=open,high,low,close,volume&endDate=2026-10-04&resampleFreq=1min&startDate=2026-09-28\`.

| Original custody evidence | Exact result |
|---|---|
| Original raw source SHA256 | \`f01d2d4ada743310eacc1b0b557342371e62351584d388dbf813d1543a4415e6\` |
| Original source receipt identity | \`caaa9e4ab4cf1f040dd2bb972e25959bce60bc9716058dd8b9edb0eb3f429822\` |
| Original raw uncompressed response bytes | **228,741** |
| Canonical original materialized Parquet SHA256 | \`a2ab8c769a700f3f4bd5c75ddce8516b2ed99655e7d53818b72d9b4f5a459ce7\` |
| Parquet byte size | **45,076** |
| Materialized manifest SHA256 | \`9ebf258a467c3c0f359c8d26fd4e95a0c0de4d046611b7afb05c0c0f151ffe46\` |
| Verified original rows | **2,136** |

Original mounted archive: \`/Volumes/Mastermind/market-data/tiingo\`. The existing incumbent \`scripts.tiingo_materialize.materialize_one\` first returned **WOULD_WRITE** with the two exact output files not present, then ran **exactly once** and returned **WRITTEN 2,136**. The existing original \`lib.dataos.tiingo_reader.read_research_view('boats-bars','2026-10-15',raw_sha,purpose='INSPECTION',max_rows=3000)\` independently reverified raw SHA, source receipt/context identity, 2,136 original-to-L1 projected rows, Parquet content digest and manifest flags.

**Admitted use remains INSPECTION ONLY.** The source explicitly has \`pit_backtest_eligible=false\`, \`dataos_identity_admitted=false\`, \`redistribution_admitted=false\`, vendor venue scope \`BOATS single ATS\` (not NBBO). No original historical publication/correction vintage, marketable bid/ask size/fill or order execution is certified. This is the **third successful original SOXX source receipt**, not a previously missing source and not an independent prospective outcome.

## 2. Original session completeness — no invented opening bars

Original byte-matching \`fullsession_v12/tiingo_canonical_consumer_v13.py\` on this precise source digest/receipt/cutoff **2026-10-15T08:00Z** returned exit 0, source rows **2,136**, **54** complete, exact-thirty-row 30m source-timestamp buckets and **18 incomplete 30m buckets withheld**.

| Overnight start in New York local time | Observed 1m timestamps | Expected for this night | Missing | Complete original-source 30m buckets |
|---|---:|---:|---:|---:|
| Sun Sept 27 (source-boundary partial midnight–04:00 only) | 240 | 480 | 240 | 8 |
| Mon **Sept 28** | 478 | 480 | 2 | 14 |
| Tue **Sept 29** | 470 | 480 | 10 | 10 |
| Wed **Sept 30** | 473 | 480 | 7 | 10 |
| Thu **Oct 1** | 475 | 480 | 5 | 12 |
| **Original receipt total** | **2,136** | 2,400 across these five source nights | **264** (240 boundary + 24 real weekday source gaps) | **54** |

The four near-full weekday nights contain **1,896/1,920 source minute timestamps**. The **24** actual missing minute starts, as New York time, are:

- Sept 28 night: \`Sept 28 20:07\`, \`21:47\` (2).
- Sept 29 night: \`Sept 29 20:59\`, \`21:32\`, \`23:48\`; \`Sept 30 00:05\`, \`00:17\`, \`00:20\`, \`00:32\`, \`03:52\`, \`03:54\`, \`03:55\` (10).
- Sept 30 night: \`Sept 30 20:08\`, \`20:32\`, \`20:59\`, \`21:40\`, \`22:45\`, \`23:28\`; \`Oct 1 03:38\` (7).
- Oct 1 night: \`Oct 1 20:19\`, \`23:54\`; \`Oct 2 00:38\`, \`00:50\`, \`03:51\` (5).

The source receiver cannot determine whether a missing minute represents no trades, missing/corrected vendor bar data, or a venue/source calendar discrepancy. In particular, missing **20:xx opening-minute** bars cannot be repaired by fabricating next-open prices. Friday Oct 2 and Saturday Oct 3 20:00 starts are **normally closed BOATS evenings**; they must not be counted as 960 absent trading-source minute rows. The true holiday/special-session calendar still requires outside original venue evidence; weekday classification is not universal calendar proof.

## 3. V29 reported trade-volume support — no fabricated fills

Used the existing published \`boats_volume_support_v29\` (including its already accepted fixed original Fri/Sat session gate) on only this original receipt's typed v13 source bars. Input population partition:

| Source-night start | Positive reported volume minutes | Zero reported volume minutes | Zero-volume bars with nonflat OHLC | Complete 30m clock bars containing zero-volume inputs |
|---|---:|---:|---:|---:|
| Sept 27 partial | 187 | 53 | 37 | 8/8 |
| Sept 28 | 394 | 84 | 77 | 14/14 |
| Sept 29 | 276 | 194 | 163 | 10/10 |
| Sept 30 | 380 | 93 | 60 | 6/10 |
| Oct 1 | 325 | 150 | 138 | 12/12 |
| **Total** | **1,562** | **574** | **475** | **50/54** |

Only **4/54** timestamp-complete 30m source buckets consist entirely of 1m rows with positive vendor-reported volume. None of that establishes whether the bucket's high/low or a hypothetical exit is a marketable transaction. The zero-volume/nonflat price mechanism is **UNQUALIFIED**, not automatically a vendor defect, confirmed quote construction or evidence of trade at extrema.

## 4. V30 2H/3H/4H source-window support

The previously accepted, unmodified V30 pure-time-window audit was run against this same original 2,136-row source. Actual **overnight-only** aligned full-window counts:

| Night | Complete 2H source-input windows (of 4) | Complete 3H (of 2) | Complete 4H (of 2) |
|---|---:|---:|---:|
| Sept 27 partial | 2 | 0 | 1 |
| Sept 28 | 3 | 1 | 1 |
| Sept 29 | 0 | 0 | 0 |
| Sept 30 | 1 | 0 | 0 |
| Oct 1 | 0 | 0 | 0 |

The four near-full nights give **4/16 2H**, **1/8 3H**, **1/8 4H** source-complete overnight windows. **Zero** completed 2H/3H/4H source-input windows consist entirely of minutes with positive reported venue volume. The trailing two hours of an 8h overnight session do not count as a full 3H candle. This is **NOT** the original strategy's three observed **RTH** hours and does not generate 2H/3H/4H MACD, Stoch RSI or RSI signals.

## 5. Three-receipt immutable source frontier, checked without mixing prices

The previously accepted SOXX sources were:
- Oct 5–11 requested period: **2,148** rows; raw SHA256 \`1c2a544683a9c270183b52213bdf1445655b237957003ae2e47f40772fcde885\`.
- Oct 12–13 requested period: **720** rows; raw SHA256 \`ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e\`.

The two earlier accepted receipts contributed **2,868** distinct original SOXX source-minute timestamps. Three independent exact original-source receipt reads, comparing **only UTC timestamp identity**, then proved **zero duplicated minute timestamps across source receipts** and **5,004 distinct SOXX 1m source times** (2,136 + 2,148 + 720). No source OHLC prices were spliced or exported; each receipt retains its own archival timestamp, request context, adjustment and source-vintage claims.

Across the **nine near-full or full eligible weekday nights** (Sept 28–Oct 1, Oct 5–8, Oct 12), the original source record contains:

| Fixed source support | Verified count |
|---|---:|
| Original 1m starts / expected | **4,284 / 4,320**; 36 missing |
| Original minute bars with positive reported volume | **3,061** |
| Original zero-volume minute bars | **1,223** |
| Zero-volume minute bars with nonflat OHLC | **1,082** |
| Strict timestamp-complete 30m bars | **118 / 144** |
| Strict 30m time bars entirely positive-volume constituent minutes | **7 / 118** |
| Complete overnight-local 2H source windows | **17 / 36** |
| Complete overnight-local 3H source windows | **5 / 18** |
| Complete overnight-local 4H source windows | **5 / 18** |
| Higher-timeframe windows with every minute positive-volume | **0 at 2H, 3H, and 4H** |

The other **three source-boundary nights** (Sept 27, Oct 4, Oct 11) contribute 240 minutes apiece and are incomplete solely **within the retrieved receipt ranges**. This is not proof those true venue nights were closed or had no trades. Nine original-source night observations do not equal nine independent strategy entry/followthrough outcomes, and neither source quality nor mathematical price-bar completeness demonstrates a fundable order.

## 6. DONE / DO_NOT_REDO / next disjoint producer period

- **DONE:** third successful original operator Tiingo SOXX request; third immutable receipt/source identity; one existing original 2,136-row L1 materialization; independent original L0/L1 reader and v13/V29/V30 venue-session/volume/source-window audit; receipt overlap accounting.
- **DO_NOT_REDO:** same September 28–October 4 vendor call, re-materialization, accepted older two calls, repeated v2–v24 strategy backtests or archived short Q/T audit. Do not produce alternative credential/access/source/writer systems.
- **READY OFFLINE ONLY:** the original \`scripts.tiingo_ingest.plan_page\` can form exactly one **disjoint September 21–27, 2026** SOXX \`boats-bars\` 1m OHLCV request, with verified pure planner SHA256 \`aec4567db37217c405e999a4b8f85b54f07c7754b933de1bbbc9b1cbdfe0c5c6\`. It has **NOT** been dispatched or authorized by the planner. Execute only via the original admitted operator if current provider account/source rate and permissions permit, followed by existing source receipts and quality gates. No provider attempt/retry is necessary within this research-only read phase.
- The frozen independently preregistered **Oct 14, 2026–Apr 13, 2027 ET** original-parent entry window still has **ZERO mature, source-qualified independent economic episodes scored**. Historic BOATS OHLC remains **NOT PIT and NOT quote marketability evidence**, and a 52-RTH-hour stop/followthrough comparison cannot be built from only these overnight bars.

**Result:** \`THIRD_SOXX_ORIGINAL_REST_RECEIPT_ACCEPTED / L1_2136_ROWS / CORE_FOUR_NIGHTS_1896_OF_1920 / THREE_RECEIPT_5004_UNIQUE_SOURCE_MINUTES / NO_TRADING_ACCEPTANCE\`.
