# ECON contracts — W2 prices & replay (A02, A03, A05 hand-off, A12)

Owner: `pbr-econ` (ECON domain, PBR program #1693). Status: **decided by ECON. These are
engineering contracts for the build lanes.** The A02 and A03 behaviour changes are
**reserved**: they get built, made green and independently reviewed, then go back to the
Fable seat for the acceptance row. ECON does not merge them, and nothing here is deployed.

Source baseline: `origin/master` 230e9a30. Evidence: the read-only VPS capture
`/Volumes/Mastermind/evidence/pbr/econ-capture-20261022T073119Z/` (#1698; not committed).
Every incidence number below comes from that capture, using commands listed in §5.

Three verdicts stay separate. This file is about **operational correctness** and
**economic qualification**. It makes no claim about investment value.

---

## (a) A02 — NAV qualification contract (`portfolio/paper_account.py`)

### The hole, as observed on master

- **`mark()`** (`paper_account.py:3294`) blocks on unfinalised settlement receipts and
  persists the price each held line was last observed at. That metadata is honest:
  `current_price`, `current_price_asof`, `current_price_source` and
  `current_price_time_kind`, never rolled back to an older date. The NAV it writes is not:
  `current_nav = cash + Σ shares × prices.get(ticker, pos["avg_cost"])` (`:3380`). A
  missing quote therefore books that line at cost, which hides its unrealised P&L.
- **`nav()`** (`:1701`) has the same `prices.get(t, avg_cost)` substitution. Its callers
  are the builder payloads (`bot/autonomous.py:593,750`, `china.py:514,680`,
  `etf.py:332,609`, `heavyweight.py:567,729`, `hk.py:509`) and
  `app/web.py:1339` `account_preview`.
- **Sizing sites with the same pattern.** `rebalance` (`:2015`, `:2056`) and
  `queue_orders` (`:2327`, `:2365`) do it too. These are adjacent A02 holes, recorded
  here and out of this PR's scope (see "Out of scope").
- **A carry can be re-stamped as fresh.** `mark()` stamps
  `current_price_asof = <mark asof>` for every price it is handed, including a price that
  `marks.mark_symbols()` resolved from its `last-good-carry` store. This is the same
  re-stamping that `marks.py` explicitly forbids for its own carry store.
- **The bot freeze already exists, and A02 must preserve it.** `brain/decision_submission.py`
  labels an unpriced held line `holding_mark_source = "account_avg_cost_fallback"` (`:296`).
  The builders (`bot/autonomous.py:209-222`, `china.py:207`, `hk.py:208`) then set
  `decided=False` with `frozen_held_quote_fallback`. The audit does not claim that this
  fallback currently authorises trading. A02 changes **valuation records**, not that
  decision fence.

### Valuation precedence (one pure helper, used by `mark()`)

The new pure function is
`paper_account.valuation(prices, asof, portfolio_id=None, *, price_evidence=None) -> dict`.
It performs no writes. For every held line with `shares != 0`, in order:

1. **FRESH.** `prices[t]` is finite and > 0, **and** `price_evidence[t]` attests a
   same-date observation: `stale_days in (None, 0)`, `source` is not a carry label, and
   `observed_asof == asof` whenever it is present.
2. **CARRIED.** One of two cases. Either `prices[t]` is finite and > 0 but its evidence
   says carry or `stale_days > 0`. Or `prices[t]` is absent and the persisted
   `current_price` satisfies `current_price_asof <= asof` (direction-aware; a newer
   persisted mark never values an older date) and
   `asof − current_price_asof <= marks.carry_stale_max_days` (the same doctrine knob,
   default 30). A CARRIED line keeps `price`, `price_asof`, `age_days` and `source`.
3. **UNATTESTED.** `prices[t]` is finite and > 0 but no evidence was supplied. This is a
   legacy caller. The value is used, but the line cannot qualify.
4. **UNPRICED.** Everything else. Never `avg_cost`, never zero.

`nav_status` for the book on `asof`:

| status | condition | NAV row written? | `nav` | `nav_qualified` |
|---|---|---|---|---|
| `QUALIFIED` | every held line FRESH (or the book holds no positions) | yes | cash + Σ value | = `nav` |
| `PROVISIONAL` | no UNPRICED line; ≥1 CARRIED or UNATTESTED | yes | cash + Σ value (back-compat number) | `null` |
| `WITHHELD` | ≥1 UNPRICED line, including the fully unpriced book | **no**; an existing row for that date is left untouched | — | — |

### Record contract (all additions; existing keys keep their meaning)

`nav_history.jsonl` rows gain the following keys. Readers that use `date/nav/cash/invested/spy_nav/benchmark` are unaffected.

```json
{"date": "...", "nav": 0.0, "cash": 0.0, "invested": 0.0, "spy_nav": 0.0, "benchmark": "SPY",
 "nav_status": "QUALIFIED|PROVISIONAL",
 "nav_qualified": 0.0,
 "carried": [{"ticker": "X", "price": 0.0, "price_asof": "YYYY-MM-DD", "age_days": 1,
              "source": "...", "value": 0.0, "weight_of_invested": 0.0}],
 "carried_value": 0.0, "carried_fraction": 0.0,
 "unattested": ["TICKER", "..."],
 "mark_source": "paper_account_mark|settlement_receipt|..."}
```

- **WITHHELD.** Append one idempotent-per-`(date, mark_source)` row to a new per-book
  `nav_withheld.jsonl`:
  `{date, mark_source, unpriced: [{ticker, shares, last_observed_price, last_observed_asof}], carried: [...], reason}`.
  `last_observed_*` is reported for diagnosis only and never enters a valuation. Exposure
  is stated in **shares** and in the last observed price, never at cost. The previous
  row stands.
- **Return value.** `mark()` returns the valuation dict instead of `None`. Existing
  callers ignore it.
- **`mark()` never raises because pricing is incomplete.** This is load-bearing.
  `bot/settle.py:849` treats any `mark()` exception as a finalisation failure and keeps
  the settlement receipt. A kept receipt blocks **every** later `mark()` for that book
  (`:3315`). Raising on an unpriced line would therefore freeze the book's NAV
  indefinitely. Settlement finalisation (cash and shares) must not depend on price
  completeness.
- **Persisted per-position mark metadata.** A CARRIED input keeps its **observed** date:
  `current_price_asof = price_evidence.observed_asof`, or `asof − stale_days`. It is never
  re-stamped to the mark date. The existing no-rollback rule is unchanged.
- **Benchmark (`spy_nav`).** Unchanged in this PR. A missing benchmark price already
  yields `null`. Benchmark qualification is A12 (§d).

### Composition

- **With the bot freeze.** Unchanged and preserved. `decision_submission` still labels
  `account_avg_cost_fallback` and the builders still freeze. A02 adds a second, independent
  guarantee: the **NAV ledger** never books cost as market.
- **With #824** (`brain/decision_submission.py`, outside ECON's file family). #824 turns
  the decision-boundary fallback into `DecisionBoundaryFreeze("unpriceable_held_position:<t>")`
  and keeps the builder fences. A02 and #824 touch disjoint files. Once both land, the
  same unpriced line produces (i) a frozen decision through #824 and the builder fence,
  and (ii) a WITHHELD NAV row through A02. Neither depends on the other's merge order.
- **With callers.** Wiring `price_evidence` is how a caller earns `QUALIFIED`.
  - `app/scheduler.py:1300-1390` already holds `marks.mark_symbols()` output (`union_usd`).
    It should pass `mark_symbols(...)["sources"]`, which carries `source` and `stale_days`
    today and `observed_asof` once A03 lands. That one-line wiring belongs to the RUNTIME
    file family and is requested from RUNTIME (W4).
  - Callers left unwired produce `PROVISIONAL` rows. That label is honest, not a regression.
- **`nav()`.** It keeps its float signature for back-compat. It gains
  `strict: bool = False` and routes through `valuation()`.
  - With `strict=True`, CARRIED lines are used and a WITHHELD valuation raises
    `NavWithheld(ValueError)`.
  - The legacy default stays avg_cost-substituting until every caller has migrated,
    because the callers are outside ECON's family (`bot/*.py` builders → RUNTIME,
    `app/web.py` → PRODUCT). The legacy path emits a counted
    `nav_avg_cost_fallback_used` log line so the remaining substitutions are measurable.
  - The default flips to strict in a later, separate PR once the counter is zero.

### Historical incidence (identify before estimating impact)

- **US union marks** (`data/marks/<asof>.json`, 77 files, 2026-07-03 → 10-21):
  - 0 held tickers UNPRICED;
  - 3 carries (MCY, DD, SGOV, age 1 d, on 07-30);
  - 59 UNPRICED rows, all `^HSI`, which is the HK benchmark and is not held.
  - So on the scheduler path, the avg_cost NAV substitution had **no observed incidence
    for US-held names**.
- **Builder-path marks** (`bot/*.py → mark()`) are not persisted per line, so their
  incidence cannot be read directly. It is a §5 census item: replay share counts from
  `fills.jsonl` against independent closes, and flag dates where
  `invested ≠ Σ shares × close` by about `shares × (close − avg_cost)`.
- **Rows dated on non-session days.** These are NAV rows dated a weekend, holiday or
  pre-open day whose values are byte-identical to the previous row, i.e. all lines
  carried while labelled fresh:
  - US: 06-28, 07-12, 07-19, 09-07, and 10-22 (written before the 10-22 session opened);
  - CN: 09-25 and 10-01 → 10-07;
  - HK: 10-01 and 10-19.
  - Under this contract they become `PROVISIONAL` with `age_days ≥ 1`. That is a
    labelling change; no value is restated. Historical rows are **not rewritten**. Any
    corrected history is a separately classified derived series.

### Acceptance (L-E3)

- The pure-helper unit matrix covers every combination of FRESH / CARRIED (from evidence
  and from persisted metadata) / UNATTESTED / UNPRICED × QUALIFIED / PROVISIONAL / WITHHELD.
- Direction-aware carry: a newer persisted mark never values an older date.
- No `avg_cost` term in any `mark()` or `valuation()` value path (grep test).
- `mark()` does not raise when the book is unpriced, and the settlement-receipt path is
  exercised.
- WITHHELD leaves an existing same-date row byte-identical.
- The `nav()` default is unchanged; `strict=True` raises `NavWithheld`.
- Carry re-stamp: `current_price_asof` equals the observed date.
- Existing `test_paper_account*` and `test_daily_marks` suites stay green.

**Out of scope for L-E3.**
- `rebalance` and `queue_orders` sizing that substitutes avg_cost. These are W3 simulator
  inputs; sizing must consume a qualified valuation and refuse when it is unpriced.
- Flipping the `nav()` default.
- Caller wiring outside `portfolio/`.
- `reset_cost_basis_to_market()` (`:1670`). It rewrites avg_cost to market and wipes
  unrealised P&L, and it has no non-test caller on master. It is a dormant reset tool and
  conflicts with the W1 no-reset law. It is flagged for W1 removal or quarantine and is not
  used by any lane.

---

## (b) A03 — direction-aware known-at for `portfolio/marks.py`

**Disposition: CONTINUE #726, #727 and #728. Do not supersede.**
- All three apply cleanly to master 230e9a30.
- Stacked, they pass 75 tests: their new tests plus `test_marks`, `test_shadow_books`,
  `test_interim_marks` and `test_daily_marks`.
- Their designs are correct as far as they go. L-E4 rebases them onto `origin/master` as
  one ECON carrier, preserving the original commits and authorship, and adds items 4-8
  below.

What #726/#727/#728 already contribute (kept as is):

1. `_days_between(requested, observed)` is **directional**, returning requested −
   observed. A carry is eligible only when `0 <= d <= carry_stale_max_days`, so a
   later observation can never qualify for an earlier cutoff.
2. `_polygon_eod(symbol, asof)` has a historical cutoff. For `asof < today` it calls
   `polygon.daily_closes(symbol, asof, asof)` (that session's bar only) and never the
   snapshot.
3. Consumers propagate asof:
   - `desk_ab` passes asof into `_gather_prices` (#727).
   - `shadow_books` uses one normalised `mark_asof`, and the live-quote fill is allowed
     only when `mark_asof == today` (#728).

What L-E4 adds:

4. **Observed date on every source row.** `mark_symbols()["sources"][S]` gains
   `observed_asof`, `retrieved_at` and `basis`, and `stale_days` is computed from
   `asof − observed_asof` for **every** source, not only carry:
   - Polygon aggregates use the bar date.
   - The yahoo parquet uses the index date of the last row ≤ asof.
   - Today `_yahoo_parquet` returns `s.iloc[-1]` with no age check, so a parquet row
     days older than asof is labelled fresh with `stale_days=None`.
   - A yahoo row older than the stale bound is ineligible. A row inside the bound is
     reported with its age, so A02 classes it CARRIED.
5. **Same-day close vs after-hours print.** All 77 captured union-mark files were written
   at about 22:xx UTC, after the US close, labelled `polygon-eod`. For `asof == today`,
   `_polygon_eod` calls `snapshot_price`, which takes **`lastTrade` first**. At 22Z that
   is an extended-hours print, not the official session close.
   - Contract: `asof == today` and the session is closed → `daily_closes(sym, asof, asof)`
     (the official bar).
   - Snapshot is used only before the close, under the distinct source label
     `polygon-intraday`, and never satisfies A02 FRESH-for-close.
   - A `prevDay` snapshot fallback is reported with `observed_asof` = the previous
     session, so it classes CARRIED with age ≥ 1.
6. **Monotone carry.** The carry store is refreshed only when the new `observed_asof` is
   ≥ the stored `asof`. A historical replay or backfill (`asof < max stored asof`) must
   never roll `last_good.json` backward. The `data/marks/<asof>.json` audit file stays
   per-asof.
7. **Adjustment basis.**
   - Polygon `adjusted=true` aggregates and yahoo dividend-adjusted closes are restated
     after later splits and dividends. A historical mark fetched after a corporate action
     is "as adjusted at retrieval", not "as known at asof".
   - Contract: each source row records `basis` (`split_div_adjusted_at_retrieval` or
     `raw`).
   - For valuing **unadjusted** share counts on `asof < today`, the raw-close path
     (`daily_closes(..., adjusted=False)`, a new keyword defaulting to today's behaviour)
     is the qualified one. An adjusted historical close is reported, carries its basis,
     and does not qualify A02 FRESH when a corporate action falls between asof and
     retrieval.
   - This is the §7.2 `basis` observation field.
8. **Incidence census (read-only, ECON).** Record actual incidence; this is not proof
   that every backtest is contaminated.
   - Live store: 77 of 77 `data/marks/<asof>.json` files have `ts` date = asof (76) or
     the same US evening rolling into the next UTC day (1, 07-15 → 07-16T01:06Z). So
     **no historical backfill of the live union-mark store is observed**, and the
     absolute-days and undated-snapshot defects had **no observed incidence on the live
     scheduler path**.
   - Exposure sits in the replay and backtest consumers: `desk_ab`, `shadow_books` and any
     `mark_symbols(asof < today)` caller. Corrected replay histories are classified
     separately from originals, and originals are preserved.
   - The magnitude of item 5 (after-hours `lastTrade` vs official close) is still
     unmeasured. It is a W3 census item against Polygon raw daily aggregates.

**Acceptance (L-E4).**
- The #726/#727/#728 tests pass unchanged.
- New tests:
  - directional stale (negative d is ineligible);
  - yahoo stale age reported and bounded;
  - `asof == today` after close uses the aggregate, not `lastTrade`;
  - `prevDay` is classed carried;
  - monotone carry under replay;
  - basis field present.
- `pfn(sym)` injection keeps working for existing tests.
- `test_marks`, `test_daily_marks`, `test_interim_marks` and `test_shadow_books` stay
  green.

**Reserved.** Items 4, 5 and 7 change mark selection, so the carrier returns to the seat.

---

## (c) Disposition of #824 / #726 / #727 / #728 and interfaces consumed

| carrier | disposition | why | lane | interface it hands on |
|---|---|---|---|---|
| #726 | **CONTINUE** (rebase + items 4–8) | applies cleanly, tests green on 230e9a30, design correct | L-E4 | `mark_symbols(symbols, asof)["sources"][S] = {source, price, stale_days, observed_asof, retrieved_at, basis}` — the `price_evidence` input to A02 |
| #727 | **CONTINUE** (folded into the L-E4 carrier) | asof propagation into `desk_ab._gather_prices` is correct | L-E4 | replay consumers call `mark_symbols(..., asof)` with the decision asof |
| #728 | **CONTINUE** (folded into the L-E4 carrier) | one `mark_asof`; live-quote fill only when `mark_asof == today` | L-E4 | shadow books value through the same source rows. Its own note that `_mark_to()` still substitutes avg_cost is **routed to L-E3's follow-up** and is not fixed silently |
| #824 | **CONTINUE as its own carrier** (not ECON's file) | `decision_submission` raises `DecisionBoundaryFreeze` instead of the avg_cost fallback; keeps the builder fences; composes with A02 (§a) | seat / owner of `brain/decision_submission.py` | the decision boundary consumes the same "unpriced held line" fact that A02 records as WITHHELD |

Build lanes and the interfaces they consume:

- **L-E3 (A02).** Consumes `price_evidence: Mapping[str, {source, stale_days, observed_asof?}]`.
  It must accept today's `mark_symbols()["sources"]` shape, with `observed_asof` optional
  until L-E4 lands.
- **L-E4 (A03).** Produces that shape. Neither lane edits the other's file.
  `paper_account.py` (L-E3) and `marks.py` (L-E4) are disjoint, so they can build in
  parallel.
- **L-E5 / A05.** The #1614 selected-source context is consumed **read-only**. Executable
  eligibility is a separate contract (`EXECUTABLE_PRICE_ELIGIBILITY.md`) that reuses this
  file's `observed_asof` / `basis` / session fields. It does not reuse the valuation
  status.

---

## (d) A12 — benchmark plan (#1432 / #1433 / #1434)

Scope: #1433's −105 pp example is a **reproduced source counterexample, not an observed
managed-book loss**. No claim is made that it caused any account's result.

1. **Land #1432 first** (`brain/benchmark_ledger.py` `latest()` selects ISO-dated ledger
   files only, so the `_series.json` and `_series_meta.json` sidecars can no longer
   displace it).
   - The master `benchmark_ledger.py` is byte-identical to #1432's tested base.
   - The diff applies cleanly and its 23 tests are green.
   - Selection semantics are not NAV/mark/settlement semantics, and the file is in
     ECON's family (`portfolio/benchmark*` → `brain/benchmark_ledger.py`).
   - **Merge path:** ECON may merge after green checks plus an independent `VERDICT: PASS`
     review lane.
   - Live relevance: the capture's `benchmark/` holds `_series_meta.json` next to the
     dated files, so the sidecar collision exists in the live layout.
2. **#1434 helper** (`brain/benchmark_comparison.py`: `compare_curves`,
   `aligned_regime_envelope`) implements the #1433 smallest boundary:
   - named curves;
   - explicit cohort and asof cutoff;
   - actual common endpoints, with ≥2 finite-positive dated points;
   - no forward-fill and no missing-as-zero;
   - C(end)/C(start)−1 rebasing without re-weighting;
   - pairwise deltas on the named pair only;
   - one shared window for ranking;
   - regime-max recomputed after alignment.

   Disposition: CONTINUE. It is review-ready as a pure helper with **no consumer wired**,
   so it is mergeable with the same evidence as #1432.
3. **Consumer proof** (what closes A12). Each consumer must call the helper and
   **withhold** an unsupported delta:
   - the web benchmark-delta surface (PRODUCT family);
   - the improvement-agenda benchmark item (RESEARCH/seat);
   - attribution, which stays `building` with no score.

   Constraints:
   - The scheduler builds benchmarks **before** the book mark loop and supplies no book
     curves. So the consumer reads `nav_history` (with A02 `nav_status`) and benchmark
     ledgers **after** the mark loop. It does not re-order the scheduler.
   - Persisted cumulative leaderboard returns are not replaced.
   - CN and HK keep their native benchmark lineage (`000300.SS`, `^HSI`).
4. **A02 composition.** A comparison window whose endpoint rows are `PROVISIONAL` carries
   that label through. A `WITHHELD` date is not an endpoint.

Sequencing:
- #1432: review lane → ECON merge.
- #1434: review lane → ECON merge.
- Consumer PRs: owners of web/agenda, with ECON review. Wave 1 builds A12 only if a slot
  is free.

---

## 5. Commands behind the incidence numbers (read-only, local capture)

- **Union-mark incidence.** Iterate `live-data/marks/20*.json`. Count `sources[*].source`
  in (null, `last-good-carry`) per file, list the tickers, and compare against held
  tickers. Result: held unpriced = 0; carry = 3 (07-30, age 1); `^HSI` unpriced = 59.
- **Backfill detection.** For each file, `ts.date() − as_of` gives the histogram
  `{0: 76, 1: 1}`. The UTC write hour is `22` for 76 files and `01` for 1.
- **Identical consecutive NAV rows.** Compare per-book `nav_history.jsonl` rows on
  `(nav, cash, invested)`. Dates are listed in §a.
