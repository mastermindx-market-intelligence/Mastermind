# PRODUCT contract requests: wave 1

Owner: `pbr-product` (PRODUCT domain, PBR program #1693). This file lists the fields the product surface needs and does not own.

The display rule: until a field ships through its owner's contract, the view renders the word `unavailable` in that slot, with no number, zero, placeholder dash or inferred value. A request names the field, type, nullability, units and provenance. It does not prescribe implementation.

Census-derived rows (E11, S5) come from the verified census in `PRODUCT_CENSUS.md` (gap map V2, V4 and V6).

Status vocabulary: `requested` → `accepted by owner` → `shipped (PR #)` → `consumed (PR #)`.

## To ECON (accounting, marks, settlement)

ECON has published the A02/A03/A12 contracts in #1699. Rows marked *(A02)* or *(A12)* are consumption requests against that published shape. They do not ask for new design.

| # | field (where) | type | null | units | provenance | product consumer | status |
|---|---|---|---|---|---|---|---|
| E1 | `nav_history[].nav_status` *(A02)* | enum `QUALIFIED\|PROVISIONAL` | absent on pre-A02 rows → render `unverified` | — | `paper_account.valuation()` | Overview hero NAV badge; Performance curve point styling | requested (A02 published) |
| E2 | `nav_history[].nav_qualified` *(A02)* | number | null when PROVISIONAL | USD (book currency for CN/HK) | same | Overview: show the qualified NAV; a PROVISIONAL row shows `nav` with the "provisional" label | requested |
| E3 | `nav_history[].carried[]` `{ticker, price, price_asof, age_days, source, value, weight_of_invested}` *(A02)* | array | empty array, never absent once A02 lands | price in book ccy; `age_days` in calendar days | same | Overview limitations list ("MU priced from 2026-10-21 close, 1 day old") | requested |
| E4 | `nav_history[].unattested[]` *(A02)* | string[] | empty array | tickers | same | Limitations list | requested |
| E5 | `nav_withheld.jsonl` rows *(A02)* `{date, mark_source, unpriced[], carried[], reason}` | file per book | file absent → no withheld dates | shares and last observed price, never cost | `paper_account.mark()` | Performance: a WITHHELD date is a gap with a reason, not a flat line | requested |
| E6 | an API projection of E1–E5 for the **current** valuation (e.g. `/api/portfolio.valuation = {status, asof, nav, nav_qualified, carried[], unattested[], unpriced[]}`) | object | `status:"unavailable"` when no valuation exists | — | ECON helper; PRODUCT owns the `app/web.py` wiring | Overview header | requested. PRODUCT will wire it in `app/web.py` once ECON names the read helper; the legacy `paper_account.nav()` call at `app/web.py:1339` migrates to `valuation()` at the same time |
| E7 | `account.cash` | number | **must stay distinguishable from 0** (`/api/portfolio` currently coerces `or 0.0`) | book ccy | `account.json` | Overview cash tile | requested: confirm that a missing `cash` is a contract error. PRODUCT then removes the coercion and renders `unavailable` |
| E8 | benchmark comparison *(A12, #1434 helper)* `{status: supported\|unsupported, reason, start, end, book_return, bench_return, delta}` | object | `status:"unsupported"` → every number null | fraction | `brain/benchmark_comparison.compare_curves` | Overview "vs SPY" tile; Performance overlay | requested. PRODUCT consumer PR follows #1434 merge (ECON reviews) |
| E9 | pending-target lifecycle: `expires_at`, `superseded_by`, `final_disposition` (`filled\|partially_filled\|expired\|superseded\|rejected`), `disposition_at`, `receipt_id` | ISO-8601 UTC / enum / string | each null until known; never absent | — | settlement (`bot/settle.py`) + `pending_target.json` | Pending activity: show the expiry/supersession of a queued target and its final outcome | requested |
| E10 | per-fill realized P&L basis for closed-trade stats (`fills[].realized_pnl`, `fills[].cost_basis_method`) | number / enum | null for buys | book ccy | settlement | Trade History scorecard (win rate only above a minimum closed-sample size) | requested |
| E11 | per-holding return attribution over a stated window `{ticker, window_start, window_end, contribution, contribution_basis: realized\|unrealized\|both, priced_through}` | array | a holding with an unqualified mark in the window → `contribution:null` with the reason | fraction of book NAV at window start | settlement + A02 marks | Performance: which holdings drove the return (census gap V4: attribution missing) | requested (census) |

## To RUNTIME (provider, lifecycle, scheduling)

| # | field | type | null | units | provenance | product consumer | status |
|---|---|---|---|---|---|---|---|
| R1 | lifecycle projection per book `{run_status: ok\|degraded\|failed\|halted\|not_scheduled, last_decision_at, last_attempt_at, next_scheduled_at, failure_reason_code, halted_by}` | object | `run_status:"unavailable"` when there is no projection | ISO-8601 UTC | RUNTIME lifecycle store | Operations view; Overview status strip | requested. L-P4 builds against a documented stub that renders `unavailable` until this ships |
| R2 | `next_eligible_session` for a queued target `{session_open_at, market, reason}` | object | null when not queued | ISO-8601 with offset | market calendar + scheduler | Pending activity ("fills at the 2026-10-22 09:30 ET open"). Today the UI uses `market.next_open`, which is the market's next open, not necessarily the book's eligible session | requested |
| R3 | provider and data-feed health `[{feed, status: live\|stale\|down, asof, stale_after_s}]` | array | empty → `unavailable` | seconds | feed-health gate | Operations view | requested |
| R4 | settlement receipt reference `{receipt_id, status: retained\|finalised, retained_reason}` per book | object | null when none | — | `bot/settle.py` | Operations failure states (a retained receipt blocks marks) | requested |
| R5 | scheduler wiring of `price_evidence` (ECON A02 caller, `app/scheduler.py:1300-1390`) | — | — | — | RUNTIME | prerequisite for E1 = QUALIFIED | ECON already requested it. PRODUCT records the dependency only |

## To RESEARCH (decision context, thesis)

| # | field | type | null | units | provenance | product consumer | status |
|---|---|---|---|---|---|---|---|
| S1 | per-holding thesis `{ticker, thesis_summary, probability, check_by, falsifier, stage 0–4, decision_id, asof}` | object per holding | holding without a thesis → `unavailable` | probability 0–1; date | decision ledger | Holdings detail drawer | requested |
| S2 | 6-dimension confirmation scorecard per holding `{dim, score, evidence_ref}`×6 | array | missing dims are listed, not zero-filled | score scale named by RESEARCH | scorecard engine | Holdings detail | requested |
| S3 | per-name exit rationale for a queued exit `{ticker, decision_id, exit_reason_code, narrative, asof}` | object | null → the row shows the exit is queued without a rationale | — | decision ledger | Pending activity: the reason MU is being exited, which never overrides the account (§10.2) | requested |
| S4 | evidence items `[{claim, source, asof, observed\|inferred}]` | array | empty | — | research layer | Decision context; inferred items are tagged | requested |
| S5 | per-holding horizon and review condition `{ticker, horizon_end, next_review_at, review_condition, decision_id}` | object per holding | absent → `unavailable` (never derived from holding age) | date; ISO-8601 UTC | decision ledger / thesis store | Position review and Manager decision (census gaps V2 and V6: no horizon, no next-review condition) | requested (census) |

## Product-side truth rules these requests serve (MASTERPLAN §10.2, verbatim)

- "A natural-language explanation cannot overrule the actual account."
- "A queued MU exit must show as a pending change while MU is still held."
- "An unavailable benchmark displays unavailable rather than zero."
- "Do not visually reward a missing-price flat line as low volatility or a tiny closed-position sample as a winning strategy."
