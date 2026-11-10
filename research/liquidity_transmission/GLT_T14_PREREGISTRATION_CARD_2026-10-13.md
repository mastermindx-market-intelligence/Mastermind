# GLT T14 — Preregistration card v1 (one outcome, one primary horizon, finite look budget)

Machine twin: `research/liquidity_transmission/glt_preregistration_card.v1.json` (this document is rendered from it; the JSON governs on any conflict).

| Field | Value |
|---|---|
| card_version | `glt_preregistration_card.v1` |
| frozen_at | 2026-10-19 |
| card_hash | `da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee` |
| event_definition_id | `evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66` |
| validated | false |
| evidence tier | preregistration; no outcome, price or return was read to produce this card |

## 0. Chosen first outcome and primary horizon

The first outcome is **spy** (`SPY`), return basis **total_return**, currency basis **usd**: y = log(1 + forward total return over h target sessions) = log(P_(anchor+h) / P_anchor) on the T12 total_return basis

The primary horizon is **20 target sessions**, with sensitivity horizons 5, 60. No other horizon may be promoted after a look.

Three ex-ante reasons for the outcome:

1. product usefulness: spy is the broad US equity benchmark that other card entries are judged against
2. source eligibility: native USD on its native us_equity_sessions calendar, so the outcome needs no FX leg; T13 lists no overlap family for spy, so no mechanical target overlap with the treatment
3. ex-ante precision: effective N is set by the treatment event calendar, identical for every target, so the choice of target cannot buy precision; spy adds no FX or calendar-alignment loss on top

Ex-ante reasons for the primary horizon:

1. 20 sessions spans the BOJ month-end publication cadence and the weekly H.4.1/ECB release lags with room for the response
2. 60 sessions leaves too few non-overlapping episodes in the dev and reserved windows (see power.expected_effective_n)
3. at 5 sessions the release lag consumes most of the response window

No outcome, price or return was read to make any choice on this card, and no performance figure appears in it.

Upstream owners:

- **T03_register**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5`
- **T05_knowledge_time**: `macro:engine/global_liquidity_knowledge_time.py@7533b434cda92fc600859ef4d1860192f3bc7fa5`
- **T11_event_definition_docket**: `mastermind:research/liquidity_transmission/GLT_T11_EVENT_DEFINITION_DOCKET_2026-10-13.md@dc816f498f7cffa19cc82210ca8d73643fa5f156#base-policy-row`
- **T11_eventization**: `mastermind:brain/liquidity_lab/eventization.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#event_definition_id`
- **T12_target_card**: `mastermind:brain/liquidity_lab/target_card.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#BROAD_TARGET_CARD_V1`
- **T12_target_card_sha256**: f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537
- **T13_estimand_card**: `mastermind:research/liquidity_transmission/glt_estimand_card.v1.json@dc816f498f7cffa19cc82210ca8d73643fa5f156`
- **T13_estimand_card_file_sha256**: 44a78d4a7b615b9b5941d613b05cb0af1ae949e8232fa34dcd87ada54a518ff1

## 1. exact source archive, rights and information-vintage roles

**sources**

- **source_id = fed_total_assets**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=fed_total_assets`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_us_government
  - **licence_class**: public_us_government
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**:
    - T11 event calendar (state.monetary_impulse_z per T13 treatment.construction)
    - B2 (WALCL leg)
    - B4 (4-week change of WALCL)
- **source_id = ecb_total_assets**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=ecb_total_assets`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_with_attribution (attribution required on any display)
  - **licence_class**: public_with_attribution
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**:
    - T11 event calendar (state.monetary_impulse_z per T13 treatment.construction)
    - B4 (4-week change of ECBASSETSW, native EUR, no FX)
- **source_id = boj_total_assets**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=boj_total_assets`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_with_attribution; month-end anchor mandatory (DSC:BOJ-ASSETS-REQUIRE-MONTH-END-ANCHOR)
  - **licence_class**: public_with_attribution
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**:
    - T11 event calendar (state.monetary_impulse_z per T13 treatment.construction)
    - B4 (4-week change of JPNASSETS, native JPY, no FX)
- **source_id = fed_rrp**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=fed_rrp`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_us_government
  - **licence_class**: public_us_government
  - **vintage_role**: reconstructed_research=eligible; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: eligible
  - **feeds_first_outcome**: true
  - **used_by**: B2 (RRP leg of the net-liquidity identity)
