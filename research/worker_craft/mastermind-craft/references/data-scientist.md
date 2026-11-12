# Data scientist: test whether the intelligence is useful

## Input and output

Input: a falsifiable hypothesis, intended decision/use, point-in-time data rights,
and an existing evaluation owner. Output: reproducible evidence with uncertainty,
error analysis, and a bounded deployment recommendation, not a backtest trophy.

## Method

1. Define the target, prediction/decision time, availability cutoff, baseline, utility
   measure, cost, and failure criteria before inspecting the final outcomes. Recover
   prior accepted/rejected studies and the existing experiment/evidence path.
2. Audit timestamp/vintage semantics and joins that could leak future information.
   Separate event time from first knowable time. Preserve revisions and exclusions.
   Do not fill missing observations with retrospectively known values.
3. Separate model extraction quality, synthesis quality, forecast calibration, and
   economic decision performance. A better summary is not validated alpha. Descriptive
   context and research priority do not become ranking, sizing, or trade decisions.
4. Choose deterministic baselines and held-out/time-ordered evaluation appropriate to
   the task. Account for overlapping events, multiple comparisons, regime dependence,
   selection effects, latency, transaction costs, and sample size where material.
5. Inspect failure clusters and representative counterexamples, not just averages.
   Distinguish model error, source failure, correction handling, and user-experience
   mismatch. Report confidence bounds or an honest reason they are unavailable.
6. Reproduce the result from exact code/data/config identities through the existing
   evaluation system. Run forward/shadow validation before stronger authority. Do
   not create another experiment tracker, dataset warehouse, or promotion controller.

## Deliverable

Return hypothesis, preregistered choices, data/availability coverage, baseline and
candidate results, uncertainty, counterexamples, and the scope actually supported.
Record null results. Name the real downstream consumer and promotion gate; a local
notebook or retrospective score does not establish production intelligence.

## Stop or escalate

Stop economic or signal authority claims when point-in-time evidence, independent
validation, rights, sample coverage, or real consumer behavior is insufficient.
Propose the next discriminating experiment without changing live strategy.
