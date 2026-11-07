# Mastermind Paper Cash Trading Suite — Architecture Freeze

**Date:** 2026-09-11  
**Chairman:** Chris  
**Owner:** Sol  
**Operation:** `paper-cash-trading-suite-20260911-sol-001`  
**Protected source pin:** `mastermindx-market-intelligence/Mastermind@e61f2951136bdc03a7ec2f5f12f960af26656a4c`  
**Skillpack:** `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1  
**State:** `SPEC_ONLY / SOURCE_ONLY / PRODUCTION_INERT`

## 1. Outcome

Turn the existing Mastermind Self-Directed paper book into a professional paper-cash trading workspace inside the Portfolio product without creating a second trading engine, second Portfolio truth, second authentication plane, or any live-broker authority.

The user should be able to move through one uninterrupted loop:

```text
Find security
-> understand current state/change/risk/catalyst
-> construct a paper order
-> preview cash + portfolio impact
-> submit
-> observe order/fill state
-> manage the position
-> review P&L + portfolio impact
-> revisit the original thesis and what was known at entry
```

The suite is **paper only**. Nothing in this program routes a real order or grants broker authority.

## 2. Product thesis

A generic paper broker is commodity. Mastermind should reach broker-grade paper execution parity, then differentiate on **decision rehearsal**:

1. realistic enough execution semantics that the user trusts the simulation;
2. the Mastermind Decision Spine visible at the moment of a trade;
3. deterministic pre-trade portfolio-impact context;
4. point-in-time thesis/intelligence capture so later review can compare the decision with what actually happened;
5. a useful learning loop, not merely a green/red P&L table.

The paper account is therefore a **decision laboratory attached to Market OS**, not a toy stock game and not a naked LLM recommendation surface.

## 3. Current estate recovered

### 3.1 Canonical user-driven paper engine already exists

`portfolio/self_directed.py` is the existing user-driven paper book and remains the canonical execution owner for this program. Current capability includes:

- fresh USD 1,000,000 cash account;
- long-only / no leverage;
- market orders sized by shares or dollars;
- live fill during the regular session;
- next-session-open queue when the market is closed;
- buy bounded by cash and sell bounded by shares held;
- pending-order cancellation;
- persistent account snapshot;
- persistent fill ledger;
- thesis notes by ticker;
- NAV history and SPY benchmark marking;
- positions with live marks, weights and unrealized P&L;
- FIFO replay for realized P&L and win rate;
- publication into the existing firm-exposure view;
- scheduler participation in the existing daily mark sweep.

This is substantial existing infrastructure and must be extended, not replaced.

### 3.2 Portfolio Desk is a different thing

`app/pfolio.py` + `sql/0002_portfolio_positions.sql` are a personal holdings CRUD/risk surface backed by `portfolio_positions` in Supabase. It is not an order engine. Creating/editing/closing a row changes a holdings record; it does not create an order, fill, cash movement or realized execution trail.

That surface remains the canonical personal/real-holdings lane where applicable. It must not become the execution ledger for Self-Directed merely for UI convenience.

### 3.3 Market OS Portfolio remains canonical real holdings

The existing Market OS architecture freezes one canonical Portfolio for the user's actual holdings and explicitly rejects another competing Portfolio store/composer. Paper Trading is therefore a **sibling mode** under My Market / Portfolio, not a reinterpretation of the canonical real Portfolio.

Recommended product information architecture:

```text
My Market
  Portfolio
    Real Portfolio
    Paper Trading
      Overview
      Trade
      Orders
      Positions
      Activity
      Performance
      Journal