- **source_id = fed_tga**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=fed_tga`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_us_government
  - **licence_class**: public_us_government
  - **vintage_role**: reconstructed_research=eligible; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: eligible
  - **feeds_first_outcome**: true
  - **used_by**: B2 (TGA leg of the net-liquidity identity)
- **source_id = fed_net_liquidity**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=fed_net_liquidity`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class derived; recomputed in-harness by the formula owner engine.canon.load_net_liquidity_components from the OPEN inputs fed_total_assets, fed_rrp, fed_tga
  - **licence_class**: derived
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**: B2 (overlay state recomputed from WALCL - RRP - TGA)
- **source_id = dtwexbgs**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=market_liquidity_proxies;series=DTWEXBGS`
  - **rights_state**: OPEN
  - **rights_basis**: register display reason for this family states verbatim: (DTWEXBGS/DFII10 are public US government); the family licence_class licensed_no_redistribution is carried by the HY OAS member
  - **licence_class**: licensed_no_redistribution
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**: B4 (4-week change of log DTWEXBGS), window start (DTWEXBGS begins 2006-01-02)
- **source_id = dfii10**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=market_liquidity_proxies;series=DFII10`
  - **rights_state**: OPEN
  - **rights_basis**: register display reason for this family states verbatim: (DTWEXBGS/DFII10 are public US government)
  - **licence_class**: licensed_no_redistribution
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: true
  - **used_by**: B4 (4-week change of DFII10)
- **source_id = fx_eurusd**
  - **register_ref**: macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=ecb_total_assets;role + mastermind:research/liquidity_transmission/glt_estimand_card.v1.json@dc816f498f7cffa19cc82210ca8d73643fa5f156#treatment.construction
  - **rights_state**: UNPROVEN
  - **rights_basis**: register ecb_total_assets.role: the in-repo Yahoo EURUSD store is licensed_no_redistribution; no in-repo grant for internal research computation is recorded; this card does not upgrade it (K01.02)
  - **licence_class**: licensed_no_redistribution (register role sentence)
  - **vintage_role**: conversion leg (EURUSD=X) of the USD-converted global balance-sheet composite that defines the T11 event calendar
  - **register_verdict**: unregistered_conversion_leg
  - **feeds_first_outcome**: true
  - **used_by**:
    - T11 event calendar (state.monetary_impulse_z per T13 treatment.construction)
- **source_id = fx_usdjpy**
  - **register_ref**: mastermind:research/liquidity_transmission/glt_estimand_card.v1.json@dc816f498f7cffa19cc82210ca8d73643fa5f156#treatment.construction (no register or dataset-registry rights row found at 7533b434cda92fc600859ef4d1860192f3bc7fa5)
  - **rights_state**: UNPROVEN
  - **rights_basis**: no rights record for the USDJPY=X store exists in the register or the dataset registry; absence of proof, not a finding of restriction; this card does not upgrade it (K01.02)
  - **licence_class**: unrecorded
  - **vintage_role**: conversion leg (USDJPY=X, month_end) of the USD-converted global balance-sheet composite that defines the T11 event calendar
  - **register_verdict**: unregistered_conversion_leg
  - **feeds_first_outcome**: true
  - **used_by**:
    - T11 event calendar (state.monetary_impulse_z per T13 treatment.construction)
- **source_id = spy_total_return_bars**
  - **register_ref**: `macro:config/dataset_registry.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#dataset_id=equity.bars.daily.yahoo`
  - **rights_state**: UNPROVEN
  - **rights_basis**: dataset registry licensing vendor_terms_personal_use; no in-repo grant for research computation is recorded; this card does not upgrade it (K01.02)
  - **licence_class**: vendor_terms_personal_use
  - **vintage_role**: outcome y (Adj Close basis, total_return per T12); stored bases are re-adjusted by Yahoo at every fetch, adjustment_asof owed
  - **register_verdict**: registered_dataset_rights_unproven
  - **feeds_first_outcome**: true
  - **used_by**: outcome y, B3 (trailing SPY return, realized vol, 200-session mean)
- **source_id = peer_etf_bars_efa_eem_hyg**
  - **register_ref**: `macro:config/dataset_registry.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#dataset_id=equity.bars.daily.yahoo`
  - **rights_state**: UNPROVEN
  - **rights_basis**: dataset registry licensing vendor_terms_personal_use; no in-repo grant for research computation is recorded; this card does not upgrade it (K01.02)
  - **licence_class**: vendor_terms_personal_use
  - **vintage_role**: B5 lagged common-risk-factor input (trailing 20-session equal-weight log return of efa, eem, hyg known at the origin)
  - **register_verdict**: registered_dataset_rights_unproven
  - **feeds_first_outcome**: true
  - **used_by**: B5
