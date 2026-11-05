# GLT T15/T16 — same-information baselines and response-path evidence

- Status: research measurement only. `validated: false`. Display tier at most; nothing serves.
- Estimand: `predictive_response` only. `identification_status` NOT_IDENTIFIED (the card's
  treatment status); interpretation `association_only`. T16 emits no causal estimand and
  accepts no identification receipt; T17 owns identification.
- Frozen card: `research/liquidity_transmission/glt_preregistration_card.v1.json`,
  card_hash `da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee` (unchanged;
  this PR edits neither the card nor any T14 module).
- Evidence in this note is **fixture evidence** (synthetic panels built by the tests and by a
  scratch harness). No price, return or source observation was read. No look was recorded
  (`ForwardLedger.record` 0 calls, `grade` 0 calls). Nothing on or after `reserved_start`
  2022-01-03 was admitted.

## 1. What was built

| Module | Task | Purpose |
| --- | --- | --- |
| `brain/liquidity_lab/baselines.py` | T15 | Same-information baseline ladder implementing the existing `ResponseCurveEstimator` Protocol; `PairedPopulation` / `restrict_to_common` / `score_paired` (C27); train-only transforms with `check_train_only` (C17); `novelty_disposition`; LTIFO loader, hash and family mask (C26). |
| `brain/liquidity_lab/window_guard.py` | T15 | `WindowGuard`: admits train/dev rows only, refuses reserved rows and counts each refusal by reason. |
| `research/liquidity_transmission/glt_ltifo_sensitivity.v1.json` | T15 | Frozen leave-target-family-out definition (sensitivity only). |
| `brain/liquidity_lab/response_path.py` | T16 | `ResponsePathSpec` read only from the frozen card; `SearchBudget` against `family.n_trials_total`; pooled, state-conditioned and local-projection challengers on one walk-forward plan; `fit_response_path`; `response_time_functional`; `delay_cost_sensitivity`. |
| `brain/liquidity_lab/path_inference.py` | T16 | Episode blocks; episode-block studentised bootstrap with pointwise and sup-t simultaneous bands; leave-one-episode-out and leave-one-era-out influence; `incremental_skill` / `path_multiplicity`, which abstain on `StatisticalDependencyUnavailable`. |
| `brain/liquidity_lab/response_evidence.py` | T16 | Additive CONTRACTS §5 read projection (`ResponseCurveCell` is not replaced). |

## 2. Card fields used (quoted from the frozen card)

- `horizons`: unit `target_sessions`; candidates `[5, 20, 60]`; primary `20`; sensitivity `[5, 60]`.
  There is no response-time functional field.
- `family.n_trials_total`: `54` (1 outcome × 3 horizons × 3 M1 configs × 6 baselines).
- `windows`: train 2008-01-04..2017-12-29; dev 2018-01-02..2021-12-31; reserved_start
  2022-01-03; `purge_sessions` 60.
- `power.blocks`: "one shock episode is one block; every row an episode generates (horizon, target) shares that block; rows are never events".
- `power.dependence_rule`: "episodes thinned by effective_episode_dates so overlapping windows never both count; HAC Newey-West lags 4 over episode-ordered differentials".
- `paired_population`: thinned event origins inside the evaluated window where M1 and every
  baseline B1–B6 predict and the outcome is mature and unambiguous.
- `coverage_denominator`: all thinned event origins inside the window; "coverage below 0.80 makes the comparison insufficient".
- `models[M1].hyperparameters.min_effective_n`: 10.

## 3. Baseline ladder (T15)

Each class declares its information set as `condition_keys`. `fit` refuses any other key, so
no comparator can receive information it did not declare.

