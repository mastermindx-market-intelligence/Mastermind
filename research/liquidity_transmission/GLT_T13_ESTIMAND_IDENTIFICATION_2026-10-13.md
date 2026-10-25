# GLT T13 — estimand and identification record (2026-10-13)

- Status: frozen research card; `validated: false`; evidence tier `research_measurement_only`; identification_status `association_only`
- Machine twin: `research/liquidity_transmission/glt_estimand_card.v1.json`
- Test: `tests/test_liquidity_lab_estimand_card.py`
- Acceptance: C20, C23
- Relation id: `glt_rel_monetary_impulse_to_broad_targets.v1` (card `glt_estimand_card.v1`, frozen 2026-10-13; caller-supplied freeze date recorded by T13; nothing reads a wall clock)

T13 fits nothing and reads no outcome or price data; it declares what any later estimate would mean.

## 1. Treatment

- family `measured_monetary_impulse`; state_family `monetary_impulse`; shock_type `policy_liquidity_impulse`; measure `state.monetary_impulse_z`; shock_class `observed_state_change`; identification_status `NOT_IDENTIFIED`
- construction: causal expanding z of the weekly change in the weighted mean causal z of USD-converted log central-bank balance sheets: WALCL; ECBASSETSW converted with EURUSD=X; JPNASSETS converted with USDJPY=X (month_end).
- timing: known_at under the T05 knowledge-time law (publication availability), never observed_at.
- event definition: brain.liquidity_lab.eventization.event_definition_id(policy); no production EventizationPolicy is ratified. Constant-FX variant: local-currency component from T04 decompose_fx_change; used only by the mechanical_target_overlap falsifier.

| role | path@commit | symbols |
| --- | --- | --- |
| producer | `engine/global_liquidity_transmission.py@eb57d3db6448b9e785e1500efef4d9a49f79f427` | `causal_orthogonal_residual` |
| T04_accounting | `engine/global_liquidity_accounting.py@eb57d3db6448b9e785e1500efef4d9a49f79f427` | `decompose_fx_change`, `standardized_magnitudes`, `reserves_from_balance_sheet` |
| T05_knowledge_time | `engine/global_liquidity_knowledge_time.py@eb57d3db6448b9e785e1500efef4d9a49f79f427` | `eligible_as_of`, `cutoff_utc`, `anchor_month_end` |
| config | `config/global_liquidity_transmission_v1.yml@eb57d3db6448b9e785e1500efef4d9a49f79f427` | (whole file) |

The source commit `eb57d3db6448b9e785e1500efef4d9a49f79f427` is the macro merge of PR 9157; the four blobs were unchanged at the later commit `a9939167d46b6ab1a73bf0a24e7f05554bf29ad8`.

## 2. Outcome family

Card `BROAD_TARGET_CARD_V1` (`glt_broad_target_card.v1`, module `brain/liquidity_lab/target_card.py`). Card hash `f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537` is `BROAD_TARGET_CARD_V1_SHA256`, the canonical SHA-256 of `BROAD_TARGET_CARD_V1.to_dict()`. It is pinned in `target_card.py`, and a build that drifts from it is refused. BTC and BABA are not members.
Planning horizons (business days): [5, 20, 60]. `primary_horizon_bdays: null`: no primary horizon is chosen until the T14 preregistration card.
Return basis: each entry's card basis (default total_return); no substitute basis. Horizon counting: declared-calendar sessions from the card govern; an estimator horizon counted on supplied closes is admissible only when every declared session in the window is supplied, otherwise the outcome is immature and never shifted; implementation belongs to T15. Basis data rights: UNRESOLVED: a licensed total-return or dividend-adjusted series per entry must be recorded before any outcome read (T14/T15 precondition).