- **source_id = hy_oas**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=market_liquidity_proxies;series=BAMLH0A0HYM2`
  - **rights_state**: UNPROVEN
  - **rights_basis**: register display reason: HY OAS custody gap, the ICE BofA licence is not verified in repo
  - **licence_class**: licensed_no_redistribution
  - **vintage_role**: reconstructed_research=conditional; vintage_qualified_research=excluded; prospective_eligibility=conditional; archive=none
  - **register_verdict**: conditional
  - **feeds_first_outcome**: false
  - **used_by**:
    - none in this card; blocks the deferred T13 usd_funding_impulse bucket
- **source_id = nfci_anfci**
  - **register_ref**: `macro:config/global_liquidity_sources_v2.yml@7533b434cda92fc600859ef4d1860192f3bc7fa5#id=nfci_anfci`
  - **rights_state**: OPEN
  - **rights_basis**: register licence_class public_us_government
  - **licence_class**: public_us_government
  - **vintage_role**: reconstructed_research=excluded; vintage_qualified_research=excluded; prospective_eligibility=excluded; archive=none
  - **register_verdict**: excluded
  - **feeds_first_outcome**: false
  - **used_by**:
    - none in this card; register reconstructed_research verdict excluded (whole-history re-estimation, not point-in-time)

Rights states are copied from the register and never inferred. UNPROVEN means no in-repo grant was found; it is not a finding that use is forbidden.

## 2. eligible universe, subject/contract identities, delistings or population limitation

**universe**

- **card_ref**: `mastermind:brain/liquidity_lab/target_card.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#BROAD_TARGET_CARD_V1`
- **card_sha256**: f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537
- **eligible_target_ids**: spy, qqq, smh, igv, iwm, tlt, hyg, lqd, gld, slv, dbc, uso, cper, efa, eem, fxi, mchi, kweb
- **first_study_target_ids**: spy
- **exclusions**:
  - **target_id = btc**
    - **reason**: crypto motivating example: archived motivation per SCIENCE_PROTOCOL section 9 / acceptance C22; no new crypto programme
  - **target_id = baba**
    - **reason**: single-name motivating example: archived per SCIENCE_PROTOCOL section 9 / acceptance C22; excluded by role (single_name) and by name

## 3. training/development/reserved time windows and contamination exclusions

**windows**

- **calendar**: us_equity_sessions
- **train_start**: 2008-01-04
- **train_end**: 2017-12-29
- **dev_start**: 2018-01-02
- **dev_end**: 2021-12-31
- **reserved_start**: 2022-01-03
- **reserved_end**: 2026-06-30
- **frontier**: 2026-06-30
- **purge_sessions**: `60`
- **refractory_sessions**: `0`
- **start_rule**: train_start = DTWEXBGS first observation 2006-01-02 plus 104 weeks of minimum history for the causal expanding z
- **frontier_rule**: last anchor whose 60-session outcome matures before frozen_at
- **contamination_exclusion**: an episode is assigned to the window holding its anchor; an episode whose h-session outcome would mature in a later window is purged (purge_sessions = max horizon); overlapping episodes are thinned by validation.effective_episode_dates(dates, horizon_bdays=h); refractory 0 per the event policy
- **effective_episode_rule_ref**: `mastermind:brain/liquidity_lab/validation.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#effective_episode_dates`
- **reserved_role**: RETROSPECTIVE holdout, not untouched confirmation: production liquidity curves were fit on history that spans it; untouched confirmation is prospective accrual after frozen_at (reveal.prospective)

## 4. economic estimand and the causal diagram or predictive conditioning set

**estimand_card_ref**

- **path**: `research/liquidity_transmission/glt_estimand_card.v1.json`
- **ref**: `mastermind:research/liquidity_transmission/glt_estimand_card.v1.json@dc816f498f7cffa19cc82210ca8d73643fa5f156`
- **relation_id**: glt_rel_monetary_impulse_to_broad_targets.v1
- **identification_status**: association_only
- **treatment_identification_status**: NOT_IDENTIFIED

**estimand**

