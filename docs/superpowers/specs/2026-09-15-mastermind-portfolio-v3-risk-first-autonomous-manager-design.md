---
title: Mastermind Portfolio V3 — Risk-First Autonomous Portfolio Manager Architecture Freeze
status: ARCHITECTURE_APPROVED / SPEC_ONLY / RECORDS_ONLY / PRODUCTION_INERT
operation_key: mastermind-portfolio-v3-risk-first-autonomous-manager-design-20260915-sol-001
approved_by: Chairman Chris
approved_at: 2026-09-15
protected_skillpack_basis: f249802eab3695ff24c9a903798899466c444252
current_protected_recheck: 36f74c02edc938f7f5c41f38743f93ee34be2b2b
skillpack: mastermind.sol_skillpack.v1 1.0.1 / bootstrap major 1
macro_snapshot: fc59066581be1a52e4c89a8e3e1ba2c39796419a
capability_state: SPEC_ONLY
production_effect: NONE
---

# Mastermind Portfolio V3 — Risk-First Autonomous Portfolio Manager Architecture Freeze

## 0. Executive ruling

Chairman Chris approved the corrected high-level architecture on 2026-09-15.

The frozen method is:

> One accountable root portfolio manager produces relative, evidence-bound investment views. Independent specialist research supplies claims rather than votes. Empirical reliability and R-ORTH independence determine how much evidence counts. A risk-first hierarchical constructor creates the base book. Bounded alpha tilts express the portfolio manager's judgment. A deterministic projection layer enforces costs, portfolio risk, and feasibility. The existing paper-account and settlement plane remains the only portfolio-state mutation authority. Every new layer earns authority through isolated forward experiments and factor-aware attribution.

This architecture rejects both failed extremes:

```text
LLM discretion without quantitative discipline
    -> narrative certainty, unstable weights, churn, hidden factor bets

deterministic gates without accountable portfolio judgment
    -> information loss, residual cash, stale allocations, fragmented responsibility
```

The V3 target is therefore a **risk-first, evidence-independent, alpha-tilted portfolio system**.

This record freezes architecture, ownership, contracts, sequencing, falsifiers, and no-rebuild boundaries. It does not authorize a live allocator, a second active US book, a production model turn, a deployment, or any portfolio-state mutation.

---

## 1. Outcome before code

### 1.1 Primary persona and user job

The primary persona is Chairman Chris creating Mastermind as a serious autonomous paper portfolio manager.

The user job is:

> Give me one coherent, inspectable, genuinely intelligent portfolio manager that can find the best available opportunities, construct a resilient book, explain every material decision, learn from forward outcomes, and demonstrate whether it creates real stock-selection value rather than merely holding cash or repackaging market and factor exposure.

The product must answer, for every decision cycle:

1. What is the current market and risk state?
2. What opportunities deserve research now?
3. Which claims are facts, estimates, inferences, or unresolved?
4. Which ideas are independently supported rather than duplicated by correlated evidence?
5. Which names belong in the portfolio, which do not, and why?
6. What is each position's role, weight range, horizon, catalyst, and falsifier?
7. What portfolio risks, hidden factor bets, event concentrations, and scenario losses result?
8. Why is the selected target superior to holding the current book, holding cash, or choosing the best rejected alternative?
9. What changed since the prior decision?
10. What did the system later learn about selection, sizing, timing, exits, and evidence quality?

### 1.2 Machine and intelligence job

The machine job is to transform current, provenance-bearing evidence into one correction-safe decision snapshot; coordinate bounded research; construct one shadow target; prove feasibility and stability; preserve the exact information set; and produce forward attribution without altering the live V2 portfolio.

The intelligence job is to identify real relative opportunity while refusing false precision, correlated confirmation, hindsight leakage, and narrative-driven capital authority.

### 1.3 Moat

The moat is not "an LLM picks stocks."

The moat is the combination of:

- Mastermind's existing market-intelligence estate;
- point-in-time evidence and correction lineage;
- one accountable root portfolio manager;
- bounded specialist research with explicit independence families;
- canonical Grey Deer market-risk truth;
- portfolio factor and relationship structure;
- risk-first construction plus bounded judgment;
- exact decision-to-outcome attribution;
- prospective policy experiments;
- no hidden promotion from explanation into money authority.

### 1.4 Ten-out-of-ten end state

A ten-out-of-ten system has all four completion dimensions:

**Truth**

- Fresh, rights-safe, correction-safe inputs.
- Exact observed, known, as-of, generated, and correction clocks.
- Complete or explicitly partial opportunity coverage.
- No hidden substitution of stale, missing, or retrospective data.

**Intelligence**

- Structured claims, causal mechanisms, contradictions, relationships, and uncertainty.
- Reliable evidence weighted by empirical skill and independence.
- Comparative judgment across current holdings, finalists, rejected ideas, and cash.
- Explicit abstention when the evidence cannot support a decision.

**Product**

- One coherent premium workflow from snapshot to research to target to proof.
- Clear separation of strategic thesis, tactical allocation, execution, and emergency state.
- Exact weight waterfall and portfolio-risk explanations.
- Real degraded, blocked, corrected, and no-change states.

**Learning**

- Forward, leakage-resistant grading.
- Factor-aware performance attribution.
- Separate selection, construction, timing, execution, and cost contributions.
- Promotion and demotion through preregistered evidence rather than narrative confidence.

---

## 2. Approval and authority

### 2.1 Chairman approval

The Chairman approved the corrected architecture after an adversarial hardening turn. That approval authorizes this architecture record. It does not authorize implementation effects beyond this records-only publication.

### 2.2 Constitutional authority

The protected Mastermind Charter v2 remains controlling:

- P1: nothing trades on one evidence plane;
- P2: wrong data shrinks, never flips;
- P3: every signal earns authority;
- P4: cash and defensives are first-class positions;
- P5: perception before position;
- P6: every mistake becomes machinery;
- P7: one source of truth per concept;
- P8: autonomy is earned in shadow;
- P9: books differ on a nameable axis or die;
- P10: deployment is part of the system.

V3 extends those laws. It does not supersede them.

### 2.3 Current V2 freeze

`autonomous` remains the sole active US stock-selection portfolio.

The V2 forward-evaluation ruling remains binding until a separate accepted cutover decision:

- no second live US allocator;
- no unmeasured V2 retune hidden inside V3;
- no new model, sizing, fill, or self-promotion authority in the live path;
- Prophet, Neural Web, sector, technical, and options context do not directly size or mutate an account;
- omission remains not-a-sale;
- deterministic code owns eligibility, sizing, settlement, and mutation;
- research children remain read-only;
- learning remains observational/request-only.

V3 begins in isolated shadow. It cannot share the V2 live cohort as if the policy generations were one architecture.

---

## 3. Exact current-source basis

### 3.1 Protected Mastermind source

This architecture was composed against protected Mastermind and its exact Skillpack at:

```text
f249802eab3695ff24c9a903798899466c444252
```

Current protected master at final plan recheck:

```text
36f74c02edc938f7f5c41f38743f93ee34be2b2b
```

The protected movement from `f249802e...` through `19b61118...` and `36f74c02...` consists of Executive submit-fence PR #654 and host-placement binding PR #655. Their changed paths are disjoint from this records-only Portfolio specification and plan. The Skillpack `INDEX.md` blob remains byte-identical at `5909db6e26b9d61e0622f83079733857010989da`, and the carrier history-preservingly composes current protected master.

Skillpack loaded atomically from the original protected basis above:

```text
schema: mastermind.sol_skillpack.v1
version: 1.0.1
minimum_bootstrap_major: 1
```

Required procedures loaded from the same commit:

- `docs/sol_skills/INDEX.md`
- `docs/sol_skills/COLD_START.md`
- `docs/sol_skills/RECONCILE_STATE.md`

### 3.2 Mastermind source anchors

Exact protected source anchors consumed:

