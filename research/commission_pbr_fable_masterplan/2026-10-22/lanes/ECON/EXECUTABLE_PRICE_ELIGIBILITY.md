# EXECUTABLE_PRICE_ELIGIBILITY.md — spec (pbr-econ L-E5, part B)

Status: **SPEC ONLY — approves no code change, no enforcement, no deployment.**
Program: Portfolio Bot Rebuild (#1693), ECON lane, 2026-10-22. Companion census:
`PRICE_EVIDENCE_CONSUMPTION.md` (same directory). Audit context: A05 — a positive scalar
can become a simulated execution price with no time/venue qualification; #1614 carries
selected-source context but explicitly does not certify execution eligibility.

Problem in one line: the only execution-price predicate on the paper settlement path is
`_trusted_execution_price` — finite and > 0 (`portfolio/paper_account.py:1739-1750`,
applied `:1820-1823`, `:2081`, `:3249-3270`) — so a stale close, an adjusted print, a
prior session's open, or a queued estimate can each price a simulated fill. Source labels
(`polygon_open`, `yahoo_open`, `last_price`) record which fallback fired, not what the
price is evidence of.

Governing doctrine (Masterplan §7.2): every load-bearing observation carries
instrument+units; event/market time, publication/availability time, retrieval time,
recording time; session + timezone; source + source-generation id; raw-vs-adjusted basis
and FX quote identity; freshness/coverage status; and an authority class. A portfolio mark
date is never relabeled as an exchange timestamp. Raw executable prices are used for
transaction simulation.

---

## 1. The eligibility record

A new, sibling structure — proposed schema `mastermind.execution_eligibility.v1` — bound
per settled ticker alongside (never inside) `mastermind.settlement_price_evidence.v1`.
It must NOT overwrite `execution_qualification` in the existing schemas: today's validator
rejects any value other than `"not_checked"` (`price_evidence.py:239-242`, `:494`;
`fx_evidence.py:128`), and those fields sit inside the transaction preimage, so changing
them rotates fill ids (`price_evidence.py:440-446`).

Record shape (one per ticker):

```
{
  "schema": "mastermind.execution_eligibility.v1",
  "ticker": str,                      # canonical symbol, joins the settled quote
  "venue_mic": str|null,              # M1
  "instrument_class": "common_stock"|"etf"|"index",   # M1
  "session_date": str|null,           # M2  ISO exchange-local trading date
  "session_open": str|null,           # M3  exchange-local instant
  "session_close": str|null,          # M3
  "session_timezone": str|null,       # M3  IANA zone id
  "calendar_version": str|null,       # M12 session-calendar generation id
  "market_event_at": str|null,        # M4  UTC exchange event instant (or null + reason)
  "available_at": str|null,           # M5  provider publication/availability instant, unit declared
  "retrieved_at": str|null,           # from existing clocks (fetch/response pairs)
  "recorded_at": str|null,            # cache anchor / observation clock
  "source": str,                      # existing label
  "source_generation_id": str|null,   # M7 declared, unit-typed provider generation
  "basis": "raw"|"adjusted"|null,     # M6
  "price": float|null,                # the scalar the verdict binds to (positive)
  "currency": str,                    # native quote currency
  "fx_generation_id": str|null,       # M9  shared by both legs of a converted fill
  "decision_cutoff": str,             # M8  UTC instant the read must precede
  "max_observation_age_seconds": int, # policy parameter in force at check time
  "authority_class": "valuation"|"research_context"|"risk_input"|"executable_observation",  # M10
  "freshness": "within_bounds"|"stale"|"undated",     # existing age fields, verdict applied
  "eligibility": {"outcome": "eligible"|"ineligible"|"unknown",
                   "reason": str|null, "rules_version": str, "checked_at": str}   # M11
}
```

### 1a. Fields that already exist in the #1614 family (26)

| # | Field | Where today |
|---|-------|-------------|
| 1 | `ticker` | all schemas |
| 2 | `price` / `price_local` | `price_read.v1/v2`, `polygon_snapshot_evidence.v1`, `yahoo_daily_bar_evidence.v1/v2` |
| 3 | `currency` | `price_read` (also `input_currency`), polygon (hardwired `USD`), settlement; **absent from yahoo schemas** (local price, implied ccy) |
| 4 | `payload_ticker` / `payload_ticker_status` | polygon |
| 5 | `source` | `price_read`, settlement quotes |
| 6 | `attempts` (bounded source-attempt log) | `price_read` |
| 7 | `upstream` / `upstream_status` / `upstream_reason` (one-hop binding) | `price_read` |
| 8 | `source_text_sha256` (+ fx `source_text_digest_basis`) | `price_read`, `fx_rate_evidence.v1` |
| 9 | `source_bar_label` / `source_bar_label_kind` | all schemas (a date/label — NOT a session claim) |
| 10 | `source_path` | fx |
| 11 | fx pair `symbol` | fx |
| 12 | retrieval start (`fetch_started_at` / `source_read_started_at`) | yahoo, fx |
| 13 | retrieval end (`download_returned_at` / `response_returned_at` / `source_read_returned_at`) | yahoo, polygon, fx |
| 14 | `cache_anchor_at` | polygon |
| 15 | `cache_age_observed_at` / `cache_observed_at` | polygon, fx |
| 16 | `fetch_age_seconds` / `cache_age_seconds` | yahoo, polygon |
| 17 | `within_cache_ttl` | yahoo, polygon |
| 18 | cache basis declarations (`cache_refresh_basis`, `cache_clock_basis`, `cache_state`, `cache_day_basis`, `cache_population_day`) | yahoo, polygon, fx |
| 19 | `source_updated_raw` + `source_updated_unit: "not_established"` | polygon (opaque provider integer) |
| 20 | `fx_observation`, `fx_operation`, `fx_rate`, `fx_binding_reason` | `price_read.v2` |
| 21 | `consumed_as`, `source_convention_qualification` | fx |
| 22 | `status`/`read_status` + `reason` | all |
| 23 | `stage` (coarse context label: `us_open_selection`, `settlement_selection`, `decision_input`, `paper_live`, `paper_current`) | `price_read` |
| 24 | `market_observed_at` — field present, **hardwired `None`** everywhere | all |
| 25 | `execution_qualification` — field present, **hardwired `"not_checked"`** and validator-enforced so | all |
| 26 | settlement-level `binding_status` / `omitted_quote_count` / `capture_error` | `settlement_price_evidence.v1` |

### 1b. Fields missing for eligibility (12)

| # | Missing | Why it blocks eligibility |
|---|---------|--------------------------|
| M1 | `venue_mic`, `instrument_class` | A label like `polygon_open` cannot establish venue; index marks (SPY benchmark leg) must not be treated as single-stock opens |
| M2 | `session_date` (declared) | Yahoo's exchange-date match is computed internally and recorded only as a boolean reason + date label (`yahoo_feed.py:536-556`); polygon records no bar date at all (`source_bar_label: None` is *required* by the polygon validator, `price_evidence.py:114-115`) |
| M3 | `session_open`/`session_close`/`session_timezone` | Session windows and zone are nowhere recorded |
| M4 | `market_event_at` value | `market_observed_at` exists but no producer ever fills it |
| M5 | `available_at` with declared unit | Polygon's `updated` integer has `source_updated_unit: "not_established"` by contract (`polygon.py:227-230`); yahoo has no publication time at all (retrieval clocks only) |
| M6 | `basis` raw/adjusted | Polygon `day.o` and daily-bar Open adjustment basis is unrecorded; `polygon.daily_closes` fetches `adjusted=true` (`polygon.py:97`) — the family contains both bases with no declaration |
| M7 | `source_generation_id` | No declared provider generation id; the opaque `updated` integer is unusable as one while its unit is unestablished |
| M8 | `decision_cutoff` binding | The cutoff lives only in caller scope; no record states which cutoff a read was admitted against |
| M9 | `fx_generation_id` shared across legs | `cache_population_day` exists per fx read, but a converted fill (china/hk books: `bot/settle.py:684-699`) binds no common generation between the native leg and the fx leg |
| M10 | `authority_class` | `stage` is descriptive, not a contract; nothing separates valuation from executable observation |
| M11 | `eligibility` verdict block | Absent; today's schemas structurally forbid claiming qualification |
| M12 | `calendar_version` | Session claims need the holiday-calendar generation they were checked against |

---

## 2. Outcomes and the binding rule

- **`ELIGIBLE`** — the record is complete for its venue (§1b fields populated for the
  applicable rows) and every venue rule in §3 holds against the decision cutoff.
- **`INELIGIBLE(reason)`** — a rule is *positively violated*: observation available after
  the cutoff; age over `max_observation_age_seconds`; session mismatch; adjusted basis;
  fx generation mismatch; mark date presented as exchange time; missing source generation.
  The reason is one of a closed, named set (per counterexample in §4).
- **`UNKNOWN(reason)`** — a required field is absent/undeclared (today: all of them).
  Unknown is not eligible and not a violation — it is missing evidence.

**Binding rule: only `ELIGIBLE` may price a simulated fill.** One `INELIGIBLE` or
`UNKNOWN` ticker fails the settlement the same way `unpriceable_target_requirements` does
today — structured fail-closed, no partial write (existing pattern:
`bot/settle.py:115-152`, `paper_account.py:3249-3270`).

**The positive-scalar fallback is never ELIGIBLE.** Specifically, regardless of value:
`last_price` / `_current_price` fallback labels (`bot/settle.py:605-616`), the `est_price`
rescue fallback (`scripts/fill_pending_now.py:101-102`), `avg_cost` in any position
(`:2015`, `:2056`, `nav :1707`, `mark :3381`), and `decision_mark` records with
`upstream=None` (`bot/settle.py:404-407`) are `INELIGIBLE("positive_scalar_fallback")`.
`_trusted_execution_price` remains the floor predicate (never weakened); eligibility is
strictly stronger and strictly additive.

---

## 3. Per-venue rules

Common rules, all venues: the observation's availability time must be ≤ `decision_cutoff`
(no future observations); age = `cutoff − available_at` ≤ `max_observation_age_seconds`;
`session_date` must equal the settlement session for that venue's calendar
(`calendar_version` bound); basis must be `raw` for execution sizing (Masterplan: raw
executable prices for transaction simulation); native-currency price required, conversions
carried as a bound fx leg; the settle scheduler's own convention (US book settles
~15:00 UTC ≈ 10:00 ET, `bot/settle.py:12-14`) is a caller fact, never an exchange fact.