| target_id | asset_class | overlap_families | leave_target_family_out |
| --- | --- | --- | --- |
| `spy` | us_equity | none | false |
| `qqq` | us_equity | none | false |
| `smh` | us_equity | none | false |
| `igv` | us_equity | none | false |
| `iwm` | us_equity | none | false |
| `tlt` | rates | `real_yield_10y` | true |
| `hyg` | credit | `high_yield_oas` | true |
| `lqd` | credit | `high_yield_oas`, `real_yield_10y` | true |
| `gld` | commodity | `broad_dollar` | true |
| `slv` | commodity | `broad_dollar` | true |
| `dbc` | commodity | `broad_dollar` | true |
| `uso` | commodity | `broad_dollar` | true |
| `cper` | commodity | `broad_dollar` | true |
| `efa` | dm_equity | `broad_dollar` | true |
| `eem` | em_equity | `broad_dollar` | true |
| `fxi` | china_equity | `broad_dollar` | true |
| `mchi` | china_equity | `broad_dollar` | true |
| `kweb` | china_equity | `broad_dollar` | true |

## 3. Estimands

### 3.1 Predictive — `glt_estimand_predictive.v1`

- quantity: E[log(P_(anchor+h) / P_anchor) on the card basis | a measured monetary-impulse episode first known at known_at, information set I_known_at], h in the card planning horizons
- conditioning set: pre_treatment confounders listed below; registered condition buckets us_liquidity_quality and usd_funding_impulse, measured at known_at. usd_funding_impulse at known_at is partly a mediator; conditioning on it makes this a conditional predictive association and forbids any causal reading of the conditioned cells.
- status: association only; never an effect of policy. Novelty: must beat the direct-component and leave-target-family-out baselines of protocol section 6 on identical origins before any claim of incremental information. Gate: T14 preregistration (one outcome, one horizon) and walk-forward validation before any read. The predictive association is a separately qualified claim and is never read as a policy effect (SCIENCE_PROTOCOL §5).

### 3.2 Causal — `glt_estimand_causal_total.v1`

- quantity: total response of the target log return at horizon h to an identified intervention in central-bank balance sheets, every mediator left free. a direct effect holding a mediator fixed is a different estimand and is not declared.
- `estimable: false`. The causal estimand is not estimable. It requires: "identification_receipt: a named design with first-stage relevance, timing, exclusion argument, no-anticipation evidence and a threat analysis".

## 4. Causal design (ACCEPTANCE C23)

| confounder | timing | path |
| --- | --- | --- |
| `lagged_growth_news` | pre_treatment | growth deterioration moves balance-sheet policy and asset returns together (reaction function) |
| `lagged_financial_stress` | pre_treatment | stress episodes trigger emergency facilities that expand balance sheets while risk assets fall |
| `lagged_inflation_and_policy_rate_path` | pre_treatment | inflation and the expected rate path drive purchase and runoff decisions and discount rates |
| `lagged_treasury_plumbing` | pre_treatment | TGA and ON RRP shifts change reserves relative to balance-sheet totals and move funding markets |
| `lagged_target_returns_and_volatility` | pre_treatment | policy reacts to market declines; trailing returns also carry momentum |
| `lagged_global_common_risk_factor` | pre_treatment | a global risk factor moves policy, the dollar and every target |
| `lagged_broad_dollar_level` | pre_treatment | the dollar translates ECB and BoJ assets into the USD stance and prices USD-quoted targets |

| mediator | path |
| --- | --- |
| `contemporaneous_broad_dollar` | balance-sheet impulse to dollar to USD-quoted returns |
| `contemporaneous_real_yield_10y` | balance-sheet impulse to term premium and real yields to duration assets |
| `contemporaneous_high_yield_oas` | balance-sheet impulse to credit spreads to credit and equity |
| `usd_funding_impulse_composite` | the macro usd_funding composite of the three channels above |

| collider | path |
| --- | --- |
| `post_treatment_market_stress_response` | realized post-treatment volatility or drawdown is caused by the impulse and by unobserved private shocks that also move returns |
| `post_treatment_funding_stress_realized` | realized funding stress after the impulse is a common effect of policy and private funding shocks |
| `outcome_conditioned_episode_selection` | keeping only episodes in which markets visibly reacted selects on a common effect of treatment and outcome noise |

