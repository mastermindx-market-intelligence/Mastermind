# 3H parent-turn vs 15/30m confluence + delay controls (v15/v16)

This directory stores pre-outcome specifications, reproducible source code, safe derived performance measurements, and a software proof for the **same** SOXX, SMH, QQQ, AMD historical year.

**Original OHLC/volume snapshots remain private** on mini4: `/private/tmp/soxx_terminal_finepivot_20261011_v14/`. The code imports frozen v11 upstream research helpers from that host; it does not fetch data, trade or create a source archive.

- `SIMULTANEOUS_SPEC.json` and `simultaneous_v15.py`: 3H turn + existing lower pivot versus armed lower pivot (denominator = existing lower-pivot signals).
- `PARENT_ONLY_AND_DELAY_CONTROLS_SPEC_V16.json` and `parent_delay_controls_v16.py`: pure 3H turn, 3H+15m/30m pivot, and delay controls (denominator = all 3H extreme arms).
- `parent_delay_results_v16.json`: per-symbol and cross-week diagnostic aggregate outcomes.
- `PARENT_V16_VERIFICATION.json` and `verify_parent_v16.py`: source hashes, 34 independent OHLC replays, 164 paired accounting checks.
- Parent source used **completed** higher candles and next 15-minute open. Market microstructure, venue quote fills and known-at history were not proven.
- **This is a falsification/research archive**, not a recommendation to automate trading.
