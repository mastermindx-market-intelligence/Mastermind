# Self-Directed US Equity Overnight Quotes & PAPER Limits

Scope: `bot.mastermind-x.com/self` (the existing **Self-Directed** paper book),
not the autonomous Brain, real holdings, an Alpaca brokerage account, or
`data_layer/overnight.py`'s independent macro futures risk watcher.

## Market/session contract

- **Regular** (unchanged): 09:30–16:00 ET on valid US sessions. The manual
  existing ticket fills at the simulated regular quote or queues for the next open.
- **Overnight** (opt-in on order ticket): Sunday–Thursday 20:00 ET until the
  next US session day 04:00 ET. Friday and Saturday nights and nights before NYSE
  holidays do not simulate overnight execution. Exceptional venue suspensions
  are caught by quote freshness and asset eligibility.
- Only **immediately marketable overnight paper LIMIT** orders are supported.
  Buy crosses a recent ask not above the user's limit; sell hits a recent bid
  not below the limit. The requested size must not exceed displayed top-of-book
  size. Unmarketable limits are explicitly rejected—not left live, not converted
  into a next-open regular market order. No partial fill or persistent overnight
  resting order is claimed.
- Existing long-only, cash, position, P&L and history accounting are reused.
  No real-money brokerage order API, broker submit, or leverage route is added.

## Vendor configuration — on the authoritative VPS only

Use secrets from the existing server-side secret manager/environment; **never**
place credentials in source, UI, browser, PRs or chat:

- `ALPACA_API_KEY_ID`, `ALPACA_API_SECRET_KEY` (alternative Alpaca-standard
  `APCA_API_KEY_ID` / `APCA_API_SECRET_KEY`). Credentials authorize **market
  data GET** and **asset GET** only. The code never sends a brokerage order.
- Without real-time BOATS entitlement confirmation, the quote display requests
  `feed=overnight`, explicitly **indicative**, and cannot simulate a fill.
  Older cached regular/last-known marks remain clearly labeled as such.
- After independently confirming a genuinely **real-time BOATS quote entitlement**
  for that exact key, set `MASTERMIND_ALPACA_BOATS_REALTIME_CONFIRMED=1`. This
  changes the quote source to `feed=boats`. The flag is an operator attestation,
  not proof of subscription: the runtime cannot infer paid entitlement from 200 OK.
- Only after validation of eligibility, holiday/session clock, quote timestamps,
  UI/API authorization, and paper ledger tests set
  `MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED=1`. Both positive flags, active
  instrument eligibility, quote sizes, valid spread and age <=30 seconds are
  necessary to simulate an immediate fill. Missing flags, credentials, entitlement,
  stale quote or asset eligibility **fail closed**.
- Alpaca docs: https://docs.alpaca.markets/us/docs/245-trading-for-trading-api
  and https://docs.alpaca.markets/us/reference/stocklatestquotes-1.

## API and display

`GET /api/self_directed/quote?ticker=AAPL` returns the existing last-known
mark plus `overnight` bid/ask/provenance/status (when in overnight session).
`GET /api/self_directed` overlays fresh midpoint marks for held symbols as
**indicative overnight NAV preview**, not an official EOD settlement. It never
writes paper positions on GET. The ticket communicates the current session,
quote age/source, eligibility, and whether execution is available.

`POST /api/self_directed/order` (existing OPERATOR bearer protection) accepts
`{ticker,side,shares|notional,session:"overnight",limit_price}`. Only explicit
session selection uses the overnight route. Order limits remain enforced by
the server; browser controls are not the security gate.

## Release/acceptance checklist

1. Run `tests/test_overnight_equities.py`, `tests/test_self_directed.py`,
   existing operator-auth and portfolio UI tests, plus JS syntax checks.
2. Verify the candidate branch, CI and independent review; merge only via the
   normal Mastermind delivery workflow. Do not deploy draft/unmerged source.
3. Verify the exact merged master build on VPS, health HTTP 200, credentials
   available without secret exposure, the provider entitlement and non-stale
   named-symbol quotes during a natural overnight session.
4. With the paper-book backup and operator authentication verified, place an
   actual **paper** buy then sell in a test account under limit/size guards;
   inspect cash, fills, positions, NAV and FIFO history. Repeat a
   nonmarketable, stale, ineligible and outside-session order, proving no
   mutation. Do not claim real broker execution or production coverage from
   a local mocked test.
5. Keep the feature unavailable if credentials or paid real-time entitlement
   are absent. It is **not** appropriate to substitute a delayed, indicative or
   previously cached quote merely to mark the feature enabled.

Limitations of this initial source slice: marketable immediate overnight limits
only, no standing order lifecycle or depth/partial fills. The underlying
Self-Directed paper ledger is an existing separate file-based portfolio; a
comprehensive crash-recovery transaction migration is not implied by this slice.
