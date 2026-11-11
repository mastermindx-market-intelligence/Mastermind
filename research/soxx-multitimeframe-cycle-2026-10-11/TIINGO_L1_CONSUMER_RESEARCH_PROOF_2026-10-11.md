# Genuine Tiingo historical BOATS L1 consumer proof

**Date:** Oct 11 ET / Oct 12 UTC, 2026. **Owner:** incumbent Macro Data OS archive, not a new data plane.

| Receipt source | 1-minute rows converted | Verified Oct 8 20:00–Oct 9 04:00 ET | Complete 30-minute buckets (all captured nights) |
|---|---:|---:|---:|
| AMD | 720 | 480 / 480 minutes | 24 |
| AAPL | 687 | 462 / 480 minutes, **18 missing** | 12 |

AMD earlier Oct 7 night: 240/480; AAPL earlier Oct 7 night: 225/480. All examined OHLC were valid and reported volume present; original source raw-body hashes matched each immutable receipt. Consumer checked each materialized L1 row's receipt ID, body SHA, source/venue/basis flags, capture cutoff and clock before normalization. **A gap-free AMD overnight session is not a complete 24-hour session.**

Checksum anchors: AMD `ae742fbb3d8427d25c200104070c17d7b332c8be6d6250306b31560383389d03`; AAPL `e279bcc1ffe5230a5d1bdb40d6ec1e5ac3e0302f8997a2def0848db7d4a7ed85`.

Pre-existing BOATS firehose L0 receipt scan: 20 original 2026-10-12 UTC segments, combined 19,651 Q/347 T/0 B; SOXX appeared with seven T and no Q during the initial evening burst. This demonstrates partial source access, not continuous valid SOXX venue quotation. Market messages, proprietary raw bars and subscription identifiers are **not** copied to GitHub. Receipt rights remain unverified for public data redistribution.

The v13 consumer has **41 passing tests total** including original v12 tests and 15 new L1 tests. v13 refuses split-basis claims and all non-bar execution/PIT assertions. Original full-year SOXX BOATS remains unavailable to this research; a strategy performance backtest has **not** been performed. Qualified history acquisition is an existing Tiingo collector/entitlement owner operation, not a new ChatGPT credential probe.

Source owner evidence: [Macro PR #8698](https://github.com/mastermindx-market-intelligence/macro/pull/8698) merged. Archive remains on M2. Original research branch: [Mastermind PR #1338](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1338).
