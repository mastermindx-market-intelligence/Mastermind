# GLT T17 — causal identification layer (2026-10-13 programme, built 2026-10-19)

Task T17 of WS:GLOBAL-LIQUIDITY-TRANSMISSION. Base: Mastermind master
`0c8cb6b4686e66c0f8a22767c44951ba8005e06d`. Artifacts:
`research/liquidity_transmission/glt_identification_card.v1.json` (frozen card),
`brain/liquidity_lab/identification.py` (receipts and a separately labelled causal
estimate), `tests/test_liquidity_lab_identification.py` (68 tests). Acceptance cases:
C20, C23, C30.

## §0 What this is and is not

- **Is:** a gate that decides, per (relation, shock class, instrument, target, horizons,
  train/dev window), whether a causal reading is identified. It writes an
  `IdentificationReceipt` that lists **every** failure reason. Only a receipt with
  status `IDENTIFIED_FOR_CONTEXT`, bound to this card's `definition_hash`, can produce a
  `CausalEstimateCard` labelled `identified_causal_for_context`.
- **Default and current state: `NOT_IDENTIFIED`.** No rights-proven, point-in-time
  policy-announcement surprise series exists in either repository (§2), and programme
  law forbids a new collector. The real cell is therefore
  `BLOCKED:<instrument> → NOT_IDENTIFIED` (§5).
- **Is not:** a change to any general predictive claim. T16's
  `ResponseEvidenceProjection` and every T09–T16 output keep `NOT_IDENTIFIED`. The
  causal card is a different class with no projection fields and no conversion. It
  carries `validated: False` and `evidence_tier: identified_causal (context-bound)`.
  It produces no probability, score, rank, size, weight or trade instruction.
- **Is not:** a read of anything dated on or after the preregistration card's
  `reserved_start` (2022-01-03). Every outcome row passes `WindowGuard`. A reserved
  row is counted as refused and then raises `ReservedWindowTouched`. No look is
  recorded.

## §1 The estimand restated (T13 card, unchanged)

- `relation_id`: `glt_rel_monetary_impulse_to_broad_targets.v1`.
- Estimand card: `research/liquidity_transmission/glt_estimand_card.v1.json`.
  - File sha256 `44a78d4a7b615b9b5941d613b05cb0af1ae949e8232fa34dcd87ada54a518ff1`.
  - Status `association_only`.
- Preregistration card: `card_hash` `da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee`.
  - File sha256 `9519241f…`.
- Event definition: `evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66`.
- Shock class: `policy_announcement_surprise`. This is one of the two eventization
  classes that can name an outside instrument; `forecast_innovation` is the other.

The causal estimand is the response of a broad target's log return over horizons
h ∈ {5, 20, 60} business days to an exogenous policy-announcement surprise. The
response is identified through the reduced form and the IV ratio. Reduced-form slopes
and IV ratios are reported per horizon, never as a path.

The estimand card's `forbidden_controls` are spliced into the identification card byte
for byte (§4, `test_forbidden_controls_bytes_equal_estimand_card`):

- mediators, causal only:
  - `contemporaneous_broad_dollar`
  - `contemporaneous_real_yield_10y`
  - `contemporaneous_high_yield_oas`
  - `usd_funding_impulse_composite`
- colliders, predictive and causal:
  - `post_treatment_market_stress_response`
  - `post_treatment_funding_stress_realized`
  - `outcome_conditioned_episode_selection`
- post-treatment outcome: `contemporaneous_or_future_target_returns`
- post-treatment common factor, causal only: `contemporaneous_global_common_risk_factor`

## §2 Instrument census

The census was run on 2026-10-19. Lane K0 ran on ubuntu1 (glm, read-only) over the
macro clone at `ee79a5dd`. The seat confirmed the registers and key rows against macro
main `3ae40fd3d9c36bce0eb818bed95f43ac643c4096`, and checked Mastermind at
`0c8cb6b4`. No `data/` or `site/` file was opened, and no observation dated on or
after 2022-01-03 was read.

