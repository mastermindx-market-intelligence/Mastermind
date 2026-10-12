# Canonical Macro Tiingo reader → SOXX BOATS research consumer: actual evidence

**October 11 ET / October 12 UTC, 2026.** Production data owner: Macro Data OS; research code owner: Mastermind PR #1338. No new market-data collector, API credentials, live service mutation, trading, or raw licensed data redistribution.

## Real read path and source identity

An independent, sparse, *read-only source checkout* of Macro main at `1f25c4abd1eae583d4166c7b970e70aabea95377` was used on M2 with the existing immutable Tiingo archive. The exact integration used canonical:
`lib.dataos.tiingo_reader.read_research_view("boats-bars", "2026-10-11", raw_sha256, root=existing_archive, purpose="INSPECTION", max_rows=2000, check_mount=True)`
→ the v13 `l1_to_bars` receipt/capture/provenance checks
→ `audit_overnight_nights` and `resample_complete_30m`.

The first live owner historical capture is AMD `ae742fbb3d8427d25c200104070c17d7b332c8be6d6250306b31560383389d03`, 720 vendor one-minute rows. Oct 8 20:00–Oct 9 04:00 ET: **480 of 480 required minutes**, 16 complete 30-minute candles. Its Oct 7 preceding night is partial 240/480. Across all captured nights, 24 30-minute bars are complete.

The other historical capture is AAPL `e279bcc1ffe5230a5d1bdb40d6ec1e5ac3e0302f8997a2def0848db7d4a7ed85`, 687 one-minute rows. Oct 8 night: **462/480**, missing 18; Oct 7: 225/480. The consumer withheld 12 partial 30-minute buckets and emitted 12 complete buckets across both partial nights.

The exact owner reader, not direct unsupported Parquet decoding, successfully verified source receipt and original raw-body/L1 projection lineage for both captures. No licensed bar values were transmitted from M2 into the repository.

## Reproducible bounded invocation

The CLI `fullsession_v12/tiingo_canonical_consumer_v13.py` accepts an **existing exact historical receipt SHA**, one source observation day, a vendor symbol, an explicit capture cutoff and requested ET night dates. Run with a working `PYTHONPATH` containing current Macro Data OS source plus this research directory. It invokes **no API**, writes no new archive data, and produces only a redacted aggregate JSON coverage report. It refuses missing/mismatched source, invalid rights/PIT flags, mixed capture vintages, nonnumeric or imprecise volume, unknown market sessions and inconsistent capture clocks.

Tests: original v12 26 + v13 L1 15 + new CLI containment 4 = **45 distinct passing unit tests** across the verified research source. Canonical M2 real-archive invocation succeeded independently for both instruments. The exact metadata-only outputs are in `fullsession_v12/evidence` and claim zero exported market rows.

## Remaining SOXX and trading gates

The inspected existing archive contains historical `boats-bars` receipts for AAPL/AMD, **not** historical SOXX BOATS bars for the requested year. SOXX appeared only as seven T and zero Q in an opening burst of separate native Q/T/B firehose data; this is not a gap-free quote history. Historical Tiingo REST OHLC does not supply old order-book bid/ask execution. The archive's source rights flags explicitly withhold redistribution/PIT claims. No continuous 24-hour indicator/quote study, actual fills, accepted profit edge, new vendor-probe authorization or production launch has occurred.

**Research acceptance remains blocked on a licensed, actual SOXX BOATS historical minute-series and sufficiently granular daytime series with matched adjustment/capture basis, plus historical marketable quote records or a separately stated no-fill bound.** Existing Macro Data OS remains the only Tiingo source collector/authority.
