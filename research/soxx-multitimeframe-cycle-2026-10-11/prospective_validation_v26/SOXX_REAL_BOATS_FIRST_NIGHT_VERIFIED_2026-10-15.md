# SOXX real Tiingo BOATS REST: first historical full-night source acceptance

**Acquisition:** user-operated, *original incumbent* Tiingo collector, October 15, 2026 UTC. **Independent consumer / L1 qualification:** current Mastermind SOXX research session on the original M2 external archive. Status: **REAL_ORIGINAL_REST_RECEIPT + CANONICAL_L1_INSPECTION + ONE_FULL_NIGHT_TIMESTAMPS_PROVEN**; **NOT point-in-time, marketable quote fills, independent SOXX strategy validation, full-year BOATS history or production trading acceptance**.

This is evidence from the **actual first SOXX HTTP-200 REST response**, not another synthetic example or a second provider request. Prior original source study v2–v24, 91-episode research and accepted V26/V27/V28 results are frozen and not rerun. All private vendor OHLC prices and trade-by-trade rows stay within the original Macro Data OS archive. GitHub stores **only counts, status flags, digests, clock bounds and quality caveats**.

## 1. Original collector result and immutable source identity

User directly ran the already admitted Macro source command once, on the original M2 collector and mounted 4 TB drive:
\`python3 -m scripts.tiingo_ingest collect --sources boats-bars --symbols SOXX --start 2026-10-12 --end 2026-10-13 --max-requests 1 --pause-seconds 1.25\`.

User terminal returned **attempted=1 / ok=1 / new=1 / failed=0 / row_hints=720 / bytes=77,271 / errors=[]**. The consumer independently inspected the ORIGINAL \`boats-bars\` receipt dated **2026-10-15 UTC** and verified **HTTP 200**, \`source=boats-bars\`, \`symbol=SOXX\`, \`resampleFreq=1min\`, \`columns=open,high,low,close,volume\`, explicit Oct 12–13 request bounds and original raw bytes **77,271**. Actual immutable capture clock: **2026-10-15T05:19:25.281764+00:00**.

- Original uncompressed source SHA256: **\`ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e\`**.
- Original receipt identity: **\`a90016abfd49a712215bdea2d08a8fe81bb8c4f398e803472082d8289534c8df\`**.
- Canonical 720-row Parquet output SHA256: **\`30164abb1df917373b09db54418ad4052c3598f9716c8c985c96984faa775cfa\`**, 21,863 bytes.
- Materialized manifest SHA256: **\`c2be8fcf977f8322488d32cec159bee0ae52e28167e0cabc15e9c5916b9ed8fc\`**.

The installed original \`scripts.tiingo_materialize.materialize_one\` first passed dry-run status **WOULD_WRITE (720)** after rehashing the exact original raw response and receipt. A **single** original-producer L1 materialization then returned **WRITTEN (720)** for \`normalized/boats-bars/2026-10-15/{source_sha}.parquet\` and its matching original manifest. The output and manifest files did **not** exist before this phase. No collision, rewrite of an existing receipt, alternative Data OS or second source writer was introduced.

The **original canonical** \`lib.dataos.tiingo_reader.read_research_view('boats-bars','2026-10-15',sha,purpose='INSPECTION',max_rows=1000)\` independently reverified original raw-body hash, receipt identity, materialized Parquet hash, exact L1 row equivalence and all provenance fields: **720 rows accepted**. Status **RESEARCH_ONLY_VENDOR_SOURCE**. Its source/manifest flags explicitly remain **\`pit_backtest_eligible=false\`, \`redistribution_admitted=false\`, \`dataos_identity_admitted=false\`, \`is_nbbo=false\`, \`executable_price_proven=false\`**. Vendor historical publication/adjustment vintage admission is **UNVERIFIED**; these flags are not permissions or data-quality overrides. No credential value appeared in the assistant's tools or committed evidence. The user-operated original collector privately accessed its existing credential, as designed. The assistant made **zero additional external vendor requests**.

## 2. Verified SOXX overnight clock and completeness via the original source consumer

Ran the **byte-pinned existing** \`fullsession_v12/tiingo_canonical_consumer_v13.py\` (Git blob \`6b2ef150f7b37479445de65b357b4c9480da3265\`) against that exact original raw SHA and receipt, with true timezone-aware New York overnight windows and source cutoff **2026-10-15T06:00:00Z**. The matching \`tiingo_l1_v13.py\` blob was \`12c12e343a417410110405de6caeec8da9d92892\`. Returned **\`EXISTING_ARCHIVE_READ_ONLY_CONSUMED\`**, exit 0, with **zero vendor price rows emitted**, without re-requesting or re-materializing anything.

| Eastern overnight start / end | Observed unique minute starts | Expected | 30m buckets with ALL 30 one-minute source rows |
|---|---:|---:|---:|
| Sunday **Oct 11 20:00** → Mon Oct 12 04:00 | **240** (00:00–03:59 half only) | 480 | **8** |
| Monday **Oct 12 20:00** → Tue Oct 13 04:00 | **480** | 480 | **16** |
| Tuesday **Oct 13 20:00** → Wed Oct 14 04:00 | **0** (outside the fetched Oct 12–13 response period) | 480 | 0 |

The source contains exactly **720 unique, UTC-sorted and precisely minute-aligned rows**; no duplicate timestamps, invalid positive-price/finite OHLC fields or violated high/low ordering were found. Every row reports \`session=overnight\`, \`venue=BOATS\`, \`volume_available=true\`. The exact complete Oct 12 night runs from **2026-10-13T00:00:00Z to 07:59:00Z**. No implied daytime/RTH bars, stop fills, historical bid/ask, continuous trading or 52-RTH-hour outcome.

### Crucial: complete timestamp lattice is NOT a whole night of actual executed trades

A separate independent aggregate audit of the same *canonical read-only rows* found:

| Night | Minute bars with **positive reported volume** | Zero-volume bars | Zero-volume bars **with nonzero high–low price range** | Strict complete 30m buckets containing at least one zero-volume minute |
|---|---:|---:|---:|---:|
| Oct 11 (partial) | 141 | **99** | **94** | 8 of 8 |
| **Oct 12 (complete clock)** | **428** | **52** | **49** | **13 of 16** |

Across all 720 bars there are **151 zero-volume minutes**, **143** of which also have positive OHLC range, and 9 flat OHLC bars. For the full Oct 12 night, the longest consecutive run of zero-volume minutes is **4** and the largest zero-volume count in any 30m bucket is **10**. All 16 full-night 30m buckets contain at least some positive-volume minutes; **13 of 16** nevertheless depend partly on zero-volume source bars to appear minute-complete.

Tiingo documents \`volume\` in historical BOATS OHLC as **the number of shares traded on BOATS**: https://www.tiingo.com/documentation/boats . Therefore, a source row with **zero reported trades but nonflat high/low** cannot by itself prove that the depicted highs/lows were transaction-executable on the single ATS. The provider's specific no-trade/OHLC construction mechanism is **not established**; do **not** assert that every such row is a vendor bug or definitely quote-derived. Mark the issue **\`ZERO_VOLUME_NONFLAT_OHLC_PRICE_SEMANTICS_UNQUALIFIED\`**, not “good traded intraminute OHLC.” The source's \`afterHours\` compatibility flag never broadens BOATS beyond the native 20:00–04:00 ET window. No aggressive forward-fill was introduced by this research consumer.

The first **ten** Oct 12 20:00–20:09 ET historical bars all report **positive** volume (and 9 show positive range), consistent in timing with the **previously accepted**, *not rerun*, BOATS live Q/T capture (2,926 Q / 142 T over ~9m11s). This is **a time-window cross-check only**, not a trade-by-trade volume sum, direct quote join, deduplicated feed, verified sale conditions or historical executable price.

## 3. What this truly unlocks—and does not

**PROVEN:** The existing licensed-user Tiingo BOATS REST \`SOXX\` endpoint returned an actual HTTP 200 one-minute historical response; raw and normalized original-source hashes/receipt identity reconcile; one complete 480-minute overnight **timestamp grid** and 16 30m OHLC *source-presence buckets* are available in the original archive. The user no longer needs to ask another session to find their disk or create a new collector. This is **real source acquisition**, not an assumed entitlement.

**NOT PROVEN:** BOATS historical bid/ask/available-size at a contemplated sell instant, true transaction-supported highs/lows for zero-volume bars, verified historical publication/adjustment vintages, complete RTH + multi-night warmup, a full 2025–26 overnight year, independence of future time sample, PIT eligibility or any economic advantage from early exit. **One Oct 12 night is before the frozen Oct 14, 2026 prospective entry window**; it is not an independent SOXX holdout. The original 91-episode development result and v24 adverse-slippage losses remain unchanged.

**Capability states:** source acquisition **PROVEN_LIVE for one exact historical BOATS SOXX response**; original L0→L1 internal inspected data **PROVEN_LIVE for one receipt**; complete timestamp 8-hour overnight night **PROVEN for Oct 12 ET**; actual continuous execution-price/quote coverage **NOT PROVEN**; prospective independently scored cycle-failure **NOT PROVEN**; live trading **NOT ENABLED**.

## 4. Exact continuation frontier

1. **DO NOT REDO original 2026-10-12..13 SOXX REST request**; original raw SHA, receipt and materialized manifest are accepted. Reuse the above hashes/reader proof unless original producer logic/source bytes materially change. The user has already run the authenticated provider call once; never regenerate it or select another account because it succeeded.
2. For future additional historical nights/warmup, use only **new, disjoint time windows** on the same existing Tiingo collector, with its normal authenticated quota/rights/source-writer admission. An existing registered key and successful receipt do not authorize silent provider retries or an unbounded whole-year source crawl. Do not call the earlier platform-refused provider-auth action via alternate carrier.
3. After any new original BOATS receipt, consume it via \`read_research_view\` and the original \`tiingo_canonical_consumer_v13.py\`, preserving full session/no-trade/zero-volume anomalies. Report completeness of bar presence **separately** from positive-volume/tradable liquidity, and record correction/PIT vintage truth rather than manufacturing it.
4. Preserve both fixed 30m and 3RTH-hour prospective checkpoints, the original 3H parent-turn entry, 1.5% stop, quarter sold at +2%, 52 observed RTH-hour horizon, every original parent and every harm from profitable continuation. Do **not** score independent strategy performance until valid unseen paired outcomes have completed and executable/no-fill evidence is admitted.

There were **no historical strategy backtest reruns**, synthetic performance replacements, model-originated sizing, proprietary row publications, new collectors/schedulers, production service changes or live orders in this phase.