- **predictive**: glt_estimand_predictive.v1 restricted to target spy and horizon 20 (5, 60 sensitivity), marginal over the deferred condition buckets: E[y | a measured monetary-impulse episode first known at known_at, its direction, I_known_at]
- **causal**: glt_estimand_causal_total.v1 is not estimated (T13 estimable false; no identification receipt)
- **conditioning_set**:
  - shock direction (ShockRecord.direction, known at first_detected)
- **deferred_conditioning**:
  - **bucket = us_liquidity_quality**
    - **reason**: its financial-conditions input nfci_anfci is register-excluded for reconstructed research (not point-in-time)
  - **bucket = usd_funding_impulse**
    - **reason**: contains HY OAS, rights UNPROVEN; and T13 notes it is partly a mediator
- **forbidden_controls**:
  - **id = contemporaneous_broad_dollar**
    - **kind**: mediator
    - **applies_to**: causal
  - **id = contemporaneous_real_yield_10y**
    - **kind**: mediator
    - **applies_to**: causal
  - **id = contemporaneous_high_yield_oas**
    - **kind**: mediator
    - **applies_to**: causal
  - **id = usd_funding_impulse_composite**
    - **kind**: mediator
    - **applies_to**: causal
  - **id = post_treatment_market_stress_response**
    - **kind**: collider
    - **applies_to**: predictive, causal
  - **id = post_treatment_funding_stress_realized**
    - **kind**: collider
    - **applies_to**: predictive, causal
  - **id = outcome_conditioned_episode_selection**
    - **kind**: collider
    - **applies_to**: predictive, causal
  - **id = contemporaneous_or_future_target_returns**
    - **kind**: post_treatment_outcome
    - **applies_to**: predictive, causal
  - **id = contemporaneous_global_common_risk_factor**
    - **kind**: post_treatment_common_factor
    - **applies_to**: causal
- **interpretation**: association only; never an effect of policy

## 5. event and correction/refractory policy, decision cutoff and target calendar

- **event_definition_id**: `evdef_f559621219beafdebd254b21458f06f97cc98b3566ae6e13a8bc0d5a8cb2eb66`

**event_policy**

- **thresholds**:
  - **material_abs_z**: `1.0`
  - **reset_abs_z**: `0.4`
  - **min_coverage**: `0.7`
  - **min_confidence**: `0.7`
  - **max_observation_gap_bdays**: `10`
  - **refractory_bdays**: `0`
- **thresholds_ref**: mastermind:research/liquidity_transmission/GLT_T11_EVENT_DEFINITION_DOCKET_2026-10-13.md@dc816f498f7cffa19cc82210ca8d73643fa5f156#base-policy-row (1.0, 0.4, 0.7, 0.7, 10, 0)
- **ratification**: NOT Sol-ratified: the T11 test BASE policy is declared here explicitly because EventizationPolicy has no production default; ratifying different thresholds mints a new card version
- **event_calendar**: numpy_busday_mon_fri_no_holidays
- **target_calendar**: us_equity_sessions
- **decision_cutoff**: an origin uses only information whose T05 known_at is at or before the episode first_detected business date; the forecast is fixed before the anchor close
- **correction_policy**: keep-first: the first ForwardLedger record or grade per key is authoritative (KeepFirstConflict); a later source correction never rewrites a recorded forecast or grade; a corrected input requires a new card version

## 6. fixed target, horizon, anchor price and maturity/ambiguous-data rules

**first_outcome**

- **target_id**: spy
- **symbol**: SPY
- **return_basis**: total_return
- **currency_basis**: usd
- **outcome_variable**: y = log(1 + forward total return over h target sessions) = log(P_(anchor+h) / P_anchor) on the T12 total_return basis
- **target_card_ref**: `mastermind:brain/liquidity_lab/target_card.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#BROAD_TARGET_CARD_V1.entries[spy]`

**horizons**

- **unit**: target_sessions
- **candidates**: `5`, `20`, `60`
- **candidates_ref**: `mastermind:brain/liquidity_lab/target_card.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#PLANNING_HORIZONS`
- **primary**: `20`
- **sensitivity**: `5`, `60`

**target_rules**

- **anchor_price**: official_close
- **anchor_rule**: the anchor is the official close of the first declared-calendar session strictly after the first-detection calendar date
- **maturity_rule**: an outcome at horizon h is mature only when the official close of the h-th declared-calendar session after the anchor session is available as of the evaluation clock; a missing close keeps the outcome immature and never shifts the horizon to a later session
- **ambiguous_data_rule**: an outcome whose anchor or h-th official close is missing, flagged, stale, or not yet available at the evaluation clock is ambiguous: it is excluded from the paired population, counted in the coverage denominator, never imputed and never shifted to a later session
- **calendar_owner**: portfolio.market_calendar.is_trading_day
- **calendar_coverage**: 2025-01-01, 2027-12-31

