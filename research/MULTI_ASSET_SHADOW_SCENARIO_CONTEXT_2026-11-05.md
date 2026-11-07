# Multi-asset portfolio what-if context: source-only implementation and adoption boundary

**Date:** 2026-11-05 America/Vancouver. **Operation:** `multiasset-shadow-20261105-sol`.
**Parent commission:** Grey Deer / MAS-258 / Macro #10795 (MA-4) and Chairman's multi-asset directive.
**Mastermind source base:** `337d69d5b0e8aa2e3ce5019f4b528912947d2e3b`.
**Protected procedure:** Mastermind same commit as base, Skillpack 1.0.1, bootstrap major 1.

**State:** isolated research-source implementation; no production or live-client consumer, no portfolio decision, no predictive qualification or release. Parent MA-4 remains incomplete. This module does not authorize any money movement or account mandate change.

## Exact owner fit

Do **not** replace or import into the current `portfolio/firm_allocator.py` (shadow-only inter-book allocator), `portfolio/shadow_books.py` (existing forward-policy counterfactual owner), `portfolio/firm_exposure.py` (firm-level look-through and US-book subtract-only cap), `portfolio/instrument_policy.py` (market-specific positive stock eligibility), `portfolio/mandate_packet.py` (mandate advisory) or `brain/posture_decider.py` (default-off shadow posture). Their statuses do not grant authority to this feature.

Existing `portfolio/fx.py` permits approximate static CNY/HKD fallback paper marks: NOT qualified FX for a new cross-jurisdiction return/hedging simulation. `portfolio/fx_evidence.py` is the incumbent rate provenance interface; the new pure comparator requires **declared qualified FX ancestry**, and still does not independently authenticate an FX quote. A future native adapter must check both actual source and first availability before passing such input.

The Portfolio Bot Rebuild (Mastermind #1693, #1695) is an existing, separate Fable-owned operational/economic program. Its source and writers are not displaced or used as authority. This additive implementation owns only `portfolio/global_scenario_context.py`, `tests/test_global_scenario_context.py` and this scope record; no existing portfolio module was edited.

## Consumer job

Given a **caller-supplied and owner-qualified** immutable book/mandate snapshot and fully specified candidate alternatives, compare hold, higher cash, partial rotation or staged return across explicit **hypothetical** return scenarios. Show net results, non-additive shared risk-key exposures, constraint conflicts, precise costs and missingness. Cash must have its own assumed return; no free implicit cash. Neither an observed ETF market return nor a historical market analog is a forecast.

### Contract

`portfolio.global_scenario_context.compare(book, alternatives, scenarios, *, as_of)` is deterministic, no I/O, state or clock calls. Inputs include:
- Book and constraint revision; explicit timezone-aware known-at / valid-until, base currency, funded positions and cash exactly summing to one; instrument identities with current policy refs, eligibility and shared risk keys. These declared fields are **not** authenticated simply by this function.
- Every proposed alternative has an ID, explicit funded target positions and cash, and per-traded-notional **one-way** fee, spread-crossing and market-impact costs, separated to avoid recharging quoted full spread.
- Every hypothetical scenario has source/revision ref and first-known/expiry clocks, a separately assumed cash return and finite base-currency total returns for every target with weight above zero; foreign instruments require explicit qualified FX ancestry. No probability or model confidence is accepted or originated.
- Maximum per-instrument concentration, risk-key concentration (non-additive groups), traded-notional fraction, and minimum cash are caller-supplied constraint ceilings. Breaches are identified, never overridden.

`scenario_gross_return = cash_weight * cash_assumption + sum(target_weight * instrument_assumption)`.

`one_time_cost = sum(abs(target_w - current_w) * (fee + spread_crossing + impact)_bps / 10000)`.

`scenario_net_return = scenario_gross_return - one_time_cost`.

The cash funding leg is not charged as an asset trade. Both a sell and a buy are charged when both happen. Comparisons are sorted by **identity**, not expected performance. `worst_hypothetical_net_return` is the minimum among supplied, fully qualified artificial scenarios; it is **not** statistical expected shortfall (no scenario probabilities or sampling distribution).

Missing source/revision, invalid/naive clocks, stale data, unknown FX, incompatible return basis, unknown instrument, nonfinite inputs, duplicate IDs, partial scenario coverage and constraints produce explicit abstention, ineligibility or partial statuses. All `authority` values are false; no optimization, ranking, sizing, orders, notifications, ledger or capital schedule.

## Adversarial validation and limits

Focused `tests/test_global_scenario_context.py` includes fully-funded arithmetic, cash, sell/buy cost once, hypothetical worst-case, source clocks, FX direction/provenance, unavailable assumptions, duplicate identity, risk-cap constraints, input mutation and input-order digest stability. Adjacent `tests/test_firm_allocator.py` includes a source-level shadow-only import guard: this new module is not imported by any active sizing or bot logic and does not reference the incumbent allocator's Python module identifier.

A local test pass is **not** a qualified actual user book: all current fixtures are synthetic and use policy refs that do not assert real eligibility. Before a real consumer, the book owner must supply one legitimately observed account snapshot with mandate revision; the instrument owner must approve cross-asset eligibility or explicitly refuse it; the FX owner supplies exact quote/vintage/cost data; the risk forecast owner supplies scientifically qualified horizons; the existing forward evaluation owner grades net utility, costs, turnover and re-entry. Test missing/stale/foreign/conflicting scenarios and actual signed-in UI / API path. No account input belongs in public source control.

## Original-mission continuity

MA-1 Macro #10795 provides observational ETF context and should release through the Macro's existing CI/merge-on-green path separately. This Master's pure MA-4 prework is independent and cannot be activated by MA-1. MA-2 market stress, MA-3 preregistered forecast science and MA-5 Macro/Terminal/Mastermind joins remain outstanding. No historical failed GEX experiment is rerun; no capital-policy or alert opt-in is silently changed.