| Path | Blob |
|---|---|
| `AGENTS.md` | `0abc3a2da8ea9dd8c9e3b0436f968e2b7803db29` |
| `research/MASTERMIND_CHARTER_V2.md` | `01ae914ab4013b8db9ac7f7af02405cbb801e3c6` |
| `docs/PORTFOLIO_V2_FORWARD_EVALUATION_2026-08-11.md` | `2b4f3bdb8a1b1a05beb73541dd8f797aa4559b7c` |
| `portfolio/registry.py` | `f5eb632d8f2d8dfcdbe11abb19076f9d746b38fe` |
| `brain/decision_submission.py` | `79da9129ae269a7f9c007e38c1cc5d0e3fe9945d` |
| `bot/autonomous.py` | `b57105bba4d863a268231fb382c9fff8d1c31710` |
| `portfolio/forward_evaluation.py` | `ef9944ebed235803ea32e7532c0a03884675cc69` |
| `portfolio/shadow_books.py` | `935d4facc6c859e86fed00448c74284f9c2d4fca` |
| `brain/research_desk.py` | `702e398f107831e862efafd6e5df35ca703361a4` |

### 3.3 Macro source anchors

Bounded Macro snapshot:

```text
fc59066581be1a52e4c89a8e3e1ba2c39796419a
```

Exact source anchors:

| Path | Blob |
|---|---|
| `agentos/decisions/DEC-PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK.md` | `e9c8bb20563fb6375e36d7de9b755082ad470237` |
| `engine/risk_envelope.py` | `3b0df2d426f50245142b943e38faf4996f96e995` |
| `engine/neuralweb/covariance_spine.py` | `82cf31e77ce087f375cfa719bda5cd9050a2d831` |
| `engine/factor_exposure.py` | `52cc784da54d9a3c4659091f275a5c81851625ff` |

### 3.4 Current adjacent carriers

**Mastermind PR #548**

- Operation: `prophet-rotation-consumer-read-20260909-sol-001`
- Head: `2e30afd72d5f8be5f39a15d0f21c223aa77835f4`
- State: `OPEN / DRAFT / HOLD / RED / PRODUCTION SOURCE UNCHANGED`
- Owns the current non-lossy sector/rotation consumer contract.

This architecture must not duplicate or race that repair.

**Mastermind PR #398**

- Operation: `mastermind-outcome-learning-v1-complete-vertical-20260902-sol-001`
- Head: `293e3bb9ffd72d1c42d8f96674d23e67ba1f28b6`
- State: `OPEN / DRAFT / HOLD / BUILT_NOT_PROVEN`
- Owns one proposed generic Outcome Learning generation.

This architecture may consume an accepted future contract but must not treat the open PR as protected capability or rebuild it.

### 3.5 Collision result

At architecture publication time:

- the target spec path did not exist;
- no `portfolio-v3` branch existed;
- no open PR directly implemented this V3 methodology;
- the records-only spec path is disjoint from active implementation paths;
- this carrier creates no runtime or source-writer collision.

---

## 4. Current capability ledger

| Capability | State | Canonical evidence |
|---|---|---|
| One active US managed book (`autonomous`) | `PROVEN_LIVE` | Registry, V2 cutover, live forward marker |
| Paper-only settlement and marking | `PROVEN_LIVE` | Existing canonical paper-account path |
| Typed ADD/HOLD/TRIM/EXIT boundary | `PROVEN_LIVE` | V2 decision submission |
| Omission is not a sale | `PROVEN_LIVE` | V2 decision boundary |
| Common-stock-only US identity policy | `PROVEN_LIVE` | Registry and instrument policy |
| V2 exact forward cohort | `PROVEN_LIVE` | Forward-evaluation marker and read surface |
| V2 security-selection alpha | `PARTIAL` | Architecture exists; sufficient forward evidence is not established here |
| Complete non-lossy sector/rotation consumption | `BROKEN` | PR #548 real-artifact proof |
| Grey Deer risk producer | `BUILT_NOT_PROVEN` for Portfolio consumption | Macro producer exists; Portfolio cutover separately gated |
| Portfolio consumption of canonical risk truth | `PARTIAL` | Owner decision exists; end-to-end live cutover not established here |
| Factor-exposure measurement | `BUILT_NOT_PROVEN` | Macro measurement/context engine |
| R-ORTH structural-independence context | `BUILT_NOT_PROVEN` | Macro context-only rail |
| Existing research desk | `PARTIAL` | Research/proposal path exists; not V3 claim DAG |
| Existing counterfactual shadow books | `BUILT_NOT_PROVEN` | Isolated policy arms exist |
| V3 Decision Snapshot | `NOT_BUILT` | — |
| V3 Claim ledger | `NOT_BUILT` | — |
| V3 PM View | `NOT_BUILT` | — |
| Reliability and independence fusion | `NOT_BUILT` | — |
| Risk-first constructor | `NOT_BUILT` | — |
| Bounded alpha tilt | `NOT_BUILT` | — |
| Convex feasibility projection | `NOT_BUILT` | — |
| Weight-stability gate | `NOT_BUILT` | — |
| Full selection/construction/timing/cost attribution | `PARTIAL` | Existing evaluators do not close all decomposition legs |
| V3 product cockpit | `NOT_BUILT` | — |
| V3 live portfolio authority | `NOT_BUILT` and not authorized | — |
| Overall V3 | `SPEC_ONLY` | This architecture record |

---

## 5. Problem diagnosis

### 5.1 The architecture is not failing because it lacks more signals

Mastermind already has a large intelligence estate.

The current failure is primarily a **decision and construction problem**:

- rich context is not always consumed completely;
- correlated signals can appear like independent confirmation;
- ordinal intent discards useful relative information;
- fixed sizing rules do not compare the whole book;
- current holdings can preserve stale weight relationships;
- cash can emerge as unexamined residue;
- no single layer measures whether the PM, constructor, timing, or risk overlay earned its keep;
- raw returns can be mistaken for security-selection skill.

### 5.2 Information loss at the decision boundary

V2 correctly removed raw numeric sizing authority from the model. The current boundary makes model weight fields advisory and derives trusted numeric targets from ordinal intent.

That protection also destroys potentially useful relative information.

The system needs a middle path:

```text
model cannot dictate an exact executable weight

but

model can express ordered preferences, uncertainty, ranges, and pairwise trade-offs
that a trusted constructor can use
```

### 5.3 Residual cash is not neutral

A portfolio that is mostly cash is making a large active allocation decision.

Cash must be treated as an explicit asset with:

- yield;
- zero equity beta;
- benchmark opportunity cost;
- scenario value;
- deployment conditions;
- an explicit rationale.

V3 must not allow cash to appear merely because too few names crossed fixed ADD thresholds.

### 5.4 More vetoes do not create better judgment

The legacy Flagship demonstrated that individually reasonable controls can compose into an incoherent sieve.

V3 preserves safety but rejects the architecture where many semi-authoritative layers independently originate, validate, size, and remove positions.

There is one root PM and one trusted construction path.

### 5.5 Exact return forecasts are not trustworthy at birth

LLMs can reason usefully about:

- relative attractiveness;
- causal mechanisms;
- scenarios;
- catalysts;
- falsifiers;
- uncertainty;
- range judgments;
- which assumptions matter.

They do not receive binding sizing authority merely by emitting an apparently precise expected return.

At birth, exact expected-return fields are diagnostic only.

### 5.6 Correlated evidence creates false confidence

Price trend, momentum, breadth, leadership, and several technical dashboards may all be transformations of the same market move.

Five correlated sources are not five independent facts.

V3 groups evidence by independence family and uses empirical reliability and R-ORTH context to control how much a family counts.

### 5.7 Raw portfolio return cannot prove stock-selection skill

A winning book may simply hold:

- more market beta;
- more momentum;
- more growth;
- less cash;
- lower volatility;
- a favored sector;
- a strong macro factor.

V3 promotion requires factor-aware decomposition, net of costs and cash.

---

## 6. Rejected architectures

### 6.1 Rejected: direct LLM weight authority

```text
LLM selects exact target weights
-> deterministic layer only checks broad caps
```

Why rejected:

