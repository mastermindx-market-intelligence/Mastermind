# Direct 4 TB Tiingo/BOATS SOXX evidence — independent M2 read-only audit

**Observed:** October 14, 2026 Eastern / October 15 UTC (host-readback 2026-10-15T02:58:19Z). **Research status:** `PARTIAL_SOURCE_OBSERVATION; HISTORICAL_SOXX_BARS_UNAVAILABLE_IN_INSPECTED_CANONICAL_ARCHIVE`. This note is scoped evidence for the original SOXX research PR #1338, **not** a new Data OS archive, source registry, credential, producer, admission, collection job or live trading workflow. The current user explicitly directed independent examination of the existing 4 TB drive. All observations below were made directly from the M2 Studio and its already installed Tiingo research reader, without waiting for a Macro owner reply.

## 1. Actual drive and canonical archive, not an assumed location

M2 path: `/Volumes/Mastermind` on `/dev/disk11s1`. Verified disk capacity **3,725.83 GiB**, used **1,861.02 GiB**, free **1,864.81 GiB** (about 3.64/1.82/1.82 TiB), not an emulated test directory. Mounted Tiingo archive: `/Volumes/Mastermind/market-data/tiingo`; inspected its **raw, normalized, receipts, manifests** BOATS source-family directories. The physical mounted drive contains much more data than the BOATS archive; do not equate total disk usage to historical SOXX history.

The *exact current canonical Tiingo historical* `boats-bars` archive directory has one observed source-day folder, `2026-10-11`. Within it:

| Stored source | Historical REST response | Original requested historical range | Materialized 1m rows | BOATS source provenance |
|---|---|---|---:|---|
| AAPL | HTTP 200, observed 2026-10-11T17:51:08Z | 2026-10-08 to 2026-10-09 | 687 | Existing raw receipt, normalized Parquet and manifest |
| AMD | HTTP 200, observed 2026-10-11T17:51:06Z | 2026-10-08 to 2026-10-09 | 720 | Existing raw receipt, normalized Parquet and manifest |
| **SOXX** | **No historical receipt or materialized source** | **Not established** | **Not established** | **No SOXX historical `boats-bars` source** |

Both actual historical receipts specify `resampleFreq=1min`; their manifests report `pit_backtest_eligible=false`, `redistribution_admitted=false`, `dataos_identity_admitted=false`, and historic publication timing unverified. These aren't invalid receipts; they are **not accepted PIT/fill evidence** and neither is a SOXX source. The older accepted AAPL/AMD 480/480 and 462/480 single-night completeness findings remain separate from their two-day total row counts here.

This is **direct observation of the existing canonical BOATS-bars family**, not a claim that Tiingo the company has no additional history, that the account cannot serve SOXX, or that no unrelated permitted archive elsewhere contains SOXX. No denied broad RTH-family inventory was retried.

## 2. Actual existing BOATS live-capture evidence

The `boats-firehose` canonical archive contains raw capture source days **2026-10-11, 2026-10-12 and 2026-10-13**, **2 + 20 + 2,000 receipts** respectively. The days here are **UTC storage directory labels**, not necessarily local overnight trading dates.

| UTC source-day directory | Actual capture/receipt time envelope | Source message counts | Literal vendor `soxx` observations | Source coverage interpretation |
|---|---|---|---|---|
| Oct 11 | 2026-10-11T17:08:52Z, a few milliseconds | 2 control/other | 0 Q, 0 T | Handshake only; outside overnight session |
| **Oct 12** | **2026-10-12T00:00:10.173304–00:00:13.477090Z** (Sunday Oct 11, 20:00 ET opening) | **20,000 messages: 19,651 Q, 347 T, 2 other, 0 B** | **0 Q, 7 T, 0 B** | Only **~3.304 seconds** of receipt-time envelope, not full session |
| Oct 13 | 2026-10-13T00:00:19.596058–00:09:30.354887Z (Monday Oct 12, 20:00–20:09 ET) | **2,000,000 frames / 2,000 segments** | **2,926 Q, 142 T, 0 B** | Previously verified **~9m11s** only; not repeated here |

The October 13 SOXX result is **accepted earlier evidence**, from the original complete 63-report audit, retained private metadata SHA256 `10a38dfb96d485feda8745016ec12f6b7e6f8c62d19ab6baeff2b0db8d92ee17`; **no unchanged 2,000-capture repeat audit was run**.

