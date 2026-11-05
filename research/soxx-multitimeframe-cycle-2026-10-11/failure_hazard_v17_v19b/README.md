# SOXX early cycle failure / time-to-stop hazard v17–v19b

**Falsification result, not a production trading signal.** Full findings: [FINDINGS_V17_V19B.md](FINDINGS_V17_V19B.md).

Original signal rules and price-timeframe research in `../terminal_finepivot_v14/` and `../turn_confluence_v15_v16/`. All real vendor bar payloads remain private on mini4; public code is offline-only.

Predeclared specifications: `PARENT_TURN_CYCLE_EXIT_SPEC_V17.json`, `FIVE_MINUTE_REPLAY_SPEC_V18.json`, `NO_IGNITION_3H_SPEC_V19.json`, `KLAC_GAP_CENSOR_SPEC_V19B.json`.

Source: existing Terminal public read-only consumer; original 2025-10-09–2026-10-08 regular-session window, timezone-aware ET reconstruction, prior MACD/Stoch warmup, 1.5% emergency risk stop, 25% at +2% and 5 bps per side. **Actual BOATS 20:00–04:00 and quote fill proof absent**.

Executed modules: `parent_cycle_exit_v17.py`, `audit_5min_v18.py`, `replay_5minute_v18.py`, `no_ignition_v19.py`, `test_no_ignition_v19.py`, `no_ignition_eval_v19.py`, `klac_gap_censored_v19b.py`, `validate_no_ignition_v19b.py`.

Results and source manifests retain negative experiments and denominator accounting. No new chart publisher, account authentication, scheduled collector, auto-trader or live trade.