## 7. model families, transformations, hyperparameters and finite tuning budget

**models**

- **model_id = M1**
  - **family**: direction_split_hierarchical_mean_curve
  - **estimator_ref**: `mastermind:brain/liquidity_lab/estimator.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#HierarchicalMeanCurveEstimator`
  - **transforms**:
    - **name = log1p_forward_total_return**
      - **fit_on**: train
      - **note**: deterministic; no fitted parameter
    - **name = direction_partition**
      - **fit_on**: train
      - **note**: harness partitions episodes by ShockRecord.direction; estimator unchanged
  - **fit_on_definition**: fitted only on episodes strictly before the evaluated fold or window, after the horizon purge; for L2/L3 that is every development episode whose h-session outcome matures before reserved_start
  - **hyperparameters**:
    - **prior_strength_grid**: `0`, `5`, `20`
    - **min_effective_n**: `10`
    - **model_version**: glt_t14_m1.v1
    - **condition_keys**: none: the estimator receives the empty tuple; direction is applied by the harness partition
  - **tuning_budget**: `3`
  - **selection_rule**: L1: lowest MSE over dev walk-forward validation folds whose validation_start is on or after dev_start; ties go to the smaller prior_strength

## 8. baselines, primary paired population and coverage denominator

**baselines**

- **baseline_id = B1**
  - **rung**: unconditional
  - **definition**: training mean of non-overlapping SPY h-session log total returns
  - **inputs**: spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: clark_west (B1 is nested in M1)
- **baseline_id = B2**
  - **rung**: current_regime
  - **definition**: training mean of y by net-liquidity quantity overlay state (expanding|neutral|contracting) recomputed in-harness from WALCL - RRP - TGA under the engine/regime.py liquidity_overlay config; that config was tuned on full history, so this baseline is contaminated in its favour (harder to beat, conservative) and is recorded as such
  - **inputs**: fed_total_assets, fed_rrp, fed_tga, fed_net_liquidity, spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: newey_west_tstat(lags=4)
- **baseline_id = B3**
  - **rung**: context
  - **definition**: OLS of y on the trailing 20-session SPY log return, 60-session realized volatility and the sign of the close versus its 200-session mean
  - **inputs**: spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: newey_west_tstat(lags=4)
- **baseline_id = B4**
  - **rung**: direct_component
  - **definition**: OLS of y on 4-week changes of log WALCL, log ECBASSETSW (EUR), log JPNASSETS (JPY), log DTWEXBGS and DFII10; no FX leg, no HY OAS; these mediators are forbidden only for the causal estimand (T13 forbidden_controls.applies_to)
  - **inputs**: fed_total_assets, ecb_total_assets, boj_total_assets, dtwexbgs, dfii10, spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: newey_west_tstat(lags=4)
- **baseline_id = B5**
  - **rung**: lagged_common_risk_factor
  - **definition**: OLS of y on the trailing 20-session equal-weight log return of efa, eem and hyg known at the origin; replaces leave-target-family-out, which T13 marks not applicable to spy (overlap_families empty, leave_target_family_out false), and implements the T13 common_risk_factor falsifier
  - **inputs**: peer_etf_bars_efa_eem_hyg, spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: newey_west_tstat(lags=4)
- **baseline_id = B6**
  - **rung**: lower_complexity_alternative
  - **definition**: direction-pooled event mean: HierarchicalMeanCurveEstimator as shipped with prior_strength 0 over all episodes regardless of direction
  - **inputs**: T11 event calendar, spy_total_return_bars
  - **fit_on**: train
  - **known_at**: origin (T05 known_at <= episode first_detected)
  - **test**: newey_west_tstat(lags=4)

**incumbent**

- **status**: none eligible
- **reason**: production liquidity curves were fit on full history spanning dev and reserved; reported separately if shown, never counted in the family

- **paired_population**: thinned event origins (effective_episode_dates at horizon h) inside the evaluated window where M1 and every baseline B1-B6 issue a prediction and the outcome is mature and unambiguous

- **coverage_denominator**: all thinned event origins inside the evaluated window; coverage = paired / denominator; coverage below 0.80 makes the comparison insufficient

## 9. practical error/utility margins, uncertainty and joint power design

**margins**