| Venue | Session (regular) | Timezone | "Open" means | Max age vs cutoff (v1 default, parameterized) | Basis | Currency / FX generation |
|-------|-------------------|----------|--------------|----------------------------------------------|-------|--------------------------|
| US — NYSE/Nasdaq | 09:30–16:00 | `America/New_York` (DST-aware) | The settlement session's regular-session opening print (opening auction / first regular-way trade). Snapshot `day.o` qualifies only when bound to that session date; a daily-bar Open qualifies only when its `source_bar_label` is that session date | 4h from `available_at` (covers the 10:00 ET settle; no same-tolerance reuse next day — the session rule already excludes prior days) | raw (unadjusted) | USD native; no fx leg |
| SSE/SZSE incl. STAR (688xxx) | 09:30–11:30, 13:00–15:00 (opening call auction 09:15–09:25) | `Asia/Shanghai` | The settlement session's opening call-auction print (the day-open). A-shares have no US-session overlap: a "settle at open" run at a US-hour cutoff cannot be ELIGIBLE for an A-share leg | 4h from `available_at`, and availability must be ≥ that session's 09:25 CST | raw | CNY native; any USD conversion needs `fx_generation_id` shared by every converted leg of the same fill; static fallback rates (`fx.py:34`, `_FALLBACK CNY 7.2`) are `INELIGIBLE("fx_static_fallback")` |
| HKEX | 09:30–12:00, 13:00–16:00 (pre-opening auction 09:00–09:30) | `Asia/Hong_Kong` | The settlement session's opening print after the pre-opening session. HK-book gating already distinguishes the HKEX calendar+hours (`bot/settle.py:73-84`) — the eligibility record inherits that calendar identity | 4h from `available_at`, and availability ≥ that session's 09:30 HKT | raw | HKD native; same fx-generation rule; static 7.80 peg fallback ineligible |