| Rung | Class | Information set | Card | SCIENCE_PROTOCOL §6 rationale |
| --- | --- | --- | --- | --- |
| unconditional | `PooledMeanBaseline` | () — training event-row mean | B1 / B6 | asset response: unconditional mean |
| context | `PriceMomentumBaseline` | target 20-session return sign, 60-session vol tercile, above-200-MA flag | B3 | asset response: return/vol/trend context |
| direct_component | `ComponentBaseline` | 4-week-change signs of WALCL, ECBASSETSW, JPNASSETS, DTWEXBGS, DFII10 | B4 | direct observable macro inputs |
| direct_funding | `DirectFundingBaseline` | 4-week-change signs of DTWEXBGS, DFII10 | B4 funding legs | funding composite contains dollar/real yield/HY: direct-component comparator (C26) |
| persistence_no_change | `PersistenceBaseline` | () — last training episode | – | component outlook: persistence/no-change |
| announced_only | `AnnouncedOnlyBaseline` | unavailable: the card registers no announced-path series | – | component outlook: announced-only (abstains; no stand-in) |
| no_gap_zero_increment | `NoGapBaseline` | () — predicts 0 | – | remaining repricing: no-gap/zero-increment (T18 consumes it) |

The card's B3/B4/B5 are OLS forms. The existing cell-keyed runner cannot score a row-level
regression without editing `validation.py`, which is protected. T15 therefore fits them as
partition means over origin-known sign/bucket keys. This is a declared deviation. B2
(net-liquidity regime) and B5 (lagged peer factor) need inputs with unproven rights; they are
listed under the empirical disposition below.

## 4. Paired population (C27) and LTIFO (C26)

Fixture C26 panel: n_rows 240, n_shocks 80, n_episodes_effective 40. Candidate, DirectFunding
and the LTIFO-masked DirectFunding run on one walk-forward plan. `restrict_to_common` keeps only
the common keys:

| Fold | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Paired keys | 4 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 5 | 59 |

- Dropped to reach the common population: candidate 1, direct_funding 0, direct_funding_ltifo 1.
- Coverage: 59/60, so the comparison is sufficient.
- An asymmetry of one key is refused with `PopulationMismatch`
  (`test_c27_paired_population_refuses_one_key_asymmetry`).

LTIFO definition `glt_ltifo_sensitivity.v1`, `definition_hash`
`d4746b2ba92f23f16c51e9abae37e78a23a4a76f7342def3d42157171ba49c62`. The hash is recomputed from
the canonical JSON excluding the hash field. Families are broad_dollar, real_yield_10y,
high_yield_oas and cb_balance_sheet. `spy` maps to no family, so its LTIFO mask is empty, which
matches the card's B5 note that LTIFO is not applicable to spy. The status is sensitivity only.

## 5. Increment versus direct_funding (C26) — negative result

- Natural judge (`engine.validation`) is not importable in this repository (ModuleNotFoundError).
  The increment is therefore withheld with the exact text:
  `StatisticalDependencyUnavailable: engine.validation.newey_west_tstat is required for incremental scoring`.
  Status `novelty_withheld`, p_value `None`. No p-value is fabricated.
- FDR across paths abstains with:
  `StatisticalDependencyUnavailable: engine.validation.benjamini_hochberg is required for W-LIQ.3 FDR`.
