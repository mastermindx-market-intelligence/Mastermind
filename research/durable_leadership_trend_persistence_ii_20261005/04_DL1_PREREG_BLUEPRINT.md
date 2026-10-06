# 04 — Draft Experiment DL-1 Preregistration Blueprint

This blueprint is detailed enough for a later research CEO to write the frozen preregistration. It is **not itself the frozen preregistration** and it authorizes no outcome read.

## Research question

**H1:** For a stock that is a current relative-strength leader, identity-qualified independent peer continuity and breadth within its point-in-time GICS industry group predict subsequent leader-state survival after controlling for rich own-stock momentum, residual momentum, beta, and volatility.

**H0:** After those own-stock and common-factor controls, the out-of-sample predictive contribution of the frozen independent group feature family is zero or economically immaterial.

---

## Population

### Preferred confirmation route

Common equities in a frozen set of developed **ex-U.S.** markets with:

- point-in-time company / industry-group membership;
- adjusted prices including dead / delisted securities;
- stable issuer identifiers;
- at least 126 prior trading sessions at formation;
- a frozen liquidity / investability rule applied using only information available at formation;
- lawful research/model-use rights.

Country membership and currencies must not be pooled naively. Leadership ranks are calculated within the prespecified local market / country universe, and country effects enter as nuisance controls.

### Fallback route

Point-in-time S&P 1500 members on formation dates **strictly after the DL-1 freeze**, with no use of 2022-07-06 through 2026-06-02 as confirmatory efficacy evidence.

The route must be selected before outcome access and may not be switched after an unfavorable read.

---

## Leader-state definition

At formation date t, calculate each eligible stock's cumulative **126-session market-relative return** using data through the close of t.

A stock is a leader if it lies in the **top quartile** of the eligible cross-section.

The state definition must be frozen before fresh outcomes are inspected.

### Primary outcome

Y20 = 1 if the stock remains in the top relative-strength quartile at t+20, otherwise 0.

### Secondary confirmatory outcome

Y60 = 1 if the stock remains in the top relative-strength quartile at t+60, otherwise 0.

### Structural secondary outcome

time_to_leader_exit = first post-formation session at which the name is outside the top quartile, right-censored at 60 sessions.

### Material-break secondary outcome

First entry into the bottom half of the cross-sectional leadership rank during the 60-session window.

### Why top quartile?

It is interpretable, supplies enough cross-sectional membership for transition estimation, and aligns with already-used descriptive top-quartile survival semantics without being selected from DL-1 outcomes.

---

## Formation clock

- Form every fifth local trading session from a prespecified anchor.
- All features use close-t or earlier information.
- The prediction interval begins at t+1.
- Fixed 20- and 60-session roles are used across stocks.
- No per-stock timeframe selection.
- No horizon optimization against fresh outcomes.

Trend Persistence consumes supported time semantics; it does not create a competing timeframe optimizer.

---

## Group definition

### Primary

GICS **industry group** effective on t.

### Secondary

GICS **industry**, run only under a frozen rule that the focal stock has at least 10 identity-qualified eligible independent peers at formation.

No subindustry, theme, ETF, basket, or graph grouping enters DL-1.

---

## Point-in-time membership rule

A membership / classification is usable only if the source record says it was effective by t.

Later restatements or classification changes are not backcast unless the source explicitly represents historical effective intervals.

The focal issuer and known alternate listings are excluded from all group calculations.

If issuer identity is unresolved, follow the existing Leadership Evidence uncertainty contract rather than silently treating the security as an independent peer.

---

## Frozen group predictor family

Keep the family intentionally small.

| Predictor | Concept |
|---|---|
| peer_residual_strength | Leave-issuer-out equal-weight peer return after broad-market/common-factor residualization, measured over frozen 60/120-session windows |
| peer_continuity | Fraction / bounded estimate of prior peer leaders that remain leaders at formation, reusing identity-qualified continuity semantics |
| breadth_diffusion | Fraction of independent peers above the frozen peer leadership reference, plus one frozen change term |
| leader_dependency | Concentration / HHI of peer contribution to group positive relative return, excluding the focal issuer |

### Explicit exclusions

No focal-stock path efficiency, gain retention, distance from high, drawdown-shape, or renamed B2 variable enters the group feature family.

No analyst revisions, options, shorting, fund flows, supply-chain edges, dynamic themes, or graph clusters enter DL-1.

---

## Strong stock-only baseline S

At minimum:

- own 20/60/120/252-session market-relative returns;
- own residual momentum;
- 20/60/120-session realized volatility;
- beta;
- size;
- liquidity / turnover;
- country / market state;
- broad-sector or common-factor nuisance controls.

No claim is allowed merely because group information beats a weak “past return only” model.

---

## Mandatory model views

### N — nuisance/base-rate

Base rate plus prespecified nuisance controls.

### G — group-only

Frozen group predictors plus nuisance controls, excluding focal-stock momentum.

### S — stock-only

Strong own-stock baseline.

### A — additive

S + G.

### I — interaction

S + G + frozen stock×group interaction terms.

### Principal scientific contrasts

- G − N
- A − S
- I − A

The **group-only comparator is mandatory**. If G predicts the environment but A does not beat S, the result is group timing/context rather than stock-selection skill.

---

## Mandatory challengers

