# Full-session BOATS research importer v12

Research-only code. This is **not** an authenticated market-data collector, new Data OS authority, broker order facility, or declaration that historical SOXX BOATS data have been acquired. The parser consumes supplied vendor records, distinguishes ET-display timestamps from true UTC, separates BOATS overnight from daytime, builds completeness-aware 2H/3H/4H panels, and refuses simulated fills when historical quotes are missing.

Original source: prior chat research artifact `SOXX_BOATS_FullSession_Research_Importer_v12_2026-10-11.zip`; pure Python standard library. Run `python3 -m unittest -q test_fullsession test_cli` from this directory. Last verified 26 tests passing on 2026-10-11.

Retrospective historical data and source rights are separate from publication, 24-hour strategy acceptance and actual execution. Do not convert a single night's BOATS OHLC into a gap-free year of historical quotes. Use existing Tiingo/Macro Data OS and Terminal/Quote Hub, not a second data collector.
