# 05 — Integration Map, Product Outputs, Falsification, and Source Register

> **FREEZE AUTHORITY NOTICE — FINAL HARDENING**  
> This document is historical design context only and is **not freeze-authoritative**. Any language below that makes continuous survival/hazard the DL-1 primary endpoint, prefers an ex-U.S. confirmation route, requires a DL-1 interaction model or `I − A` contrast, calls `PROSPECTIVE_US_POST_FREEZE` operationally selected before its taxonomy-source gate clears, or otherwise conflicts with the final source/experiment specification is **SUPERSEDED**. `07_DL1_PREREG_DRAFT_FREEZE_READY.md` is the sole experiment authority. `06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md` is the sole owner/source-route authority. Historical text in this file may not be used to loosen, recover, or reinterpret a superseded design choice.

## Integration map

The successor must consume existing owners rather than create competing systems.

| Research object | Existing owner to consume | Successor role |
|---|---|---|
| Peer identity and leave-issuer-out continuity | Prophet Leadership Evidence / engine/group_flow.py | Read-only measurement substrate; validate predictive value |
| Theme identity, PIT membership, ThemeState | GMI Theme Graph | Required substrate for later dynamic-theme replication |
| Published-theme persistence measurements | RPH-0 | Reuse survival / transition semantics; do not reinterpret as alpha |
| Fixed time / grain semantics | Temporal Grain / data-clock owners | Consume fixed horizons; no outcome-optimized timeframe |
| Broad regime | Existing regime owner | Prespecified interaction only |
| Rotation / Sector Pulse observations | Existing rotation owners | Descriptive covariates / challengers where contracts permit |
| Trial / look accounting and outcomes | TrialLedger / Evaluation OS | One-reveal registration; no duplicate ledger |
| Portfolio / ranking decisions | Existing portfolio / Prophet owners | **No authority from research birth** |

### RPH-0 boundary

RPH-0 already measures descriptive persistence of published theme rankings, including top-quartile survival, residency, transition, and rank half-life.

Reuse:

- state-transition semantics;
- survival / residency measurement concepts;
- censoring / half-life language.

Do not infer:

- return alpha;
- stock-selection skill;
- optimal holding period;
- causal theme durability.

The predictive question that remains is whether current independent peer/theme state predicts **future** leader survival or economic durability.

### Prophet Leadership Evidence boundary

Reuse the existing identity-qualified independent-peer observation and continuity infrastructure, especially the distinction between stable peer leadership and same-breadth/new-leader turnover.

Do not create a duplicate peer engine.

### GMI Theme Graph boundary

GMI owns canonical theme identity, PIT membership, correction semantics, and ThemeState.

Trend Persistence must consume those objects. It must not create another theme taxonomy, theme-membership archive, or ThemeState service.

### Temporal Grain boundary

Temporal Grain owns grain / anchor / kernel / data-plane timescale research.

Trend Persistence consumes fixed supported horizons. It must not create a per-name outcome-optimized timeframe selector.

### Outcome / evaluation boundary

Use the existing outcome / evaluation / look-accounting owners. Do not create a second trial registry, outcome ledger, or look-budget mechanism.

---

## Conceptual product outputs if evidence succeeds

These are research concepts, not requested schemas or production contracts.

| Concept | Evidence requirement | Recommended status |
|---|---|---|
| leadership_survival_probability | Calibrated OOS survival model | **Primary candidate** |
| trend_break_hazard | Valid discrete-time hazard model | **Primary candidate** |
| expected_leadership_half_life | Stable survival curve over adequate history | Secondary candidate |
| group_confirmation | Demonstrated A − S increment | Candidate |
| peer_continuity | Existing measurement + predictive validation | Candidate |
| breadth_diffusion_state | Independent incremental evidence or validated mechanism | Context / candidate |
| leader_dependency | Concentration associated with failure after controls | Risk / context candidate |
| pullback_recovery_probability | Separate calibrated path endpoint | Later candidate |
| evidence_quality | Identity / PIT / sample / estimability contract | **Required alongside every probability** |