| candidate | repo:path@sha | provides | rights_state | clock rule | qualifies? |
|---|---|---|---|---|---|
| GLT source register | macro:`config/global_liquidity_sources_v2.yml`@3ae40fd3 | 20 balance-sheet / money / credit / funding / market-liquidity sources (`fed_total_assets` … `cross_currency_basis`) | `licence_class` per source (e.g. public_us_government) | release-dated levels | **No** — no announcement, surprise or calendar source |
| GLT source matrix | macro:`research/GLOBAL_LIQUIDITY_SOURCE_MATRIX_2026-10-13.md`@3ae40fd3 | coverage matrix of the 20 sources | — | — | **No** — no instrument row |
| Instrument declarations | macro:`config/causal_instruments.yml`@3ae40fd3 L90 (`fomc_decision`, `surprise_component`, `event_tape: declared`) | a declaration only; it requires a futures-implied-path decomposition that no module computes | no rights field | none (no tape) | **No** — declared, never wired |
| ZQ / SR3 implied policy path | macro:`collectors/rate_futures.py`@3ae40fd3 L1–L3, L226 (`period = "5y" if full_history else "3mo"`) | daily futures-implied path levels (the decomposition *input*), not a surprise | undeclared | collection date; vendor history only 5y rolling | **No** — no rights, no 2008–2021 coverage, no surprise |
| FOMC announcement days | macro:`engine/event_window.py`@3ae40fd3 L20, L63 | static 2000–2025 calendar, display only | undeclared | static list | **No** — calendar only, no surprise magnitude |
| FOMC decision history | macro:`scripts/research/hs2_event_reactions.py`@ee79a5dd L45–148 | web-compiled decision dates plus event-window returns | undeclared | research script | **No** — dates only; reads outcomes |
| CB meeting calendars | macro:`engine/cb_desk.py`, `engine/event_calendar.py`, `engine/china_event_calendar.py`, `engine/hk_event_calendar.py`@ee79a5dd | forward calendars (mostly 2026) | undeclared | forward | **No** — calendar only, wrong span |
| Realized CB policy rates | macro:`engine/cb_desk.py`@ee79a5dd L11, L18–25 | FRED levels; "no consensus surprise scoring" | undeclared | FRED vintage | **No** — realized, not surprise |
| FOMC statement text | macro:`engine/marketing/fomc_statements.py`@ee79a5dd | statement prose | undeclared | fetch time | **No** — not a numeric instrument |
| Press feeds | macro:`config.yml`@ee79a5dd L4777–4820 | RSS prose (ec_presscorner, boe_news `VERIFIED_PUBLIC_REUSE`; ecb_press, council_eu `UNVERIFIED_EXCLUDED`) | partial | live | **No** — prose, live only |
| PBoC OMO / corridor | macro:`collectors/china_omo.py`, `collectors/china_pboc.py`@ee79a5dd | observed operations and administered rates | undeclared | observed | **No** — levels, not surprise |
| Mastermind held-risk flags | Mastermind:`portfolio/held_risk.py`@0c8cb6b4 L21, L635 | "no FOMC calendar available — always omit" | — | — | **No** — no source |
| Mastermind eventization vocabulary | Mastermind:`brain/liquidity_lab/eventization.py`@0c8cb6b4 L22 | the class name `policy_announcement_surprise` only | — | — | **No** — vocabulary, no data |

Disposition: `RIGHTS_PROVEN_INSTRUMENT: NO`, so the card's `instrument_candidates` is
`[]`. Under the card's `instrument_candidate_rule`, an entry needs all of:

- `instrument_id`;
- `source_ref{repo, path, sha}`;
- `rights_state: RIGHTS_PROVEN`;
- `clock_rule: first_system_known`;
- `announcement_type`.

## §3 Frozen rules and their ex-ante justification

