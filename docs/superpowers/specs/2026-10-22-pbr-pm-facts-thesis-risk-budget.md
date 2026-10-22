# PBR L-S3 spec — typed PM facts, durable thesis + amendments, evidence-conditioned risk budget

- Program: Portfolio Bot Rebuild (mastermindx-market-intelligence/Mastermind#1693). Parent: `pbr-research` (Opus).
- Class: design (this wave writes one spec; no source changes). Implementation lane: L-S5.
- Disposition for: MASTERPLAN defect rows A14/A15/A16 (§4 register), §2.6, §7.4–§7.6, §7.8, §9.1–9.3; external source X6 (Micron primary event dates).
- Governing frozen laws: V3 design spec §7 (`docs/superpowers/specs/2026-09-15-mastermind-portfolio-v3-risk-first-autonomous-manager-design.md:482-516`) — esp. law 2 isolated shadow (:485), law 11 no LLM-probability sizing authority at birth (:494), law 12 reliability and independence over source count (:495), law 13 contradiction is not averaged away (:496), law 23 existing planes stay canonical (:506), law 28 no duplicate stores (:511). Settlement boundary §8.7 (:582-588): shadow artifacts have no route to existing writers.

## 0. Verified case evidence base

All case facts below were read verbatim from `~/lanes/tmp/pbr-res-ls3-factspec/case_rows.jsonl` / `case_fills.jsonl` (line numbers are `line_index_0based`). Fixtures for tests (§5) are produced by a sibling lane at `tests/fixtures/pbr/decision_cases/` (schema `pbr.decision_case_fixture.v1`; each record carries the verbatim `row`, `case_holding`, `case_row_falsifiers`; the MU entry fixture additionally carries `external_facts` with event_date 2026-09-30).

| Case | Row | Decision / asof | Key verified facts |
|---|---|---|---|
| MU entry | autonomous 75 | `decision.v1.8d700b90434853b846f2ef2e`, asof 2026-10-02, accepted 2026-10-02, settled 2026-10-05 | Add, medium, proposed 0.08 → weight 0.10, `deterministic_conviction_allocator.v2`. why_now gates full size on "10/22 earnings catalyst"; falsifier: "Q4 FY2026 gross margin (reported 2026-10-22) prints below 35.5%"; exit_plan "GM% miss <35.5% on 10/22 … Trail stop near 107.5"; rationale "3 analyst PT raises to 130-140"; memo.timing "MU earnings 2026-10-22 is the key catalyst/risk"; top-level falsifiers repeat the 2026-10-22 date. Fill: buy 92 @ USD 1069.68 on 2026-10-05 (fill_id `c9ec0d95…`). X6: Micron announced 2026-08-26 and reported the fiscal-Q4 results 2026-09-30 — both before asof. |
| MU amendment | autonomous 76 | `decision.v1.978d5a72e61fdefbaad6c902`, asof 2026-10-05, settled 2026-10-06 | Hold, conviction medium→**high**, weight 0.098528, `weight_source` → `deterministic_existing_hold.v1` (brain/decision_submission.py:797-799). Falsifier replaced (60d relative-to-SPY / government-support), exit_plan replaced. No amendment record exists in any inspected row. |
| MU planless exit | autonomous 89 | `decision.v1.cbf98cc5bfd573cec5ba33e0`, asof 2026-10-22 06:23 UTC, queued | Full MU exit in `exit_decisions`/`requested_exit_decisions` with evidence "prophet: MU held_without_active_plan (no active management plan)", "rationale null"; summary says MU "carries no live thesis (null rationale, Prophet held_without_active_plan)" — although rows 75/76 hold thesis, horizon, falsifier, exit plan. Row 78 (asof 2026-10-07) is the first row whose JSON contains `held_without_active_plan` (attached to AAPL evidence; MU's falsifier cites "Prophet invalidation"). |
| 688062.SS sizing | china 35 | `decision.v1.d1f14bdd0e04d6d379f17efe`, asof 2026-08-12 | Add, medium, weight 0.12 == regional medium cap (brain/decision_submission.py:450), `deterministic_incremental_regional_allocator.v1`. Rationale: single-source evidence, degraded technical coverage, non-FDR-cleared advisory Neural Web signal "require a measured starter"; "Thesis probability is estimated at 62%". Fill: buy 3716 @ CNY 32.65 on 2026-08-13. Rows 36–37 hold at ~0.1248 with high conviction citing the same limitations. |
| XOM control | autonomous 38–40 | `decision.v1.3050203fdc5b109680b6c74e` (08-12), `.c48571d8…` (08-13, settled 08-14), `.7d572dc4…` (08-14, settled 08-17) | Add, medium, weight 0.10, falsifier "Close below $153; structural failure below approximately $137.50" — levels within ~3% of the 2026-08-13 fill 618 @ USD 158.03 (case_fills autonomous 87). Positive control: must remain eligible under every new check. |

Falls recorded for MU (2026-10-09 sell 59.438102 @ 1054.17) and 688062.SS partial exits exist in `case_fills.jsonl`; they are episode context, not inputs to eligibility.

## 1. Scope and authority

RESEARCH-owned **new modules only**, all inside the RESEARCH capability family (config/authority_map.yml:47):

- `brain/facts.py` — typed fact record + verification rules (§2).
- `brain/thesis_store.py` — durable thesis + amendment records, status derivation (§3).
- `brain/shadow_risk_budget.py` — evidence-conditioned risk budget, shadow only (§4).
- One versioned parameter config for (c): `config/pbr_shadow_risk_budget.yml`, schema `pbr.shadow_risk_budget_params.v1`, created by L-S5.

**Not wired into live decisions in this wave.** No allocator behaviour change: `brain/decision_submission.py` is not modified, and nothing here is called from `normalize()` (brain/decision_submission.py:609). No registry membership (no `portfolio/registry.py` change), no pending-target route, no settlement call; per frozen law 23 (:506) and settlement boundary §8.7 (:582-588) the existing target/pending-target/fill/settlement writers stay sole mutation owners. Storage is **only** under a caller-supplied directory argument (`store_dir: Path`); there is no default path and no module-level data path — in deliberate contrast to `brain/ledger.py:11`, whose fixed `_LEDGER` lives at `data/brain/theses.jsonl`.

Consumer integrations are named later, seat-reserved steps (§6). This spec grants no admission, capacity, or effect clearance.

## 2. (a) `brain/facts.py` — typed fact record + verification rules

Precedent for typed, unit-carrying, authority-labelled records: `brain/decision_context.py` (`_SCHEMA_VERSION = "decision_context.v2"`, brain/decision_context.py:29; unit/horizon metadata prevents incomparable magnitudes from masquerading as one scale, brain/decision_context.py:31). `source_family` follows the claim-contract precedent (`mastermind.portfolio_research_claim.v1`, V3 spec §13.1:916).

### 2.1 FactRecord (TypedDict, schema `pbr.fact.v1`)

| Field | Type / vocabulary | Notes |
|---|---|---|
| `fact_id` | str | Stable id: sha256 of (claim_text, instrument, kind, source_ref) truncated. |
| `claim_text` | str | Verbatim claim as stated in decision materials. |
| `kind` | `event_date \| price_level \| price_target \| metric \| other` | Closed enum. |
| `instrument` | dict | Qualified identity (ticker, book, venue, identity_status as recorded on the holding, e.g. `trusted_company_profile.v1`). |
| `value` | Any | The claimed date, price, or number; `None` for pure prose. |
| `unit`, `currency` | str | Must be non-null when kind is price/metric. |
| `period` | str \| None | e.g. `FY2026-Q4` for the MU gross-margin claim. |
| `published_at`, `available_at`, `observed_at` | ISO datetime \| None | Point-in-time discipline (MASTERPLAN §7.5). |
| `basis` | dict \| None | Price/adjustment basis: adjustment convention, split assumption, mark type. Required for price kinds. |
| `source_class` | `primary_filing \| company_release \| vendor_derived \| news_summary \| model_interpretation` | Closed enum; distinguishes primary filing from vendor metric, news summary, model interpretation (MASTERPLAN §7.5). |
| `source_family` | str | Underlying source family; several dashboards over one price series are one family (MASTERPLAN §7.5). |
| `source_ref` | str | URL, file ref, or row/decision id. |
| `decision_asof` | date | The asof of the decision the fact supports. |

`ExternalFact` uses the same record for primary evidence supplied by callers/fixtures (e.g. X6's event_date 2026-09-30, source_class `company_release`).

### 2.2 VerificationOutcome (closed enum) and rules

`VERIFIED | CONTRADICTED | UNVERIFIED | BASIS_UNRECONCILED | NOT_APPLICABLE`, with a reason string and the compared values. `verify_fact(fact, *, primary_evidence, reference_mark=None, config) -> Outcome`:

- **(i) Dated catalyst.** kind `event_date`, where the claim asserts a *future* catalyst relative to `decision_asof`: if any primary evidence record (source_class `primary_filing` or `company_release`) shows the event date ≤ decision asof, the outcome is `CONTRADICTED`. MU: claim "due 2026-10-22" vs X6 event_date 2026-09-30 ≤ asof 2026-10-02 → CONTRADICTED. The rule evaluates **every** `event_date` fact extracted from the entry package — why_now, falsifier, exit_plan, rationale, top-level falsifiers, memo timing — so it fires regardless of which component carried the bad date (the MU date appears in all of them; the checker must not privilege one field).
- **(ii) Price basis bridge.** kind `price_level` or `price_target`: compute `ratio = claim_value / reference_mark` (reference mark = decision-time mark if supplied, else the episode entry fill; currency and basis from `fact.basis` must match the mark's). Ratio outside the declared tolerance band (config, §4.3) **without** an explicit bridge (a stated currency/adjustment/split reconciliation in `fact.basis.bridge`) → `BASIS_UNRECONCILED`. MU: targets 130–140 and trail 107.5 against fill 1069.68 (ratio ≈ 0.10–0.13) → BASIS_UNRECONCILED. XOM: 153 and 137.50 against 158.03 (0.87–0.97) → inside band, not BASIS_UNRECONCILED. This is an unexplained scale/basis discontinuity finding — **not** a claim that the fill price was wrong (MASTERPLAN §2.6).
- **(iii) Risk-increase eligibility.** `entry_fact_findings(facts, outcomes, action)` → an add/new-entry claim is **ineligible** when any supporting fact is CONTRADICTED or BASIS_UNRECONCILED (frozen law 13, :496 — contradiction is not averaged away; MASTERPLAN §7.5 "the affected risk-increasing claim must remain ineligible"). Shadow output only; it does not veto anything live.
- **(iv) Advisory-coverage asymmetry.** A missing advisory fact, missing provider coverage, or UNVERIFIED facts never produce ineligibility for a **hold** or an **authorized risk reduction** (exit/trim). Rule (iii) conditions only risk-*increasing* actions (MASTERPLAN §7.5, §7.8 "missing data must not silently liquidate a name").
- Facts with insufficient evidence resolve `UNVERIFIED` and are recorded, never discarded; kind `other` without a check resolves `NOT_APPLICABLE`.

In this wave FactRecords are constructed deterministically by callers/tests from fixture fields; prose extraction is out of scope (§6, Q5).

## 3. (b) `brain/thesis_store.py` — durable thesis + amendment records

### 3.1 Records (schemas `pbr.thesis.v1`, `pbr.thesis_amendment.v1`)

`ThesisRecord` — one per **position episode** (open at first entry fill, close when the position reaches zero), linked to actual entry fill ids:

`thesis_id, book, ticker, episode_open_date, episode_close_date?, entry_fill_ids[], why_now, fact_ids[], horizon, falsifiers[], exit_conditions[], position_role (starter | established | risk_reduction), originating_decision_id, created_at, schema`

`AmendmentRecord` — append-only:

`amendment_id, thesis_id, changes{field: {old, new}}, reason, evidence_refs[], effective_at, recorded_at, accountable_decision_id, schema`

Store layout under caller-supplied `store_dir`: `theses.jsonl` + `amendments.jsonl`, append-only writes; an amendment is a new line, never a rewrite of an earlier one.

- **Non-retroactivity.** Retrieval is `thesis_as_of(thesis_id, at)`: the view of every field as of a date — the latest amendment with `effective_at ≤ at` wins. An amendment whose `effective_at` precedes the originating decision's asof is rejected (`retroactive_amendment_rejected`), so an amendment cannot retroactively rewrite an earlier failed prediction (MASTERPLAN §7.8).
- **Relationship to the existing thesis ledger.** `brain/ledger.py` (`data/brain/theses.jsonl`, brain/ledger.py:11; one open thesis per subject, brain/ledger.py:24-32; `close()` rewrites, brain/ledger.py:35-56) remains the accountability spine feeding FORGE calibration (brain/calibration.py:1-28, `MIN_N = 12` at :30, `FLOOR = 0.5` at :31). The new store is a **different granularity** — episode-scoped, fill-linked, amendment-lineaged — and is not a second writer or mirror of that ledger (law 28, :511). `brain/calibration.py` reads the old ledger unchanged; reconciliation is seat-reserved (§6).

### 3.2 Status derivation and the retrieval view

`thesis_view(book, ticker, episode, provider_packet, as_of)` returns:

- `local_thesis_status`: `ACTIVE | AMENDED | INVALIDATED | EXCLUDED | NONE_RECORDED` — derived **only** from the local store (ACTIVE: record exists, unamended, episode open; AMENDED: ≥1 amendment; INVALIDATED/EXCLUDED: terminal amendments with those reasons; NONE_RECORDED: no ThesisRecord for the episode).
- `provider_plan_status`: `active_plan | held_without_active_plan | unavailable` — derived only from the Prophet packet: in `management`/`discovery` → active_plan; in the `held_without_active_plan` list (produced at brain/portfolio_intelligence.py:512 as `sorted(held_set - planned)` inside `prophet_board()`, brain/portfolio_intelligence.py:444, and surfaced through the market packet at brain/portfolio_intelligence.py:1109) → held_without_active_plan; feed absent (`feed_active` false / empty payload) → `unavailable`.
- `findings[]`.

**Separation rule (binding):** a missing provider plan can never produce local `NONE_RECORDED`. `NONE_RECORDED` requires the absence of a local ThesisRecord, nothing else. When `provider_plan_status` is `held_without_active_plan` (or `unavailable`) while a local thesis exists, emit finding `PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT` — the exact MU-89 failure ("carries no live thesis … Prophet held_without_active_plan" while rows 75/76 hold a full thesis). The packet is context-only (brain/portfolio_intelligence.py:508), so it can add a finding but never erase local state. Symmetrically, a stale local thesis does not block an authorized exit (§2.2 rule iv).

### 3.3 UNRECORDED_AMENDMENT detection

`detect_unrecorded_amendments(consecutive_holdings_for_episode)` compares consecutive accepted holdings rows for the same held episode and emits `UNRECORDED_AMENDMENT` (with the field diff) when any of `falsifier, exit_plan, horizon, position_role, conviction` materially differs and no AmendmentRecord links the two decision ids. MU 75→76: conviction medium→high, falsifier and exit_plan replaced → detected. Detection is a finding on the lineage, not a live-action veto. Perturbation: an explicit AmendmentRecord covering the diff suppresses the finding.

## 4. (c) `brain/shadow_risk_budget.py` — evidence-conditioned risk budget (shadow)

### 4.1 Inputs and output

Inputs (per name, per decision): `position_role`; role adverse-scenario loss budget (portfolio-NAV fraction, config); evidence quality — independent source-family count, primary-vs-derived mix (§2.1 source_class), technical-coverage flag, calibration status of any stated probability; concentration — issuer/event exposure (existing same-issuer weight, correlated-event overlap); the categorical cap in force (passed in as data, values from `_sizing_policy`: autonomous {high .15, medium .10, low .05}, brain/decision_submission.py:444; regional {high .18, medium .12, low .06}, brain/decision_submission.py:450 — read as inputs, never imported into sizing).

Output `RiskBudgetAssessment`:

```
eligible_weight + waterfall [
  categorical_cap      -> value, source
  role_budget          -> value, role, declared loss budget, config ref
  evidence_haircut     -> multiplier, drivers (source families, primary mix, coverage)
  concentration_limit  -> value, drivers (issuer/event)
  eligible_weight      -> min of the above steps
] + assumptions[] + config_version
```

### 4.2 Zero-influence rule for uncalibrated probabilities

A stated thesis probability with `calibration_status != "calibrated"` (per brain/calibration.py:30 MIN_N=12 and its de-confidencing-only contract, brain/calibration.py:1-18) has **zero** allocation influence: it is not an input to any waterfall step (frozen law 11, :494). The 688062.SS "62%" is an uncalibrated manager assertion (MASTERPLAN §2.6) and must not move `eligible_weight`.

### 4.3 Ex-ante parameters and the anti-fitting rule

All parameters (tolerance band for §2.2(ii), role loss budgets, evidence-multiplier table, concentration factors) live in `config/pbr_shadow_risk_budget.yml` with schema `pbr.shadow_risk_budget_params.v1`, `frozen_at`, per-parameter written justification, and version bumped on any change.

**Anti-fitting rule (binding).** Parameters must NOT be chosen to make 688062.SS come out at any particular number, to avoid its realised −CNY 22,196.94 contribution, or to guarantee MU/XOM any outcome (MASTERPLAN §7.6 "neither a sector label nor the word 'starter' establishes safety … rather than choosing caps to fit this known loss"). Audit mechanism:

1. Parameters are frozen (committed with `frozen_at` + justification) **before** any case-fixture evaluation is written; the case tests (§5) are the auditors of that order — the config test refuses a missing/late `frozen_at`.
2. The 688062.SS case test asserts only: the waterfall is fully explained; role `starter` + single-source evidence maps to a budget **strictly below** the categorical cap; it never asserts a specific eligible weight.
3. Any later parameter change bumps `version`, carries a new justification, and re-runs the full case suite — regressions in the positive control (XOM must remain eligible) fail the change.

## 5. (d) Regression tests (failing-then-passing)

Fixtures (sibling lane): `tests/fixtures/pbr/decision_cases/{mu_2026-10-02_entry, mu_2026-10-05_amendment, mu_2026-10-22_planless_summary, cn_688062_2026-08-12_sizing, xom_2026-08-12_positive_control}.json`, schema `pbr.decision_case_fixture.v1`.

**Baseline (passes on master; documents the gap).** The current path every fixture row went through is `normalize()` (brain/decision_submission.py:609), which produces `mastermind.target_book.v2` (brain/decision_submission.py:1023), accepts holding memo fields verbatim (brain/decision_submission.py:752-767), defaults conviction (brain/decision_submission.py:750-751), drops only rationale-less rows (brain/decision_submission.py:683), sizes adds purely by categorical caps (brain/decision_submission.py:544, cap lookup :559-561, `weight_source` :594), and emits an audit dict with **no** fact/thesis/budget sections (brain/decision_submission.py:1003-1021). Baseline tests monkeypatch `brain.decision_submission._latest_holdings` (module attr used at :622; real one reads the live account, brain/decision_submission.py:205) to return the prior book derived from the fixture row (row holdings minus the case ticker, at recorded weights; case ticker absent for entries), and `_instrument_identity_for_book` (:342) to the recorded `identity_status` as a verified identity; then call `normalize(book, args, deterministic_sizing=True, decision_asof=…)` with `args` rebuilt from `case_holding` / `row`.

**Contract tests (fail on master, pass after L-S5).** Failure on master is the module ImportError *and* the test body must assert the specific verdict once the module exists — no `xfail(raises=…)` that could absorb a different defect. No network, no live data; all stores under `tmp_path`.

### 5.1 `tests/test_pbr_facts.py`

- `test_baseline_master_normalize_accepts_entry_adds_without_findings` — MU and 688062.SS entry fixtures: normalize() accepts the add; add-row weight == categorical cap (0.10 autonomous medium; 0.12 regional medium), reproducing the recorded weights; `submission_audit` contains none of `fact_verification`, `thesis_continuity`, `risk_budget` and no CONTRADICTED/BASIS_UNRECONCILED/UNRECORDED_AMENDMENT value anywhere in the payload. (Passes on master.)
- `test_baseline_master_normalize_accepts_exit_without_thesis_finding` — MU-89 fixture: requested exit accepted into `exit_decisions` with `reason_code` risk_limit; no thesis-continuity finding. (Passes on master.)
- `test_mu_entry_catalyst_contradicted_in_every_component` — for the event_date fact built from *each* of why_now / falsifier / exit_plan / memo timing, `verify_fact` against `external_facts` (event_date 2026-09-30, source_class company_release) returns `CONTRADICTED`; the roll-up flags every one, not a privileged field.
- `test_mu_perturbation_event_after_asof_not_contradicted` — same fact, perturbed external event_date 2026-10-30 (> asof) → outcome is not CONTRADICTED.
- `test_mu_price_claims_basis_unreconciled` — price_target 130–140 and price_level 107.5 vs reference mark 1069.68 → `BASIS_UNRECONCILED` with the ratio recorded in the outcome.
- `test_xom_price_levels_reconciled_positive_control` — 153 / 137.50 vs 158.03 → not BASIS_UNRECONCILED; every XOM fact eligible.
- `test_risk_increase_ineligible_when_any_supporting_fact_bad` — MU entry action `add` → `entry_fact_findings` returns ineligible citing the CONTRADICTED catalyst and BASIS_UNRECONCILED levels.
- `test_missing_advisory_coverage_never_blocks_hold_or_risk_reduction` — with provider coverage absent and facts UNVERIFIED: `hold` and `exit`/`trim` remain eligible; only `add` is conditioned.

### 5.2 `tests/test_pbr_thesis_store.py`

- `test_baseline_master_amendment_and_exit_leave_no_trace` — rows 75→76 and the row-89 exit run through normalize() (monkeypatched seams as above): no amendment record, no planless finding; documents the A15 gap. (Passes on master.)
- `test_thesis_record_roundtrip_linked_to_entry_fill` — write the MU ThesisRecord with `entry_fill_ids=["c9ec0d95…"]`; retrieve by episode and by fill id.
- `test_amendment_append_only_and_non_retroactive` — record the 75→76 amendment; `thesis_as_of(…, 2026-10-02)` still returns the original falsifier/exit_plan; an amendment with `effective_at` before the originating asof is rejected.
- `test_unrecorded_amendment_detected_mu_75_to_76` — consecutive holdings from the two fixtures, no amendments → `UNRECORDED_AMENDMENT` listing conviction medium→high, falsifier and exit_plan changed. Perturbation: explicit AmendmentRecord → no finding.
- `test_provider_plan_missing_never_yields_local_none_recorded` — provider packet `held_without_active_plan` for MU + local thesis present → `local_thesis_status` in {ACTIVE, AMENDED}, finding `PROVIDER_PLAN_MISSING_LOCAL_THESIS_PRESENT`; `unavailable` feed → same separation. Perturbation: no local record and no provider plan → `NONE_RECORDED` legitimately, and the exit path stays eligible.
- `test_xom_thesis_episode_positive_control` — XOM ThesisRecord from rows 38–40 with both fill ids; retrieval eligible under every check.

### 5.3 `tests/test_pbr_shadow_risk_budget.py`

- `test_baseline_master_sizing_is_purely_categorical` — `_allocate_deterministically` (brain/decision_submission.py:544) on the 688062.SS and MU add rows reproduces 0.12 / 0.10 from conviction caps alone; audit carries no evidence term. (Passes on master.)
- `test_waterfall_fully_explained_for_all_cases` — every case fixture yields a five-step waterfall, each step with value and explanation; `eligible_weight` ≤ every predecessor.
- `test_starter_single_source_budget_below_categorical_cap` — 688062.SS (starter, one source family, degraded coverage) → `eligible_weight` < categorical cap 0.12; asserts strict inequality only.
- `test_uncalibrated_probability_has_zero_influence` — eligible weight identical with the 62% probability present vs absent.
- `test_xom_positive_control_remains_eligible` — XOM (multi-family evidence) → `eligible_weight` > 0 and no step zeroes it. Perturbation: XOM price levels pushed outside the band without a bridge → BASIS_UNRECONCILED propagates into the haircut (the machinery is conditional on evidence, not on the name).
- `test_config_frozen_ex_ante_and_versioned` — config exists with schema `pbr.shadow_risk_budget_params.v1`, `frozen_at`, `version`, and a justification for every parameter; missing `frozen_at` or bare justification fails.

Run command (when implemented): `mkdir -p ~/lanes/tmp/pytest; PYTEST_DEBUG_TEMPROOT=~/lanes/tmp/pytest ~/lanes/venv/bin/python -B -m pytest -p no:cacheprovider -o addopts="" -q tests/test_pbr_facts.py tests/test_pbr_thesis_store.py tests/test_pbr_shadow_risk_budget.py`.

## 6. Non-goals and seat-reserved items

Non-goals this wave: any modification of `brain/decision_submission.py` or allocator behaviour; live wiring of fact/thesis/budget outputs into decision submission; UI display (PRODUCT); ledger/settlement effects (ECON); resetting or redefining the V2 marker or the August-11 cohort; any claim of investment value.

Seat-reserved later steps (each needs its own assignment and review): (1) normalize() audit integration — surfacing fact/thesis findings in `submission_audit` (brain/decision_submission.py:1003); (2) allocator consumption of `eligible_weight` (law 24 sequential testing, :507); (3) PM-view fields consuming `thesis_view`; (4) structured per-holding provider-plan field instead of prose evidence strings (today `held_without_active_plan` is a ticker list at brain/portfolio_intelligence.py:512 plus prose in evidence arrays); (5) reconciliation of episode theses with `data/brain/theses.jsonl` / calibration; (6) prospective shadow-run fact extraction (deterministic parser or bounded LLM extraction with audit sample); (7) parameter-freeze ownership ruling for the config.

## 7. Open questions

1. Does the UNRECORDED_AMENDMENT change-set include `conviction` (a sizing input that changed medium→high at MU 76) or only thesis-semantic fields? MU 76 changed both, so the case cannot decide it; the ruling affects false-positive rate on pure conviction upgrades.
2. Which reference mark is canonical for the §2.2(ii) bridge at entry time — the decision-time quote or the realized fill? This wave accepts either (fill as fallback, as in the MU fixture); a live shadow run must pin one to stay point-in-time honest.
3. Who freezes and owns `config/pbr_shadow_risk_budget.yml` (which seat signs `frozen_at`), and where does the freeze-order evidence live beyond the commit history?
4. Should `INVALIDATED`/`EXCLUDED` terminal amendments require a linked fact outcome (e.g. a dated falsifier event) rather than free-text reason, to keep MASTERPLAN §7.8's "review large losses against the original decision" auditable?