Benchmark legs (SPY / 000300.SS / ^HSI) settle inside the same transaction
(`paper_account.py:3258-3263`) and get their own verdicts; an index symbol's
`instrument_class: "index"` mark is eligible only for the benchmark NAV leg, never as a
single-name fill price.

---

## 4. Counterexamples — each a named future test

| # | Test name | Injected condition | Required outcome |
|---|-----------|--------------------|------------------|
| 1 | `test_future_observation_rejected` | `available_at` (provider publication) after `decision_cutoff` — e.g. snapshot `updated` (once unit-typed) post-dates the cutoff | `INELIGIBLE("observation_after_cutoff")`; no fill booked |
| 2 | `test_stale_beyond_max_age_rejected` | age `cutoff − available_at` > `max_observation_age_seconds` (e.g. prior-evening retrieval consumed at 10:00 ET settle) | `INELIGIBLE("stale_beyond_max_age")` |
| 3 | `test_prior_session_open_rejected` | daily-bar Open with `source_bar_label` = previous trading day presented as today's fill price (the `exchange_date_mismatch` case yahoo currently swallows into a fallback, `yahoo_feed.py:549-556`) | `INELIGIBLE("session_mismatch")`; fill does NOT silently fall through to `last_price` |
| 4 | `test_adjusted_basis_rejected` | `basis: "adjusted"` scalar (e.g. an `adjusted=true` aggs close, `polygon.py:97`) used for execution | `INELIGIBLE("adjusted_basis")` |
| 5 | `test_fx_generation_mismatch_rejected` | two legs of one china-book fill converted at different fx cache generations (one leg yesterday's `CNH=X`, one today's) | `INELIGIBLE("fx_generation_mismatch")` for the fill |
| 6 | `test_mark_date_presented_as_exchange_time_rejected` | a stored `current_price`/`current_price_asof` (`current_price_time_kind: "portfolio_mark_date"`, `paper_account.py:3375`) offered as the exchange event time of an executable observation | `INELIGIBLE("mark_date_not_exchange_time")` |
| 7 | `test_missing_source_generation_rejected` | otherwise-complete record with `source_generation_id: null` (today's universal state — polygon `updated` unit unestablished) | `UNKNOWN("source_generation_missing")`; not ELIGIBLE |
| 8 | `test_positive_scalar_fallback_never_eligible` | `last_price`, `est_price`, or `avg_cost` scalar passes `_trusted_execution_price` | `INELIGIBLE("positive_scalar_fallback")` even though the numeric predicate passes |

---

## 5. Where the check sits (call sites from part A)

Primary seam — the price→fill boundary on the complete-target path:

- `portfolio/paper_account.py:3249-3282` — `settle_target`: alongside
  `unpriceable_target_requirements` (which keeps its positive-scalar floor), an eligibility
  recheck runs over the same `prices`/`sources` map before `_pending_clear_transition` and
  `rebalance`; failures raise the existing `UnpriceableExitPrices`-style structured stop.
- `portfolio/paper_account.py:2077-2093` — `rebalance`'s dropped-name exit gate: same
  recheck for direct low-level callers.
- Verdicts are captured beside `price_evidence.settlement_snapshot` at
  `portfolio/paper_account.py:535-553` and read back via the settlement receipt
  (`validated_settlement_snapshot`, `price_evidence.py:472-521`;
  `app/settlement_price_read.py:222-246`) — the reader gains the verdict as inspection
  material, exactly as #1614's capture did.

Bypass seams (part A §A.2) each need their own gate before enforcement can claim coverage;
gating only Chain A would just move fallback fills to these paths:

- `execute_fill` scalar/`_current_price` selection — `paper_account.py:2196` (caller:
  `bot/derisk.py:610`).
- `fill_pending._px_for` — `paper_account.py:2471-2475` (callers: `bot/phase2.py:2702`,
  `scripts/fill_pending_now.py:108`, including its `est_price` fallback `:101-102`).
- Flagship open cycle — `bot/phase2.py:2696-2709`.
- Heavyweight build→rebalance — `bot/heavyweight.py:509-525`.
- Advisor-book simulator — `portfolio/self_directed.py:192, 367` (separate store; scope
  decision explicit in the enforcement review).
- Evidence-optional seam — `bot/settle.py:398-409`: under enforcement, an evidence-build
  failure must stop settlement (UNKNOWN ≠ eligible), not proceed with empty context.

---

## 6. Rollout — no numeric change first

Constraints that shape this: capture shape is part of the transaction preimage, so any
change to what joins `transaction_identity` rotates future transaction/fill ids
(`price_evidence.py:440-446`); and today every producer is structurally ineligible
(all of §1b missing), so immediate enforcement would block all settlement.

- **Step 0 — this spec.** No code. Approval of the field set, outcome rule, venue table,
  and counterexample tests.
- **Step 1 — shadow (no numeric behavior change).** Producers compute verdicts from
  already-captured evidence and store them OUTSIDE the preimage (receipt-adjacent sidecar
  or an additive receipt field excluded from `transaction_identity`), so ids, fills,
  sizing, and NAV are byte-identical. Acceptance: all seven evidence test suites stay
  green (`test_selected_price_evidence`, `test_selected_price_receipt_integration`,
  `test_fx_price_evidence`, `test_polygon_open_price_evidence`,
  `test_polygon_snapshot_evidence_capture`, `test_yahoo_open_evidence_capture`,
  `test_settlement_price_read` — current source state: 411 passed, 6 failed
  environment-only per part A §A.3), plus the eight §4 tests passing, plus a
  numeric-identity assertion that shadow verdicts change no id and no fill.
  Gate owners observe shadow verdict distributions before any flip.
- **Step 2 — enforcement (separately approved, behavior-changing).** Flip
  `settle_target`/`rebalance` to require ELIGIBLE; producers gain the §1b fields they can
  populate; UNKNOWN/INELIGIBLE fail closed through the `_unpriceable_target_stop`
  pattern; bypass sites (§5) gated in the same change or explicitly out of scope by name.
  This step changes which fills book (fallback-priced fills stop booking) and therefore
  requires its own approval, its own rollout review, and the bot's paper-only, no
  auto-execution boundaries untouched.

## 7. What this spec does NOT authorize

1. No source edits, no tests written, no deployment, no install claim — spec only.
   (Install status unchanged: 43f83e068 merged, not installed on the VPS at ff16c192c.)
2. No declaration that any current producer or record is ELIGIBLE. Today all are UNKNOWN.
3. No enforcement now, and no change to any numeric behavior, fill id, or sizing.
4. No overwrite of `market_observed_at` / `execution_qualification` in existing schemas
   (validator-rejected and id-rotating); eligibility is a sibling record.
5. No removal or weakening of existing fail-closed guards
   (`_trusted_execution_price`, unpriceable-target stops, quarantine/CAS paths).
6. No real-money execution, no auto-execution, no trading or runtime authority — the bot
   remains paper-only with deterministic engines owning all sizing.
7. No claim of provider authenticity: an ELIGIBLE verdict means the observation satisfies
   the session/time/basis/currency rules, not that the provider told the truth.
8. No new queue, watcher, or permission path; rollout steps 1–2 proceed only through the
   program's existing admitted engineering lanes and review gates.