- Test stand-in judge (a fixture t-test, **not** HAC and not the card's test), reported only to
  show that the disposition logic works:
  - candidate vs direct_funding: MSE improvement 1.06499e-06, p 0.483701 → `novelty_withheld`.
    **Result: no gain over direct_funding.** On a dollar-sensitive target the candidate carries
    no information beyond the funding legs it already contains. This is reported as a result.
  - candidate vs LTIFO-masked direct_funding: improvement 8.03501e-05, p 6.5e-07 →
    `novelty_admissible_for_review`. This only shows that masking the target's own family makes
    the comparator weaker. It is not novelty.
- Fixture MSE: candidate 3.26932e-05, direct_funding 3.37582e-05, LTIFO-masked 1.13043e-04.

## 6. Response path (T16)

The fit uses one walk-forward plan purged at h60 (purge 60) and reused across horizons. 18
challenger trials were charged against the card budget, leaving 36 of 54. Trial n+1 past the
budget raises `SearchBudgetExceeded`.

Fixture out-of-sample MSE at h20:

| Model | M1 prior0 | M1 prior5 | M1 prior20 | Local projection | Pooled | State-conditioned prior5 |
| --- | --- | --- | --- | --- | --- | --- |
| OOS MSE | 2.24779e-05 | 2.24457e-05 | 2.23229e-05 | 1.92777e-05 | 2.24779e-05 | 2.24457e-05 |

On v1 the pooled challenger is identical to M1_prior0, and the state-conditioned challenger is
identical to the incumbent: the card declares no condition keys, so `condition_bucket` is
"all". The local projection uses only the declared shock size and supplies no exogeneity (S31).
Paths are in-sample descriptions; skill comes only from the walk-forward scores.

### Dependence design (C28): rows are never episodes

| Panel | n_rows | n_shocks | n_episodes_effective |
| --- | --- | --- | --- |
| C28 fixture (4 shocks × 2 targets × 5 horizons) | 40 | 4 | 3 |
| C26 fixture | 240 | 80 | 40 |
| Response-path fixture, spy h20 band | 126 | 42 | 28 |

Overlapping shocks within the 60-session purge share one block. In C28, shocks 0 and 1 are 10
sessions apart and form `episode:2010-03-02` (20 rows). They count once, never twice.

### Both bands at h20, side by side (C29)

spy, direction +1, n_rows 126, n_shocks 42, n_episodes_effective 28, level 0.90. Episode-block
studentised bootstrap with deterministic seed. Point estimate 0.0026625.

| Band | Lower | Upper | Critical value | Certifies a path |
| --- | --- | --- | --- | --- |
| pointwise | 0.00144019 | 0.00388481 | 1.64826 | no |
| simultaneous (sup-t) | 0.00111289 | 0.00421211 | 2.08962 | yes |

The simultaneous band contains the pointwise band at every horizon in the grid
(`test_c29_simultaneous_band_contains_the_pointwise_band_at_every_horizon`).

### Response-time functional

- As declared by the card: **unavailable**. Reason: "the frozen card declares no response-time
  functional (horizons carry unit/candidates/primary/sensitivity only); no response time is
  estimated".
- Fixture demonstration only:
  - peak with the simultaneous band → `supported_region` over candidates [5, 20, 60], (0, open];
  - time-to-0.5-fraction → interval (0, 60];
  - peak with the pointwise band → `unavailable` (C29: a pointwise band cannot certify a
    functional).
- The output is never a single session.

### Delay-cost sensitivity (measurement table, not a recommendation)

M1 prior5, spy, direction +1. Path points h5/h20/h60 = 0.0021025 / 0.00301484 / 0.00487934.

| Delay k | Horizon H | Remaining response | Share of path |
| --- | --- | --- | --- |
| 0 | 5 | 0.002103 | 1.000 |
| 0 | 20 | 0.003015 | 1.000 |
| 0 | 60 | 0.004879 | 1.000 |
| 1 | 5 | 0.001682 | 0.800 |
| 1 | 20 | 0.002594 | 0.861 |
| 1 | 60 | 0.004459 | 0.914 |
| 5 | 20 | 0.0009123 | 0.303 |
| 5 | 60 | 0.002777 | 0.569 |
| 10 | 20 | 0.0006082 | 0.202 |
| 10 | 60 | 0.002473 | 0.507 |
| 20 | 60 | 0.001865 | 0.382 |
| 40 | 60 | 0.0009323 | 0.191 |

### Era and episode influence (h20)

- Most influential block: `episode:2008-05-13` (shock `liq_2008-05-12_glt_composite_0003`).
- Maximum single-episode share: 0.099.
- Most influential era: 2008; era concentration 0.188.
- n_episodes_effective 28.
- Default eras are calendar years. A declared era map is supported.

## 7. CONTRACTS §5 projection

The projection has exactly the 22 §5 fields, in §5 order. Fixture spy h20 values:

- effect_estimate 0.00301484; uncertainty_kind `simultaneous`; `path_claim_allowed` true.
- independent_episode_count 28; target support 42 and borrowed prior support 5, kept separately
  visible.
- identification_status `NOT_IDENTIFIED`; evidence_tier `research_measurement_only`.
- baseline_comparison: abstained, with the HAC SDU text.
- protocol `walk_forward_one_plan_purge60@da060bf4`.

A null cell carries no effect_estimate, no band, and an abstention_reason. A cell is null when
the most conservative independent count — min(cell effective_n, band purged episodes) — falls
below min_effective_n 10.

## 8. Window guard and ledger

| Run | Rows in | Admitted | Refused |
| --- | --- | --- | --- |
| C26 fixture | 240 | 240 | 0 |
| C28 fixture | 40 | 40 | 0 |
| response-path fixture | 480 | 480 | 0 |
| synthetic reserved probe | 3 | 2 | 1 (`reserved_window`: 1) |

ForwardLedger: 0 records, 0 grades. There were zero looks.

## 9. Empirical disposition (train/dev)

`validate_card` on the frozen card returns these codes:

- `BLANK_RIGHTS:fx_eurusd`
- `BLANK_RIGHTS:fx_usdjpy`
- `BLANK_RIGHTS:spy_total_return_bars`
- `BLANK_RIGHTS:peer_etf_bars_efa_eem_hyg`
- `UNCOVERED_CALENDAR:train`
- `UNCOVERED_CALENDAR:dev`
- `UNCOVERED_CALENDAR:reserved`

No empirical cell was run.

| Cell | Window | Disposition |
| --- | --- | --- |
| M1 prior0/5/20 × h5/h20/h60 (outcome y) | train, dev | `BLOCKED:BLANK_RIGHTS:spy_total_return_bars; UNCOVERED_CALENDAR:<window>` |
| Event calendar (T11 composite episodes) | train, dev | `BLOCKED:BLANK_RIGHTS:fx_eurusd; BLANK_RIGHTS:fx_usdjpy` (ECB/BOJ USD conversion legs) |
| B1 unconditional, B3 context, B6 lower-complexity | train, dev | `BLOCKED:BLANK_RIGHTS:spy_total_return_bars; UNCOVERED_CALENDAR:<window>` |
| B2 current regime | train, dev | `BLOCKED:BLANK_RIGHTS:spy_total_return_bars; UNCOVERED_CALENDAR:<window>` |
| B4 direct component / direct_funding | train, dev | `BLOCKED:BLANK_RIGHTS:spy_total_return_bars; UNCOVERED_CALENDAR:<window>` |
| B5 lagged common risk factor | train, dev | `BLOCKED:BLANK_RIGHTS:peer_etf_bars_efa_eem_hyg; BLANK_RIGHTS:spy_total_return_bars` |
| Bands, influence, delay table, §5 projection | train, dev | `BLOCKED:` all of the above (no empirical path exists) |
| Anything in the reserved window | reserved | out of scope (no read; WindowGuard refuses) |

## 10. Declared deviations

- B3/B4/B5 are fitted as partition means, not OLS. B1 is an event-row proxy.
- DirectFunding is the B4 funding subset (DTWEXBGS, DFII10). HY OAS is excluded because it is
  UNPROVEN and not in B4.
- WindowGuard implements T13 counting.
- One plan, purged at h60, is reused across horizons.
- Challenger trials count against the card's 54.
- The pooled challenger equals M1_prior0 on v1. The state-conditioned challenger equals the
  incumbent on v1.
- The local projection is binned.
- The bootstrap keeps only complete draws.
- The card declares no functional, so the functional is unavailable.
- `engine.validation` is absent, so the HAC test and FDR abstain.
- `validate_card` returns 7 codes, not the empty tuple the packet assumed.
- `identification_status` carries the card's treatment status NOT_IDENTIFIED. The estimand-level
  `association_only` is carried in identification_assumptions.

Nothing here is validated. Evidence tier is retrospective train/dev predictive measurement at
most, and in this PR only fixture evidence exists.
