# Terminal 15/30m SOXX cycle-failure research, v14

This is a **frozen exploratory research** wave, not a trading strategy, licensed raw-data export, or an independent holdout.

Full findings and limitations: [FINDINGS_V14.md](FINDINGS_V14.md). Original historical data remain in the private mini4 research scratch directory with source hashes in `sources.json` and `PEER_SOURCE_METADATA.json`.

Provenance: existing public Terminal read-only `/api/intraday` with explicit ET market-local display epochs and source evidence `point_in_time_availability=not_verified`, `price_adjustment=not_verified`, `completeness=not_assessed`. No direct Tiingo/Alpaca/Massive credentials or vendor API calls.

Evidence files:
- Frozen pre-outcome specifications: `SPECIFICATION.json`, `PEER_SPEC.json`, `STRUCTURE_ADMISSION_SPEC.json`.
- Scripts: `study_v14.py`, `peer_v14.py`, `structure_admission_v14.py`, `validate_v14.py`.
- Safe-derived outcomes: `summary_v14.csv`, `peer_summary_v14.csv`, `structured_admission_summary_v14.csv` and related paired result tables.
- `VALIDATION_V14.json`: source parity, prefix chronology, independent replays, aggregate checks.

The scripts depend on the preserved v11 upstream source modules and intentionally **do not** fetch vendor data or create new archives. To reproduce locally, provide your own lawfully licensed Terminal snapshots at the original private dataset paths and match the SHA evidence. The source files, unlike the actual OHLCV, are suitable for public code review.

Status: new granular access **PROVEN FOR EXISTING READ-ONLY TERMINAL CONSUMER**; new strategy quality/production/BOATS execution **NOT PROVEN**.
