# C19 G12 — WP06 / WP07 / WP11 producer→reader→page traces, verified on BASE

Seat: Fable CEO, C19 (session 7ab343c8). Dated 2026-10-19, 05:5xZ.
Closes the C19 half of gap G12 in `research/C19_WP21_P0_DECISION_2026_10_17.md` ("traces taken on trust by the reviewer"; owner split: C19 for the traces, the composer owner for any composer leg). This document verifies the traces. It builds no composer leg (seat decision D1, 2026-10-19).
Source: read-only census lane K3 `c19-w6s-g12-traces-census-minimax-20261019` (ubuntu1, MiniMax-M3, census class), BASE `80f270c44bcdf11f5e71dacc05b11a0875a01d7f`, sentinel `C19-W6S-G12-TRACE: PARTIAL 80f270c44bcd` (rc 0, 2026-10-19T05:05:50Z), worktree clean at exit. The WP06 and WP11 traces are the lane's, seat-verified by spot-checking the cited lines on BASE; the WP07 trace is the seat's own (the lane traced the wrong modules — Q2). No ledger row value, outcome, budget, price or label was printed by the lane or the seat.

## Q0 — where the WP21 census wrote the trace rows

The lane searched macro BASE for the WP21 decision document and found it absent, with bounds: `git ls-files | grep -iE "WP21|commission_19_fable|C19_WP21"` → 0; `git ls-files | grep -iE "masterplan.*c19|c19.*masterplan|commission_19_fable_masterplan"` → 0; `git grep -l "WP21"` → 0; `grep -rln "G12" --include=*.md` → only `config/signal_foundry_blocklist.yml`, whose hits are the blocklist ids `BL-G120/BL-G121/BL-G122`; `grep -rln "Q1 trace"` → 0.

Seat disposition: the absence is correct and expected. `research/C19_WP21_P0_DECISION_2026_10_17.md` and `research/commission_19_fable_masterplan/` live in the **Mastermind** repository (master `research/`), not in macro; the seat's frozen K3 spec named the wrong repository for Q0. The G12 row is therefore cited from Mastermind, and the three traces below are recovered from the macro code on BASE — which is the evidence G12 asked for in the first place.

## Q1 — WP06 durable trial accounting: writer → readers → where the chain ends

| Hop | file:line | symbol |
|---|---|---|
| Writer module | `engine/trial_ledger.py:25` | module docstring (`"""Trial Ledger …"""`) |
| Writer path | `engine/trial_ledger.py:54` | `DEFAULT_PATH = Path("data") / "trial_ledger.jsonl"` |
| Writer method | `engine/trial_ledger.py:593` | `def log_declared_budget(self, n, *, family, …)` |
| Writer context manager | `engine/trial_ledger.py:694` | `class register_trials:` |
| Reader import | `engine/calibration_hub.py:25` | `from engine.trial_ledger import TrialLedger` |
| Reader roll-up | `engine/calibration_hub.py:431` | `def _trial_ledger_summary(root: Path)` |
| Reader instantiation | `engine/calibration_hub.py:434` | `TrialLedger(Path(root).joinpath("data", "trial_ledger.jsonl"))` |
| Page render | `engine/calibration_hub.py:537` | `def render_html(s)` |
| Entry point | `engine/calibration_hub.py:641` | `def run(root=None, persist=True)` |
| Persist JSON | `engine/calibration_hub.py:649` | `(out / "summary.json").write_text(...)` |
| Persist page | `engine/calibration_hub.py:652` | `write_page(site / "calibration.html", render_html(s))` |

Ends at `site/calibration.html` (+ `data/calibration/summary.json`; the module docstring at `engine/calibration_hub.py:14` names both). The lane's sparse worktree did not materialize `site/`; the page end is the producer's write call, not an inspection of the rendered file. `data/trial_ledger.jsonl` was named, never opened.

## Q2 — WP07 evaluation primitives: `engine/validation.py` → readers → site/JSON pages (seat trace)

**What the lane did.** It read "evaluation primitives and admission" as the quant-assessment research modules Q01–Q20 (`engine/options_arbfree_surface.py:1`, `engine/offexchange_share_basis.py:5`, `engine/options_execution_sensitivity.py:7`, …, each self-declared "RESEARCH REFERENCE — NOT WIRED") and the admission modules `engine/research_codegen/admission.py:1` and `engine/k3e_eval_admission.py:1`, and concluded "no wired chain" with `git ls-files | grep c19_wp07` → 0. Both statements are true of those modules and say nothing about WP07, which shipped as fixes inside an existing module rather than as a new file. Lane verdict on this question: misidentified; the seat cured it by tracing the package itself instead of opening a repair round (the trace is read-only and the seat already held the tree).

