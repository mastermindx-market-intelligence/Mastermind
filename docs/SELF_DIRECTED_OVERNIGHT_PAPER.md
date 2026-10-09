# Mastermind Bot — Tiingo BOATS overnight quote & paper-limit contract

**Target:** existing user-driven Self-Directed paper book at
`bot.mastermind-x.com/self`; no separate account, no real broker execution.
**Source carrier:** Mastermind PR #1293 (same Web workspace, same branch).
**Status:** code is built/testable; live data and production activation are held
until the exact Tiingo account entitlement and approved licenses are verified.

## Vendor and commercial entitlement

Use **Tiingo BOATS Overnight Real-time** as the sole overnight stock quote
provider. Do not use Alpaca, Polygon EOD, IEX daytime quotes, delayed prices,
ordinary Tiingo composite closing prices or synthetic midpoints to qualify
overnight paper fills.

Official primary references:
- Tiingo BOATS REST: https://www.tiingo.com/documentation/boats
- Tiingo BOATS product, subscription and rights:
  https://www.tiingo.com/products/boats-blue-ocean-ats-real-time-overnight-stock-prices
- Tiingo Commercial redistribution policy:
  https://www.tiingo.com/documentation/general
- Tiingo authentication: https://www.tiingo.com/documentation/general/connecting

BOATS uses `GET https://api.tiingo.com/boats/<ticker>`. A successful entitled
response is a one-element JSON list containing `ticker`, `quoteTimestamp`,
`bidPrice`, `askPrice`, `bidSize`, `askSize`, `last`,
`lastSize`, etc. Header: `Authorization: Token <TIINGO_API_KEY>`.
The token stays in server-side environment/secret storage and never appears in
URLs, HTML, logs, API responses, this document or git.

Tiingo's **Commercial/Business plan is not evidence of BOATS entitlement**.
BOATS Real-time is a separate add-on. Furthermore, ordinary Commercial API
license is **internal use only**. Tiingo states separately that redistribution
to website/app customers requires written permission; BOATS non-display
trading use can require its own licensing. The operator must verify exact
licensing for both product surfaces before enabling either one. Do not
interpret a technical HTTP 200 response as licensing approval.

## Independent fail-closed server settings

All are OFF unless explicitly set on the authorized production environment:

| Variable | Effect |
|---|---|
| `TIINGO_API_KEY` (or `TIINGO_API_TOKEN`, `TIINGO_TOKEN`) | Existing confidential server-side Tiingo token |
| `MASTERMIND_TIINGO_BOATS_DISPLAY_AUTHORIZED=1` | Allows network BOATS quote reads that can reach customer-facing `GET /api/self_directed*` and HTML; only after actual **redistribution/display** rights verified |
| `MASTERMIND_TIINGO_BOATS_NONDISPLAY_AUTHORIZED=1` | Allows reading BOATS specifically to simulate orders under the verified **non-display** agreement |
| `MASTERMIND_OVERNIGHT_PAPER_FILLS_ENABLED=1` | Independently arms **paper-only** instant limit fills; never real broker orders |

The **customer-facing order route needs all three authorizations**: display,
non-display simulation, and paper rollout. Its fills and history reveal the
venue quote/price to the user, so merely enabling non-display use would not
justify execution under an internal-only agreement.

The **same Tiingo data request** cannot be used to sidestep a missing display
or non-display license. Internal calculations without an appropriate use grant
stay held, regardless of whether the API key happens to return a quote.
Successful entitlement, public redistribution permission, simulation/non-display
permission and production feature activation are all distinct evidence.

A denied 401/402/403 is `entitlement_required`, 429 is `rate_limited`,
404 is `symbol_not_quoted`. All are structured non-executable statuses.
Provider error bodies and exception messages are suppressed to prevent token
leaks. No automatic fallback to another unlicensed feed.

## Overnight clock and fill model

- An overnight paper session runs Sunday–Thursday **20:00 to 04:00 ET**,
  ceasing Friday at 04:00; no Friday/Saturday night or holiday-eve paper
  fills. Venue closures and exceptional halts that cannot be confirmed must
  fail closed through live quote freshness and a two-sided positive book.
- **Marketable immediate limit only**. Buy uses the observed ask no higher than
  the user's limit; sell uses bid no lower than the limit. An unmarketable or
  too-large order is rejected, **never converted into a next-open regular
  market order**, nor left as a resting order or assigned an invented fill.
- Quotes must be at most 30 seconds old, with no more than 5 seconds future
  clock skew, finite positive bid and ask, non-crossed (bid below ask),
  spread <=5%, and positive displayed bid/ask sizes. `quoteTimestamp` is
  mandatory. A fresh last trade or `timestamp` cannot refresh a stale BBO.
- Requested share quantity cannot exceed available top-of-book size and
  **must be fully affordable/held**. Long-only; no leverage or shorts.
  The backend always re-fetches a live quote at order submission.
- A current BOATS quote is *venue-observed liquidity*, not guaranteed broker
  execution. A simulated fill is a paper modeling convention only.
- All accepted fills write to the original Self-Directed cash/positions/
  fills/history ledger, stamped with session, requested limit, venue/source,
  quote timestamp and execution timestamp. Existing daily open queue remains
  unchanged. No new ledger, account or exchange calendar owner is introduced.

## Portfolio and UI

Customer-facing quote API shows Tiingo bid/ask/mid/last, sizes, quote timestamp
and typed freshness/entitlement status only after display authorization.
During the overnight session the original paper-book UI may overlay a *preview*
from a fresh BOATS midpoint for up to 16 held symbols. This is never an official
daily NAV mark or an executable order price. A stale/unauthorized name remains
clearly marked as last-known regular and cannot paper fill.
The ticket requires explicit overnight-session selection and a positive limit.
Show **Data sourced by Tiingo** linked to https://www.tiingo.com on licensed
customer display, per Tiingo redistribution attribution requirement.

## Acceptance/proof and release gates

1. Run adapter contract tests (unauthorized display/non-display, no token,
   403/429/500, non-BOATS/mismatched response, stale `quoteTimestamp`,
   crossed/overspread/zero-size BBO, real list payload and header handling).
2. Run existing Self-Directed order/ledger/UI/auth tests plus JS syntax.
3. Confirm source code and license flags leave customer quote feeds held by
   default. Missing entitlement never triggers a real-money or paper fill.
4. Qualify exact head with CI, independent review and protected GitHub merge
   procedure; deploy only exact merged `origin/master`, not PR branch.
5. With the account's **BOATS Real-time** entitlement and licensed use
   independently confirmed, perform a bounded natural-session VPS quote-read
   and verify data freshness, actual entitlements, symbol and display rights.
6. Back up existing paper state and perform a protected manual paper buy/sell,
   plus rejection scenarios, verifying the same positions/cash/history ledger.
   Confirm customer display attribution, latency, no secret leakage and
   `/health` on deployed release.

Unproven data rights, vendor entitlement, CI, production installation and
natural overnight trading acceptance are explicit separate gates. A mock-test
pass is not a production 24/5 trading claim.