- **units**: y in log total-return units; MSE in squared log-return units
- **error**: MSE(M1) <= 0.98 * min over B1-B6 of MSE(B) on the paired population
- **utility**: sign hit rate of M1 at least 3 percentage points above the best-MSE baseline on the paired population
- **joint_rule**: a gain claim requires both margins and the multiplicity rule
- **uncertainty_form**: one-sided paired loss-differential test per baseline: engine.validation.newey_west_tstat(lags=4) on episode-ordered squared-error differentials, clark_west for nested B1; reached through validation.score_incremental_predictions
- **uncertainty_refs**:
  - `macro:engine/validation.py@7533b434cda92fc600859ef4d1860192f3bc7fa5#newey_west_tstat`
  - `macro:engine/validation.py@7533b434cda92fc600859ef4d1860192f3bc7fa5#clark_west`
  - `mastermind:brain/liquidity_lab/validation.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#score_incremental_predictions`

**power**

- **design**: joint: both margins at h20 on the reserved window; MDE = (z_0.95 + z_0.80) / sqrt(N_eff) = 2.487 / sqrt(N_eff) standard deviations of the per-episode loss differential
- **expected_effective_n**:
  - **basis**: event calendar only, simulated (weekly z iid N(0,1) or AR(1) rho 0.6 under the declared hysteresis, greedy thinning); no source or outcome data read; the real T11 calendar needs the UNPROVEN FX legs
  - **seed**: `20261019`
  - **sims**: `400`
  - **windows**:
    - **train**:
      - **start**: 2008-01-04
      - **end**: 2017-12-29
      - **weekday_sessions**: `2606`
      - **upper_bound_effective_n**:
        - **h5**: `521`
        - **h20**: `130`
        - **h60**: `43`
      - **sim_iid_p10_p50_p90**:
        - **h5**: `113`, `123`, `133`
        - **h20**: `73`, `78`, `82`
        - **h60**: `34`, `36`, `37`
      - **sim_ar1_rho0.6_p10_p50_p90**:
        - **h5**: `66`, `74`, `80`
        - **h20**: `56`, `61`, `67`
        - **h60**: `30`, `32`, `34`
    - **dev**:
      - **start**: 2018-01-02
      - **end**: 2021-12-31
      - **weekday_sessions**: `1044`
      - **upper_bound_effective_n**:
        - **h5**: `208`
        - **h20**: `52`
        - **h60**: `17`
      - **sim_iid_p10_p50_p90**:
        - **h5**: `43`, `49`, `55`
        - **h20**: `28`, `31`, `34`
        - **h60**: `13`, `14`, `15`
      - **sim_ar1_rho0.6_p10_p50_p90**:
        - **h5**: `26`, `29`, `34`
        - **h20**: `21`, `25`, `28`
        - **h60**: `12`, `13`, `14`
    - **reserved**:
      - **start**: 2022-01-03
      - **end**: 2026-06-30
      - **weekday_sessions**: `1172`
      - **upper_bound_effective_n**:
        - **h5**: `234`
        - **h20**: `58`
        - **h60**: `19`
      - **sim_iid_p10_p50_p90**:
        - **h5**: `49`, `55`, `62`
        - **h20**: `31`, `35`, `38`
        - **h60**: `15`, `16`, `17`
      - **sim_ar1_rho0.6_p10_p50_p90**:
        - **h5**: `29`, `34`, `38`
        - **h20**: `24`, `28`, `31`
        - **h60**: `13`, `15`, `16`
- **mde_reserved_h20**: about 0.42 to 0.47 SD at reserved N_eff 28 to 35
- **declared_underpowered**: true
- **non_rejection**: insufficient, never evidence of no effect

## 10. dependence blocks, overlap purging and familywise/multiplicity treatment

**power (dependence)**

- **blocks**: one shock episode is one block; every row an episode generates (horizon, target) shares that block; rows are never events
- **dependence_rule**: episodes thinned by effective_episode_dates so overlapping windows never both count; HAC Newey-West lags 4 over episode-ordered differentials

**windows (contamination)**

- **purge_sessions**: `60`
- **refractory_sessions**: `0`
- **contamination_exclusion**: an episode is assigned to the window holding its anchor; an episode whose h-session outcome would mature in a later window is purged (purge_sessions = max horizon); overlapping episodes are thinned by validation.effective_episode_dates(dates, horizon_bdays=h); refractory 0 per the event policy
- **effective_episode_rule_ref**: `mastermind:brain/liquidity_lab/validation.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#effective_episode_dates`