**STRONG INFERENCE —** Keep these as separate observables and calibrated probabilities. Do not average them into a single 0–100 persistence score unless future evidence establishes a defensible aggregation.

Every eventual output should expose uncertainty and abstain when:

- peer identity is inadequate;
- industry membership is uncertain;
- the group is too small;
- the horizon lacks enough matured observations;
- the model is outside its supported regime;
- evidence quality fails the frozen contract.

---

## Falsification conditions

### Hard closure rules that remain binding

The B2 focal-stock path-shape family remains closed.

The exact eleven-sector C1 construction remains closed.

The already-inspected 2022-07-06 through 2026-06-02 dates do not become fresh confirmatory evidence.

### Independent-peer confirmation falsifier

If a correctly PIT, focal-excluded industry-group model fails to improve leader survival beyond stock-only residual momentum / volatility on genuinely untouched evidence, close the principal static-group peer-confirmation thesis.

### Stock-selection falsifier

If group-only predicts survival but stock+group does not improve stock-only, stop describing group persistence as a stock-selection capability. Preserve it only as group-level timing/context if independently useful.

### Breadth / continuity falsifier

If continuity / breadth effects vanish after common-factor momentum and market-regime controls, interpret them as repackaged factor exposure rather than independent durability information.

### Dynamic-theme generalization falsifier

If a static-group result passes but a later PIT dynamic-theme replication fails, retain the narrower industry result and close the claim that durability generalizes to evolving themes.

### Program-level kill condition

If DL-1 fails on untouched data and the only remaining support comes from options, flows, revisions, themes, or networks that require individually tailored definitions and multiple new licensed datasets, the rational ruling should become:

**KILL / NO FURTHER INVESTMENT**

Do not serially search feature families until something passes.

---

## Final recommendation

**CONTINUE — NARROWED**

The next study should test one claim:

> Does identity-qualified, leave-issuer-out peer continuity and breadth in a point-in-time finer economic group materially improve the predicted survival of a current stock leader beyond its own momentum, residual momentum, beta, and volatility?

It should use:

- **one primary grouping:** GICS industry group;
- **one primary endpoint family:** top-quartile leadership survival with associated state-exit hazard;
- **one frozen feature family:** peer residual strength, peer continuity, breadth/diffusion, and leader dependency;
- **four explicit model views:** stock-only, group-only, additive, and interaction;
- **genuinely new evidence:** independent international PIT history if lawfully available, otherwise prospective post-preregistration U.S. accrual.

The stopping rule is simple:

> If independent group evidence cannot materially improve survival prediction beyond strong own-stock/common-factor controls on untouched data, close the static-group durable-leadership thesis rather than searching for a renamed persistence score.

---

# Internal evidence register

The package is grounded in the current Mastermind / Macro estate inspected by the Deep Research commission. The following references are evidence, not new authority.

## Mastermind — protected source pin 877b1e7f275da0b6d3558d2667778b32d628bf67

- research/TREND_PERSISTENCE_PROTOCOL.md
- research/TREND_PERSISTENCE_READOUT.md
- research/TREND_PERSISTENCE_PREREG_V1.md
- research/TREND_PERSISTENCE_PREREG_V2.md
- research/TREND_PERSISTENCE_PREREG_B2.md
- research/TREND_PERSISTENCE_PREREG_C1.md
- research/data/trend_persistence_b2_result.json
- research/data/trend_persistence_c1_result.json
- research/trend_persistence_group.py — measurement context only
- PR #1155
- PR #1226
- PR #1230
- PR #1252

Pinned source root:

https://github.com/mastermindx-market-intelligence/Mastermind/tree/877b1e7f275da0b6d3558d2667778b32d628bf67

## Macro / Agent OS

The Deep Research commission inspected:

- agentos/workstreams/WS-TREND-PERSISTENCE.md
- agentos/decisions/DEC-TREND-PERSISTENCE-STOPS-AT-WAVE-B.md
- agentos/decisions/DEC-TREND-PERSISTENCE-STOPS-AT-WAVE-C.md
- 2026-10-03, 2026-10-04, and 2026-10-05 Trend Persistence handoffs
- research/prophet_v4/leadership_evidence_v1/README.md
- existing engine/group_flow.py independent-peer / continuity work and its research contracts
- Macro PR #7064 — held RPH-0 published-theme-leadership-persistence research carrier
- current Temporal Grain Intelligence workstream and relevant research
- agentos/workstreams/WS-GMI-THEME-GRAPH.md
- current Theme Graph PIT-membership / ThemeState architecture
- relevant Sector Pulse, rotation, basket archive, theme-history, Prophet leadership, and relative-strength research
- LIMITATIONS.md persistence / rotation limitations

The exact Macro source identities should be repinned by the later implementation/research CEO before any modifying or outcome-reading commission. This package does not claim that a research snapshot grants future authority.

---

# External source register

## Momentum / continuation / industry / network

- Moskowitz & Grinblatt, “Do Industries Explain Momentum?”  
  https://onlinelibrary.wiley.com/doi/full/10.1111/0022-1082.00146

- Grundy & Martin, “Understanding the Nature of the Risks and the Source of the Rewards to Momentum Investing”  
  https://academic.oup.com/rfs/article-abstract/14/1/29/1587146

- Ehsani & Linnainmaa, “Factor Momentum and the Momentum Factor”  
  https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13131

- Hou, “Industry Information Diffusion and the Lead-lag Effect in Stock Returns”  
  https://academic.oup.com/rfs/article-abstract/20/4/1113/1615954

- Cohen & Frazzini, “Economic Links and Predictable Returns”  
  https://onlinelibrary.wiley.com/doi/10.1111/j.1540-6261.2008.01379.x

- Rouwenhorst, “International Momentum Strategies”  
  https://onlinelibrary.wiley.com/doi/full/10.1111/0022-1082.95722

- Moskowitz, Ooi & Pedersen, “Time Series Momentum”  
  https://doi.org/10.1016/j.jfineco.2011.11.003

- Blitz, Huij & Martens, “Residual Momentum”  
  https://www.sciencedirect.com/science/article/abs/pii/S0927539811000041

## Information diffusion / attention / revisions

- Da, Gurun & Warachka, “Frog in the Pan: Continuous Information and Momentum”  
  https://academic.oup.com/rfs/article-abstract/27/7/2171/1578455

- Hong, Lim & Stein, “Bad News Travels Slowly”  
  https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00206

- Hung, Li & Wang, “Post-Earnings-Announcement Drift in Global Markets”  
  https://academic.oup.com/rfs/article-abstract/28/4/1242/1928671

## Demand / volume / crash / positioning

- Lee & Swaminathan, “Price Momentum and Trading Volume”  
  https://onlinelibrary.wiley.com/doi/pdf/10.1111/0022-1082.00280

- Wermers, “Mutual Fund Herding and the Impact on Stock Prices”  
  https://onlinelibrary.wiley.com/doi/abs/10.1111/0022-1082.00118

- Daniel & Moskowitz, “Momentum Crashes”  
  https://doi.org/10.1016/j.jfineco.2015.12.002

- Diether, Lee & Werner, “Short-Sale Strategies and Return Predictability”  
  https://academic.oup.com/rfs/article-abstract/22/2/575/1596032

## Historical taxonomy / relationship-source planning

- S&P Dow Jones Indices, GICS overview  
  https://www.spglobal.com/spdji/en/education/article/talkingpoints-an-overview-of-sp-500-sector-indices-and-25-years-of-gics/

- S&P Global differentiated data  
  https://www.spglobal.com/market-intelligence/en/solutions/differentiated-data

- FactSet Revere industry / supply-chain history  
  https://insight.factset.com/category-tools-and-tips-factset-reveres-industry-classification-supply-chain-and-hierarchy-data-can-now-be-used-in-your-templates-and-custom-reports

- LSEG business and industry classifications  
  https://www.lseg.com/en/data-analytics/financial-data/reference-data/classifications/business-and-industry-classifications

Public vendor pages are sufficient to identify candidate source families, not to infer Mastermind pricing, entitlements, redistribution rights, storage rights, or model-use permissions.