- false numerical precision;
- model-to-model instability;
- prompt sensitivity;
- no empirical calibration at birth;
- difficult attribution;
- unsafe coupling between language confidence and capital.

### 6.2 Rejected: direct mean-variance optimization over LLM returns

```text
LLM expected returns + sample covariance
-> optimizer
-> target
```

Why rejected:

- expected-return error dominates;
- small forecast perturbations can cause large weight changes;
- covariance inversion amplifies noise;
- concentration often hides behind mathematical optimality;
- a clean optimizer result can create false authority.

A direct-return optimizer remains a shadow challenger. It is not the principal constructor until forward evidence earns that role.

### 6.3 Rejected: permanent multi-agent investment committee

```text
specialist agents vote
-> consensus score
-> target
```

Why rejected:

- duplicated narratives;
- correlated opinions;
- serial latency;
- unclear accountability;
- false consensus;
- hidden veto stacking;
- high token cost;
- a committee can recreate the Flagship sieve.

Specialists produce claims. The root PM decides.

### 6.4 Rejected: another intelligence fusion score

V3 does not create a universal alpha score, conviction score, risk score, or super-signal.

It preserves separate:

- facts;
- forecasts;
- reliability;
- uncertainty;
- risk;
- opportunity rank;
- PM preference;
- construction;
- execution.

### 6.5 Rejected: another active portfolio book

V3 is not appended to `portfolio/registry.py` as an active book.

It begins under the existing shadow/evaluation owner and remains invisible to settlement.

### 6.6 Rejected: another market-risk truth plane

Portfolio does not recreate market state, hazard, or capital policy.

It consumes Grey Deer and owns only book-specific application.

### 6.7 Rejected: deletion-first cutover

Legacy and V2 paths remain available for comparison and rollback until separately accepted cutover.

---

## 7. Frozen architectural laws

1. One canonical live US managed book remains `autonomous`.
2. V3 begins in isolated shadow, not in the active registry.
3. Macro owns market and macro intelligence.
4. Grey Deer owns canonical market-risk truth.
5. Portfolio owns manager intent, construction, sizing, settlement, and outcome learning.
6. Every V3 decision binds to one immutable point-in-time Decision Snapshot.
7. One root PM is accountable for the whole book.
8. Research children produce claims only.
9. Research children cannot submit targets, choose executable weights, or mutate portfolio state.
10. PM judgment begins as ordinal rank, pairwise preference, uncertainty, and weight ranges.
11. Exact LLM expected-return forecasts have no principal sizing authority at birth.
12. Evidence is weighted by empirical reliability and independence, not source count.
13. Contradiction increases uncertainty; it is not averaged away.
14. A risk-first hierarchical method creates the anchor portfolio.
15. A bounded alpha tilt expresses PM judgment.
16. A deterministic projection layer owns feasibility, cost, turnover, and risk constraints.
17. Constructor instability is a hard acceptance signal.
18. Cash is an explicit active allocation.
19. Grey Deer can constrain risk; missing or stale Grey Deer can never loosen it.
20. The constructor cannot add a discretionary name the root PM did not select.
21. Risk and adversarial layers are subtract-only.
22. Strategic thesis, tactical allocation, execution, and emergency clocks remain separate.
23. The existing target, pending-target, fill, settlement, and marking planes remain canonical.
24. Research, construction, and execution improvements are tested sequentially.
25. Promotion depends on factor-aware stock-selection evidence, not raw NAV.
26. No automatic learning promotion.
27. No automatic shadow-to-live promotion.
28. No duplicate feature store, lifecycle, queue, account, risk engine, covariance engine, or correction ledger.
29. No architecture component may claim guaranteed profitability.
30. Green CI is source integration, not portfolio effectiveness.

---

## 8. Canonical owner map

### 8.1 Macro owns

- market and macro intelligence artifacts;
- source contracts and provenance;
- Prophet upstream decisions and plan geometry;
- Neural Web context and relationships;
- Grey Deer market-risk truth;
- factor-exposure measurement;
- R-ORTH structural-independence context;
- sector, theme, event, policy, earnings, and source-native evidence.

Macro outputs do not automatically become Portfolio sizing authority.

### 8.2 Portfolio owns

- book state and mandates;
- root PM decisions;
- selected and rejected names;
- book-specific risk application;
- managed-book construction and sizing;
- shadow targets;
- pending targets;
- simulated settlement;
- fills, marking, NAV, decisions, and outcomes;
- portfolio learning and experiments;
- product workflow for portfolio decisions.

### 8.3 Grey Deer boundary

Grey Deer answers three separate questions:

1. measured state;
2. transition hazard;
3. capital policy.

Portfolio maps accepted policy into book-specific constraints.

Portfolio may choose less risk than the lawful ceiling. It may not create a local fusion that exceeds it.

### 8.4 R-ORTH boundary

R-ORTH remains context-only.

V3 may consume its measurements of structural overlap and effective independence.

V3 may not promote R-ORTH into a signal, ranker, gate, or direct sizing owner.

### 8.5 Factor-model boundary

The Macro factor engine measures exposure and concentration.

It is not a stock-selection signal.

V3 consumes it for risk decomposition, clustering, scenario analysis, and attribution.

### 8.6 Executive and provider boundary

Executive OS owns Job, Attempt, Worker, and Event lifecycle.

Provider Control owns provider availability, quota, and cooling.

V3 creates no model-session registry, retry queue, or provider control plane.

### 8.7 Settlement boundary

The existing paper-account, pending-target, fill-receipt, settlement, and mark writers remain sole mutation owners.

Shadow artifacts have no route to those writers.

---

## 9. Target architecture

```text
Canonical current source artifacts
        |
        v
V3-S0 Decision Snapshot
  content-addressed, point-in-time, correction-safe
        |
        +-------------------------------+
        |                               |
        v                               v
Opportunity Map                  Canonical Risk Context
cross-sectional candidates       Grey Deer / factor / R-ORTH / relationships
        |                               |
        v                               |
Adaptive Research DAG                  |
specialist Claims only                 |
        |                               |
        +---------------+---------------+
                        |
                        v
                  Root PM View
       selected / rejected / ranks / ranges / uncertainty
                        |
                        v
                 Risk-First Anchor
                        |
                        v
                  Bounded Alpha Tilt
                        |
                        v
          Deterministic Feasibility Projection
                        |
                        v
               Weight Stability Gate
                        |
                        v
                Isolated Shadow Target
                        |
                        v
        Shadow Marking / Attribution / Evaluation
                        |
                        v
             Independent Promotion Review
                        |
                        v
          Separate Chairman Cutover Decision
```

The first implementation vertical stops at Decision Snapshot. No model or target is part of V3-S0.

---

## 10. Decision Snapshot

### 10.1 Purpose

The root PM should not enter a session and hunt through tools until it happens to form a story.

Every V3 cycle begins with one immutable:

```text
mastermind.portfolio_decision_snapshot.v1
```

This is not a new data warehouse.

It is a content-addressed manifest over existing canonical artifacts and bounded derived views.

### 10.2 Required domains

| Domain | Canonical input |
|---|---|
| Book truth | Current paper account, positions, cash, accepted target, unsettled receipts |
| Risk truth | Grey Deer envelope and coverage/authority state |
| Market structure | Sector/theme rotation, breadth, dispersion, liquidity |
| Independence | R-ORTH covariance-spine output |
| Factor risk | Macro factor exposures and covariance inputs |
| Candidate geometry | Prophet regional plan state |
| Relationships | Neural Web candidates, conflicts, dependencies, contagion context |
| Fundamental state | Earnings, revisions, valuation, quality, balance sheet |
| Positioning | Options, institutional, insider, ETF/fund, political and alt-data evidence |
| Priceability | Instrument identity, quotes, liquidity, trading calendar |
| Event state | Earnings, catalysts, filings, policy and material corporate events |
| Historical memory | Existing thesis, prior forecasts, decisions, fills, and outcomes |

### 10.3 Source receipt

Every referenced source carries:

```text
source_id
producer
repository / contract owner
schema
schema_version
definition_id
artifact_digest
observed_at
known_at / available_at
as_of
generated_at
correction_generation
freshness_state
coverage_state
rights_class
authority_class
```

`observed_at` and `known_at` are distinct.

A fact observed at 09:00 but unavailable to Mastermind until 11:00 cannot enter a 10:00 decision.

### 10.4 Snapshot states

```text
COMPLETE
PARTIAL
BLOCKED
INVALID
CORRECTED_GENERATION_AVAILABLE
```

A missing source never becomes an empty complete source.

A stale source never becomes a current calm source.

### 10.5 Correction law

If a source corrects a same-date artifact after the decision cutoff:

- the original snapshot remains immutable;
- the correction creates a new source generation;
- the next decision references the new generation;
- historical evaluation uses the generation actually available to the PM;
- no page or continuation token may mix generations.

### 10.6 Bounded payload

The snapshot has:

- a closed root manifest;
- bounded sections;
- explicit pagination or section retrieval;
- byte ceilings;
- counts and omitted-row receipts;
- stable native IDs;
- no arbitrary caller-selected file path;
- no secret-bearing text.

### 10.7 Dependency on PR #548

If PR #548 remains red or unmerged, sector/rotation data enters V3-S0 only as an explicit partial dependency.

V3-S0 must not duplicate #548's reader.

A later accepted #548 generation can fill the source slot without changing V3-S0 ownership.

---

## 11. Opportunity Map

### 11.1 Purpose

The root PM should compare a cross-section rather than repeatedly ask whether one ticker passes.

The Opportunity Map is a deterministic, provenance-bearing projection over existing candidates and current holdings.

### 11.2 Candidate sources

Initial candidate families include:

- current holdings;
- previous near-miss rejects;
- Prophet candidates;
- sector and theme leaders;
- Neural Web candidates;
- earnings and revision inflections;
- valuation and quality changes;
- balance-sheet and credit changes;
- flow and positioning anomalies;
- event-driven discoveries;
- existing universe prediction ledger;
- externally researched ideas admitted with rights and provenance.

### 11.3 Funnel shape

The target operating shape is empirical, not frozen. A representative flow is:

```text
~1,500 liquid names
        -> 100-250 surfaced candidates
        -> 30-50 research candidates
        -> 10-25 finalists
        -> 12-25 portfolio positions
```

Counts remain experiment variables.

### 11.4 No hidden authority

The Opportunity Map provides:

- identity;
- reasons surfaced;
- source families;
- coverage;
- freshness;
- current-holding state;
- deterministic eligibility;
- research priority.

It does not set executable weights or mutate the book.

### 11.5 Research priority

Research priority is distinct from trade rank.

A high-priority candidate may be:

- high potential and high uncertainty;
- a current holding near a falsifier;
- a disagreement among important evidence families;
- a candidate whose research could materially alter portfolio risk;
- a near-miss alternative that makes cash or a held position hard to justify.

---

## 12. Adaptive Research DAG

### 12.1 One accountable root PM

The root PM owns:

- final selected and rejected set;
- strategic and tactical thesis;
- comparative rank;
- pairwise preferences;
- uncertainty;
- weight ranges;
- cash comparison;
- target rationale;
- accepted and rejected claims.

It is the only model surface allowed to produce a PM View.

### 12.2 Specialists produce claims, not votes

A specialist may answer bounded questions such as:

| Role | Decision question |
|---|---|
| Fundamental | Are earnings and cash-flow expectations wrong? |
| Revisions | Is the estimate trajectory improving or deteriorating? |
| Valuation | What expectations are embedded in price? |
| Catalyst | What can change market belief, when, and with what probability? |
| Positioning | Who is crowded, under-owned, hedged, or forced? |
| Technical/execution | Is the current price a viable entry for this thesis? |
| Neural Web | What hidden dependencies, conflicts, or contagion paths exist? |
| Adversarial | What is the strongest reason the thesis is wrong? |
| Portfolio interaction | Does this add an independent bet or duplicate an existing one? |

A specialist cannot:

- submit a portfolio target;
- choose an executable weight;
- create an exit;
- mutate thesis state;
- invoke settlement;
- promote its own role;
- write portfolio state.

### 12.3 Research admission

Research is commissioned when expected decision value is high:

```text
portfolio materiality
x decision uncertainty
x probability research changes the decision
x freshness need
x cost and latency budget
```

Low-materiality candidates do not receive principal-model research by default.

Mechanically resolvable facts use deterministic tools.

### 12.4 Anti-anchoring

For material new candidates:

1. the first thesis assessment does not see the desired weight;
2. the adversarial assessment does not see the bull analyst's confidence;
3. the portfolio-interaction assessment sees the proposal only after independent risk context exists;
4. the root PM receives every claim, contradiction, and provenance receipt.

### 12.5 No permanent committee

There is no quorum, majority vote, permanent roster, or consensus score.

The research DAG is adaptive and sparse.

---

## 13. V3 artifact contracts

### 13.1 `mastermind.portfolio_research_claim.v1`

A Claim is a bounded proposition:

```json
{
  "schema": "mastermind.portfolio_research_claim.v1",
  "claim_id": "stable-id",
  "snapshot_id": "sha256:...",
  "subject": "NVDA",
  "role": "fundamental",
  "proposition": "FY27 data-center expectations remain too low",
  "direction": "POSITIVE",
  "horizon_sessions": 63,
  "magnitude_band": "MATERIAL",
  "probability": 0.64,
  "uncertainty": 0.41,
  "evidence_refs": [],
  "source_family": "fundamental_revisions",
  "independence_family": "earnings_expectations",
  "contradictions": [],
  "falsifier": "two consecutive material negative revisions",
  "expires_on": "2026-11-30",
  "method": "fundamental_analysis",
  "authority": "RESEARCH_ONLY"
}
```

Closed vocabularies and bounds belong in the implementation contract.

The probability is an estimate to grade. It is not capital authority.

### 13.2 `mastermind.portfolio_pm_view.v1`

The root PM View contains:

```text
snapshot identity
portfolio identity
selected names
explicit rejects
action per held/selected name
ordinal attractiveness
pairwise preferences
minimum / preferred / maximum weight ranges
uncertainty
strategic thesis
tactical thesis
horizon
catalysts
falsifiers
scenario sensitivities
accepted claims
rejected claims
unresolved contradictions
cash comparison
decision memo
```

The PM View has:

```text
execution_authority = false
numeric_target_authority = false
```

### 13.3 `mastermind.portfolio_risk_anchor.v1`

The anchor records:

```text
selected universe
covariance generation
factor generation
relationship generation
cluster method
cluster membership
risk budgets
anchor weights
cash anchor
coverage
stability diagnostics
authority = construction_context
```

It does not settle or mutate an account.

### 13.4 `mastermind.portfolio_target_projection.v1`

The projection records:

```text
current book
risk anchor
PM tilt inputs
constraints
estimated costs
scenario constraints
turnover
infeasibilities
weight waterfall
final shadow target
stability state
abstention/reduction reason
execution_authority = false
```

### 13.5 `mastermind.portfolio_shadow_decision.v1`

The accepted shadow decision binds:

```text
snapshot
claims
PM View
risk anchor
projection
model generation
policy generation
constructor generation
shadow account
evaluation cohort
```

It cannot be consumed by the live pending-target or settlement path.

---

## 14. Reliability and evidence independence

### 14.1 Reliability identity

Reliability is estimated by:

```text
model_or_role_generation
x evidence_family
x market
x horizon
x regime
x decision_type
```

Examples:

- root PM / US / 63 sessions / selection rank;
- revisions role / US / 63 sessions / earnings inflection;
- technical role / US / 5 sessions / entry timing;
- Prophet / HK / 10 sessions / WAIT versus ENTER;
- Neural Web / US / 21 sessions / conflict shrink.

### 14.2 Hierarchical shrinkage

Sparse reliability cells shrink toward broader priors:

```text
specific cell
-> same role and horizon
-> same evidence family
-> global role prior
-> neutral prior
```

A new model or prompt generation does not inherit full authority from an old generation.

