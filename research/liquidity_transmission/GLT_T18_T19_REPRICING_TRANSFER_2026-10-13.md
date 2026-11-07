# GLT T18 + T19 — remaining-repricing projection and regional transfer challenge

**Evidence tier:** research. **validated:** False. Nothing in this note or in the two modules
it describes is a trading signal, a size, or a forecast that a decision may consume.
The quantity `d(u)` is labelled **observed divergence from the reference path** everywhere.
Uncertainty in T18 and T19 is pointwise. Significance and multiplicity belong to T20.

| Task | Module | Tests | Frozen definition | definition_hash |
| --- | --- | --- | --- | --- |
| T18 | `brain/liquidity_lab/repricing.py` | `tests/test_liquidity_lab_repricing.py` | `research/liquidity_transmission/glt_repricing_rules.v1.json` | `026efcf4320973b6e76b45bffd4d7f1c0a88bb51b882d7e3c86ccdb90e68623f` |
| T19 | `brain/liquidity_lab/regional_transfer.py` | `tests/test_liquidity_lab_regional_transfer.py` | `research/liquidity_transmission/glt_transfer_cards.v1.json` | `032b8bbd21e7361e8ddb2d0ddfc811fd714f803fc1d12cb7e45068fa84fe465a` |

Both definitions bind:

- preregistration card hash `da060bf47e8eafc7e94d0cadbb4135c9207a069aad9eef3539ea9d62911d6aee`;
- broad target card `glt_broad_target_card.v1`, sha256 `f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537`.

Both definitions were committed to the branch before any lane ran a fit, in their own
first commit. Every loader recomputes the hash and refuses a mismatch.

## 1. T18 contract

`project` reads one issued `ForwardForecast` from `ForwardLedger` (`load_original_forecast`) and the
T16 `ResponsePath` that produced it. It requires the exact model and source binding, and
`m0(H)` equal to the forecast's expected return within 1e-12. It returns one
`RepricingProjection` with separate fields:

- `reference_path_discrepancy` = `d(u) = m0(u) - a(u)`. This is a diagnostic about the path
  already travelled. It has its own support record and is never an input to any other field.
- `remaining_response_estimate` = `g(u, H)`. It exists only when a remaining-interval
  qualification passes, and it is sealed against that qualification. The `m0(H) - a(u)`
  shortcut is unreachable. No code path derives `g` from `d`, and a forged object fails the seal.
- `percent_complete` = `a(u) / (a(u) + g(u, H))`. It is computed only when qualification passed
  and every withholding gate is clear. Otherwise it is null with a typed reason, using the
  frozen precedence: `expired` > `no_qualified_remainder` > `denominator_near_zero` >
  `sign_uncertain` > `not_economically_meaningful`. The two thresholds, 0.005 and 0.0025
  log return, were fixed from the units before any fit. The rules file records the rationale.
- Thesis status. `active` is the default. With caller-supplied invalidating information the
  status is `eliminated`: the remainder is null with `invalidated_by_new_information`, and the
  exit is unchanged. When the ledger already holds a `forecast_grade` row the status is
  `expired`. The exit `H` is immutable, so any other exit argument raises
  `HorizonExtensionError`, and an elapsed exit raises.
- Units: cumulative log total return in USD. `m0`, `a`, `d` and `g` share one basis. A mixed
  basis or currency is refused.

A read-only projection leaves the `ForwardLedger` file hash identical.
`append_projection` appends exactly one `forecast_repricing_update` row, with its own
`known_at`, and never rewrites the original forecast row.

## 2. T18 comparators

Qualification uses the paired out-of-sample MSE of remaining-interval log returns
`log(P_H / P_u)` on identical `(shock_id, target_id, horizon_bdays)` keys. It goes through
`PairedPopulation.require` over all four members, which needs at least 10 paired keys.
Every member's rows first pass `WindowGuard.admit(fold="dev")` built from the
preregistration card. Refused rows are counted and never enter a loss.

The candidate qualifies only if its MSE is at most 0.98 × the comparator MSE for **every**
comparator:

| Comparator | Definition |
| --- | --- |
| `no_gap` | `g = 0` for every remaining interval |
| `direct_state` | The T15 direct-observable rung refit at `u`. `model_version` must start with `glt_t15_component.v1` or `glt_t15_direct_funding.v1` and end with `@da060bf4`. |
| `original_fixed` | `g = m0(H) - m0(u)` from the T16 reference path |

If any comparator fails, the result is `no_incremental_support`. A candidate that only fits
the travelled path does not qualify. A negative qualified remainder is reported as negative
and is never inverted.