**family**

- **axes**:
  - **outcomes**: spy
  - **horizons**: `20`, `5`, `60`
  - **model_configs**: M1_prior0, M1_prior5, M1_prior20
  - **baselines**: B1, B2, B3, B4, B5, B6
- **n_outcomes**: `1`
- **n_horizons**: `3`
- **n_models**: `3`
- **n_baselines**: `6`
- **n_trials_total**: `54`

- **family.trials**: 54 trials: spy|h20|M1_prior0|B1, spy|h20|M1_prior0|B2, spy|h20|M1_prior0|B3, spy|h20|M1_prior0|B4, spy|h20|M1_prior0|B5, spy|h20|M1_prior0|B6, spy|h20|M1_prior5|B1, spy|h20|M1_prior5|B2, spy|h20|M1_prior5|B3, spy|h20|M1_prior5|B4, spy|h20|M1_prior5|B5, spy|h20|M1_prior5|B6, spy|h20|M1_prior20|B1, spy|h20|M1_prior20|B2, spy|h20|M1_prior20|B3, spy|h20|M1_prior20|B4, spy|h20|M1_prior20|B5, spy|h20|M1_prior20|B6, spy|h5|M1_prior0|B1, spy|h5|M1_prior0|B2, spy|h5|M1_prior0|B3, spy|h5|M1_prior0|B4, spy|h5|M1_prior0|B5, spy|h5|M1_prior0|B6, spy|h5|M1_prior5|B1, spy|h5|M1_prior5|B2, spy|h5|M1_prior5|B3, spy|h5|M1_prior5|B4, spy|h5|M1_prior5|B5, spy|h5|M1_prior5|B6, spy|h5|M1_prior20|B1, spy|h5|M1_prior20|B2, spy|h5|M1_prior20|B3, spy|h5|M1_prior20|B4, spy|h5|M1_prior20|B5, spy|h5|M1_prior20|B6, spy|h60|M1_prior0|B1, spy|h60|M1_prior0|B2, spy|h60|M1_prior0|B3, spy|h60|M1_prior0|B4, spy|h60|M1_prior0|B5, spy|h60|M1_prior0|B6, spy|h60|M1_prior5|B1, spy|h60|M1_prior5|B2, spy|h60|M1_prior5|B3, spy|h60|M1_prior5|B4, spy|h60|M1_prior5|B5, spy|h60|M1_prior5|B6, spy|h60|M1_prior20|B1, spy|h60|M1_prior20|B2, spy|h60|M1_prior20|B3, spy|h60|M1_prior20|B4, spy|h60|M1_prior20|B5, spy|h60|M1_prior20|B6

**multiplicity**

- **rule**: intersection-union within a horizon (a claim at h needs rejection against every baseline; p_h = max over baselines), then Benjamini-Hochberg across the 3 horizons via validation.apply_bh_fdr; the primary claim is h20 only and the sensitivity horizons cannot rescue it
- **alpha**: `0.1`
- **fdr_ref**: `mastermind:brain/liquidity_lab/validation.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#apply_bh_fdr`

## 11. reveal custodian and permitted number of looks through existing evaluation ownership

**reveal**

- **custodian**: ForwardLedger
- **custodian_ref**: `mastermind:brain/liquidity_lab/ledger.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#ForwardLedger`
- **split_owner_ref**: `mastermind:brain/liquidity_lab/validation.py@dc816f498f7cffa19cc82210ca8d73643fa5f156#build_walk_forward_plan`
- **walk_forward_spec**:
  - **holdout_start**: 2022-01-03
  - **min_train_episodes**: `20`
  - **validation_episodes**: `5`
  - **step_episodes**: `5`
- **external_note**: the macro TrialLedger is external (different repository) and is not the custodian here
- **look_budget**: `3`
- **looks_declared**:
  - **look_id = L1**
    - **at**: 2026-10-20
    - **window**: dev
    - **horizons**: `20`
    - **purpose**: M1 prior_strength selection on dev walk-forward folds
    - **requires**: reveal_blockers(card) is empty
  - **look_id = L2**
    - **at**: 2026-10-20
    - **window**: reserved
    - **horizons**: `20`
    - **purpose**: primary comparison of the selected M1 against B1-B6
    - **requires**: L1 recorded and reveal_blockers(card) is empty
  - **look_id = L3**
    - **at**: 2026-10-20
    - **window**: reserved
    - **horizons**: `5`, `60`
    - **purpose**: sensitivity horizons together, one look
    - **requires**: L2 recorded and reveal_blockers(card) is empty
