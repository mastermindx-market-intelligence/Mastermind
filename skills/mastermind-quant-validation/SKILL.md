---
name: mastermind-quant-validation
description: Evaluate Mastermind predictive signals, backtests, event studies, Options Prophet models or factor experiments for point-in-time validity, leakage, overfitting, realistic costs and out-of-sample robustness. Use before claiming predictive utility or comparing research candidates. Do not use for basic descriptive arithmetic or as permission to rank securities, size positions or execute trades.
---

# Mastermind Quant Validation

## Work inside the current assignment

Reuse the verified Mastermind source pin and applicable repository instructions; do
not restart full bootstrap for each observation. This method supplies no runtime,
tool grant, release approval or trade authority. Keep denied actions denied and
EFFECT_UNKNOWN on the original operation and carrier. Continue independent safe
work instead of widening access or retrying an uncertain effect. Use existing
Executive/Fabric, Agent OS, source, browser and deployment owners, not replacements.

## Freeze the research contract

Identify the hypothesis, intended use, prediction horizon, label, universe,
benchmark, sampling cadence, decision cutoff and meaningful success criterion.
Record code/data/config revisions, random seed when applicable, candidate selection
history and held-out protocol. Use existing data and evaluation owners; do not
replace production computation or add a new signal authority.

Read [validation cases](references/cases.md) before accepting performance claims.

## Audit historical knowability

Bind point-in-time universe membership, delisted instruments, corporate actions,
publication lags, revisions, exchange calendar/timezone and missing-data policy.
Every feature must be available at the decision time; event time alone does not
prove availability. Separate price adjustment choices from what a strategy could
know then. Fail the dependent conclusion when required point-in-time inputs are
unavailable; do not silently use today's survivors or later-restated data.

## Separate selection from evaluation

1. Use time-respecting train/validation/test partitions or an appropriate
   prespecified event-study design. Explain why that design matches the dependence
   structure; random row splits usually cannot settle a temporal forecast claim.
2. Fit normalization, imputation, feature selection and hyperparameters on training
   data only. Keep validation for selection and untouched test for evaluation.
   Repeatedly selecting on the test turns it into validation; obtain a new holdout.
3. For overlapping label/information intervals, purge intersecting training
   observations; apply an embargo when the dependence/feature design requires it.
   Choose gaps from the information horizon, not a decorative universal percentage.
4. Walk forward using only the data available in each window. Report pooled and
   per-window results, regime/concentration sensitivity and unstable parameters.
   Retuning after each test result must be disclosed as another selection step.
5. Account for the number and dependence of tried candidates when interpreting
   significance. Use uncertainty estimates appropriate for serial correlation and
   small samples. Record the baseline and null/control comparisons.

## Test implementability and useful prediction

Include realistic commissions, bid/ask spread, slippage, turnover, borrow, latency,
liquidity/capacity and fill assumptions where relevant. Do not grant fills at
prices observed only after a signal. Compare gross versus net and multiple
reasonable stress scenarios; zero friction is not a deployment result.

Select metrics that match the job: discrimination and calibration for forecasts;
net return, drawdown, exposure, turnover and uncertainty for a trading simulation.
Preserve prevalence/imbalance and tied scores when evaluating classifiers. High
in-sample Sharpe or AUC alone is not economic utility. Inspect concentration,
nonstationarity, benchmark dependence, tail risk and failure regimes.

## Return a falsifiable verdict

Return the experiment contract, immutable evidence, leakage findings, selection
history, split/time diagram in text, baselines, out-of-sample estimates with
uncertainty, costs/stress results, limitations and the next falsifier. Use a
qualified verdict such as unsupported, promising but unvalidated, or validated
for the stated research use. Do not invent a universal pass threshold.

Research validation, prospective shadow observation, accepted production signal
use and trading authority are separate. Never auto-promote a candidate to live
ranking, alerts, sizing or execution. A future paper/shadow test requires the
existing owner's authorized path; no self-created watcher or trading loop.