### 14.3 Evidence families

Initial independence families include:

```text
price_technical
fundamental_revisions
valuation
flow_positioning
macro_liquidity
sector_theme
event_catalyst
graph_relationship
balance_sheet_credit
```

The list is versioned.

### 14.4 Correlated-family collapse

Within one family, multiple readings are combined conservatively rather than summed.

Candidate methods include:

- robust median;
- trimmed mean;
- bounded consensus;
- strongest qualified evidence plus contradiction record.

The exact method remains empirical.

### 14.5 Across-family fusion

Across families, contribution depends on:

- empirical reliability;
- freshness and coverage;
- structural independence;
- contradiction;
- horizon fit;
- method generation.

A conceptual score is:

\[
q_i =
\frac{
\sum_g R_{g,h,r} C_{i,g} I_{i,g} S_{i,g}
}{
\sum_g |R_{g,h,r} C_{i,g} I_{i,g}|
}
\]

where:

- \(R\) is reliability;
- \(C\) is coverage and freshness;
- \(I\) is independence weight;
- \(S\) is signed ordinal evidence.

The implementation need not use this exact formula at birth. The law it represents is frozen.

### 14.6 Uncertainty

Uncertainty increases with:

- claim disagreement;
- missing required evidence;
- stale or partial inputs;
- low effective sample;
- untested model generation;
- scenario sensitivity;
- factor-model weakness;
- event binary risk;
- constructor instability;
- unmodeled relationships.

High confidence with high uncertainty cannot create a large position without explicit bounded justification.

### 14.7 R-ORTH boundary

R-ORTH remains context-only.

V3 may consume structural-overlap and effective-independence measurements.

V3 may not make R-ORTH a signal, ranker, gate, or direct sizing owner.

The Portfolio constructor owns the book decision.

---

## 15. Risk-first construction

### 15.1 Why risk first

The principal constructor must remain useful even when expected-return estimates are weak.

Risk-first construction:

- creates a stable baseline;
- prevents nominal diversification from hiding one macro bet;
- makes the PM tilt attributable;
- reduces sensitivity to small forecast changes;
- permits honest comparison with equal weight and direct optimization.

### 15.2 Inputs

The anchor consumes:

- PM-selected names;
- current holdings;
- covariance estimate;
- factor exposures;
- idiosyncratic risk;
- sectors and industries;
- themes;
- Neural Web relationships;
- R-ORTH clusters;
- event buckets;
- liquidity;
- Grey Deer policy ceiling;
- explicit cash.

### 15.3 Candidate methods

The first empirical family includes:

- equal risk contribution;
- hierarchical risk parity;
- hierarchical equal risk contribution;
- inverse-volatility within relationship clusters;
- equal weight as a control.

The exact method is not frozen.

Each challenger must expose:

- cluster formation;
- risk contribution;
- concentration;
- perturbation stability;
- coverage;
- null behavior.

### 15.4 No covariance invention

When covariance or factor coverage is missing:

- no model may invent a precise relationship;
- names may be conservatively grouped by known sector/theme/event relationships;
- position and cluster limits tighten;
- the system may abstain;
- missing risk data never increases a weight.

### 15.5 Risk anchor authority

The risk anchor is not a trade target.

It is the stable baseline from which bounded PM judgment is expressed.

---

## 16. Bounded alpha tilt

### 16.1 Purpose

The PM's judgment must matter, but it cannot bypass empirical and portfolio constraints.

A conceptual transform is:

\[
w_i^{pre}
\propto
w_i^{risk}
\exp\left(
\kappa
\frac{q_i}{\max(u_i,u_{min})}
\right)
\]

where:

- \(w_i^{risk}\) is the risk anchor;
- \(q_i\) is reliability- and independence-adjusted comparative score;
- \(u_i\) is uncertainty;
- \(\kappa\) is bounded alpha intensity.

The exact transform is not frozen.

### 16.2 Frozen behavior

- The PM can increase or decrease relative preference within bounds.
- The PM cannot add a name it did not select.
- The PM cannot exceed its own declared maximum range.
- A risk/adversarial layer can only reduce or block.
- Missing evidence can only reduce authority.
- The final target remains deterministic from sealed inputs.
- Every deviation from the risk anchor has an attributable reason.

### 16.3 Weight range

Each selected name carries:

```text
minimum_weight
preferred_weight
maximum_weight
```

A minimum greater than zero is a meaningful PM assertion and must be supported.

A preferred weight is not executable authority.

A maximum is an upper bound, not a target.

### 16.4 Weight waterfall

Each final shadow weight must be explainable as:

```text
risk anchor
+ PM relative-preference tilt
+/- reliability adjustment
- uncertainty adjustment
- cluster concentration adjustment
- factor/risk adjustment
- event adjustment
- transaction-cost/no-trade adjustment
= final shadow target
```

---

## 17. Deterministic feasibility projection

### 17.1 Purpose

The projection finds the nearest lawful portfolio to the pre-target.

A representative objective is:

\[
\min_w
D(w,w^{pre})
+
\lambda_{\Sigma} w^\top \Sigma w
+
\lambda_{tail} TailLoss(w)
+
\lambda_{turn}\|w-w_0\|_1
+
\lambda_{cost} Cost(w-w_0)
\]

subject to canonical constraints.

### 17.2 Constraint families

```text
long only
no leverage
weights plus cash equal one
single-name limits
sector and industry limits
theme and relationship-cluster limits
factor and beta limits
liquidity limits
event-risk limits
scenario-loss limits
turnover and no-trade bands
identity and priceability
PM weight ranges
Grey Deer policy ceiling
```

### 17.3 Feasibility states

```text
FEASIBLE
FEASIBLE_REDUCED_TILT
CARRY
ABSTAIN
INFEASIBLE
INVALID
```

`FEASIBLE_REDUCED_TILT` means the requested PM tilt was reduced to satisfy stability or risk.

`CARRY` means preserve the current shadow book.

`ABSTAIN` means no lawful target can be formed with current evidence.

`INFEASIBLE` reports conflicting constraints.

`INVALID` reports contract or identity failure.

### 17.4 Optimizer boundary

A convex solver is a deterministic actuator over accepted inputs and constraints.

It is not:

- a source of expected returns;
- a market forecaster;
- a promotion authority;
- a risk-truth owner;
- a reason to hide infeasibility.

---

## 18. Weight-stability gate

### 18.1 Required perturbations

Before accepting a shadow target, perturb:

- PM ranks;
- pairwise preferences;
- reliability weights;
- evidence-family contribution;
- covariance window;
- covariance estimator;
- hierarchy linkage;
- transaction costs;
- risk-policy boundary;
- one ambiguous source at a time.

### 18.2 Measured outputs

```text
L1 weight change
turnover change
top-holding rank changes
cluster-budget changes
scenario-loss changes
cash change
constraint-binding changes
```

### 18.3 Stability states

```text
HIGH
MEDIUM
LOW
UNMEASURABLE
```

A LOW or UNMEASURABLE target cannot silently proceed unchanged.

The system must:

- reduce alpha intensity;
- widen uncertainty;
- choose a more stable anchor;
- stage the research decision;
- carry the current book;
- or abstain.

### 18.4 User-visible explanation

The product must say what made the target unstable.

Examples:

- "NVDA and AVGO swap materially under small expected-edge changes."
- "Energy cluster weight depends on one low-confidence covariance estimate."
- "The target becomes cash-heavy when the Grey Deer ceiling tightens one state."
- "The selected biotech sleeve is dominated by one event-risk assumption."

---

## 19. Gross exposure and cash

### 19.1 Grey Deer ceiling

Grey Deer supplies canonical market state, hazard, and policy evidence.

Portfolio maps accepted policy into a book-specific gross ceiling.

Portfolio may choose less gross.

Portfolio may not use a local market fusion to exceed the canonical ceiling.

### 19.2 Unknown-protective behavior

If Grey Deer is missing, stale, invalid, or unresolved:

```text
market_risk_state = UNKNOWN_PROTECTIVE
```

This can only:

- carry;
- reduce;
- abstain;
- cap new risk.

It cannot loosen constraints.

### 19.3 Opportunity-conditioned gross

Gross is a function of:

- lawful Grey Deer ceiling;
- number of independent opportunities;
- calibrated opportunity quality;
- uncertainty;
- dispersion;
- liquidity;
- event concentration;
- best rejected alternatives;
- cash opportunity cost.

Exact functional form remains empirical.

### 19.4 Cash contract

Cash carries:

```text
weight
yield assumption
benchmark opportunity cost
scenario value
deployment trigger
PM rationale
best rejected alternative
```

The PM must compare cash with at least the best rejected opportunity.

A large cash weight cannot be described merely as prudence.

### 19.5 No forced investment

V3 does not force full investment when qualified opportunities are absent.

It forces explicit reasoning and attribution.

---

## 20. Scenario architecture

### 20.1 Deterministic scenario library

Initial scenario classes include:

- rates up;
- rates down;
- growth scare;
- growth acceleration;
- inflation reacceleration;
- oil/geopolitical shock;
- liquidity contraction;
- credit stress;
- USD surge;
- China policy/growth shock;
- semiconductor/AI drawdown;
- broad volatility and correlation shock.

### 20.2 Scenario inputs

Scenario sensitivity comes from:

- factor exposure;
- historical stress behavior;
- sector/theme membership;
- idiosyncratic risk;
- Neural Web relationships;
- explicit event exposure;
- current book structure.

### 20.3 LLM scenario role

The root PM or specialist may:

- identify a missing scenario;
- describe a causal transmission path;
- identify key assumptions;
- propose a shadow scenario;
- explain nonlinear or event-specific behavior.

It may not at birth:

- assign a binding scenario probability;
- erase deterministic stress loss with narrative optimism;
- originate capital policy;
- override Grey Deer.

---

## 21. Decision clocks and thesis state

### 21.1 Four clocks

| Clock | Typical horizon | Governs |
|---|---:|---|
| Strategic thesis | 3-12 months | Business and industry thesis |
| Tactical allocation | 2-12 weeks | Relative opportunity and target range |
| Execution | 1-10 sessions | Entry timing and no-trade state |
| Emergency sentinel | intraday | Halt, identity, stale data, severe risk |

### 21.2 Thesis states

```text
CREATED
STRENGTHENED
WEAKENED
CATALYST_APPROACHING
CATALYST_RESOLVED
FALSIFIER_WATCH
PARTIALLY_INVALIDATED
FULLY_INVALIDATED
CLOSED
```

A tactical price move cannot silently rewrite a strategic thesis.

A thesis update records:

- prior state;
- new evidence;
- changed assumptions;
- changed probability or uncertainty;
- changed horizon;
- changed action;
- whether the change affects construction.

### 21.3 Exit law

An exit requires one of:

- explicit PM EXIT with evidence;
- hard deterministic safety condition;
- instrument or mandate violation;
- exact thesis falsifier;
- separately accepted risk or settlement rule.

Omission remains not-a-sale.

---

## 22. Execution methodology

### 22.1 Core V3 comparison

The first V3 constructor experiment uses the same:

- decision cutoff;
- market calendar;
- priceability;
- execution assumption;
- transaction-cost assumption;
- marking convention

as the V2 comparison.

This isolates selection and construction.

### 22.2 Staged execution is later

Starter positions, tranches, confirmation, and staged exits are separate ablations.

They cannot enter the first V3 target-generation comparison because that would confound:

- selection;
- sizing;
- entry timing;
- execution.

### 22.3 Canonical settlement reuse

Any future executable V3 target must enter through:

- existing target identity;
- existing pending-target owner;
- existing settlement;
- existing fill receipt;
- existing mark and NAV writer.

No new order queue or fill ledger is permitted.

---

## 23. Learning and evaluation

### 23.1 Three learning levels

**Forecast calibration**

- probability calibration;
- Brier score;
- rank information coefficient;
- forecast error;
- interval coverage;
- confidence reliability;
- effective independent sample.

**Portfolio attribution**

- benchmark;
- cash and gross;
- market beta;
- style and macro factors;
- sector allocation;
- theme allocation;
- stock selection;
- PM selection;
- constructor sizing;
- entry timing;
- exit timing;
- transaction costs;
- residual.

**Policy experimentation**

- discovery;
- shadow hypothesis;
- preregistration;
- forward evidence;
- independent review;
- explicit promotion or demotion.

### 23.2 No self-promotion

A lesson, claim, role, model, parameter, or policy cannot promote itself.

Promotion requires:

- sufficient forward evidence;
- accepted methodology;
- no unresolved integrity failure;
- independent review;
- explicit authority decision.

### 23.3 Effective sample

The evaluator must not treat many same-day names or overlapping horizons as independent samples.

It records:

- decision-date clusters;
- overlapping windows;
- market regimes;
- issuer concentration;
- factor concentration;
- effective sample size.

### 23.4 Policy generation

Every material policy change creates a new generation.

Outcomes are stratified by generation.

A changed prompt, model, constructor, data contract, or risk policy cannot silently pool with prior evidence.

### 23.5 V2 preservation

V3 shadow evaluation never resets, edits, or appends to the V2 live cohort as if the policies were one generation.

---

## 24. Sequential experiment program

### 24.1 Experiment 1 — constructor quality

Hold the selected set fixed.

Compare:

1. current coarse allocator;
2. equal weight;
3. risk anchor;
4. risk anchor plus bounded PM tilt;
5. direct expected-return optimizer challenger.

Primary questions:

- Which method is most stable?
- Which method avoids hidden concentration?
- Which method improves risk-adjusted outcomes net of cost?
- Does the PM tilt add value over the risk anchor?
- Does direct expected-return optimization earn any authority?

### 24.2 Experiment 2 — research quality

Hold the winning constructor fixed.

Compare:

1. root PM with compiled snapshot only;
2. root PM plus adaptive specialist research;
3. no Neural Web context;
4. no Prophet context;
5. deterministic candidate-ordering control.

Primary questions:

- Which research layer changes selection?
- Which improves calibration?
- Which adds independent stock-selection contribution?
- Which only adds cost or duplicated narrative?

### 24.3 Experiment 3 — execution quality

Hold selected names and target weights fixed.

Compare:

1. next-open target;
2. no-trade bands;
3. staged entry;
4. staged exit.

### 24.4 Experiment 4 — full V3 challenger

Only after component attribution is interpretable:

```text
V2 live policy
versus
complete V3 shadow policy
```

### 24.5 Multiple comparisons

The program preregisters:

- primary metric;
- secondary metrics;
- sample floors;
- decision clusters;
- horizons;
- costs;
- demotion criteria;
- comparison family.

A winner is not selected by whichever metric looks best after the fact.

---

## 25. Promotion ladder

### 25.1 Source acceptance

Source can merge only after:

- exact-head tests;
- owner/collision proof;
- independent review;
- current-base integration proof;
- final Sol adjudication.

Source merge establishes at most:

```text
BUILT_NOT_PROVEN / PRODUCTION_INERT
```

### 25.2 Shadow activation

Shadow activation requires:

- installed source identity;
- separate shadow storage;
- zero active-registry membership;
- no live pending-target route;
- one real snapshot-to-shadow-target journey;
- negative controls proving no settlement effect;
- rollback/disarm.

### 25.3 Twenty-session checkpoint

Evaluate only:

- data completeness;
- provider completion;
- decision reproducibility;
- execution correctness;
- zero authority violations;
- stability;
- attribution completeness.

No alpha claim.

### 25.4 Sixty-session checkpoint

Evaluate:

- operational reliability;
- extreme cash and concentration;
- constructor stability;
- costs and turnover;
- claim and forecast ledger completeness;
- first falsification signals.

No annual-horizon claim.

### 25.5 One-hundred-twenty-six-session review

Earliest serious paper-policy review, requiring:

- at least twenty material decisions;
- sufficient matured 21- and 63-session episodes;
- at least eight independent date clusters;
- more than one meaningful market condition;
- complete factor and cash attribution;
- no severe integrity or authority failure.

