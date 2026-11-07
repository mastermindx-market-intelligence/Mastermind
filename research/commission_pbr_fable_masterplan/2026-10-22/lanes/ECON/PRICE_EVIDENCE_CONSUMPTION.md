# #1614 selected-price evidence — source consumption proof (pbr-econ L-E5, part A)

Census lane: `pbr-econ-le5`, 2026-10-22. Worktree `pbr-econ-le5` at origin/master
`230e9a301` (contains merge 43f83e068 "Capture selected price context in paper settlement
receipts"). This is a **SOURCE consumption proof on origin/master only**. Installation is a
separate gate: the VPS runs `ff16c192c` with pre-#1614 `paper_account.py`/`bot/settle.py`
blobs and no `portfolio/price_evidence.py`. Nothing here is a deployment claim.

Scope guard repeated from the code itself: every schema in the #1614 family hardwires
`market_observed_at: None` and `execution_qualification: "not_checked"`, and the snapshot
validator *rejects any other value* (`portfolio/price_evidence.py:238-242`, `:494`;
`portfolio/fx_evidence.py:128`). Capture proves agreement with captured inputs, never
session, availability time, adjustment basis, venue, or order eligibility. The trace below
shows where the evidence is produced, where it is bound, and — decisively — that no
execution decision anywhere consumes it.

---

## A.1 Hop table — call graph from source read to reader

Statuses: **PRODUCED** = an evidence record is created/bound at this hop; **CONSUMED** =
an already-produced record (or its host call) is read/bound downstream; **NOT_CONSUMED** =
the value flows but its evidence/source context does not reach any downstream consumer.

### Chain A — `settle_open` (scheduler open settle; the complete evidence path)

| # | Hop | file:line | Status |
|---|-----|-----------|--------|
| A1 | Polygon source read: `day_open` selects snapshot `day.o`; raw fetch `_snapshot` (60 s TTL cache, retrieval clocks) | `data_layer/polygon.py:393-417`, fetch `:341-390`, observation emit `_emit_open_observation` `:244-337` | PRODUCED — `mastermind.polygon_snapshot_evidence.v1` (clocks, payload ticker, opaque `updated` with unit `not_established`) |
| A2 | Yahoo source read: `open_price_local` selects latest daily-bar Open; exchange-date match computed internally (zone selected by suffix) but only the date label + reason are recorded | `data_layer/yahoo_feed.py:521-568`, observation `_open_price_evidence` `:280-345` | PRODUCED — `mastermind.yahoo_daily_bar_evidence.v2` (`source_bar_label`, fetch clocks, `cache_refresh_basis: shared_close_cache`) |
| A3 | Paper fallback read: `_current_price` → `_live_price` (yahoo_close → tushare_close → vendored snapshot → engine series; FX divide via `fx.to_usd`) | `portfolio/paper_account.py:1599-1658`, `_live_price` `:1463-1596`, FX evidence `portfolio/fx_evidence.py` (`mastermind.fx_rate_evidence.v1`) | PRODUCED — `mastermind.price_read.v1`/`v2` (stages `paper_live`, `paper_current`; attempts + upstream) |
| A4 | USD open selection `_open_price_usd`: priority polygon day.o → Yahoo Open → `_current_price` (label `last_price`); each read wrapped in `price_evidence.read_with_evidence` (`:587`, `:598`, `:609`), each selection recorded via `make_read`+`emit` in `observed` (`:569-578`) with `attempts` notes (`:562-567`) | `bot/settle.py:526-616` | PRODUCED — `price_read.v1`, stage `us_open_selection`, selected source's own evidence as `upstream` child |
| A5 | Per-book aggregation `_price_and_sources`: etf (`etf_universe.price`, read `:663`), USD (`price_fn`=`_open_price_usd`, read `:677`), non-USD (`_current_price` `:689` then `fx.usd_to` `:693`, FX-converted v2 record via `observe(..., fx_context=...)` `:635-645`, `:697-698`) | `bot/settle.py:619-699` | PRODUCED — stage `settlement_selection` records; `result()` returns `(prices, sources)` (`:647-654`) and publishes `observations` into the `_evidence` sink (`:650-651`) |
| A6 | Capture at settle entry: `read_with_evidence(_price_and_sources, pid, sym_set, _open_price_fn=...)` returns `((prices, sources), price_context)` | `bot/settle.py:1081-1084` | CONSUMED — selection evidence carried into the settle call |
| A7 | Execution call: `call_with_evidence(paper_account.settle_target, prices, asof, portfolio_id=pid, _price_sources=sources, evidence=price_context)` | `bot/settle.py:1102-1109` | CONSUMED |
| A8 | `settle_target`: unpriceable gate `unpriceable_target_requirements` (`:3249-3253`; benchmark added `:3258-3263`) — predicate is `_trusted_execution_price` = finite positive scalar (`:1739-1750`, applied `:1820-1823`); then `_pending_clear_transition(..., prices, price_sources, _evidence)` | `portfolio/paper_account.py:3175-3291` (gate `:3249-3270`, transition `:3271-3273`) | CONSUMED (evidence passed on); the gate itself consumes only the scalar — positive-scalar admission, no time/venue qualification |
| A9 | Receipt capture: `transition["settlement_price_evidence"] = price_evidence.settlement_snapshot(settlement_prices, settlement_price_sources, registry.currency(pid), _evidence)`; on capture failure a `capture_error: snapshot_failed` stub is stored instead — capture never vetoes a numeric settlement | `portfolio/paper_account.py:535-553` (constructor `portfolio/price_evidence.py:438-469`, validator `:472-521`) | PRODUCED — `mastermind.settlement_price_evidence.v1` (per-ticker `binding_status` matched/unavailable + reason) |
| A10 | Fill simulation: `settle_target → rebalance(target, prices, asof, ...)` `:3274-3282` — sizing `target_dollar/px` (`:2035-2042`, NAV fallback `prices.get(ticker, pos["avg_cost"])` `:2015`), sell px `:2056`, dropped-name exit gate `_trusted_execution_price` `:2077-2093`, buy px `:2100-2132` | `portfolio/paper_account.py:3274-3282` → `rebalance` `:1948-2162` | **NOT_CONSUMED** — fills price off the bare scalars; no code path reads the evidence record to qualify, scale, or veto a fill |
| A11 | Commit + receipt: `_commit_account_and_fills(..., followup=_followup)` `:2138-2146` builds the transaction with `identity` seed embedding `followup` (incl. the evidence) in the hash preimage (`:1349-1392`, `transaction_id` `:1358`), then commits via `_recover_paper_transaction_unlocked` (`:1392-1393`), which durably publishes the receipt through `_write_settlement_receipt(transaction, pid)` `:1299` — receipt carries `transaction_identity` `:615`, `settlement_prices` `:623`, `settlement_price_sources` `:624-626` | `portfolio/paper_account.py:1319-1393`, `:1222-1312` (write at `:1299`), `:557-643` | PRODUCED — evidence becomes part of the immutable transaction preimage (hash-bound; ids can change when capture shape changes, `price_evidence.py:440-446`) |
| A12 | Finalization projection: `validated_settlement_receipt_prices(receipt)` `bot/settle.py:757`; executed rows rebuilt with `fill_price_source` from `settlement_price_sources` (default `settlement_snapshot`) `:796-801`; NAV mark `paper_account.mark(prices, ...)` `:849-855` | `bot/settle.py:708-957` | CONSUMED — numbers + source *labels* for ledger/position-log/mark rows; the observation record itself is still not interpreted (no eligibility read) |

### Chain B — `execute_or_queue` direct open-session settlement (decision marks)

| # | Hop | file:line | Status |
|---|-----|-----------|--------|
| B1 | Decision marks built upstream, unobserved: autonomous `_current_price` loop `bot/autonomous.py:265-273`; china `bot/china.py:265` (`fx.usd_to(_current_price)`), hk `bot/hk.py:260`, etf `bot/etf.py:240` (`etf_universe.price`), heavyweight `bot/heavyweight.py:512` | see left | **NOT_CONSUMED** — the reads that actually select these scalars never pass an evidence sink; nothing is produced at the true source read |
| B2 | Context manufactured at settle time: `make_read(ticker, price, currency, "decision_mark", stage="decision_input")` per ticker; on ANY exception `price_context` stays `{}` and settlement proceeds | `bot/settle.py:398-409` (`:404-407`, swallow `:408-409`) | PRODUCED — but a context-free v1 record: `source="decision_mark"`, `upstream=None`, no clocks, no bar label. Describes the scalar, does not evidence its origin read |
| B3 | Execution call with `_price_sources={ticker: "decision_mark"}` and the manufactured context | `bot/settle.py:410-417` | CONSUMED |
| B4 | Then identical to A8→A11 (`settle_target` → `_pending_clear_transition` → receipt) | `portfolio/paper_account.py:3271-3282`, `:535-553`, `:1299` | as A8–A11 |

Note the seam at B2/A-side equivalent: `bot/settle.py:408-409` — evidence build failure is
swallowed and the fill still executes; the receipt later shows `binding_status:
"unavailable"` per quote (A9). Execution is never gated on evidence presence. This is the
deliberate #1614 contract ("Observation failure must never discard or replace a numerical
price", `price_evidence.py:424`) and also the load-bearing gap A05 names.

### Chain C — read side (the ONLY evidence consumer in the tree)

| # | Hop | file:line | Status |
|---|-----|-----------|--------|
| C1 | Reader trigger: decision-availability view imports and invokes `read_settlement_price_evidence` with registry currency + `validated_settlement_receipt_prices` + decision fingerprint | `app/web.py:1273` (import), `:1287-1294` (call) | CONSUMED (trigger) |
| C2 | Inspection: receipt fingerprint match `:137-144`; price-map validation `:145-151`; capture extracted from `receipt["transaction_identity"]["followup"]["settlement_price_evidence"]` `:196-198`; `snapshot_failed` stub handled `:204-214`; decoder mounted by default to `portfolio.price_evidence.validated_settlement_snapshot` `:222-228`; rebuild `:229-242` | `app/settlement_price_read.py:26-247` | CONSUMED — `validated_settlement_snapshot` (`price_evidence.py:472-521`) deterministically re-derives the capture from the retained prices/sources and rejects drift (`settlement_price_capture_mismatch` `:519-520`) |
| C3 | Result: `price_context` + `context_status` surfaced in the decision-availability payload | `app/settlement_price_read.py:243-246` → `app/web.py:1299` (JSON response) | CONSUMED — display/inspection only. No scheduler, gate, or execution path reads `price_context` anywhere in the tree |

### Explicit NOT_CONSUMED inventory

1. **Fill pricing never consumes evidence** — A10: `rebalance` prices every fill from the
   bare `prices` dict; neither `settle_target` nor `rebalance` reads the observation record.
2. **`execute_or_queue` response rows drop the source stamp** — `bot/settle.py:477` calls
   `_diff_trades(before, after, prices)` *without* `sources` (the `fill_price_source`
   argument exists at `bot/settle.py:109-111` but is only used on the finalization path,
   `:796-801`).
3. **Persisted fill rows carry no source/evidence fields** — `_persisted_fill_facts`
   (`portfolio/paper_account.py:146-156`) emits shares/price/value only; `fills.jsonl` rows
   have no source or observation reference.
4. **`execution_qualification` is structurally unusable as a gate** — hardwired
   `"not_checked"` at `price_evidence.py:401`, `:468`; `polygon.py:283`;
   `yahoo_feed.py:202` (v1), `:297` (v2); `fx_evidence.py:225`; receipt stub
   `paper_account.py:552`; and *required* to be exactly that by
   `price_evidence.py:239-242`, `:494` and `fx_evidence.py:128`. Any future claim of
   eligibility in these fields is rejected by today's validator by design.
5. **`market_observed_at` is `None` in every emitted record** — the field exists in all
   schemas but no producer ever fills it; event time is therefore never available to any
   consumer (see part B gap list).
6. **Yahoo session check is internal and unrecorded** — `open_price_local` compares the bar
   date to "today" in exchange-local time (`yahoo_feed.py:536-556`) but records only a
   boolean outcome (`reason: exchange_date_mismatch`) + date label; no consumer re-checks
   the label against the settlement session.

---

## A.2 Bypass inventory — prices that can reach an execution/fill without the evidence path

| # | Site | Mechanism | Callers |
|---|------|-----------|---------|
| D1 | `portfolio/paper_account.py:2196` | `execute_fill`: `px = price if (price and price > 0) else _current_price(ticker)` — fill priced by caller scalar or an unobserved `_current_price` read | `bot/derisk.py:610` (fast de-risk sell, no price arg → `_current_price`) |
| D2 | `portfolio/paper_account.py:2471-2475` | `fill_pending._px_for`: `prices.get(ticker)` → `_current_price(ticker)` fallback; fills at that px (sells `:2482-2503`, buys `:2506-2531`) | `bot/phase2.py:2702`, `scripts/fill_pending_now.py:108` |
| D3 | `bot/phase2.py:2696-2709` | flagship marks built solely from `paper_account._current_price` (`:2697`), then `fill_pending(_prices, asof)` + `rebalance(dict(_tw), _prices, asof)` — full flagship fill cycle with no evidence anywhere | scheduler/open-market build |
| D4 | `bot/heavyweight.py:509-525` | prices from `_current_price` (`:512`) → `paper_account.rebalance(priceable, prices, asof, ...)` (`:525`) | heavyweight book build |
| D5 | `scripts/fill_pending_now.py:97-108` | manual rescue `_fill_price` chain: `polygon.day_open → quote → snapshot_price`; **then the queued order's own `est_price` becomes the fill price** (`px, src = float(o.get("est_price") or 0.0), "est_price"`) → `fill_pending` | operator rescue run |
| D6 | `portfolio/paper_account.py:2077-2093` | `rebalance` dropped-name exit: `_trusted_execution_price(prices.get(ticker))` — finite-positive admission, no evidence; also sell-line default `prices.get(ticker, pos["avg_cost"])` `:2056` (guarded by `:2035-2037`, so the avg_cost default is defensive/unreachable in the sell path) and NAV sizing fallback `prices.get(ticker, pos["avg_cost"])` `:2015` (affects share counts, not fill price) | every `rebalance` caller (A10, D3, D4) |
| D7 | `bot/settle.py:605-616` via `:552-557` | the `last_price` fallback of `_open_price_usd` **is observed** (not a bypass) but is precisely A05's positive-scalar-simulated-execution case: yesterday's/last Close books today's simulated fill, labelled only `last_price` | A5→A7 settle path |
| D8 | `bot/settle.py:398-409` | evidence-optional seam: context-build exception leaves `price_context = {}` and settlement proceeds (receipt records `binding_status: unavailable`) | Chain B |
| D9 | `portfolio/self_directed.py:192, 367` | advisor-book simulator prices its own fills at its own `_current_price`; separate store from `paper_account` (adjacent, listed for completeness — not the settlement path) | advisor chat order flow |
| D10 | `portfolio/nav` `:1701-1709`, `mark` `:3380-3383` | `prices.get(ticker, pos["avg_cost"])` valuation fallbacks — **not fills**; listed because avg_cost must stay out of the execution class. `mark` already stores `current_price_time_kind: "portfolio_mark_date"` (`:3375`) — the existing guard against relabeling a mark date as an exchange timestamp | valuation/reporting |

Positive-scalar admission predicate: `_trusted_execution_price`
(`portfolio/paper_account.py:1739-1750`) is the *only* execution-price test on the
complete-target path (A8) and the exit path (D6): finite and > 0. It cannot distinguish a
session-open from a stale close, an adjusted print, a wrong-currency scalar, or a
fabrication. This is the exact hook part B replaces with an eligibility verdict.

---

## A.3 Test results

Command (from this worktree, as instructed):
`~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q <file>` per file.

| File | passed | failed | skipped |
|------|--------|--------|---------|
| `tests/test_selected_price_evidence.py` | 100 | 0 | 0 |
| `tests/test_selected_price_receipt_integration.py` | 0 | 6 | 0 |
| `tests/test_fx_price_evidence.py` | 88 | 0 | 0 |
| `tests/test_polygon_open_price_evidence.py` | 42 | 0 | 0 |
| `tests/test_polygon_snapshot_evidence_capture.py` | 31 | 0 | 0 |
| `tests/test_yahoo_open_evidence_capture.py` | 23 | 0 | 0 |
| `tests/test_settlement_price_read.py` | 127 | 0 | 0 |

Failure lines (all 6 in `test_selected_price_receipt_integration.py`, parametrizations
`test_real_producer_receipt_retry_and_default_mounted_decoder[filled-*]` and
`[zero_fill-*]` for autonomous/china/hk):

```
tests/test_selected_price_receipt_integration.py:298: 
    ...
tests/test_selected_price_receipt_integration.py:36: ModuleNotFoundError
E       ModuleNotFoundError: No module named 'lib'
```

Root cause: **environment, not source**. `_source_inputs` imports `from lib import store`
(test line 36); `lib` is the vendored macro package reached through `vendor/macro`, which
at HEAD is a symlink to `macro_src` (`git ls-tree HEAD vendor/` → mode 120000) and
`macro_src` is not materialized in this lane worktree, so the import fails before any
assertion. Diagnostic re-run of the same file with the existing macro checkout on
`PYTHONPATH=/home/longr/lanes/repos/macro` (read-only; no worktree mutation):
**6 passed in 0.82s**. The tests are correct; this worktree lacks the vendored engine.

Combined run (all seven files, canonical command): 411 passed, 6 failed (all the
environment artifact above), 0 skipped.

## A.4 Method notes and open questions

- Sources traced on this worktree at `230e9a301`; the worktree is clean except the two new
  lane documents. `vendor/macro` symlink target absent (see A.3).
- `settlement_snapshot` is part of the transaction preimage: any change to capture shape
  changes future transaction/fill ids (`price_evidence.py:440-446`). Part B's rollout
  section must respect that.
- Open questions: (1) is the flagship `phase2` fill path (D3) still scheduled in
  production, or is the flagship effectively frozen (its book is marked archived-eligible in
  places)? — affects which bypass matters first. (2) `bot/derisk.py`'s heavyweight exit
  (D1) is a risk-triggered real paper sell priced by `_current_price` — should the
  eligibility gate exempt or include risk-firebreak exits? Part B proposes including them
  with an explicit risk-class rule, deferred to the enforcement decision.