- **look_at_semantics**: at is a not-before date; each look additionally requires reveal_blockers to be empty
- **prospective**:
  - **read**: T26 forward accrual: forecasts recorded keep-first in ForwardLedger after frozen_at, read once at least 20 matured h20 episodes exist
  - **counted_in_look_budget**: false
  - **reason**: out of sample by construction

## 12. full return artifact identities, negative-result handling and claim disposition

**returns**

- **artifact_ids**:
  - `research/liquidity_transmission/glt_t14_l1_dev_selection.v1.json`
  - `research/liquidity_transmission/glt_t14_l2_reserved_primary.v1.json`
  - `research/liquidity_transmission/glt_t14_l3_reserved_sensitivity.v1.json`
  - ForwardLedger rows keyed by card_hash, event_definition_id, target_id and horizon
- **artifact_identity**: every artifact carries this card_hash and event_definition_id
- **negative_result_handling**: no gain over baseline and insufficient are reportable results at the same tier and are published in the same artifacts; any change after frozen_at mints a new card version and never edits v1
- **claim_disposition**:
  - **validated**: false
  - **max_tier**: display
  - **trading_authority**: none
  - **interpretation**: association_only

**blocked_questions**

- **question = every outcome look L1-L3**
  - **missing_input**: rights for internal research computation on the Yahoo SPY and peer ETF bars and on the EURUSD=X and USDJPY=X FX legs, or licensed replacements
  - **owner**: human rights decision (Chairman)
- **question = every outcome look L1-L3**
  - **missing_input**: portfolio.market_calendar coverage for 2008-01-04..2026-06-30 (owner covers 2025-01-01..2027-12-31)
  - **owner**: engineering follow-on (calendar owner)
- **question = bucket-conditioned successor card**
  - **missing_input**: HY OAS licence (ICE BofA) and point-in-time NFCI vintages
  - **owner**: human rights decision (HY OAS); data custody (NFCI vintages)

## Validator status at freeze

`brain/liquidity_lab/preregistration.py` splits refusals into two groups.

- **Structural refusals** are defects of the card itself. On the frozen card the tuple is empty.
- **Reveal blockers** are conditions outside the card that must clear before any look. On the frozen card they are:

```
BLANK_RIGHTS:fx_eurusd
BLANK_RIGHTS:fx_usdjpy
BLANK_RIGHTS:spy_total_return_bars
BLANK_RIGHTS:peer_etf_bars_efa_eem_hyg
UNCOVERED_CALENDAR:train
UNCOVERED_CALENDAR:dev
UNCOVERED_CALENDAR:reserved
```

Every look L1 to L3 requires `reveal_blockers(card)` to be empty, so no outcome can be read until both gates clear.

## Gates

- **Human rights decision.** Internal research computation needs a rights grant for the Yahoo SPY and peer ETF bars and the EURUSD=X and USDJPY=X conversion legs, or licensed replacements. The HY OAS licence is also needed before the deferred `us_liquidity_quality` bucket can be conditioned on. This blocks reveals only.
- **Engineering follow-on.** The calendar owner `portfolio.market_calendar.is_trading_day` covers 2025-01-01 to 2027-12-31. Every window starts earlier, so coverage must be extended back to 2008 before a look.

## Deviations from the T14 packet

- **D1. Validator split.** The packet asked that the frozen card validate empty. The rights and calendar gaps are real, so the validator reports them as reveal blockers while structural refusals stay empty.
- **D2. Marginalized predictive estimand.** The T13 conditioning buckets are deferred. NFCI is register-excluded for reconstructed research and HY OAS rights are UNPROVEN, so only shock direction conditions the estimate.
- **D3. Attribution trailer.** Commits carry the Opus 5.5 trailer because that is the model that ran the seat.
- **D4. Labour placement.** The seat authored this card, its JSON twin and the validator. The fabric build lane for the validator was refused at admission before any worker started, so the seat built it directly. A non-author fabric lane reviewed the validator before merge.
- **D5. Extra refusal codes.** `INVALID_ENUM`, `INELIGIBLE_TARGET`, `UNCOVERED_CALENDAR` and `NON_PIT_INPUT` were added because the packet's codes could not express those defects.
- **D6. Fail-closed validator choices.** A list-valued section that is not a list is refused as `BLANK_FIELD`. A source feeds the first outcome unless it says `false` explicitly. A source without an id is named by its index.