| forbidden control | kind | applies_to |
| --- | --- | --- |
| `contemporaneous_broad_dollar` | mediator | causal |
| `contemporaneous_real_yield_10y` | mediator | causal |
| `contemporaneous_high_yield_oas` | mediator | causal |
| `usd_funding_impulse_composite` | mediator | causal |
| `post_treatment_market_stress_response` | collider | predictive, causal |
| `post_treatment_funding_stress_realized` | collider | predictive, causal |
| `outcome_conditioned_episode_selection` | collider | predictive, causal |
| `contemporaneous_or_future_target_returns` | post_treatment_outcome | predictive, causal |
| `contemporaneous_global_common_risk_factor` | post_treatment_common_factor | causal |

The contemporaneous funding components (broad dollar, 10y real yield, HY OAS) are mediators and are forbidden for the causal estimand. Their lagged values are pre-treatment confounders. Conditioning on a mediator changes the estimand, and controlling for a common effect (a collider) introduces bias (SCIENCE_PROTOCOL §5). These controls were fixed from the design before any fit (ACCEPTANCE C23).

## 5. Funding-family overlap

a target is in the funding family when its return mechanically shares a component of the usd_funding composite (broad_dollar, real_yield_10y, high_yield_oas): rates and credit through yields and spreads; USD-quoted commodities and non-US equity funds through the dollar numeraire. Each such target is evaluated against a leave-target-family-out baseline (protocol section 6). The 13 targets with leave_target_family_out true (tlt, hyg, lqd, gld, slv, dbc, uso, cper, efa, eem, fxi, mchi, kweb) use that baseline (SCIENCE_PROTOCOL §6); US equity targets do not. FX translation enters through the treatment construction itself, so the exclusion assumption `no_fx_translation_channel` is recorded as violated_by_measurement_construction and is tested via the constant-FX decomposition (T04 `decompose_fx_change`).

## 6. Exclusion assumptions

| id | assumption | status |
| --- | --- | --- |
| `no_fx_translation_channel` | the treatment reaches returns only through policy channels, not through the accounting FX translation of ECB and BoJ assets | violated_by_measurement_construction |
| `publication_is_news` | the balance-sheet change first known at known_at was not already priced | not_defended |
| `no_information_effect` | balance-sheet actions do not reveal central-bank information about growth or stress | not_defended |
| `facility_usage_is_not_a_stress_proxy` | emergency facility usage does not itself measure the stress that moves returns | not_defended |

None is claimed to hold.

## 7. Falsifiers (ACCEPTANCE C23)

| id | threat | test | refutes |
| --- | --- | --- | --- |
| `anticipation` | scheduled purchase and runoff paths are priced before publication, so the impulse at known_at is not news | split scheduled from unscheduled balance-sheet change; compare responses timed at announcement and at T05 known_at; the scheduled component must show no response at known_at | any claim that the published impulse moves returns |
| `reverse_policy_reaction` | balance sheets expand because markets and growth fell (facilities, QE restarts) | predict the impulse from lagged target returns, stress and growth news; report the response separately for reaction-driven and scheduled episodes | reading a negative association as policy harming returns or a positive one as policy helping |
| `common_risk_factor` | a global risk shock moves the USD-converted stance and every target at once | response must survive the lagged common-risk-factor baseline and a cross-region comparison; the contemporaneous factor is never added as a control | attributing a common-factor move to liquidity transmission |
| `mechanical_target_overlap` | the dollar sits inside the USD-converted treatment and inside USD-quoted targets; the funding composite shares dollar, real yield and HY OAS with funding-family targets | leave-target-family-out baseline for every funding-family target, plus the constant-FX treatment variant from T04 decompose_fx_change | any response that vanishes under constant FX or leave-family-out |
| `placebo_leads` | pre-trends or spurious timing produce a response before the impulse is known | same estimator on lead windows ending before known_at and on pseudo-event dates drawn from non-event weeks under a fixed protocol | the timing of any measured response |
| `weak_instrument` | a candidate instrument with weak first stage or an indefensible exclusion yields a forced causal number | declare a relevance threshold before outcomes; below it, or with an undefended exclusion, the status is NOT_IDENTIFIED | every causal estimate built on that instrument |