The additional October 12 twenty-capture audit is **new independent direct execution** on the M2, using the actual installed incumbent reader function `lib.dataos.tiingo_boats_tape.audit_boats_tape`, verified source git blob `76bf3a6c723d5f2d80804336fe03a5da1d1c9d46` (Macro worktree SHA `2a08250fe61aa59ad3e1581149f0b93e9d5a17cf`). Exact twenty receipt reference set SHA256 (canonical sorted JSON day/SHA pairs): `6fca363ebbe33266b8e74f506d794d0e1ede79b4f4390cb8a2cb669665838ec0`. It returned **`OBSERVED_SOURCE_EVENTS_NOT_COVERAGE_PROOF`**, verified all 20 original compressed bodies and their normalized projections, and used `max_examples=0`: **no quotes, trade prices or licensed raw rows were exported**.

For those **seven October 12 SOXX trades**, the owner's bounded conservative same-receipt 1-second quote diagnostic reports **7/7 with no preceding same-segment venue quote**, **0** with a fresh quote, and **7** having unqualified sale-condition fields. It does not establish those trades were economically invalid; it establishes that this capture provides no qualified price/size marketability at the observed trade instants. Across all instruments the twenty receipts had 19 positive inter-segment receipt gaps and 0 detected intrasegment raw Q/T/B arrival regressions; **transport continuity, full-night coverage, consolidated NBBO, quote execution and authentic publisher-entitlement proof are all unproven** by this function.

A full BOATS night is **20:00–04:00 ET** (8 hours). The 3.304-second and 9m11s receipt envelopes each fall short of **one complete 30-minute candle**. An envelope is not an assertion of continuous source capture; even these short spans may include gaps. No 30m/2H/3H/4H/52-observed-RTH-hour SOXX BOATS outcomes can be scored from these fragments.

## 3. Explicit direct-source bounds and producer state

At host check **2026-10-15T02:58:19Z**, there was **no BOATS canonical source-day directory after 2026-10-13** for either historical `boats-bars` or `boats-firehose` on this mount. A read-only M2 `ps -axo pid,comm` executable-name filter and `launchctl list` label filter returned **zero matches for Tiingo/BOATS**. This does **not** prove no service is running on another host or under an unrelated process name. There is also no evidence here of a continuously enabled M2 BOATS capture that filled the missing nights.

A separate bounded shallow (maximum 3-level) filename-name check within the same mounted 4 TB drive's `data`, `Offloaded`, `artifacts` trees found no obvious BOATS/Tiingo/SOXX name match. The `research` tree scan hit a 5,000-entry cap and is explicitly **TRUNCATED**: therefore this is not a global negative proof and creates no permission to search the previously denied wider RTH receipt family.

The original broader RTH receipt-family inventory and authenticated source probe were previously blocked/refused and **were not retried** through an alternate route. This inspection never read API credentials, made an external vendor request, launched a collector, modified the 4 TB archive, changed a scheduler, copied licensed market rows or enabled trading.

## 4. Capability consequences and exact next permitted action

| Capability | Verified state |
|---|---|
| Existing mounted 4 TB Tiingo archive & receipt-bound reader | **PROVEN_LIVE for bounded internal read-only research** |
| Native SOXX BOATS venue Q/T presence | **PARTIAL** (October 12/13 short captured fragments only) |
| Historic SOXX BOATS OHLC/quote replay across the original inspected year | **NOT PROVEN / not present in the inspected canonical BOATS-bars receipts** |
| Full consecutive SOXX BOATS overnight sessions | **NOT PROVEN** |
| SOXX original-parent completeness and PIT adjustment/vintage | **NOT PROVEN** |
| Executable overnight SOXX sale prices/size and independent decision utility | **NOT PROVEN** |
| Merged Terminal BOATS Quote Hub source | **BUILT_NOT_PROVEN live**; distinct from historical archive |

**Next legitimate independent action** is **not** to run the old 91-episode study again. Inspect any **new, exact SOXX historical BOATS receipt** from the established Tiingo archive through its existing bounded `read_research_view(..., purpose='INSPECTION')` and receipt-hash contracts. If none exists, obtain an **actual qualified SOXX historical session** through the existing authenticated, rate/entitlement/rights-admitted producer when authorized and available—**not** by creating a second archive, credential route or collector or bypassing a prior request denial. A single sample night must qualify source completeness and marketability; no full-year inference or trade from seven uncovered prints.

Until there is a complete original SOXX parent-entry universe and independently unseen, fully matured 30m/3RTH-h paired outcomes with real fill/no-fill bounds, run V27's score **withheld**, not an assumed positive return. The frozen preregistered entry window is October 14, 2026–April 13, 2027 ET; the original historical year is inspected development evidence. No future trades or price levels were computed here.
