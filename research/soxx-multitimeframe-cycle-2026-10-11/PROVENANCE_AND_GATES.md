# BOATS acquisition, authorization and no-lookahead contract

## What has been verified
- Alpaca's documented historical US stock `feed=boats` supports bars, quotes and trades. Historical requests require API-key credentials and documented Free plan is delayed by 15 minutes; no authenticated response was obtained for this study as of 2026-10-11. The delayed historical BOATS feed is distinct from Alpaca's derived real-time `overnight` feed.
- Tiingo documents BOATS current top-of-book, real-time firehose, and historical intraday OHLC; its REST route is `/boats/{ticker}/prices`. Historical OHLC does not establish historical quote-level order execution. Entitlement is separate from a general Business subscription.
- Terminal's PR #814 implements a private Quote Hub request for historical BOATS with `feed=boats` and `adjustment=split`. It is unmerged and deployment not proven. Live ext quote UI/Terminal data is not a complete historical archive.
- Tiingo PR #1293 remains HOLD/BUILT_NOT_PROVEN due entitlement, redistributive rights, operator identity and real-path proof. Macro Data OS PR #8698 identifies archival producer gating and a prior pre-dispatch refused live probe. Do not retry that denied action by rephrasing or crossing tools/carriers.

## Four-arm experiment
1. RTH indicator clock + RTH execution.
2. Full-session 20:00–04:00 + pre/RTH/post indicator clock + RTH-only execution.
3. RTH indicator clock + full-session execution.
4. Full-session indicator clock + full-session execution.

Keep each outcome on the **same economic holding horizon**, check exchange calendar and source availability before labeling missing as zero. A 52-hour *regular-session* timer is not a 52-hour *calendar* timer.

## Historical data conditions
- Source and venue identifier per bar, timezone-aware UTC exchange timestamp plus ET window and daylight-saving handling; no blending ET wall display epochs with UTC absolute epoch.
- Explicit corporate-action adjustment basis, side-by-side source sample checks, no fake zero-volume forward-filled bars for trading.
- For a fill, use observed venue bid/ask (buy marketability against ask; sell against bid) and timestamp/size. A candle low touching an entry limit is not a proven fill.
- All state transitions anchored to **completed** higher- and lower-timeframe bars. Include potential gap and slippage above initial stops.
- Daytime vendor data must own 04:00–20:00; BOATS owns 20:00–04:00 only. Do not override canonical daytime source using an overlapping overnight query.
- Determine first and last eligible trading session, coverage denominator, missing bars, delayed data restrictions, and the product's permitted research/non-display rights.

## Current blockers
No production-proven, authorized year of historical SOXX BOATS bars+quotes has been delivered into this research workstream. Earlier VPS SSH on a separate client was rejected by public-key authentication; no attempt was made to bypass that denial. Existing online device status does not prove authenticated data-owner route or permission to move credentials.

Next action: incumbent authorized Terminal Quote Hub or Macro Data OS owner provides a verified historical response receipt and permitted data export. Preserve the research archive and replay the frozen four-arm design, **not** an optimized backfit.

Primary source docs:
- https://docs.alpaca.markets/us/docs/245-trading-for-trading-api
- https://alpaca.markets/learn/fetch-historical-data
- https://www.tiingo.com/documentation/boats
- https://www.tiingo.com/documentation/websockets/boats
- https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/814
- https://github.com/mastermindx-market-intelligence/Mastermind/pull/1293
- https://github.com/mastermindx-market-intelligence/macro/pull/8698