### 25.6 Two-hundred-fifty-two-session review

Earliest review for annual-horizon claims.

### 25.7 Promotion criteria

A future cutover requires evidence of:

1. positive net-of-cost active return;
2. positive stock-selection contribution;
3. results not explained solely by cash, beta, sector, momentum, value, quality, or low volatility;
4. acceptable drawdown and tail behavior;
5. better calibrated views;
6. acceptable turnover;
7. perturbation stability;
8. reliable completion;
9. complete provenance and correction lineage;
10. zero authority or settlement breach;
11. successful production-style shadow operation;
12. explicit Chairman approval.

---

## 26. Product experience

### 26.1 PM Today

The primary V3 shadow cockpit must answer in the first viewport:

```text
What changed?
Can the shadow PM act?
What is the current risk ceiling?
Which decisions need attention?
How complete is the snapshot?
What is the proposed gross and cash?
How stable is the target?
```

### 26.2 Opportunity view

For each candidate:

- why surfaced;
- current state;
- evidence families;
- contradictions;
- research priority;
- selected/rejected/held;
- relationship cluster;
- factor and event exposure;
- exact source receipts.

### 26.3 Research view

For each material claim:

- proposition;
- method;
- evidence;
- independence family;
- probability and uncertainty;
- contradictions;
- falsifier;
- expiry;
- model/role generation.

### 26.4 Portfolio view

Show:

- current shadow book;
- risk anchor;
- PM tilt;
- projected target;
- cash;
- factors;
- sectors and themes;
- relationship clusters;
- scenarios;
- turnover;
- costs;
- stability;
- weight waterfall.

### 26.5 Learn view

Show:

- calibration;
- selection contribution;
- sizing contribution;
- timing contribution;
- costs;
- regime dependence;
- policy generation;
- open experiments;
- promotion and demotion state.

### 26.6 Real states

The product must render:

```text
complete
partial
blocked
invalid
no-change
correction-detected
provider-unavailable
constructor-infeasible
target-low-stability
carry
abstain
```

A spinner is not a state.

A blank panel is not a null contract.

---

## 27. Failure matrix

| Failure | Required behavior |
|---|---|
| Root PM unavailable | Carry shadow book; originate no new target |
| One non-load-bearing specialist fails | Continue with gap and higher uncertainty |
| Load-bearing specialist evidence missing | Refuse affected decision or carry |
| Grey Deer stale/missing | `UNKNOWN_PROTECTIVE`; never loosen |
| Snapshot partial | Explicit partial state; no complete claim |
| Same-date correction | New generation; no mixed page |
| R-ORTH unavailable | Do not assume independence; reduce tilt |
| Factor model unavailable | Conservative clusters and caps; never un-cap |
| Constructor infeasible | Carry or nearest reduction-only feasible target |
| Weight stability low | Reduce tilt, carry, or abstain |
| Instrument identity uncertain | Reject new ADD; held line only under existing safety law |
| New-name quote unavailable | Reject or park ADD |
| Held-name quote unavailable | Carry safely; never accidental exit |
| Settlement effect unknown | Same-carrier reconciliation; no blind retry |
| Evaluator failure | Preserve portfolio truth; repair evaluator separately |
| Learning sample insufficient | No promotion |
| Weaker fallback model used | Separate model-generation evidence |
| Specialist claims conflict | Increase uncertainty; preserve contradiction |
| External web evidence lacks provenance | Research-only; cannot cross construction boundary |
| Cash rises materially | Require opportunity-cost and best-reject explanation |
| Shadow writer attempts live path | Hard refusal and incident |
| Snapshot identity mismatch | Invalid; no target |
| Policy generation mismatch | Invalid; no pooled evidence |
| Rights state unknown | Exclude affected source or block decision |

---

## 28. Security, privacy, rights, and model safety

### 28.1 Paper-only

V3 remains paper-only.

It creates no broker connection, live-capital authority, or customer trade instruction.

### 28.2 Prompt and retrieved-data boundary

Retrieved filings, websites, news, model outputs, and repository text are untrusted data.

They cannot grant:

- tool authority;
- portfolio authority;
- source-write permission;
- deployment permission;
- model-promotion authority.

### 28.3 Rights

Every Decision Snapshot source carries a rights class.

Rights-unknown or prohibited data is excluded.

Competitor workflows may inform original design, but proprietary corpora, weights, text, assets, branding, or private data are not copied.

### 28.4 Secrets

No claim, snapshot, decision, or evaluation artifact contains:

- credentials;
- provider tokens;
- private endpoints;
- local home paths;
- session tokens;
- account secrets.

### 28.5 Model identity

Every Claim and PM View records:

- provider realm;
- model;
- reasoning mode;
- prompt/role generation;
- tool profile generation;
- fallback state.

A fallback answer does not inherit the primary model's reliability.

### 28.6 No hidden authority

The language layer cannot smuggle authority through fields named:

- confidence;
- conviction;
- probability;
- recommendation;
- required;
- validated;
- target.

Authority is defined by accepted contracts and consumers.

---

## 29. Implementation DAG

```text
Architecture spec accepted
    |
    +--> P0 current non-lossy rotation consumer repair through #548 owner
    |
    +--> P1 current Grey Deer -> Portfolio consumption qualification
    |
    v
V3-S0 Decision Snapshot
    |
    v
V3-S1 PM View + Claim contracts
    |
    v
V3-S2 risk-anchor shadow target
    |
    v
V3-S3 reliability / independence + bounded alpha tilt
    |
    v
V3-S4 deterministic feasibility projection + stability gate
    |
    v
V3-S5 complete attribution and experiment harness
    |
    v
V3-S6 adaptive specialist research
    |
    v
V3-S7 execution ablations
    |
    v
V3-S8 full shadow challenger
    |
    v
independent long-window review
    |
    v
separate Chairman cutover decision
```

Waves that are genuinely path- and authority-disjoint may proceed in parallel after their own gates.

No downstream wave may fabricate a missing upstream contract.

---

## 30. First vertical: V3-S0 Decision Snapshot

### 30.1 User and machine capability

A real current decision cycle produces one immutable, bounded, correction-safe snapshot of:

- book state;
- market/risk state;
- opportunity context;
- source coverage;
- clocks;
- correction generations.

The snapshot is readable by a machine and inspectable by an operator.

It cannot submit or settle a target.

### 30.2 Why S0 is first

Every later V3 capability depends on knowing exactly what information was available.

Without S0:

- research cannot be reproduced;
- PM decisions cannot be fairly graded;
- same-date corrections can contaminate evaluation;
- model generations cannot be compared;
- target stability cannot be interpreted;
- a shadow winner can be hindsight leakage.

### 30.3 Required integration boundaries

S0 reuses:

- current account and portfolio state;
- current Macro adapter/readers;
- accepted source contracts;
- current identity and authority maps;
- current canonical clocks;
- current shadow/evaluation roots.

S0 does not:

- call a model;
- create an agent;
- create a database;
- create a scheduler;
- add a registry book;
- touch settlement;
- change V2 behavior.

### 30.4 Minimum real journey

```text
real current source artifacts
-> bounded snapshot composition
-> exact content identity
-> explicit complete/partial/blocked state
-> correction-safe readback
-> visible source/coverage inspector
```

### 30.5 Negative proof

Acceptance must prove:

- no live target written;
- no pending target written;
- no fill written;
- no account mutation;
- no provider call;
- no hidden current-time substitution;
- no stale source cast as calm;
- no same-date generation mixing;
- no path traversal or caller-selected arbitrary file read;
- no unbounded payload.

### 30.6 Dependency on PR #548

If #548 remains red or unmerged, S0 may include rotation only as an explicit partial dependency.

S0 must not duplicate #548's reader.

A later accepted #548 generation can satisfy that source slot without changing S0's owner.

---

## 31. Acceptance and production proof

### 31.1 Architecture acceptance

This spec is accepted when:

- Chairman intent is preserved;
- owner map matches current canonical source;
- no duplicate system is introduced;
- the methodology is internally consistent;
- falsifiers are explicit;
- capability claims remain honest;
- the first vertical is bounded.

### 31.2 Source acceptance per implementation wave

Each wave requires:

- tests-first discriminators;
- exact source/collision census;
- focused and owning-neighbor tests;
- mutation or negative controls;
- clean diff;
- independent review;
- current-base proof;
- capability-state honesty.

### 31.3 Installed proof

Source merge is not installation.

Installed proof requires:

- exact merged SHA;
- installed configuration identity;
- active/disarmed state;
- rollback;
- real canonical data;
- readback.

### 31.4 Product proof

User-facing work requires:

- actual browser journey;
- real complete and degraded states;
- dark/light and responsive evidence where applicable;
- no console/page/request errors;
- visible source freshness and uncertainty;
- no fixture represented as production.

### 31.5 V3 production-style shadow proof

Before long-window evaluation:

1. one real Decision Snapshot;
2. one real root PM View;
3. one real shadow target;
4. one real isolated shadow-account mark;
5. one correction or no-change cycle;
6. one provider failure carry cycle;
7. one low-stability reduction or abstention;
8. zero live V2 effects;
9. independent evidence review.

---

## 32. Architecture falsifiers

The architecture must reopen if any of these are proven:

1. The existing shadow owner cannot safely isolate V3 without a new active book.
2. Grey Deer structurally cannot provide a book-critical market input after accepted qualification.
3. The risk-first anchor is consistently less stable than a simpler control.
4. Bounded PM tilts add no incremental value after sufficient forward evidence.
5. Exact expected-return optimization demonstrates robust, stable, independently reviewed superiority.
6. Specialist research adds cost but no independent selection or calibration value.
7. Claim contracts cannot preserve useful reasoning without unacceptable information loss.
8. Decision Snapshot latency makes the cycle operationally unusable.
9. Current source rights prevent lawful use of a load-bearing evidence family.
10. Factor and relationship coverage is too weak to support claimed portfolio risk.
11. Shadow results are dominated by cash, beta, sector, or style rather than selection.
12. The system cannot explain its weight waterfall.
13. Small input perturbations continue to cause unstable targets after tilt reduction.
14. The architecture requires a duplicate lifecycle, store, queue, or market-truth plane.
15. A material authority breach occurs.

A falsifier produces a revised architecture decision, not a hidden parameter patch.

---

## 33. What is frozen versus empirical

### 33.1 Frozen

- owner map;
- one live US book;
- V3 shadow-first;
- Decision Snapshot;
- one root PM;
- claim-not-vote research;
- empirical reliability and independence;
- risk-first anchor;
- bounded alpha tilt;
- deterministic projection;
- stability gate;
- explicit cash;
- Grey Deer ceiling;
- canonical settlement reuse;
- sequential experiments;
- factor-aware attribution;
- no automatic promotion;
- no duplicate systems.

### 33.2 Empirical

- exact frontier model;
- exact specialist roster;
- prompt wording;
- number of holdings;
- name, sector, and cluster caps;
- gross floors and ceilings;
- alpha intensity;
- reliability priors;
- sample thresholds beyond the broad ladder;
- HRP/HERC/ERC variant;
- covariance window and estimator;
- hierarchy linkage;
- scenario shock magnitudes;
- scenario probabilities;
- event-risk budgets;
- execution tranche geometry;
- no-trade thresholds;
- turnover penalty;
- UI layout.

Freezing those now would replace one arbitrary portfolio policy with another.

---

## 34. Capability-state conclusion

```text
architecture: ARCHITECTURE_FREEZE_CANDIDATE
implementation: NOT_BUILT
installation: NONE
shadow activation: NONE
live V2 effect: NONE
production portfolio effect: NONE
V3 overall: SPEC_ONLY
```

This record is not evidence that the methodology creates alpha.

It is evidence that the company has a coherent, owner-compatible, falsifiable method for building and proving the next portfolio manager without shrinking ambition or endangering the current live paper book.

---

## 35. Operator handoff

**Mission**

Build Mastermind Portfolio V3 as a risk-first, evidence-independent, alpha-tilted shadow portfolio manager while preserving one live `autonomous` book and the canonical mutation planes.

**Why it matters**

V2 restored accountability and safety but compresses useful PM judgment into ordinal sizing and cannot establish whether the manager, constructor, or intelligence estate creates real stock-selection value.

**Authority precedence**

1. Current Chairman direction.
2. Protected Mastermind Charter and strategic/authority law.
3. This accepted architecture freeze.
4. Existing V2 live ruling and owner contracts.
5. Current source and evidence.

**Verified state and recent carriers**

- Protected Mastermind: `f249802eab3695ff24c9a903798899466c444252`.
- Bounded Macro snapshot: `fc59066581be1a52e4c89a8e3e1ba2c39796419a`.
- V2 live `autonomous`: preserve.
- PR #548: existing non-lossy rotation-consumer owner; red/hold.
- PR #398: existing open Outcome Learning candidate; not protected.

**Scope**

- Decision Snapshot;
- claims and PM View;
- risk anchor;
- bounded alpha tilt;
- deterministic projection;
- stability;
- attribution;
- adaptive research;
- experiments;
- shadow product.

**Non-goals**

- no second live book;
- no broker;
- no new market-risk truth;
- no direct LLM weights;
- no committee votes;
- no universal alpha score;
- no duplicate settlement or lifecycle;
- no guaranteed-return claim.

**User journey**

```text
PM Today
-> Opportunity
-> Research
-> Portfolio
-> Learn
```

**Data/time/null/correction behavior**

- observed and known clocks separate;
- same-date corrections create new generations;
- null is not calm or zero;
- partial remains partial;
- stale never loosens risk;
- snapshots are immutable.

**Deterministic versus model method**

Deterministic:

- source acquisition;
- identity;
- snapshot composition;
- coverage;
- reliability calculations;
- risk anchor;
- projection;
- stability;
- attribution;
- state mutation.

Model:

- comparative thesis;
- causal reasoning;
- bounded claims;
- adversarial challenge;
- pairwise preference;
- uncertainty articulation;
- scenario proposal.

**Failures**

Use the failure matrix in this spec. Unknown effects remain on one carrier. Missing evidence shrinks or blocks. No blind retry.

**Implementation order**

P0/P1 dependencies, then V3-S0 through V3-S8.

**Acceptance and production proof**

Every wave requires source proof, independent review, installation proof where applicable, and real-path product proof. V3 remains shadow until long-window factor-aware evidence and explicit Chairman cutover.

**Stop condition**

Stop at the exact wave's accepted capability and leave the next dependency. Do not call planning, source merge, installation, or green CI full V3 completion.

**Continuation handoff**

After this spec is accepted, invoke the writing-plans procedure and write the exact implementation plan. Do not begin runtime implementation from this records carrier.

---

## 36. References

Canonical repository references:

- `research/MASTERMIND_CHARTER_V2.md`
- `docs/US_BOARD_AUDIT_AND_PORTFOLIO_V2_2026-08-08.md`
- `docs/PORTFOLIO_V2_FORWARD_EVALUATION_2026-08-11.md`
- `portfolio/registry.py`
- `brain/decision_submission.py`
- `bot/autonomous.py`
- `portfolio/forward_evaluation.py`
- `portfolio/shadow_books.py`
- `brain/research_desk.py`
- Macro `agentos/decisions/DEC-PORTFOLIO-CONSUMES-NOT-RECOMPUTES-MARKET-RISK.md`
- Macro `engine/risk_envelope.py`
- Macro `engine/neuralweb/covariance_spine.py`
- Macro `engine/factor_exposure.py`
- Mastermind PR #548
- Mastermind PR #398

Method references to reverify before implementation:

- covariance shrinkage and estimation error;
- hierarchical portfolio construction;
- convex multi-period portfolio planning;
- robust Sharpe comparison;
- backtest overfitting and multiple comparisons;
- decision-focused learning;
- factor-aware attribution of LLM portfolios.

Retrieved external sources remain research references only. They grant no Mastermind authority.
