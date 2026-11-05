# Second real SOXX BOATS historical receipt: October 5–11 requested week

**Source qualification:** real, original Tiingo BOATS HTTP 200 receipt and independently verified original Macro L0→L1 reader. **No new vendor calls by the research session; no historical SOXX backtest rerun; no trading activation.** Observation date October 15, 2026 UTC. This is a second, disjoint REST vintage for technical liquidity/session research, **not a forward holdout**.

## 1. Original manual operator acquisition and immutable source

The human operator executed the PREVIOUSLY APPROVED one-request canonical collector on the M2:

\`python3 -m scripts.tiingo_ingest collect --sources boats-bars --symbols SOXX --start 2026-10-05 --end 2026-10-11 --max-requests 1 --pause-seconds 1.25\`

Original observed command response: **attempted=1, ok=1, new=1, failed=0, row_hints=2148, bytes=229953, errors=[]**. The research session independently found exactly one new SOXX \`boats-bars\` receipt with HTTP **200**, canonical request path \`/boats/SOXX/prices?columns=open,high,low,close,volume&endDate=2026-10-11&resampleFreq=1min&startDate=2026-10-05\`, captured at **2026-10-15T06:23:10.923021Z**.

- Original raw source SHA256: **\`1c2a544683a9c270183b52213bdf1445655b237957003ae2e47f40772fcde885\`**
- Original immutable source receipt ID: **\`7dca959c29ee6735307523c40f6d52aa30412473ebbb757ad40cbbda6eb93a11\`**
- Existing L1 2,148-row Parquet SHA256: **\`ef487963685b57b873d13716c9b80452d039beff793b2d1164db363fa4b7cf9e\`**, 42,970 bytes
- Canonical materialized manifest SHA256: **\`4ee28a91a5b410b8a9e364d25df06ab963c79cb93bbf3c75910a1c839318ab28\`**

The **original** \`scripts.tiingo_materialize.materialize_one\` passed \`WOULD_WRITE,rows=2148\` with both target paths previously absent, then executed exactly one \`WRITTEN\` research-only L1 materialization. The **original** \`lib.dataos.tiingo_reader.read_research_view('boats-bars','2026-10-15',source_sha,purpose='INSPECTION',max_rows=3000)\` verified original raw source hash, receipt identity, original-to-L1 projection, Parquet hash and manifest, and accepted exactly **2,148 rows**. Original local research store: \`/Volumes/Mastermind/market-data/tiingo\`. No alternate Data OS, new collector, external source probe, original receipt overwrite or raw price publication.

Admission remains: **\`pit_backtest_eligible=false\`, \`dataos_identity_admitted=false\`, \`redistribution_admitted=false\`**, venue **BOATS single ATS, not NBBO**; no executable quote fill or price vintage acceptance.

## 2. Original session-clock coverage — dates are overnight starts in Eastern Time

The unchanged original \`fullsession_v12/tiingo_canonical_consumer_v13.py\` took the new SHA, original receipt ID, capture cutoff \`2026-10-15T08:00Z\`, and the true 20:00–04:00 America/New_York date windows. **Exit 0, 2,148 source rows, 64 strict complete 30-minute timestamp bars, 8 partially populated 30m buckets withheld.**

| Eligible BOATS overnight session (ET start) | Source 1m bars | Expected | Missing | Original complete 30m timestamp buckets |
|---|---:|---:|---:|---:|
| Sunday Oct 4 | **240** (00:00–04:00 half only) | 480 | 240 | 8 |
| Monday Oct 5 | **479** | 480 | 1 | 15 |
| Tuesday Oct 6 | **474** | 480 | 6 | 14 |
| Wednesday Oct 7 | **477** | 480 | 3 | 13 |
| Thursday Oct 8 | **478** | 480 | 2 | 14 |
| **TOTAL OBSERVED** | **2,148** | **2,400** for the five listed sessions | **252** (240 boundary + 12 weekday gaps) | **64** |

Among the four near-full Monday–Thursday sessions, **1,908/1,920 minute slots** were present and **12** had no row. On Tuesday Oct 6, **five of six** absent minutes occurred in the *first six minutes after the 20:00 ET opening*. This is a critical guard against imputing the 20:00 BOATS entry/opening price. Do not ascribe missing rows to vendor malfunction, zero trade or closed market without a separately qualified source/venue calendar.

The initially requested **Friday Oct 9 20:00 and Saturday Oct 10 20:00 ET** windows are **not scheduled BOATS trading sessions**, per the venue's Sunday–Thursday 20:00 ET schedule (see https://my.blueocean-tech.io/faq/how-does-blue-oceanats-operate ); those must **not** be counted as 480-minute market-data failures. The next **Sunday Oct 11 evening** is scheduled but was not within this source's returned overnight starts; prior \`2026-10-12..13\` receipt proves only 240 of that night, not an entire Sunday-night market history. This is **original session-classifier weekday evidence**, NOT a certified holiday/NYSE TRF close calendar. No unsupported calendar has been invented.

## 3. Volume support — source candles are not trade-executable prices

Ran existing published V29 \`audit_volume_support\` with an **exact, bounded weekday/scheduled-night gate repair** (same canonical original \`fullsession.classify_session\` and original 1m→30m resampler, no new holiday calendar). It reported:

| Night ET start | Positive-volume 1m bars | Zero-volume 1m bars | Zero-volume but nonflat high–low | Complete 30m clock bars containing one or more zero-volume input minutes |
|---|---:|---:|---:|---:|
| Oct 4, partial | 174 | 66 | 62 | 8 / 8 |
| Oct 5 | 314 | 165 | 157 | 15 / 15 |
| Oct 6 | 301 | 173 | 165 | 14 / 14 |
| Oct 7 | 296 | 181 | 157 | 13 / 13 |
| Oct 8 | 347 | 131 | 116 | 14 / 14 |
| **Total** | **1,432** | **716** | **657** | **64 / 64** |

There are **zero** strict 30-minute bars in this returned source for which every constituent 1-minute bar reports positive volume. This is a *caution*, not proof that every 30m vendor bar is false or unmarketable. Tiingo's official BOATS OHLC documentation defines historical \`volume\` as shares traded on BOATS, but does **not** explain the observed nonflat OHLC with zero reported shares. Do not infer the price arose from trades, midpoint, quotes or carry-forward without proof. https://www.tiingo.com/documentation/boats

The audit returns \`SOURCE_CADENCE_AND_VOLUME_DESCRIPTIVE_ONLY\`, **never** source-price marketability, NBBO, PIT, redistribution, broker execution or independent strategy performance. Recorded counts originate from accepted private L1 rows, **no licensed OHLC price or individual transaction was emitted**.

## 4. Cross-receipt time membership, no new economic episodes

Compared only the **original UTC minute timestamp sets** between the new **2,148-row** Oct 5–11 receipt and previously accepted **720-row** Oct 12–13 receipt (capture vintage one hour earlier on October 15). There are **zero shared timestamps** and **2,868 total unique source minute starts**, with this union of Eastern-session *membership counts only*:

\`Oct 4:240; Oct 5:479; Oct 6:474; Oct 7:477; Oct 8:478; Oct 11:240; Oct 12:480.\`

No price, adjustment basis or actual-event records were mixed across original receipts, stitched or re-exported. This is only evidence of disjoint source timestamp coverage; before any actual cross-receipt historical indicator one must separately qualify correction/PIT vintages and true contiguous session provenance. Both source windows precede the frozen prospective **Oct 14, 2026–Apr 13, 2027 ET** entry window. They are **not independent future trading outcomes**, do not add original 3H-parent episode labels, and do not solve historical BID/ASK marketability.

## 5. Narrow implementation repair made by this source discovery

The originally published V29 completeness audit could treat a requested Friday or Saturday night as **480 missing market-data minutes**, because \`tiingo_l1_v13.audit_overnight_nights\` blindly measures any requested date. Added an explicit *refusal* for clearly closed Fri/Sat night starts using the **existing** \`fullsession.classify_session\` at the 20:00 ET start. **Two synthetic tests reproduced false failure classification before implementation**, then 19/19 focused tests passed after repair. A Sunday-night test remained accepted. No separate calendar, quote source or new producer.

The new V29 weekday gate explicitly says **\`ORIGINAL_FULLSESSION_WEEKDAY_NOT_HOLIDAY_PROOF\`**: an actual holiday or TRF closure still requires the incumbent venue/calendar proof; the researcher must not infer a true session merely because the weekday is normally open.

## 6. Exact next action

Retain original two unique source receipts and materialized source digests. **DO NOT RE-REQUEST** October 5–11 or October 12–13, do not rerun frozen v2–v24 historical strategy studies, and do not infer fills from any 1m/30m OHLC bars.

If an operator has current original account admission/rights/quota, the next **disjoint** one-request acquisition for *historical warmup* is **September 28–October 4, 2026**, \`boats-bars SOXX 1min OHLCV\`. Follow the existing source's \`collect --max-requests 1\` and the original L0→L1→v13→V29 proof after new source receipt. The request is **not executed here**. Longer 2025–26 source history remains unknown; BOATS retail API launch July 2026 does not itself prove provider's earliest served OHLC. The independent strategy performance still awaits a full PIT-qualified historical source and executable-no-fill bounds, and the new Oct 14 prospective window through complete original 52RTH-hour outcomes.

**Result class:** \`REAL_SOURCE_2148_ROWS_VERIFIED / FOUR_NEAR_FULL_NIGHTS / NO_ALL_POSITIVE_VOLUME_30M / V29_WEEKEND_REPAIR_TESTED / RETROSPECTIVE_SOURCE_ONLY\`.