T13 declares the falsifiers; executing them belongs to T17.

## 8. Why these are not exogenous shocks (ACCEPTANCE C20)

1. `ols_residual` (any regression of the impulse on chosen regressors): orthogonal to the included regressors in sample only; still correlated with omitted drivers such as growth news, stress and the reaction function
2. `eventization_threshold_crossing` (brain/liquidity_lab/eventization.py EventizationPolicy): a deterministic function of the same endogenous state; a threshold selects large endogenous moves and adds no outside variation; event_definition_id records the choice and identifies nothing
3. `causal_orthogonal_residual` (macro engine/global_liquidity_transmission.py@eb57d3db6448b9e785e1500efef4d9a49f79f427 lines 147-165): expanding-window OLS of the impulse on the stance; causal means no look-ahead, not identification; the residual remains a function of endogenous balance-sheet changes
4. `significant_response_curve_cell` (brain/liquidity_lab/estimator.py ResponseCurveCell): an interval that excludes zero measures sampling uncertainty of an association; reverse reaction and common factors also produce significant cells; it is an output, not evidence about the input

## 9. Identification status and abstention

Status: `association_only`. No external instrument or identified-intervention receipt exists. The measured impulse is the change in an endogenous state variable that responds to growth, inflation, financial stress and FX translation; eventization at a threshold does not make it an instrument; its exclusion assumptions are undefended or violated by construction. The causal estimand is not estimated. Only the predictive association may proceed, under T14 preregistration.
A promotion to any other status needs an identification receipt object covering relevance, timing, exclusion, anticipation and a threat analysis (SCIENCE_PROTOCOL §5). A weak instrument stays NOT_IDENTIFIED.

## 10. Acceptance map

| row | evidence |
| --- | --- |
| C10 | T11 docket §4 and the tests listed there |
| C14 | T11 docket §5 and the tests listed there |
| C20 | this record §8; T11 docket §6; `tests/test_liquidity_lab_estimand_card.py::test_record_names_why_four_constructions_are_not_exogenous_shocks`, `tests/test_liquidity_lab_estimand_card.py::test_identification_status_needs_a_receipt_unless_association_only`; the eventization label tests |
| C23 | this record §4/§5/§7; `tests/test_liquidity_lab_estimand_card.py::test_forbidden_controls_never_appear_among_confounders`, `tests/test_liquidity_lab_estimand_card.py::test_every_funding_family_target_leaves_its_family_out`, `tests/test_liquidity_lab_estimand_card.py::test_all_six_falsifiers_are_declared_in_order` (declared at T13; executed at T17) |

## 11. Open items carried forward

- The session-counting / business-day calendar for outcome anchoring is carried to T15.
- Total-return rights for the card basis are UNRESOLVED.
- The producer `quality` label is not a trust gate.
- Eventization thresholds are not ratified.
- No primary horizon until T14.

## 12. Card test inventory

Tests: `test_card_parses_and_is_a_frozen_unvalidated_research_card`, `test_identification_status_needs_a_receipt_unless_association_only`, `test_forbidden_controls_never_appear_among_confounders`, `test_every_funding_family_target_leaves_its_family_out`, `test_all_six_falsifiers_are_declared_in_order`, `test_no_field_is_named_probability_alpha_or_score`, `test_card_hash_pins_the_frozen_broad_target_card`, `test_outcome_family_matches_the_card_entries_and_planning_horizons`, `test_treatment_cites_t04_t05_by_path_at_sha`, `test_predictive_and_causal_estimands_are_separate_and_causal_is_not_estimable`, `test_record_names_why_four_constructions_are_not_exogenous_shocks`, `test_card_carries_no_estimate_or_outcome_number`, `test_exclusion_assumptions_are_not_claimed_to_hold`.

Run tail: `13 passed in 1.46s`, rc=0 (`python3 -m pytest -p no:cacheprovider -rfE -v tests/test_liquidity_lab_estimand_card.py`)