**Card identity.**
- `frozen_at` `2026-10-19T13:11:19Z`.
- File sha256 `712f07d937c53864d37e3fa2c030d91c9138636cd361ad28ce4160dbd0f06716`.
- **`definition_hash` `a55f05e1e0e389e548840dc1c70da93278d9f935d4dbb623a8cb9895f5aaa81b`.** It is the
  sha256 of canonical JSON (sorted keys, `(",", ":")`, `ensure_ascii=False`) over every
  field except `definition_hash`.

**Superseded pre-fit draft.** An earlier draft was frozen at 12:49:28Z:
- `definition_hash` `d3b320ff796438b9b3721387ae3ae562912ad48aa7cd4a2ac790b21e2037f5f8`;
- file `ab1da1e4…`.

It was superseded at 13:11:09Z, before any fit and before the test file existed. Its
relevance and falsifier definitions named a null-score HAC t. That statistic's variance
carries the signal itself, so for a Gaussian instrument t² is capped near n/2: 23.1 is
unreachable below about 46 events, and the gate would have tested sample size, not
relevance. The fix names the HAC sandwich (Wald) t. Every threshold, window, seed,
exclusion and specification is unchanged. Both entries are in the ORCH-K freeze log.

**Rules.**

- **Relevance (S31).**
  - Statistic: first-stage F = t² of the HAC sandwich t (Newey-West, Bartlett kernel, 4 lags) of the OLS slope of treatment on instrument over thinned events. With one instrument this is the effective F.
  - Gate: F ≥ **23.1** and ≥ **20** thinned events.
  - Why 23.1: it is Montiel Olea–Pflueger's effective-F critical value for one instrument (5 % test, worst-case bias 10 %). It is robust to heteroskedasticity and serial correlation, unlike the iid rule of thumb of 10.
  - S31: shock identification is never automatic. Relevance is a declared gate, never inferred from a regression on shock size.
- **Anticipation.**
  - Statistic: HAC slope t of the target's log return over the 5 sessions ending the session before the announcement, on the instrument.
  - Gate: |t| ≤ 1.96.
  - Falsifier: `anticipation`.
- **Pre-trend.**
  - Statistic: the same slope t over the 20 sessions before the anticipation window.
  - Gate: |t| ≤ 1.96.
  - Falsifier: `placebo_leads`.
- **Reverse response.**
  - Statistic: HAC slope t of the instrument on the target's log return over the 25 sessions ending the session before the announcement.
  - Gate: |t| ≤ 1.96.
  - Falsifier: `reverse_policy_reaction`. It spans the whole reaction lookback, so it binds even when anticipation and pre-trend each pass.
