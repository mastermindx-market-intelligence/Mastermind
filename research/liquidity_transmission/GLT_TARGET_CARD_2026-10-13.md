# GLT broad target card V1 (T12)

Module: `brain/liquidity_lab/target_card.py` (`BROAD_TARGET_CARD_V1`, card version
`glt_broad_target_card.v1`). Tests: `tests/test_liquidity_lab_target_card.py`.

## Status

- Frozen 2026-10-13. The freeze date is supplied by the caller (`build_broad_target_card(frozen_at=...)`);
  the module reads no wall clock.
- Freeze hash. `BROAD_TARGET_CARD_V1_SHA256 = f53d9296ae1556544a0d55d1a3d742bbc169138c0ae04b5a458ceb6eaf3c5537`
  is the canonical SHA-256 of `BROAD_TARGET_CARD_V1.to_dict()` (sorted keys, no whitespace).
  `build_broad_target_card` refuses any `frozen_at` other than 2026-10-13 under v1 and refuses a
  build whose content hash differs, so a registry edit cannot silently yield a different card still
  labelled `glt_broad_target_card.v1`; it must mint v2. (T13 hardening, carried from the #1444 review.)
- `validated=False`, always. The card is an outcome ruler fixed before any outcome is read, not a result.
- Horizons are planning roles only until T14 fixes the primary.
- Additive. It sits beside `TARGETS` / `TARGET_BY_ID` in `brain/liquidity_lab/contracts.py`,
  copies their identity fields, and mutates nothing there.
- Reads no prices. It changes no estimator behaviour: `build_forward_return_panel` is untouched.
- CONTRACTS §5 (the later additive read projection) is not pre-empted. The card is a declaration
  that future outcome code consumes, not a read surface.

## The card

| target_id | symbol | asset_class | benchmark | default basis | allowed bases | underlying-holiday note |
|---|---|---|---|---|---|---|
| spy | SPY | us_equity | — | total_return | price, total_return | — |
| qqq | QQQ | us_equity | spy | total_return | price, total_return, excess_vs_benchmark | — |
| smh | SMH | us_equity | spy | total_return | price, total_return, excess_vs_benchmark | — |
| igv | IGV | us_equity | spy | total_return | price, total_return, excess_vs_benchmark | — |
| iwm | IWM | us_equity | spy | total_return | price, total_return, excess_vs_benchmark | — |
| tlt | TLT | rates | — | total_return | price, total_return | — |
| hyg | HYG | credit | — | total_return | price, total_return | — |
| lqd | LQD | credit | — | total_return | price, total_return | — |
| gld | GLD | commodity | — | total_return | price, total_return | — |
| slv | SLV | commodity | — | total_return | price, total_return | — |
| dbc | DBC | commodity | — | total_return | price, total_return | — |
| uso | USO | commodity | — | total_return | price, total_return | — |
| cper | CPER | commodity | — | total_return | price, total_return | — |
| efa | EFA | dm_equity | spy | total_return | price, total_return, excess_vs_benchmark | yes |
| eem | EEM | em_equity | spy | total_return | price, total_return, excess_vs_benchmark | yes |
| fxi | FXI | china_equity | eem | total_return | price, total_return, excess_vs_benchmark | yes |
| mchi | MCHI | china_equity | eem | total_return | price, total_return, excess_vs_benchmark | yes |
| kweb | KWEB | china_equity | mchi | total_return | price, total_return, excess_vs_benchmark | yes |

Every entry also has:
- quote currency `USD`;
- session calendar `us_equity_sessions`;
- anchor price `official_close`.

Every declared benchmark is itself a card entry; the build refuses otherwise.

## Exclusions

- `btc`: the crypto motivating example. Its motivation is archived per SCIENCE_PROTOCOL §9 and
  acceptance C22, and there is no new crypto programme. `crypto` is also deliberately unruled in
  `BASIS_RULINGS`, so if any eligible crypto entry appeared, the build would fail closed.
- `baba`: the single-name motivating example, archived per SCIENCE_PROTOCOL §9 and acceptance C22.
  It is excluded both by role (`single_name`) and by name.
- Any registry role other than `macro_proxy` is excluded by role, whatever its name.
  `card.entry(<excluded id>)` raises `ContractError` and names the reason.

## Basis choices

The default is `total_return` for every ruled asset class. `BASIS_RULINGS` holds the rationale for each:

- **us_equity**: dividends are part of holder return, and ex-dividend price drops are not economic moves.
- **dm_equity / em_equity / china_equity**: the same equity rationale, measured in USD as listed,
  with no FX or local-currency translation.
- **rates**: bond funds pay monthly distributions. A yield change in basis points is not a fund return.
  - `validate_return_basis("tlt", "yield_change_bp")` is refused.
  - A rates *view* expressed in bp is a different object from the TLT holder's outcome.
- **credit**: high-yield and investment-grade funds pay monthly distributions that are most of their return.
- **commodity**: for non-distributing commodity trusts, total return equals price. For funds that pay
  distributions, total return captures them.

Further rules:

- **FX inversion and local currency are not bases here.** Every entry is a US-listed, USD-quoted fund.
  - A basis naming FX, an inversion or local currency is refused for every entry.
  - Examples: `fx_inverted_usdhkd` for FXI and `USDCNH_inverse` for MCHI.
  - Local-currency returns and FX returns are separate outcomes, and this card does not define them.
- **excess_vs_benchmark** is allowed only where the registry declares a benchmark.
  - It is defined as the entry's total return minus the benchmark's total return over the same
    declared-calendar sessions (same anchor session, same exit session).
  - It is refused, with "no declared benchmark", for spy, tlt, hyg, lqd and the commodities.
- **price** is allowed only as a declared sensitivity. It is never the default and never a silent substitute.

## Session calendar, anchor and maturity

- Calendar: `us_equity_sessions`, owned by `portfolio.market_calendar.is_trading_day` and imported lazily.
  - Coverage runs 2025-01-01..2027-12-31.
  - A date outside it raises `ContractError` ("outside declared calendar coverage") and is never guessed.
- **Underlying-holiday rule.** The underlying market's holidays are not US sessions. The five non-US
  equity entries are measured on US equity sessions only.
  - 2026-10-01 (PRC National Day) is an HKEX holiday but a US session, so it counts for FXI, MCHI and KWEB.
  - 2026-11-26 (US Thanksgiving) is never a session.
- **ANCHOR_RULE**: the anchor is the official close of the first declared-calendar session strictly
  after the first-detection calendar date.
  - Example: a detection on Friday 2026-09-04 anchors on Tuesday 2026-09-08, because Monday 2026-09-07
    is Labor Day.
- **MATURITY_RULE**: an outcome at horizon h is mature only when the official close of the h-th
  declared-calendar session after the anchor session is available as of the evaluation clock.
  - A missing close keeps the outcome immature and never shifts the horizon to a later session.
  - Example: anchor 2026-09-08, h=5, exit 2026-09-15. With closes for 9/9..9/14 plus 9/16 and 9/17,
    the outcome is still immature.

## Horizon roles

- Planning candidates are 5, 20 and 60 sessions, drawn from `HORIZONS_BDAYS` = (1, 5, 10, 20, 40, 60, 90, 120).
- `primary` is `None` until T14 fixes it.
- Nothing in this card ranks, selects or promotes a horizon.

## Acceptance map

- **C21**: each target uses its actual return basis and its own session/maturity rule.
  - `test_tlt_yield_change_in_basis_points_is_not_a_fund_return`
  - `test_fx_quote_or_inversion_is_not_a_return_basis`
  - `test_underlying_market_holiday_is_still_a_us_session`
  - `test_calendar_helpers_anchor_count_and_refuse_outside_coverage`
  - `test_missing_exit_close_keeps_outcome_immature_and_never_shifts`
- **C22**: BTC and single-name motivating examples stay archived and excluded.
  - `test_btc_baba_and_non_macro_proxy_roles_are_excluded`

Supporting tests:
- `test_card_entries_are_the_eighteen_macro_proxies_in_registry_order`
- `test_building_the_card_never_mutates_the_registry`
- `test_horizon_roles_are_planning_only_and_card_is_not_validated`
- `test_card_and_entries_are_immutable`
- `test_frozen_at_is_caller_supplied_and_build_is_deterministic`
- `test_excess_vs_benchmark_only_where_a_benchmark_is_declared`
- `test_every_entry_defaults_to_its_ruled_total_return_basis`
- `test_unruled_asset_class_fails_closed`
- `test_card_module_reads_no_prices_and_no_clock`
- `test_estimator_horizons_are_the_untouched_contracts_constant`
- `test_registry_field_drift_cannot_stay_labelled_v1`

## GAPS

- **Calendar coverage.** The calendar owner covers 2025–2027 only. Outcomes beyond 2027-12-31
  need the owner's holiday table extended first; the card refuses rather than guesses.
- **Estimator vs card session counting.** The estimator anchors on the first *supplied* close after
  detection and counts *supplied* closes. The card counts *declared-calendar* sessions. These agree
  only when the supplied series has no missing sessions. T13 owns the reconciliation; until then,
  estimator horizons are not card horizons.
- **Total-return data.** Whether a total-return series is available for each fund, and under what
  rights, is T13's question. The card declares the basis but supplies no data.
- **No FX outcome.** The card defines no local-currency or FX outcome. If one is ever wanted, it is a
  separate outcome family with its own card.