## 3. T19 transfer cards (one per T10 region)

`glt_transfer_cards.v1.json` was frozen before any fit. Its source is the T10 regional map,
`research/GLT_T10_REGIONAL_SCENARIO_MAP_2026-10-13.md` §2 in macro at `3ae40fd3`. T10's
`measurement_status` qualifies a region's central-bank balance-sheet input only. It does
not register a local-currency return series. T19 requires both.

| Region | T10 status | Local currency | Local series / calendar | Hierarchy members (registry) | FX rights |
| --- | --- | --- | --- | --- | --- |
| us | measured | USD | registered (US sessions) | spy, qqq, smh, igv, iwm, tlt, hyg, lqd (`us`) | not applicable |
| euro_area | measured | EUR | absent / absent | none | BLANK_RIGHTS (EURUSD=X) |
| japan | measured | JPY | absent / absent | none | BLANK_RIGHTS (USDJPY=X) |
| china | assumption_only_context | CNY | absent / absent | fxi, mchi, kweb (`china_hk`) | not registered |
| hong_kong | missing_input | HKD | absent / absent | fxi, mchi, kweb (`china_hk`) | not registered |

Every card fixes its holdout plan before any fit:

- evaluation horizon 20 sessions;
- local floor `effective_n` 10;
- margin 0.98;
- leave-country-out over every hierarchy member;
- leave-era-out over three eras, each ending before the reserved start 2022-01-03:
  `e1_2008_2013` (2008-01-04..2013-12-31), `e2_2014_2019` (2014-01-02..2019-12-31) and
  `e3_2020_2021` (2020-01-02..2021-12-31).

Hierarchy members are not a free list. They must equal the registry's own targets for the
card's registry region, and an excluded or unknown id raises `ExcludedRoleError` from the
registry check.

`qualify_transfer` statuses:

| Status | When |
| --- | --- |
| `missing_input` | The T10 status is not `measured`, or the local return series or local calendar is absent. Reasons name each `missing_owner`. No cell, mean, coverage, effective n or holdout is carried. There is no USD fallback and no US cell. |
| `abstain` | Outside the registered hierarchy; no registered hierarchy; local currency mismatch; local `effective_n` below the floor; a missing holdout; a holdout plan hash that differs from the card; or no pooled cell. |
| `pooled_only_borrowed` | A pooled member cell exists but local did not win both holdouts. `borrowed_prior_effective_n` (the pooled prior's support) is reported separately from `local_effective_n` and is never added to it. |
| `supported_local` | Only when local MSE ≤ 0.98 × pooled MSE on BOTH leave-country-out and leave-era-out, with at least 10 paired keys each, under the guard. |

Whenever a US cell or a USD-quoted local cell is offered as a non-US region's local cell, the
reason `copied_us_probability_refused` is named.

`decompose_returns` splits a USD return into a local-currency leg plus an FX translation
leg, with the log identity `usd = local + fx`. Fixings must be known at or before
`known_at`, otherwise it raises `FutureFixingError`. The fixing calendar and the date set
must equal the local sessions, otherwise it raises `CalendarMismatchError`; there is no
forward fill. A non-USD series without fixings is refused.

Decision choices beyond the cards' decision text, declared here:

1. A local `effective_n` below the floor abstains before the holdouts are read. The packet
   requires it; the cards' decision text is silent on it.
2. `local_effective_n` is the largest local cell `effective_n` at the evaluation horizon,
   never a sum across targets. `borrowed_prior_effective_n` is the largest
   `prior_effective_n` among usable pooled member cells.
3. A local-currency mismatch abstains rather than raising. A local calendar mismatch raises
   `CalendarMismatchError`.

## 4. Real-cell dispositions (this branch; no `data/` read, nothing at or after 2022-01-03)

| Cell | Disposition |
| --- | --- |
| T18, any issued forecast | `BLOCKED: no issued ForwardForecast in ForwardLedger with an unelapsed exit` (the lab ledger holds no T16 forecast to project) |
| T19 us | `BLOCKED: no committed pooled-without-region and local walk-forward holdout predictions for leave-country-out and leave-era-out at h=20` (the card is measured and complete; the inputs are absent) |
| T19 euro_area | `missing_input`: local_return_series_absent, local_calendar_absent, plus 3 missing owners (no euro-area local target in the registry, no calendar owner, EURUSD=X rights blank) |
| T19 japan | `missing_input`: local_return_series_absent, local_calendar_absent, plus 3 missing owners (no Japan local target, no calendar owner, USDJPY=X rights blank) |
| T19 china | `missing_input`: t10_status:assumption_only_context, local_return_series_absent, local_calendar_absent, plus 3 missing owners |
| T19 hong_kong | `missing_input`: t10_status:missing_input, local_return_series_absent, local_calendar_absent, plus 3 missing owners |

## 5. Case to test

| Case | Test |
| --- | --- |
| C31 separate fields and support | `test_c31_projection_carries_discrepancy_and_remainder_with_separate_support` |
| C31 shortcut unreachable | `test_c31_the_m0H_minus_a_u_shortcut_is_unreachable` |
| C32 near-zero denominator | `test_c32_near_zero_denominator_withholds_percent_complete` |
| C32 sign reversal | `test_c32_sign_reversal_between_reference_exit_and_remainder_is_sign_uncertain` |
| C32 exit elapsed / expired | `test_c32_exit_elapsed_raises_and_a_graded_forecast_is_expired` |
| C33 thesis eliminated | `test_c33_invalidating_information_eliminates_the_thesis_and_keeps_the_exit` |
| C33 horizon extension | `test_c33_a_later_exit_raises_horizon_extension` |
| Ledger read-only / one row | `test_read_only_projection_leaves_the_ledger_hash_identical`, `test_an_update_appends_exactly_one_row_and_never_rewrites_the_original` |
| C34 both holdouts required | `test_c34_missing_either_holdout_abstains_with_a_reason` |
| C34 future FX fixing | `test_c34_a_future_fx_fixing_raises_future_fixing_error` |
| C34 mixed calendar | `test_c34_a_mixed_calendar_join_raises_calendar_mismatch_error` |
| §9 missing_input carries no number | `test_missing_input_region_carries_no_cell_mean_or_probability` (4 regions) |
| §9 US cell as local | `test_a_us_cell_passed_as_local_is_refused_as_copied_us_probability` (4 regions) |
| Outside hierarchy | `test_a_region_outside_the_registered_hierarchy_abstains` |
| Borrowed kept separate | `test_pooled_only_borrowed_keeps_borrowed_support_separate` |
| C22 BTC/BABA | `test_c22_btc_and_baba_raise_excluded_role_error_from_the_registry` |
| Region independence | `test_changing_one_regions_inputs_cannot_change_another_regions_result` |

A mutation probe was run on the T19 module. All eleven seeded defects turned the T19 suite red:

- one holdout suffices;
- borrowed support summed into local;
- a future fixing survives;
- forward fill allowed;
- copied-US reason dropped;
- missing_input skipped;
- excluded role swallowed;
- floor ignored;
- outside hierarchy admitted;
- guard card unchecked;
- USD fallback.

## 6. Gaps

1. `ForwardLedger` has no public amendment method. The T18 update row is appended through
   the ledger's own locked append. This is a declared deviation, and the original row is
   never rewritten.
2. The registry raises `ContractError`, not a typed excluded-role error. T19 wraps
   `BROAD_TARGET_CARD_V1.entry` and re-raises `ExcludedRoleError` with the registry message
   as its cause.
3. `ForwardForecast` carries no source-state reference, return basis or currency. T18 binds
   these through the T16 path and the frozen units.
4. A T16 `model_version` containing `@` or `+` does not fit the ledger identifier grammar. It
   is mapped deterministically by `ledger_model_version`.
5. Coverage is missing in several places:
   - The registry has no euro-area, Japan, mainland-China or Hong Kong local-currency target.
   - There is no session calendar owner for those regions.
   - EURUSD=X and USDJPY=X rights are blank.
   - There is no CNY or HKD fixing series.
6. There is no `PooledChallenger` interface. Pooled cells are the
   `HierarchicalMeanCurveEstimator` / `PooledMeanBaseline` cells that the caller supplies.
7. There is no HAC significance in T18 or T19. T20 owns it.
8. The registry regions `dm_ex_us` (efa), `em` (eem) and `global` (gld, slv, dbc, uso, cper)
   have no T10 row, so they carry no transfer card in v1.

## 7. Challenges for T20 and T24

- T20 should test the T18 qualification margin and the T19 holdout wins for significance
  under the canonical HAC interface, with multiplicity across regions, horizons and comparators.
- T24 should feed real walk-forward holdout predictions for the `us` card first. A non-US
  region can leave `missing_input` only after its owners register a local return series, a
  calendar and FX rights.
- If a future region's local cells and pooled cells share targets, the leave-country-out
  fit must exclude the region from the pooled fit at the source. T19 can only check the held-out
  member set, not how the caller fitted the pooled model.