```

### 3.4 Current security boundary must not be weakened

The authoritative bot VPS currently has explicit operator protection for mutating Self-Directed endpoints. The separate `/api/pfolio/*` personal panel acts with a service-role credential and is also tightly gated.

No part of this program may treat subscription entitlement as user identity, expose a service-role credential, or loosen authoritative-origin protection to make the UI convenient.

A general multi-user paper account requires a canonical per-user identity/storage path. Until that owner is proven, the production ceiling is an operator-scoped internal paper workspace rather than a falsely multi-user product.

## 4. Capability ledger

| Capability | Current state | Target |
|---|---|---|
| Cash account | `BUILT_NOT_PROVEN` | durable account summary + buying-power semantics |
| Market buy/sell | `BUILT_NOT_PROVEN` | professional order ticket + preview + audit trail |
| After-close queue | `BUILT_NOT_PROVEN` | explicit order state/TIF and deterministic matcher |
| Pending cancel | `BUILT_NOT_PROVEN` | cancel/replace + cancellation history |
| Positions / avg cost | `BUILT_NOT_PROVEN` | lots, exposure, day + total P&L |
| Fill ledger | `BUILT_NOT_PROVEN` | immutable order/fill linkage + execution-quality metadata |
| FIFO realized P&L | `BUILT_NOT_PROVEN` | persisted/replay-safe lot accounting |
| NAV history / SPY | `BUILT_NOT_PROVEN` | equity curve, benchmark, drawdown, period returns |
| Limit orders | `NOT_BUILT` | required |
| Stop orders | `NOT_BUILT` | required |
| Stop-limit orders | `NOT_BUILT` | required |
| DAY / GTC | `NOT_BUILT` | required |
| Reserved cash/shares | `NOT_BUILT` | required |
| Partial-fill state | `NOT_BUILT` | required where evidence supports it |
| Bid/ask-aware simulation | `NOT_BUILT` | required when quote data supports it |
| Order modification | `NOT_BUILT` | required |
| Order lifecycle ledger | `NOT_BUILT` | required |
| Cash activity ledger | `NOT_BUILT` | required |
| Account reset | `NOT_BUILT` | required, explicit/destructive |
| Export | `NOT_BUILT` | required |
| Corporate actions | `NOT_BUILT` | later realism wave |
| Extended-hours trading | `NOT_BUILT` | later, only when feed/session semantics are proven |
| Pre-trade portfolio delta | `NOT_BUILT` | differentiator |
| Entry intelligence snapshot | `NOT_BUILT` | differentiator |
| Thesis/outcome replay | `PARTIAL` | first-class differentiator |
| Fully integrated trading workspace | `NOT_BUILT` | required |
| Multi-user server identity | `NOT_BUILT` for this engine | separate prerequisite for broad rollout |
| Live browser production proof | `NOT_BUILT` for revamp | mandatory before `PROVEN_LIVE` |

## 5. Competitive parity baseline

Official product documentation reviewed on 2026-09-11 establishes a practical modern baseline:

- TradingView paper workflows expose market, limit, stop and stop-limit tickets, preview/confirmation, TP/SL attachment and position close flows.
- Webull's current paper environment includes market, limit, stop, stop-limit, trailing, conditional and grouped orders; its product explicitly tries to mirror live-trading behavior.
- Alpaca paper trading matches orders against real-time quote conditions and documents marketability, partial-fill simulation and account reset.
- Interactive Brokers explicitly frames paper trading as use of normal trading facilities in a simulated environment while warning that simulated execution differs from live execution.

Mastermind does not need every advanced order class in the first release, but it cannot call a market-only immediate/next-open executor a full trading suite.

## 6. Experience architecture

### 6.1 Persistent account rail

Always visible at the top of Paper Trading:

- Paper Equity
- Cash
- Buying Power
- Invested
- Day P&L
- Total P&L
- Total Return
- market/session state
- data freshness
- prominent `PAPER` status

Do not hide whether marks are live, delayed, carried, or unavailable.

### 6.2 Trading workspace

Desktop target:

```text
+---------------------------------------------------------------+
| PAPER | Equity | Cash | Buying Power | Day P&L | Market state |
+---------------------------+----------------------+------------+
| Security / chart /        | Mastermind context   | Order      |
| quote / levels            | Change / Risk /      | ticket     |
|                           | Catalyst / impact     |            |
+---------------------------+----------------------+------------+
| Positions | Orders | Activity | Performance | Journal        |
+---------------------------------------------------------------+
```

Mobile collapses the order ticket and intelligence panel into sheets while preserving a single submission path.

### 6.3 Order ticket

Required fields/states:

- Buy / Sell
- Market / Limit / Stop / Stop-Limit
- Shares / Dollars
- quantity/notional
- relevant limit/stop prices
- DAY / GTC
- regular-session eligibility
- estimated value
- estimated cash after / position after
- quote and freshness used by preview
- explicit review step by default
- submit disabled when price/freshness/account state is insufficient

Future optional depth after core proof:

- trailing stop;
- OCO;
- bracket take-profit/stop-loss;
- one-click mode;
- extended hours.

### 6.4 Orders

Open Orders is not the same thing as fills. Every order needs a durable identity and lifecycle such as:

```text
accepted
working
triggered
partially_filled
filled
cancel_pending
cancelled
rejected
expired
```

UI must show original quantity, filled quantity, remaining quantity, average fill, order type, prices, TIF, created/updated timestamps and status reason.

### 6.5 Positions

Required position view:

- ticker/name;
- shares;
- average cost;
- live/current mark + freshness;
- market value;
- day P&L / day %;
- unrealized P&L / %;
- portfolio weight;
- thesis status;
- relevant current Mastermind risk/change/catalyst context;
- quick Add / Reduce / Close actions routed through the same order ticket.

### 6.6 Activity

One chronological audit surface covering:

- order accepted;
- order replaced;
- trigger event;
- partial/full fill;
- cancellation;
- rejection/expiration;
- cash movement;
- reset;
- corporate action when later supported.

A cancellation must not disappear merely because it is no longer pending.

### 6.7 Performance

Minimum useful analytics:

- equity curve;
- SPY comparison;
- day / 1W / 1M / since-inception returns when history exists;
- max drawdown;
- realized / unrealized split;
- cash allocation;
- turnover;
- trade count;
- win rate with an explicit definition;
- best/worst realized trades;
- benchmark excess return.

Annualized/ratio metrics must abstain when history is too short rather than presenting unstable precision.

### 6.8 Journal and decision replay

This is the Mastermind moat.

At submission time the system may capture an immutable, authority-free decision snapshot containing references/digests and freshness for what was available to the user:

- user thesis;
- invalidate condition / what would change the thesis;
- intended horizon;
- security state/change context;
- risk legs;
- catalyst context;
- portfolio-impact preview;
- quote/session facts used for execution preview.

Later review can answer:

- What did I believe?
- What was actually known then?
- What changed afterward?
- Did the thesis work even if the trade P&L did not, or vice versa?
- Was the outcome driven by market beta, thesis, timing, or a risk that was visible at entry?

This remains descriptive/learning context. No LLM summary gains rank/size/trade authority.

## 7. Execution semantics freeze

### 7.1 Cash-account law

Initial product is cash equities/ETFs only:

- no shorting;
- no leverage;
- no margin;
- no options;
- buys cannot exceed available buying power;
- sells cannot exceed unreserved held shares;
- pending/working buys reserve cash where their maximum obligation is knowable;
- pending/working sells reserve shares;
- a second order cannot overbook the same cash/shares.

Settlement/PDT/good-faith behavior is a later explicit realism decision. Do not silently imply brokerage settlement restrictions that are not implemented.

### 7.2 Market orders

During an eligible session, a market order executes against the best supported quote evidence:

- buy prefers ask;
- sell prefers bid;
- if only a last trade is available, use it only with an explicit degraded execution-quality tag;
- never claim NBBO-quality simulation when the data does not support it.

Outside the eligible session, the order is accepted/queued according to TIF and becomes executable at the next supported session. Existing next-open behavior is preserved through migration, not silently changed.

### 7.3 Limit orders

A limit order fills only when supported market evidence proves it is marketable at the allowed price or better.

Do not infer an exact intrabar path from an OHLC bar. If available evidence cannot establish the crossing semantics safely, the order remains working or the result is explicitly lower-fidelity; the simulator does not hallucinate fill chronology.

### 7.4 Stop / stop-limit

A stop is a trigger state followed by market-order semantics. A stop-limit becomes a limit order after trigger. Trigger and fill are distinct events.

### 7.5 Partial fills

Do not add random partial fills merely to look realistic. Use deterministic partial-fill behavior only when quote/size/liquidity evidence or an explicitly versioned simulation policy supports it. Otherwise disclose `liquidity_not_modeled` and full-fill the marketable order.

### 7.6 Slippage / fees

Execution reports must distinguish:

- observed quote;
- simulated execution price;
- modeled spread/slippage component;
- fee component;
- model/version.

The initial version may use zero explicit commissions and no extra slippage beyond supported bid/ask evidence. It must say so rather than pretending this is live-exchange fidelity.

## 8. State and durability architecture

### 8.1 One execution owner

`portfolio/self_directed.py` remains the public Self-Directed execution facade. Supporting modules may be extracted only as implementation details; they do not become a second book or second authority.

The mature state should distinguish:

- account snapshot — materialized projection;
- order lifecycle ledger — append-only source for order state transitions;
- fill ledger — append-only execution facts;
- cash activity — derived from fills/account events or a single canonical event ledger;
- NAV history — existing performance projection;
- thesis/decision snapshots — journal evidence.

### 8.2 Reuse existing paper durability patterns

`portfolio/paper_account.py` already contains recoverable transaction, locking, atomic replace, fsync and settlement-reconciliation patterns. The Self-Directed upgrade should reuse/refactor those proven primitives instead of inventing a new locking/transaction service.

Current Self-Directed read-modify-write file operations are not sufficient for a professional concurrent interactive surface.

### 8.3 Identity / idempotency

Orders need durable UUID-style identity and optional client request identity. Same request identity + same semantic order is idempotent; same request identity + different order conflicts. A timeout must not cause a blind second order.

### 8.4 Migration

Existing Self-Directed account, fills, pending orders, theses and NAV history are valuable state. Migration must be explicit and testable:

1. read old snapshot/ledgers;
2. validate invariants;
3. construct new projection/events without changing economic state;
4. compare cash, shares, cost, fills and NAV;
5. retain rollback/read compatibility until production proof.

Never reset the user's existing paper history merely because the schema improves.

## 9. API architecture

Preserve existing routes as compatibility adapters where possible. The final surface should expose stable read/write contracts equivalent to:

```text
GET    /api/self_directed                 unified account snapshot
GET    /api/self_directed/quote           quote + session/freshness
GET    /api/self_directed/orders          working + historical orders
POST   /api/self_directed/order           submit order
PATCH  /api/self_directed/order/{id}      replace supported fields
POST   /api/self_directed/cancel           cancel one order
GET    /api/self_directed/history          fills/activity compatibility
GET    /api/self_directed/performance      NAV/benchmark analytics
POST   /api/self_directed/thesis           thesis/journal update
POST   /api/self_directed/reset            explicit paper-account reset
GET    /api/self_directed/export           bounded user export
```

Do not add a generic execution endpoint that can later be pointed at a broker.

## 10. Intelligence integration

The trading suite consumes existing Mastermind intelligence; it does not grant that intelligence trade authority.

Order preview may show:

- State;
- Change;
- Opportunity context;
- Risk;
- Catalyst;
- Personal impact;
- concentration delta;
- relevant alerts/change history.

For a proposed order, compute deterministic **before vs after** paper-portfolio deltas such as:

- cash %;
- position weight;
- largest-name concentration;
- sector/theme exposure where canonical mappings exist;
- risk-lane exposure where canonical risk packets exist.

The user remains the order originator. A model may explain the preview but cannot submit, resize or veto the order unless a separate future authority program explicitly proves and grants that capability.

## 11. Authentication and multi-user boundary

The current Self-Directed book is server-local and operator-scoped. A public multi-user Paper Trading product cannot share those files across users.

Before general rollout, the canonical identity/account owner must provide:

- authenticated user identity at the authoritative origin;
- per-user paper account namespace;
- user-scoped mutation authorization;
- isolation tests proving one user cannot read/write another account;
- migration/retention policy;
- no service-role exposure to browser clients.

Until then, do not weaken current protection and do not market the server-local account as multi-user.

## 12. Build sequence — small vertical slices, full vision preserved

### PT-1 — Durable Market Order Vertical

**Observable capability:** from the Paper Trading workspace, the operator can preview and submit a market buy/sell, then immediately see the same durable order, fill, cash and position state in Orders/Activity/Positions after refresh/restart.

Includes:

- durable order identity/lifecycle for existing market orders;
- cash/share reservation and strict reject semantics instead of silent economic clamping;
- transaction-safe account + order + fill mutation using existing paper-account durability patterns;
- compatibility for current Self-Directed state;
- account summary API;
- first redesigned Paper Trading workspace shell;
- order preview/review;
- open/history/activity tabs;
- tests and production browser proof.

Non-goals: limit/stop/GTC depth, corporate actions, extended hours, multi-user rollout.

### PT-2 — Working Orders

Add limit, stop, stop-limit, DAY/GTC, cancel/replace and scheduled matching using the **existing scheduler**, not a new daemon/queue.

### PT-3 — Performance Cockpit

Equity curve, benchmark, realized/unrealized attribution, drawdown, return windows, turnover and robust insufficient-history states.

### PT-4 — Mastermind Pre-Trade Intelligence

Decision Spine + deterministic portfolio-impact preview + explicit freshness/null behavior.

### PT-5 — Journal / Decision Replay

Point-in-time thesis/intelligence snapshot, trade review and outcome comparison.

### PT-6 — Execution Realism

Bid/ask-aware fills, explicit fidelity flags, deterministic supported partial fills, fee/slippage model where evidence supports it, corporate-action handling.

### PT-7 — Product Operations

Reset, export, optional import, account presets, richer empty/error/recovery states, accessibility/mobile hardening.

### PT-8 — Multi-User Rollout

Only after canonical authenticated identity/storage ownership is established. Migrate the same paper engine to per-user state without creating a parallel browser-only simulator.

## 13. PT-1 acceptance and production proof

PT-1 is not accepted on green CI alone. Required proof:

1. Existing paper account with known cash/positions/history is migrated without economic drift.
2. Browser opens the real production Paper Trading workspace.
3. Live market/session state and quote freshness are visible.
4. Market buy preview shows exact requested size, estimated obligation and account/position delta.
5. Submit produces one durable order identity and at most one economic effect.
6. Filled order appears consistently in Orders, Activity and Positions after page refresh.
7. Process restart preserves the same cash/shares/order/fill state.
8. Oversize buy is rejected rather than silently reshaped unless the UI explicitly requests `max`.
9. Oversize sell is rejected rather than silently reshaped unless the UI explicitly requests `close/max`.
10. Duplicate request identity does not double-execute.
11. Timeout/effect-unknown path reconciles the same operation rather than blind retrying.
12. Closed-market submission preserves the existing next-session semantics with an explicit queued state.
13. Cancelled/rejected orders remain in history.
14. No route can place a real broker order.
15. Existing autonomous books, real Portfolio state, risk publication and firm-exposure math remain intact.

Only after real production input reaches a visible durable result may PT-1 become `PROVEN_LIVE`.

## 14. No-rebuild boundaries

Do not create:

- another Portfolio store;
- another paper-book registry;
- another scheduler or order polling daemon;
- another auth/session/user identity system;
- another quote store;
- another risk engine;
- another Portfolio composer;
- another event bus solely for paper trading;
- an LLM execution authority;
- a live-broker adapter;
- a generic order router capable of real-money routing.

Extend the existing Self-Directed book, scheduler, data feeds, Market OS intelligence and existing security boundaries.

## 15. Current ruling

The revamp is **worth doing and structurally straightforward because the core already exists**. The current experience is low quality because the capability is fragmented: the Self-Directed execution engine is materially more capable than the Portfolio Desk UI, while the Desk itself is a manual holdings CRUD/risk surface.

The correct product move is not to embellish `portfolio_positions` CRUD. It is to surface the existing Self-Directed paper account as a first-class Paper Trading mode, harden its transaction/order model to broker-grade semantics, and then connect Mastermind intelligence/journal/review around it.

**Next implementation wave:** PT-1 Durable Market Order Vertical.  
**Preferred implementation avenue:** Terra/CTO Sol-class bounded engineering after exact source collision refresh; Fable is not required because the architecture/no-rebuild boundaries are now explicit.  
**Why not Fable:** PT-1 is a bounded engineering vertical once this architecture is accepted; scarce principal capacity is better reserved for unresolved cross-estate ambiguity or final adversarial product review.
