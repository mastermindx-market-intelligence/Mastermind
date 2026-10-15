# V29 — BOATS minute-clock completeness versus reported trade-volume support

**Research-only quality guard**, not a new dataset, vendor collector, point-in-time admission, completed execution price or strategy improvement. This is a reusable pure observer for future independently acquired SOXX nights. It reuses the exact existing v13 \`fullsession\` session calendar and \`tiingo_l1_v13\` complete-30-minute resampler rather than creating a second clock, market identity, quote source or controller.

## Why this matters in the first actual SOXX night

The first actual Tiingo BOATS SOXX historical REST download is proven under [the original one-night evidence](SOXX_REAL_BOATS_FIRST_NIGHT_VERIFIED_2026-10-15.md), with source digest \`ea6392763b0ea148084c10bd1e98d42273a2479a7625993d5a87e6cad691486e\`. The canonical v13 consumer found **480 of 480 one-minute timestamp slots** for the Oct 12, 2026 Eastern overnight session and **sixteen complete 30-minute source-presence bars**. This does **not** mean every bar is supported by trade prints.

The actual, independently qualified L0/L1 source records exactly:

| Original source night (Eastern start) | Source 1m bars | Positive reported volume | Zero reported volume | Zero-volume 1m bars with changing high–low | Strict 30m **timestamp** buckets containing at least one zero-volume minute |
|---|---:|---:|---:|---:|---:|
| Sunday Oct 11 (partial 00:00–04:00 half only) | 240 | 141 | 99 | 94 | 8 of 8 |
| **Monday Oct 12 (complete overnight clock)** | **480** | **428** | **52** | **49** | **13 of 16** |
| Tuesday Oct 13 | 0 (not requested) | 0 | 0 | 0 | 0 |

Only **3 of 16** complete-clock 30-minute bars in the Oct 12 night consist entirely of one-minute inputs with positive reported volume. This is a **descriptive liquidity-support distinction**, not an assertion that the other thirteen candles should be deleted, that their vendor prices are invalid, or that those three are executable. The vendor documents historical BOATS \`volume\` as shares traded on the single Blue Ocean ATS, and \`OHLC\` as the selected historical price bars. It does not document why the observed source sometimes reports a moving high–low and zero shares; the mechanism could involve reference/quote/aggregation effects or something else. The exact historical trade-price meaning is **UNKNOWN**. Source: https://www.tiingo.com/documentation/boats .

The original v13 resampler properly tests whether all 30 minute rows are present. It does not promise trade-by-trade marketability. V29 preserves that intact and adds a separate, explicit **zero-volume/high–low anomaly** measure so future SOXX risk/cycle analyses cannot equate a filled time lattice with a historical executable order price.

## Implemented method and type boundaries

\`prospective_validation_v26/boats_volume_support_v29.py\` implements \`audit_volume_support(bars, night_starts_et)\` on the **already** source/receipt-verified original \`fullsession.Bar\` list. The user of this module must first invoke the existing incumbent \`read_research_view(... purpose='INSPECTION')\` and \`tiingo_l1_v13.l1_to_bars\`; this module **does not** authenticate source hashes, entitlement, rights or dataset identity independently.

- Reuses **the original** v13 \`audit_overnight_nights\`, \`resample_complete_30m\`, \`trade_date\` and \`classify_session\` and never constructs new 5m/30m candles, unstated sessions or price bars.
- Rejects mixed venue/symbol/time grains, split basis, unsorted or duplicated source-minute instants, invalid minute alignment, unrequested source nights and duplicate overnight requests. Its input \`fullsession.Bar\` already rejects impossible or nonfinite price source fields.
- Keeps **positive**, **zero** and **unknown** vendor volume distinct. Unknown volume is **not zero**. Reports count of zero-volume bars with nonflat OHLC and open/close difference, whole-minute clock coverage, originally completed 30m source buckets and how many 30m buckets contain positive, zero, unknown or overlapping zero/unknown support.
- All emitted fields are **counts, original session labels, descriptors, false admission flags and caveats**, never prices, market rows, trade sizes or licensed vendor outputs.
- **Always returns false** for historic bid/ask marketability, point-in-time admission, redistribution permissions and independent strategy performance; an all-positive-volume bucket is not a certified sale at its OHLC high/low.

## Verification

**Sixteen** targeted, self-contained synthetic unittest checks pass using the existing unmodified original v13 calendar/resampler. They cover full-night but all-zero-volume source, moving OHLC with zero shares, known/unknown volume, overlapping zero and unknown within a single 30m bucket, missing time slots, duplicate timestamps, ordering, symbol/venue/basis violations, off-minute clocks, absent or duplicate requested nights and always-false execution claims.

The exact new V29 code was also executed against the real, original **720-row SOXX receipt** through the incumbent Macro reader plus byte-matching original v13 \`l1_to_bars\` and the updated quality function. **All material Oct 12 source numbers above independently reproduced**. No new Tiingo request, archive write, licensed price export, backtest, changed strategy, broker call or implicit producer schedule was involved. The original collector's manual HTTP 200 response and earlier accepted 20,000/2,000,000 message audits were reused, not repeated.

## Where the mission goes next

This adds reusable source-quality diagnostics that should accompany all later historical SOXX BOATS receipts in the original v13 research lane. The next material frontier is **separate, previously uninspected actual overnight sessions and warmup**, the original 3H parent-turn RTH source population, verified historical publication/rights and executable BOATS bid/ask/size or honest unknown-fill bounds. The original fixed October 14, 2026–April 13, 2027 prospective entry window remains the independent test period. A complete October 12 price-lattice is **pre-window technical evidence only**, not strategy win-rate or proof to deploy.