**WP07 is `engine/validation.py`** (Macro #8858 `9b86baae61cc`: `_maxdd` counts the initial loss, `vif` abstains on a rank-deficient design; #9155 `cfcb840a3702`: non-anticipating impact-cost sigma warmup in `backtest_core`). Traced by the seat on BASE `80f270c44bcd` in the closure tree:

| Hop | file:line | symbol |
|---|---|---|
| Producer | `engine/validation.py:36` | `def backtest_core(...)` (#9155 warmup) |
| Producer (private) | `engine/validation.py:447` | `def _maxdd(...)` (#8858); consumed by `block_bootstrap_ci` (`:455`, call `:475`) and `_calmar` (`:483`, call `:492`); `paired_delta_ci` `:496` |
| Producer | `engine/validation.py:638` | `def vif(...)` (#8858); `design_rank` `:658` |
| Reader A import | `engine/equity_alloc.py:22` | `from engine.validation import backtest_core, block_bootstrap_ci` |
| Reader A call | `engine/equity_alloc.py:118` | `bt = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=cash_yield)` inside `summarize` (`:112`) |
| Reader A call | `engine/equity_alloc.py:120` | `nocarry = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=None)["net"]` |
| Page builder import | `scripts/build_spvector.py:31` | `from engine import equity_alloc as ea` |
| Page builder calls | `scripts/build_spvector.py:178-179` | `alloc = ea.vector_alloc(...)`; `sc = ea.summarize(spy, alloc, "Vector", cash_yield=bills, cost_bps=COST_BPS, bootstrap=True)` (also `:183` after-tax, `:260` `bear_episodes`) |
| Page write | `scripts/build_spvector.py:318` | `write_page(out, html)` → `site/spvector.html` (docstring `:3`); `:329` `spvector_latest.json` |
| Reader B import | `engine/factor_orthogonal.py:24` | `from engine.validation import top_correlated_pairs, vif` |
| Reader B call | `engine/factor_orthogonal.py:86` | `"vif": vif(Z)` inside `overlap_diagnostics` (`:71`; `orthogonal_composite` `:61`) |
| Report builder | `scripts/factor_ic_scorecard.py:41` | imports `overlap_diagnostics` |
| Report call | `scripts/factor_ic_scorecard.py:197` | `coll = overlap_diagnostics(legs)` |
| Report write | `scripts/factor_ic_scorecard.py:246` | `(outdir / fname).write_text(json.dumps(report, indent=2, default=str))` — the factor IC scorecard JSON |

Ends at `site/spvector.html` (+ `spvector_latest.json`) and the factor IC scorecard JSON report. Other BASE readers of `backtest_core`, not traced to a page here: `engine/forex_scorecards.py:26/:152`, `engine/meta_label.py:43/:298`, `engine/lab.py:641`, `engine/signal_foundry/harness.py:252/:510/:577`, `engine/strategies.py:31`, `engine/masterminds.py:33`, `engine/active_commodity.py:30`, `engine/china_allocation.py:33-34` (`bear_episodes`, `block_bootstrap_ci`), `scripts/build_strategies.py:34`, `scripts/build_site.py:4537`, `scripts/turn_of_month_phase0.py` (research), the `calibrate_spvector*` / `calibrate_tactical` scripts; of `vif`: `scripts/stock_conviction_phase0.py:67`, `engine/meta_label.py:504`, `engine/lab.py:906`.

## Q3 — WP11 MRI producer/reader compatibility: → reader → site page

| Hop | file:line | symbol |
|---|---|---|
| Producer | `scripts/build_release_forecast.py` (named at `engine/event_window.py:524-525`) | writes the `release_forecast.v2` artifact |
| Producer path 1 | `engine/event_window.py:484` | `config.ROOT / "data" / "release_forecast" / "latest.json"` |
| Producer path 2 | `engine/event_window.py:485` | `config.ROOT / "site" / "macrodata" / "release_forecast.json"` |
| Reader paths | `engine/event_window.py:481` | `def _mri_release_forecast_paths()` |
| Reader | `engine/event_window.py:514` | `def _read_mri_surprise_dispersion(release_type, today=None, *, paths=None, now=None)` |
| Schema gate | `engine/event_window.py:574-575` | `payload["schema"].startswith("release_forecast.v2") and isinstance(payload.get("upcoming"), list)` |
| Parallel reader | `engine/release_market_context.py:1`, `:605` | MRI PR-I display-only enrichments; `def compute_expectation_read(...)` |
| Consumer | `engine/event_window.py:697`, `:721` | `def ex_ante_read(...)`; `mri = _read_mri_surprise_dispersion(release_type, today=today)` |
| Site builder | `scripts/build_event_windows.py:10` (docstring), `:252` | `snap_path.write_text(json.dumps(snap, ..., default=float))` → `site/event_windows/snapshot.json` |

Compatibility dimensions: release target — exact-type map, never prefix (`engine/event_window.py:528-529`, `_MRI_RELEASE_TYPE_MAP`); array element — nearest-future selection (`:533-536`; pinned by `tests/test_c19_wp11_reader_pins.py:65,82,91`); unit — `surprise_skew["sigma"]` standard unit, `sigma_scale_pp` carries the pp scale, `pred_spread_sigma = None` (`:540-545`); native sigma — `tests/test_c19_wp11_reader_pins.py:128` (`test_n5_sigma_surprise_comes_only_from_surprise_skew_sigma`). Ends at `site/event_windows/snapshot.json`; as with Q1, `site/` was not materialized and the page end is the producer's write call.

## Q4 — the composer negative claim (bounded)

- Lane, forward: `grep -n -i "trial_ledger\|TrialLedger\|register_trials\|mri\|admission\|calibration" app/integrated_answer.py` → three hits, all the exception class `FinancialQueryAdmissionError` (`:396`, `:463`, `:465` — `leg["degraded_reason"] = f"admission:{exc.status_code}"`), unrelated to any of the three producers. No `trial_ledger`, `TrialLedger`, `register_trials`, `mri` or `calibration` hit.
- Lane, reverse: `grep -rn "integrated_answer" engine/trial_ledger.py scripts/ engine/ --include=*.py` → 0.
- Seat, WP07: `grep -rn -E "engine\.validation|from engine import validation|import validation" engine/ scripts/ app/` on BASE → no hit under `app/` (`app/integrated_answer.py` included); every importer of `engine.validation` is an engine module or a site/calibration script.

Bounds: tracked `.py` files under `app/`, `engine/`, `scripts/` on BASE `80f270c44bcd`; name-based grep, not an import graph. Within those bounds the composer reads none of the three producers.

## Q5 — tests that assert each trace

| Trace | Tests on BASE |
|---|---|
| WP06 | `tests/test_calibration_hub.py` (line-1 docstring "the Trial Ledger roll-up"; e.g. `:46 test_cold_desk_when_sample_small`), `tests/test_trial_ledger.py`, `tests/test_trial_registration_lint.py` |
| WP07 | `tests/test_validation.py`: `:194 test_maxdd_counts_initial_loss_from_starting_capital`, `:199 test_maxdd_unchanged_when_first_return_is_gain`, `:209 test_maxdd_zero_for_monotone_gains_and_empty`, `:214 test_vif_singular_design_returns_empty`, `:222 test_vif_zero_variance_column_is_dropped_not_reported`, `:234 test_vif_full_rank_design_still_reports_values`, `:248 test_design_rank_reports_deficiency`, `:265 test_vif_never_returns_non_finite_values`, `:291 test_backtest_core_impact_sigma_warmup_is_non_anticipating`, `:310 test_backtest_core_impact_sigma_unchanged_once_window_fills` (seat) |
| WP11 | `tests/test_c19_wp11_reader_pins.py`: N1 `:59`; N2 `:65, :82, :91`; N3 `:98, :113, :118`; N4 `:163, :172, :177, :182, :195, :200`; N5 `:128, :140`; header docstring `:1-7` names both readers |

These assert the producers' contracts and (WP11) the reader's rules; none asserts the page write itself, which is a build-script effect covered by the site render, not by unit tests.

## Gaps and deviations reported by the lane

1. WP21 decision document not tracked on BASE — seat: expected, wrong repository in the spec (Q0); not a defect.
2. WP07 "cannot be followed wired end-to-end" — seat: lane misidentification; cured by the seat trace (Q2). Lane verdict: ACCEPT with this one defect, not REQUEST_REPAIR, because the cure is a read-only trace the seat already held and a second lane would only duplicate it.
3. `site/` and `data/` tracked but not materialized under the lane's sparse checkout — page-end paths come from producer code and docstrings; no rendered file or ledger row was opened. The seat's closure tree has the same cone and the seat did not open them either; G12 asks for the producer→reader→page chain, which the write calls establish.
4. No network beyond the SETUP `git fetch origin main`; `config/compiled_kill_registry.yml` not opened; no `data/trial_ledger.jsonl` rows displayed. DEVIATIONS: none; `git status --short` empty at exit.

## Disposition

- The three traces end where r1 said they end — WP06 at `site/calibration.html`, WP07 at `site/spvector.html` and the factor IC scorecard JSON, WP11 at `site/event_windows/snapshot.json` — now with file:line on BASE instead of trust.
- The composer leg for each (if any is ever wanted) is the composer owner's under `DEC:MI-BUILDOUT-I-ROUTE-WAITS-FOR-ALL-FOUR-LEGS`; C19 builds none.
