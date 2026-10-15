# Tiingo Data OS historical BOATS L1 read-only research adapter (v13)

This code **consumes existing receipt-bound Macro Data OS L1 rows**. It neither authenticates to Tiingo nor creates a data producer, archive, scheduler, a second quote owner, a paper fill simulator or a live trading algorithm. It is internal retrospective research; not authorization to redistribute vendor bars.

`tiingo_l1_v13.l1_to_bars(rows, symbol, expected_sha, receipt_id, observed_before_utc)` refuses wrong venue, duplicated/overlapping timestamps, source/receipt mismatches, mixed capture vintages, inconsistent volume, mislabeled split adjustment or false PIT/rights/quote-fill claims. It outputs only raw-basis BOATS bars with explicit receipt provenance.

`resample_complete_30m` constructs only thirty-minute bars with **all 30 one-minute inputs**; missing minute observations cause that 30-minute bucket to be withheld. `audit_overnight_nights` separately evaluates the full **20:00–04:00 ET** night denominator. Neither proves a complete twenty-four-hour trading day or a marketable quote.

Replay:
```sh
python3 -m unittest -q test_cli test_fullsession test_tiingo_l1_v13
```

**Verified:** 41 passed on mini4 research workspace 2026-10-11. The v13 L1 tests separately passed on M2 against identical source files. Read-only, pre-existing licensed Tiingo L1 Parquet snapshots: AMD 720 bars, AAPL 687 bars, with both source receipt IDs/hashes checked. AMD: Oct 8 evening–Oct 9 morning 480/480 1m, 16 complete 30m bars; earlier partial Oct 7 night 240/480. AAPL: Oct 8 night 462/480 and prior 225/480; only 12 complete 30m buckets across its observed partial 2-night dataset; 12 partial buckets withheld. No raw vendor prices or keys are stored here.

**Limitations:** the proof exercised the existing materialized L1 Parquet (with receipt ID/raw-body SHA consistency), not a fresh invocation of the full Macro `read_research_view` raw-to-Parquet equality check. PIT eligibility, licensing and quote replay remain false. No SOXX historical BOATS bar receipt was present. Concurrent firehose envelopes contain a bounded opening burst, not a gap-free overnight tick book.


**Later accepted proof:** the canonical Macro `read_research_view` successfully qualified both original AAPL and AMD raw receipts and fed this consumer; see `TIINGO_CANONICAL_READER_REAL_PROOF_2026-10-11.md`.
