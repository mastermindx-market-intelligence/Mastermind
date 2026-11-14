# Phase-neutral early-turn challenger: executed source-robustness follow-up

This is an outcome-guided experiment after the original bar-alignment sensitivity was observed. It does not replace or rename native G0, tune an anchor to returns, or turn correlated oscillator observations into independent confidence votes. All144 account variants and the54-comparison diagnostic family are preserved.

## Construction

Compute the same settled native grey-dot math on each of the three fixed dataset-anchored three-day grids. Compare any-phase onset, at least two distinct phases within six sessions, and all three distinct phases within six sessions. Confirmation is observed on its actual later session and enters at the next close; it is never backdated to the earliest dot. Context selects those pre-existing confirmation onsets. The same market-repair and receding-new-low conditions,21/63-session holds and5/20bp costs remain. This removes choosing one lucky three-day phase, not every possible dependence on input history, the two-day grid or source version.

## All-three-phase confirmation plus market repair

The following is the21-session,5bp-per-side counterfactual. Exposure is low, the newer era is only360 sessions, and the result is not risk-matched to a fully invested ETF.

| Era | CAGR | Sharpe | Maximum close drawdown | Mean exposure | Closed trades |
|---|---:|---:|---:|---:|---:|
| 2001_2006 | 2.40% | 0.466 | -9.97% | 16.55% | 107 |
| 2007_2019 | 3.24% | 0.659 | -7.01% | 16.08% | 225 |
| post_reset | 6.58% | 2.110 | -1.70% | 10.99% | 17 |

All-three confirmation with repair was profitable at the tested5bp and20bp costs in all three disclosed eras. This does not mean every phase-neutral construction worked: the earlier any-phase repair/pressure variants lost money, and two-phase confirmation had materially worse earlier drawdowns. The full matrix, not only this interesting row, is retained.

At20bp per side, all-three-plus-repair21-session CAGRs were1.79%,2.65% and6.14% in the three eras above. These are historical point estimates, not net live performance. At63 sessions, the corresponding5bp CAGRs were2.65%,5.01% and7.77%, with materially different exposure and only11 closed trades in the recent segment.

## Confirmation price and coverage

| Era | Matched confirmations | Median extra sessions | Mean extra sessions | Median entry-price increase | Mean entry-price increase |
|---|---:|---:|---:|---:|---:|
| 2001_2006 | 125 | 2.0 | 2.63 | 0.65% | 1.23% |
| 2007_2019 | 249 | 2.0 | 2.49 | 0.66% | 0.77% |
| post_reset | 19 | 2.0 | 2.58 | 0.68% | 0.65% |

This compares confirmation with the earliest of the most recent contributing phase dots inside the six-session window, using next-close prices for both. It conditions on eventual confirmation; it is NOT the average cost or success rate of all raw dots. The local team's reported nine-session lead uses a different population and cannot be subtracted from these numbers.

## Does a cash-matched baseline explain it?

The comparator is an equal initial-capital mixture of the three original phase portfolios with the same market-repair context. A hindsight static cash mixture matches the challenger's mean exposure. In2001-2006 its21-session CAGR/Sharpe/drawdown were0.82%/.217/-12.37%, versus2.40%/.466/-9.97% for all-phase confirmation. In2007-2019 the matched comparator earned2.67%,Sharpe.716,drawdown-7.58%, versus3.24%,.659,-7.01% for confirmation: higher return did not mean better Sharpe. Recently the matched comparator earned2.75%,Sharpe1.398,drawdown-1.37%, versus6.58%,2.110,-1.70% for confirmation: the challenger had a deeper drawdown despite higher return.

None of the54 mean-return comparisons against equal-phase portfolios survived the full Holm correction. The recent21-session all-phase-plus-repair contrast was favorable pointwise but did not survive that full family. These are post-development exploratory diagnostics, not an independent validation sample or correction for the entire program's previous strategy search.

## Decision

Retain all-phase confirmation plus market repair as a separately named forward challenger, together with the native dot, T1/T2 and equal-phase controls. It addresses an actual measurement fragility and has a measurable confirmation cost. It is not a universal replacement, a guaranteed bottom detector, or a proven all-objective winner. No new threshold or model was selected to repair the adverse cells. The implementation is invariant to permutation of the three phase labels and to appending future observations in the tested prefix checks; it does not claim invariance to all data-vintage or history-start changes.

The extended suite passed72 tests. Original phase-account curves remained unchanged to4.44e-16 maximum observed equity difference. No live gate, ranking, sizing, order, recurring service or source emitter was modified.
