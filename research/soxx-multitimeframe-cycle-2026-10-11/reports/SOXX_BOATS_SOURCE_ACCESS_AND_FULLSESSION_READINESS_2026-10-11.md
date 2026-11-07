# SOXX full-session pivot and cycle-failure backtest — source/access recovery

**Research date:** October 11, 2026. **State:** Historical BOATS acquisition **NOT PROVEN**, research-format adapter **TESTED**, 24-hour strategy backtest **NOT RUN**. No live trades, production changes, token extraction, policy/flag changes, unattended monitoring, or venue redistribution were performed.

## 1. Resolved vendor identity and actual Terminal routes

The forgotten external provider is **Tiingo**, whose BOATS Real-time add-on serves 20:00–03:59 Eastern top-of-book/last and historical overnight OHLC bars. The account's subscription was described by the Chairman as newly added; authentication/entitlement was not proven in this session. **Tiingo historical BOATS REST OHLC is not a historical order-book or quote replay.** Source: [Tiingo 2.7 BOATS documentation](https://www.tiingo.com/documentation/boats).

A separate source is **Alpaca**, used by the existing Terminal Quote Hub. Its `feed=boats` supports historical bars, quotes and trades with feed/plan-dependent delay. Source: [Alpaca 24/5 data plan documentation](https://docs.alpaca.markets/us/docs/245-trading-for-trading-api).

### Current implementation vs operation

- **Terminal PR [#814](https://github.com/mastermindx-market-intelligence/mastermind-terminal/pull/814)**: open and not merged at inspection. It defines `hub/lib/overnightHistory.js`, localhost-only `/overnight-bars?symbol=&date=&tf=`, requests Alpaca historical `feed=boats`, split adjustment and 15-minute safety delay, and merges only overnight rows with Massive/store daytime. This is an implementation candidate, **not proof of installed running data**.
- **Mastermind PR [#1293](https://github.com/mastermindx-market-intelligence/Mastermind/pull/1293)**: open. It implements a Tiingo authenticated *current* BOATS bid/ask adapter for the Self-Directed **paper-only** portfolio, gated on separate display and nondisplay rights, BOATS entitlement and operator authentication. `BUILT_NOT_PROVEN`; do not conflate live quote snapshots with a full-year quote archive.
- **Macro PR [#8698](https://github.com/mastermindx-market-intelligence/macro/pull/8698)**: open Tiingo Data OS archival/reader work. Its source checkpoint states no production BOATS capture/archive, an entitlement probe not proven, and an earlier attempted authenticated probe explicitly refused before dispatch. Repeated equivalent credential probing through another carrier was **not attempted**.
- The documented Quote Hub runs on a loopback-only VPS service. A single read-only SSH preflight on the currently connected computer returned `Permission denied (publickey)`. No account-switch, alternate-credential attempt, service flag adjustment or direct privileged host read followed.
- No historical Tiingo, Alpaca or Terminal BOATS dataset was obtained in this run. Previously downloaded Yahoo extended hours did not include 20:00–04:00 and remain unsuitable for a 24-hour backtest.

## 2. Existing frozen regular-hours falsifier remains negative

The original 3-hour extreme MACD context plus confirmed 1-hour pivot was not retuned. Across **53 matched positions on eight additional semiconductor stocks**, the finite early-failure guard averaged **-0.318 percentage points** relative to a same-entry, same-exposure 52-regular-hour control. Fast weakness averaged **-0.181 pp**, and momentum-recovery failure **-0.120 pp**. Week-block confidence intervals included zero. The eight stocks share factor exposures, so this is not an independent 53-market sample.

With the unchanged 1.5% stop, **48/53** of those matched positions hit their stop, **14 in their first observed hourly candle** and **26 by hour three**. At entry, **40/55** frozen constituent signals had a 1.5% stop narrower than one observed hourly ATR. A higher-timeframe close-confirmed cycle detector cannot preempt stops that occur before its first new completed observation. A 1× ATR stop with a 3% cap increased mean return but still produced 41 losses among 50 known trades; more risk alone is not demonstrated improvement.

**Actionable conclusion for research design:** Treat entry validity and emergency risk separately from slower structural cycle invalidation; do not make the stop await an original pivot several percent away. Avoid automatic stop widening and avoid claiming any strategy passed untouched forward validation.

## 3. Completed full-session research importer, not a substitute producer

The accompanying `soxx_fullsession_v12` package accepts **already-authorized, already-collected** data only:

| Input | Expected raw contract | What can be established |
| --- | --- | --- |
| Terminal/Massive daytime | `[ET_display_epoch, O,H,L,C,V]` 04:00–20:00 ET with explicit price-adjustment basis | Daytime 15/30m bars; aligned pre/RTH/post sessions, early-close classification where calendar supplied |
| Alpaca BOATS | Authenticated archive `{'bars': {'SOXX': [{t,o,h,l,c,v}, ...]}}` from `feed=boats` | Historical overnight OHLC, native UTC, venue/source label; historical orders/fills **not** implied |
| Tiingo BOATS | Licensed archive from `/boats/SOXX/prices`, array of `{date,open,high,low,close,volume?}` | Historical overnight OHLC; volume can be unknown; not a historical quote book |
| Terminal BOATS normalized route | `{'source':'alpaca-boats','status':'available','bars':[[ET_display_epoch,O,H,L,C,V],...]}` | Read-side compatibility with Quote Hub candidate. Reconstruction of active-session ET time; rejects ambiguous DST folds and unavailable evidence |
| Alpaca historical BOATS quotes | `{'quotes': {'SOXX': [{t,bp,ap,bs,as},...]}}` | Quote presence, as-of marketability and spread/size checks; **no actual trade fill claim** |

The importer rejects incompatible split bases, overlaps, crossed quotes, missing source status, non-finite OHLC, unresolved pagination, DST-ambiguous overnight timestamps, and any attribution of BOATS to an ordinary daytime vendor. The `quotes` method reports only **quote-marketable, still unfilled**.

**Full-session resampling:** One explicit 20:00 ET to next 20:00 ET trading-day clock; 30-minute bars yield **12 complete 2-hour**, **8 complete 3-hour**, and **6 complete 4-hour** aggregate candles only when all required source intervals exist. A candle with one missing interval cannot generate a valid signal. A missing entire aggregate slot also blocks stale-signal reuse. All closed-candle decision timestamps precede any admissible later signal/event use. The importer marks mixed premarket/RTH or RTH/after-hours aggregate buckets rather than silently claiming one homogeneous venue.

**Evidence:** 26 passing Python `unittest` checks, including CLI end-to-end on a clearly synthetic 24-hour fixture; a missing-overnight fixture generated **zero eligible full-session aggregate counts**. Synthetic fixtures do not constitute stock-price backtest performance. The CLI cannot claim a complete full-year bar backtest without at least 180 fully observed declared trading dates from an independently supplied exchange calendar. Historical quote execution remains blocked until quote sufficiency is separately validated.

### Reproduction (source files supplied by the authorized Data OS / Quote Hub owner)

```sh
python3 -m unittest -v test_fullsession test_cli

python3 ingest_v12.py \
  --symbol SOXX \
  --daytime-file /path/to/authorized/Massive_30m_ET_display.json \
  --daytime-format terminal \
  --overnight-file /path/to/authorized/Alpaca_BOATS_30m_historical.json \
  --overnight-format alpaca \
  --overnight-evidence available \
  --basis split --interval 30 \
  --calendar-file /path/to/verified_exchange_trading_days.json \
  --out /path/to/new/research_result
```

For Tiingo, select `--overnight-format tiingo` and reconcile raw-vs-split adjustment with the daytime source. Do not use `--tiingo-basis-attested` unless an actual adjustment contract has been verified. Do not pass API tokens to the research CLI. The Terminal history adapter must return real venue provenance and `available`, not an inferred status.

## 4. Required next proof — frozen 24-hour strategy comparison

1. **Actual permitted source access:** Existing Quote Hub/Data OS owner supplies one year of SOXX 5/15/30-minute BOATS bars, historical 20:00–04:00 quotes where licensed, and aligned 04:00–20:00 Massive bars; verify exact instrument, raw/split adjustment, ET timestamp reconstruction, coverage, date calendar, source receipts, and BOATS entitlement for read-only research. A successful API request is not proof of customer-facing redistribution/paper-fill rights.
2. **Four-arm controlled design:** RTH indicators/RTH execution; full-session indicators/RTH execution; RTH indicators/full-session quote-marketability; full-session indicators/full-session quote-marketability. Match trading-hour horizons, exposure limits, fee/slippage assumptions and each original entry episode. Overnight BOATS prints are venue-specific, not a SIP NBBO.
3. **State-machine falsification:** Apply previously frozen MACD and Stoch RSI extremes and 15/30/60m confirmed price-pivot entry variants, compare original-pivot and promoted higher-low failure definitions, retain an independent initial emergency stop, and measure both saved losers and forfeited winners. Never credit a quote touch as a confirmed fill; count unfilled orders and excluded episodes in the opportunity denominator.
4. **Acceptance threshold:** Preserve all rejected/missing/censored days, negative-control QQQ/SMH experiments, gap/slippage stress and a genuinely untouched prospective date set. An apparently exceptional few-trade win rate remains only exploratory.

## 5. Exact blocker and mode

**BOATS_BAR_HISTORY: NOT_YET_OBTAINED; BOATS_HISTORICAL_QUOTES: NOT_YET_OBTAINED.** Terminal PR #814 is open, the current runtime has not provided the authenticated Quote Hub route to this session, and the existing attempted read-only SSH preflight returned a public-key permission denial. The Tiingo source owner documents an earlier refused credential probe, which was not bypassed.

**Current ChatGPT mode:** Extra High is suitable for the implementation and read-side validation. Pro is not required to resolve a permission/entitlement/data-export gate. Once real historical bars and quotes become available, a Pro statistical adjudication may be useful, but it cannot manufacture source access.

**Canonical research frontier:** Frozen regular-session results at mini4 `SOXX_CYCLE_TRANSFER_20261011_v11.zip`; this v12 package supplies a separately replayable *reader*, not a second Data OS collector. Mission remains incomplete; no background execution is claimed.