- **Placebo and multiplicity.**
  - Draws: 200 placebo replications, seed 20261017.
  - Relocation: each relocates every thinned event to distinct admitted train/dev sessions (2008-01-04..2021-12-31) at least 5 weekdays from every event. Instrument values are kept and the reduced-form slope is recomputed.
  - p-value: p = (1 + #|placebo| ≥ |actual|) / 201.
  - Multiplicity: BH-FDR at 0.10 over the horizon family.
- **Inference (S32).**
  - Intervals are pointwise at 95 %.
  - IV-ratio sets come from Anderson–Rubin inversion with the same HAC judge, reported unbounded or empty at the grid edge.
  - No simultaneous band is declared, so `path_claim_allowed` is `false`. A path or region claim would need a band (S32).
- **Confounding news (protocol §5).** Five classes are applied to the announcement calendar only, never to outcomes:
  - `central_bank_information_release`: same session, and it counts even when bundled with the instrument's own announcement unless the `announcement_type` ends `_information_purged`. This is the central-bank information effect.
  - `other_fomc_communication`: ±1 weekday.
  - `treasury_quarterly_refunding_announcement`: ±1 weekday.
  - `scheduled_cpi_or_payrolls_release`: ±1 weekday.
  - `foreign_central_bank_policy_decision`: ±1 weekday; ECB and BoJ balance sheets sit inside the treatment.
- **C20.**
  - Only `forecast_innovation` and `policy_announcement_surprise` may be qualified.
  - A candidate whose `announcement_type` names an estimand-card `non_exogenous_construction` is refused (`NON_EXOGENOUS_INSTRUMENT`): an OLS residual, a threshold crossing, an orthogonal residual or a significant response cell.
  - `observed_state_change` and `identified_intervention` are refused as instrument classes (`SHOCK_CLASS_NOT_INSTRUMENT`).
- **C23.**
  - Three admissible specifications:
    - `rf_no_controls`;
    - `rf_lagged_market_state`;
    - `rf_lagged_macro_state`.
  - Each specification control is measured at the close of the session before the anticipation window.
  - Any forbidden, mediator, collider or undeclared control is refused at validation and again at qualification.
- **Outcome firewall.**
  - Qualification reads only pre-announcement windows (`anticipation`, `pre_trend`, `reaction_lookback`).
  - Any post-announcement row offered before a receipt is `OUTCOME_FIREWALL_BREACH`.
  - No row may reach `reserved_start` 2022-01-03.

## §4 Fixture tests (node ids, `tests/test_liquidity_lab_identification.py::`)

**C20 — a residual, threshold or orthogonalised series never implies exogeneity.**
- `test_c20_non_exogenous_construction_never_identifies[ols_residual|eventization_threshold_crossing|causal_orthogonal_residual|significant_response_curve_cell]`
- `test_c20_state_change_shock_class_is_not_an_instrument[observed_state_change|identified_intervention]`
- `test_card_mutation_names_its_code[NON_EXOGENOUS_INSTRUMENT:fixture_policy_surprise]`
- `test_card_mutation_names_its_code[SHOCK_CLASS_NOT_INSTRUMENT:observed_state_change]`

**C23 — controls match the estimand; anticipation and reverse response are tested.**
- `test_c23_controls_named_by_the_estimand_card_are_refused[...]`: 16 cases, covering 9 FORBIDDEN_CONTROL, 4 MEDIATOR_AS_CONTROL and 3 COLLIDER_AS_CONTROL.
- `test_c23_undeclared_control_is_refused`
- `test_c23_card_specifications_are_checked_at_qualification`
- `test_c23_anticipation_defeats_the_label`
- `test_c23_pre_trend_defeats_the_label`
- `test_c23_reverse_response_defeats_the_label`

**C30 — weak or invalid identification yields NOT_IDENTIFIED.**
- `test_c30_weak_relevance_is_not_identified`
- `test_c30_future_instrument_is_not_identified`
- `test_c30_confounding_news_is_not_identified`
- `test_c30_bundled_information_release_counts_unless_purged`
- `test_c30_no_instrument_on_the_frozen_card`
- `test_c30_unproven_rights_is_not_identified`
- `test_two_violations_are_both_reported`
- `test_missing_inputs_are_failure_codes`
- `test_real_cell_is_not_identified`

**Receipt binding, label path and firewall.**
- `test_causal_response_refuses_without_an_identified_receipt`
- `test_causal_response_refuses_a_mismatched_hash`
- `test_causal_response_refuses_another_panel_spec_or_horizon`
- `test_label_travels_only_with_the_receipt`
- `test_j_projection_stays_not_identified`
- `test_causal_card_is_not_a_projection`
- `test_reserved_row_raises_and_counts_refusal`
- `test_causal_response_reserved_row_raises_and_counts_refusal`
- `test_reserved_instrument_session_raises`
- `test_post_announcement_outcome_is_a_firewall_breach`
- `test_clean_run_refuses_nothing`
- `test_forward_ledger_is_byte_identical`
- `test_default_judges_abstain_verbatim`
- `test_module_hygiene`

**Card.**
- `test_frozen_card_hash_recomputes`
- `test_forbidden_controls_bytes_equal_estimand_card`
- `test_frozen_card_validates_clean`
- `test_card_mutation_names_its_code[14 codes]`

**Synthetic fixture results.** The data are generated in-test, and no real observation
is used. The first fixture fit was 2026-10-19T13:17:16Z, after `frozen_at` 13:11:19Z.

The clean world is `IDENTIFIED_FOR_CONTEXT` with reasons `()`:

| item | result |
|---|---|
| first-stage F | 340.933 |
| anticipation / pre-trend / reverse t | ≈ 0 |
| guard (qualification) | admitted 120, refused 0 |
| guard (estimate) | admitted 240, refused 0 |

| horizon | n | estimate (truth) | AR 95 % set | placebo p | BH q | reject |
|---|---|---|---|---|---|---|
| h5 | 40 | 0.004824 (0.005) | [0.002894, 0.006874], convex | 0.004975 | 0.004975 | yes |
| h20 | 40 | 0.010754 (0.010) | [0.009678, 0.011560], convex | 0.004975 | 0.004975 | yes |

The joint result is BH-adjusted and rejects h5 and h20. The simultaneous band is
`null` and `path_claim_allowed` is `false`.

Failure worlds, each `NOT_IDENTIFIED`:

| world | reasons |
|---|---|
| γ = 0.05 | `WEAK_RELEVANCE:first_stage_F=1.332<23.1` |
| n = 12 | `WEAK_RELEVANCE:thinned_events=12<20`, plus `UNTESTED` for anticipation, pre-trend and reverse response |
| anticipation | `ANTICIPATION:t=3.535` |
| pre-trend | `PRE_TREND:t=3.313` |
| reverse | `REVERSE_RESPONSE:t=5.063` |
| two violations | `FUTURE_INSTRUMENT:2008-08-18`, then `WEAK_RELEVANCE:first_stage_F=1.332<23.1` |

## §5 The real cell

The real cell is `BLOCKED:<rights-proven point-in-time policy-announcement surprise tape (realized decision minus futures-implied path, first-system-known clock) covering train/dev 2008-01-04..2021-12-31>` → **`NOT_IDENTIFIED`**.

- `qualify_identification(frozen card, instrument_panel=None, event_calendar=None, outcome_frame=None, guard=None)` returns these reasons:
  - `NO_INSTRUMENT`
  - `MISSING_INPUT:guard`
  - `MISSING_INPUT:instrument_panel`
  - `MISSING_INPUT:event_calendar`
  - `MISSING_INPUT:outcome_frame`
- The receipt is bound to `definition_hash` `a55f05e1…`.
- No outcome row was offered, so WindowGuard admitted 0 and refused 0, and there is no reserved read. (Each synthetic run's `refused_count` is in §4 and in the ORCH-K record.)
- `causal_response` refuses the receipt (`IdentificationRequired`).
- T16 stays `NOT_IDENTIFIED`.

## §6 What would change the answer (T22 / T24)

- **An instrument.** A policy-announcement surprise tape must be:
  - rights-proven (`RIGHTS_PROVEN`) and point in time (`first_system_known`);
  - the realized decision minus the futures-implied path, per `config/causal_instruments.yml` `fomc_decision`;
  - complete over 2008-01-04..2021-12-31.

  Admitting one is a source-acquisition decision for T22 (data rights), never a new
  collector inside this programme. It would enter as one `instrument_candidates` entry
  through a new card version. This card is frozen, and any change re-freezes it and
  changes the `definition_hash`.
- **Calendars.** Point-in-time announcement and confounding-news calendars (FOMC, SEP or minutes, refunding, CPI or payrolls, ECB or BoJ) are needed for the same span.
- **Gates still binding even with an instrument.** The instrument must pass:
  - F ≥ 23.1 on ≥ 20 thinned events;
  - |t| ≤ 1.96 for anticipation, pre-trend and reverse response;
  - no confounding news;
  - placebo plus BH at 0.10 per horizon.

  Even then the label is context-bound (`identified_causal_for_context`). It leaves
  T16's predictive outputs untouched, and the reserved window stays sealed until T24's
  single evaluation.
- **Known gaps for the owners.**
  - T11's `label_shock` checks only the receipt's shape. Binding the label to a verified receipt is eventization-owner work.
  - T16 has no receipt hook. That is by design: the causal card is a separate class.