1. Own-stock total-return momentum.
2. Own-stock **residual momentum**.
3. Common-factor momentum state.
4. The strong volatility-aware own-stock baseline.
5. Broad-sector state, to prove any industry-group result is not simply the old coarse-sector effect.

---

## Model class

### Primary probability model

Prespecified logistic regression for 20- and 60-session survival.

### Primary time-to-event model

Prespecified discrete-time complementary-log-log hazard.

No architecture search is allowed on confirmation outcomes. A nonlinear challenger may be preregistered later only after DL-1 establishes whether the information exists at all.

---

## Leakage controls

- No future taxonomy or membership information.
- No current-only taxonomy projected backward.
- No future-delisting knowledge in formation eligibility.
- No focal-issuer contribution to peer state.
- No alternate listing of the same issuer counted as an independent peer.
- No outcome-driven group level selection.
- No outcome-driven horizon selection.
- No post-read threshold movement.
- No hidden switch from one fresh-evidence route to another after observing efficacy.
- No development feature chosen because it correlates with survival on the contaminated U.S. dates.

---

## Dependence treatment

Stock-date rows are not independent. Inference must account for:

- overlapping 20/60-session windows;
- common formation-date market shocks;
- shared industry-group membership;
- repeated observations of the same stock.

Primary uncertainty should use a **formation-time moving-block resampling scheme** with block length no shorter than the longest gating horizon, with group-level clustering included in the resampling or variance estimator.

Country-level leave-one-market-out results must be reported.

A result dominated by one country, one industry group, or one market episode fails robustness even when a pooled p-value passes.

---

## Multiple-testing treatment

Use a closed fixed sequence:

1. A − S at 20 sessions.
2. If passed, A − S at 60 sessions.
3. If both passed, I − A at 20 sessions.

Use one-sided familywise alpha = 0.05 under a fixed-sequence procedure because the preregistered alternative is improvement, not merely difference.

G − N is a **necessary interpretation gate** and must be reported simultaneously. It may not be skipped because additive performance looks favorable.

Industry-level, severe-break, raw-return, MAE, recovery, and regime results remain secondary unless separately designated before freeze.

---

## Minimum effect worth caring about

**Preregistration proposal —** A **five-percentage-point difference in calibrated 20-session leader-survival probability** between comparable high- and low-group-confirmation states, after own-stock controls.

The exact five-point threshold should be ratified **before any fresh outcome read** through a decision-impact calculation. It must not be reduced afterward because the realized effect is smaller.

The model-value gate should additionally require out-of-sample improvement in a proper probability score such as Brier score or log loss over S. Statistical significance alone is insufficient.

---

## Power / sample-size logic

Before exposing the fresh confirmation sample:

1. Use the already-inspected U.S. sample **only** to estimate null event rates, dependence, missingness, and variance.
2. Do not use it to estimate the new hypothesis's confirmatory effect.
3. Run power calculations for the frozen minimum material effect under the actual moving-block / group dependence.
4. Require at least 80% power at the fixed familywise alpha.
5. Freeze the required number of formation dates / blocks before outcome access.
6. If the independent historical universe or prospective horizon cannot supply that power, return **WAIT FOR DATA** rather than lowering the effect bar.

The old sample can answer “how noisy is the survival label?” It cannot answer “does the new peer-continuity hypothesis work?”

---

## Development sample: permitted uses

Previously inspected U.S. data may be used for:

- code / instrument debugging;
- event-rate and missingness estimation;
- peer-count / coverage diagnostics;
- null-variance / power planning;
- verifying feature contracts are computable.

It may not be used for:

- choosing predictors because they correlate with survival;
- choosing industry group versus industry after seeing outcomes;
- choosing thresholds / horizons because they look favorable;
- reporting a new efficacy claim.

---

## Untouched confirmation

### Preferred

One immutable licensed ex-U.S. PIT panel never read for the DL-1 outcome before preregistration, executed in one registered reveal.

### Fallback

All qualifying U.S. formation dates after the frozen preregistration, up to the preregistered sample-size rule, with no efficacy interim.

---

## Advance gate

All of the following must hold:

- A − S passes the 20-session statistical gate.
- The effect meets the frozen materiality threshold.
- G − N carries real predictive information.
- The 60-session result is directionally consistent and passes if the fixed sequence reaches it.
- Calibration is acceptable.
- Sign is stable in the prescribed time blocks.
- No single country / group / episode explains the result.
- PIT / identity coverage remains above the frozen quality floor.
- The result beats residual-momentum and common-factor challengers.

---

## Kill gate

Close the DL-1 static-group peer-confirmation hypothesis if any of these occurs:

- no material A − S improvement at 20 sessions;
- apparent signal disappears against residual/common-factor momentum;
- G contains no independent predictive information;
- effect exists only when the focal issuer contaminates its group;
- result depends on current-taxonomy backcasting or future membership information;
- effect is concentrated in one group / country / episode;
- calibration is unusable despite ranking significance.

---

## Permanent closure after failure

A failed DL-1 **permanently closes this frozen industry-group predictor family for this frozen leader-survival definition**.

Do not:

- rename peer_continuity;
- change top quartile to a nearby cutoff after the read;
- move 20 sessions to 21 or 25 sessions on the same evidence;
- swap industry group for industry because the primary result failed;
- add a new feature family and call the same sample confirmatory.

A materially new hypothesis requires genuinely new evidence.
