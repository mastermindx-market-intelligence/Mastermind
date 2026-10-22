# MastermindX Research — Point-in-Time Expectations & Theme Intelligence

## Deep-census reassessment: reuse first, upgrade overlaps, build only residual gaps

**Status:** RESEARCH / ARCHITECTURE ONLY. This document authorizes no data purchase, vendor contact, production ingestion, deployment, portfolio/trading behavior change, source-authority expansion, or new control plane.  
**Protected Mastermind source pin:** `mastermindx-market-intelligence/Mastermind@715e6ac01f16ef446dc6eba3c215454d0eddb54d`  
**Protected skillpack at that pin:** `mastermind.sol_skillpack.v1` / `1.0.1` / bootstrap major `1`  
**Macro census pin used for relevant-file reads:** `mastermindx-market-intelligence/macro@b0ba2f79c25ac7892c48b24f14a167781e16247b`  
**Macro decision-boundary recheck:** current master advanced to `80fd8a1b993afe6109d289cb6916809dde70c830`; the one-commit diff touches only Entry Radar catalyst files and does not change the expectation/theme files cited below.  
**Terminal census pin:** `mastermindx-market-intelligence/mastermind-terminal@601db3352044535e327a7700221db062f5eca053`  
**Research Vault identity resolved:** `mastermindx-market-intelligence/executive-dr-vault`; targeted searches found no expectation/revision/theme implementation owner there.  
**Prior Mastermind study carrier:** PR #1223, branch `research/pit-analyst-revisions-study-2026-10-04`.  
**Direct overlapping Macro research carrier:** PR #8402, `research: harden Commission 2 PIT analyst expectations audit`, OPEN and UNMERGED at census time.  
**Direct overlapping Macro source-proof carrier:** PR #8312, `research: initiate Information→Price and complete native SRC-A1 proof`, OPEN/DRAFT and UNMERGED at census time.

> **Major correction to the first version of this study:** the original recommendation was directionally right about point-in-time expectations, but it substantially overestimated how much greenfield architecture was needed. The deep census found an already-established Expectation Market Dynamics program, an accepted physical owner for prospective EPS/revenue observations, bitemporal/correction contracts, a vendor bake-off, a frozen evaluation preregistration, a mature theme-graph owner with local-theme identity, and existing research/outcome infrastructure. The new plan is therefore **upgrade-first and integration-first**, not warehouse-first.

---

# A. Executive conclusion — what changed after the census

The highest-value problem is **not** “Mastermind needs an analyst-revisions warehouse” and it is **not** “Mastermind needs a dynamic-subtheme graph.”

Both statements are now too broad.

The deep census found that Mastermind's estate already contains:

1. a current earnings-expectation consumer in protected Mastermind;
2. a prospective expectation source owner in Macro with immutable observation/attempt artifacts, explicit clock separation, correction lineage, missingness, rights state, fiscal-period anchors and mutation gates;
3. legacy revision snapshot/history artifacts already consumed by theme-revision logic;
4. a separate monthly recommendation-revision lane;
5. a frozen Expectation Market Dynamics architecture with explicit no-rebuild law;
6. a completed public vendor research wave (`VEND-0`) whose result is already `SAMPLE_REQUIRED / PROBE_FURTHER`;
7. a frozen evaluation preregistration (`K3E-EVAL-0-V1`);
8. a bitemporal GMI Theme Graph with canonical/local theme identity, evidence, belief-time history, local-theme nodes, and a merged `theme_state/v1` producer implementation;
9. a Company Theme Exposure projection and a Terminal company-theme-context API;
10. existing PIT decision-history, outcome, rank-IC/HAC/FDR, walk-forward and trend-persistence research machinery.

Therefore the revised capability thesis is:

> **Finish, prove, and consume the existing expectation and theme owners; add only the missing institutional history/detail and cross-owner read models that cannot be obtained from the current estate.**

## What should be built next

The P0 capability is no longer a new canonical warehouse. It is a **thin, deterministic, owner-preserving expectation read model over the existing K3E/SRC-A1 source plane**, but only after the incumbent SRC-A1 proof lane is reconciled.

The next implementation owner must first inspect the outcome of Macro PR #8312. If its proof is accepted and protected, the first genuinely new slice is `EXP-1`: a read-only expectation surface over the existing `data/revisions/expectation_observations.parquet` / `expectation_attempts.parquet` source-owner records. If #8312 is rejected or remains unproven, the first slice is **repair/prove the existing SRC-A1 owner**, not create another store.

For themes, the next action is **not** to create `theme_membership_v1`. GMI already owns this territory. Mastermind should wait for/reuse the accepted GMI D2/W3B/W3C contracts and consume `theme_state/v1` / Company Theme Exposure through existing projections. Open GMI PRs must be reconciled rather than duplicated.

## What should be deleted from the old plan

Delete as new-build tasks:

- a new security/entity identity store;
- a new source-receipt store;
- a new raw estimate-history store;
- a new consensus truth store;
- a new actual-results store;
- a new theme-membership store;
- a new theme graph;
- a new validation/outcome ledger;
- a new Decision Snapshot implementation inside this program;
- a second broad vendor landscape study;
- a new LLM theme-classification control plane.

## What remains genuinely missing

The residual gaps are narrower and more valuable:

1. **accepted production proof of the existing prospective expectation source**;
2. **a deterministic expectation read model (`EXP-1`)** over that source;
3. **mature historical institutional PIT expectations** if current prospective history is insufficient for the intended empirical questions;
4. **analyst-level contributor history/identity** only if a sample proves incremental value over PIT consensus;
5. **cross-source correction/vintage validation** for any institutional source;
6. **incremental predictive validation** against existing SUE, price, news, options, fundamentals, themes and macro;
7. **accepted GMI membership lifecycle / ThemeState production semantics** where open GMI work is still incomplete;
8. **Mastermind-side consumption** of accepted K3E/GMI outputs without inventing new authority.

---

# B. Deep current-state census

## B1. Protected Mastermind

| Capability | Exact owner / evidence | State from this census | Reuse ruling |
|---|---|---|---|
| Earnings expectation risk lane | `portfolio/held_risk.py::_lane_earnings_expectation`; tests in `tests/test_held_risk.py` | **BUILT_NOT_PROVEN** from source/test census | **EXTEND CONSUMPTION, do not replace.** It already reads SUE/PEAD-style state plus `revisions.est_chg_30d`, `net_up_30d`, breadth and analyst count fixtures. |
| Per-name evidence matrix | `portfolio/lenses.py` | **BUILT_NOT_PROVEN** | **KEEP.** New expectation evidence must remain an inspectable lens/family, not an opaque fused score. |
| Decision-time signal history | `brain/signal_history.py` | **BUILT_NOT_PROVEN** | **KEEP / later extend.** This is the existing KEEP-FIRST decision-time history owner. |
| Outcome/calibration join | `brain/outcome_ledger.py`, `brain/outcomes` | **BUILT_NOT_PROVEN** | **KEEP.** No new outcome ledger. |
| Cross-sectional validation | `portfolio/predictions.py` | **BUILT / research-used** | **KEEP / GENERALIZE.** It already handles entry-date clustering, non-overlapping windows and rank-IC/HAC-style inference. |
| Survivorship-safe price substrate | `loop/single_name_panel.py` | **BUILT** | **KEEP.** It unions deep + delisted names and preserves PIT membership outside the price assembler. |
| PIT fundamentals research | `loop/fundamentals.py` | **BUILT / research** | **KEEP.** Reuse its causal/as-of discipline; do not create a separate fundamental actuals owner. |
| Research LLM lane | `brain/research_desk.py` | **BUILT_NOT_PROVEN** | **KEEP, narrow role.** It can propose hypotheses/themes but cannot own numeric PIT eligibility or source truth. |
| Physical bottleneck reasoning | `brain/bottleneck.py` | **BUILT_NOT_PROVEN** | **KEEP.** It is already display-only and anchored to observed RS; do not create another bottleneck/theme reasoning organ. |
| Rotation measurement | `brain/rotation_tensor.py` | **BUILT_NOT_PROVEN** | **KEEP.** It already provides causal price/breadth/churn/flow rotation measurements with no sizing authority. |
| Trend persistence protocol | `research/TREND_PERSISTENCE_PROTOCOL.md` | **ACTIVE RESEARCH LAW** | **KEEP.** It explicitly says group persistence must reuse existing owners and dynamic subthemes must consume Macro/GMI once PIT membership is stable. |
| Trend persistence harness | `research/trend_persistence_panel.py`, `trend_persistence_walkforward.py`, V2/B2 results | **PROVEN AS A RESEARCH INSTRUMENT** | **KEEP / reuse for methodology.** V2 confirmed 29 drawdown tests; B2 found no incremental model value over volatility-aware baselines, proving the harness can kill attractive-looking signals. |
| Group persistence Wave C | `research/TREND_PERSISTENCE_PREREG_C1.md` | **SPEC_ONLY / PREREGISTERED, not yet run** | **KEEP.** Do not create another group-persistence experiment. The prior dates are used; future confirmatory dates are required. |
| Portfolio V3 Decision Snapshot | V3 spec + S0 plan only | **NOT_BUILT** on protected master | **DO NOT BUILD HERE.** Separate Portfolio V3 owner. Future expectation evidence may consume it after that owner lands. |
| V3 claim ledger / reliability-independence fusion | V3 spec | **NOT_BUILT** | **DO NOT BUILD HERE.** This study can specify compatibility only. |
| Static system census | `data/census/CENSUS.md`, generated 2026-07-16 | **STALE for October negative proof** | **REFERENCE ONLY.** Live Git/code/PR archaeology outranks its absence claims. |

### Important Mastermind correction

The prior study treated “Decision Snapshot” as if this program might need to provide the provenance substrate. That is wrong. Portfolio V3 owns that vertical and it remains separate. Expectation/theme work should emit owner-native, provenance-bearing evidence that a future Decision Snapshot can consume; it should not build the snapshot system.

## B2. Macro — expectation/revision estate

### Existing physical source owner

`collectors/equity_revisions.py` is already the accepted owner for prospective EPS/revenue expectation accrual.

The accepted decision `DEC-SRC-A1-PROSPECTIVE-EXPECTATION-SOURCE-CONTRACT` fixes:

- owner: `collectors/equity_revisions.py`;
- source artifacts:
  - `data/revisions/expectation_observations.parquet`
  - `data/revisions/expectation_attempts.parquet`;
- legacy artifacts that must retain their semantics:
  - `data/revisions/latest.parquet`
  - `data/revisions/history.parquet`;
- explicit non-owner:
  - `collectors/yf_analyst.py` remains price-target/rating only.

The accepted `DATA_CLOCK_RIGHTS_MATRIX.md` already defines the source plane with:

- `source_effective_at`;
- `source_published_at`;
- `provider_observed_at`;
- `system_observed_at`;
- market-session classification;
- fiscal period/horizon fields;
- deterministic collection/attempt/observation identity;
- append/supersede correction lineage;
- typed missingness;
- rights state;
- idempotency;
- rate-limit evidence;
- mutation gates against fiscal rollover, zero substitution, failure overwrite, horizon collapse, unit/currency/basis drift and hindsight backfill.

This is substantially more mature than the canonical contract proposed in the first version of this study.

### Current capability state

Main's dated `CURRENT_CAPABILITY_LEDGER.md` still labels SRC-A1 `BUILT_NOT_PROVEN` after an August audit failure and subsequent repairs. That ledger is stale relative to October activity.

Open Macro PR #8312 is the current direct proof carrier. Its body reports a native October corpus and proposes promotion to `PROVEN_LIVE`, but the PR was OPEN/DRAFT and UNMERGED during this census. Therefore this study **does not promote the capability**. Current protected/main truth remains:

> **SRC-A1 = BUILT_NOT_PROVEN pending accepted proof.**

This is the single most important gate before any new expectation read model.

### Existing legacy revision analytics

`engine/theme_revisions.py` already consumes `latest.parquet` and `history.parquet` and computes:

- per-theme revision breadth;
- coverage-normalized breadth;
- 90-day estimate drift;
- PIT breadth acceleration when enough history exists;
- an explicitly display-only 30d-vs-90d proxy when PIT history is insufficient;
- honest `INSUFFICIENT_HISTORY` states;
- coverage thresholds.

This means the old plan's proposal to newly invent revision breadth/acceleration is duplicative. The work should be **generalized/reused**, not rebuilt.

`engine/analyst_revisions.py` separately computes monthly recommendation revision momentum from append-only Finnhub recommendation snapshots. It is useful adjacent evidence, but it is not analyst-level EPS/revenue estimate history.

### Existing K3E program

`research/alpha_intelligence/expectation_market_dynamics/` already contains:

- `MASTERPLAN.md`;
- `BUILD_SEQUENCE.md`;
- `OWNER_AND_REUSE_MATRIX.md`;
- `DATA_CLOCK_RIGHTS_MATRIX.md`;
- `CURRENT_CAPABILITY_LEDGER.md`;
- `VEND_0_INSTITUTIONAL_ESTIMATES_BAKEOFF_2026-08-23.md`;
- `EVALUATION_PREREG.md`;
- `eval0_preregistration.v1.json`.

Its owner law is already explicit:

```text
OWNER-NATIVE TRUTH
  expectations / events / financial facts / price / residuals / options / identity
      ↓
DERIVED K3E READ MODEL
  expectation surface → market-response surface → coupling / lag / disagreement / phase
      ↓
DESCRIPTIVE PROJECTIONS
```

K3E is explicitly not a new truth store, event system, identity plane, residual engine, ranker, publication plane or lifecycle plane.

### Vendor work already done

`VEND-0` is already complete at:

`SAMPLE_REQUIRED / PROBE_FURTHER`

No winner, rights clearance, trial or procurement authority exists. This is the correct state. The old study's broad vendor-research phase should be removed. Any future vendor work is a **record-level sample/rights bakeoff only**, and only if the current estate cannot answer the empirical question.

### Evaluation law already frozen

`K3E-EVAL-0-V1` is already frozen and has an activation receipt. It must not be silently rewritten by this study.

If a future analyst-detail experiment asks a genuinely new question, it needs a new preregistration/version with a new forward boundary. It does not justify a new evaluation system.

## B3. Macro — theme/subtheme estate

The first study's “dynamic subtheme identity gap” was true only from the narrow protected-Mastermind-repo view. It is no longer a valid estate-wide statement.

### GMI Theme Graph already owns this territory

Current Macro contains:

- `engine/theme_graph/store.py` — bitemporal graph storage semantics;
- `engine/theme_graph/identity.py` — canonical/local theme identity, including `ltheme:finviz:*` and `ltheme:ths:*`;
- `engine/theme_graph/ontology.py` / inventory;
- `engine/theme_graph/membership_evidence.py`;
- `engine/theme_graph/capability.py`;
- `engine/theme_graph/theme_state.py` — `theme_state/v1`;
- `engine/company_theme_exposure/` — context-only company-theme projection;
- `contracts/theme_graph/*`;
- local-theme materialization for Finviz/THS;
- bitemporal edge semantics with `valid_from/valid_to`, `evidence_time`, `belief_time`, `computed_at`.

The estate's own evidence census records production graph/evidence activity and thousands of latest-belief edges. Therefore **a new theme graph or theme-membership store is prohibited duplication**.

### Current GMI maturity is partial, not absent

Relevant PR state at census time:

- #8379 — merged PIT membership-history integrity repair;
- #8382 — merged `theme_state/v1` schema/compiler/reader implementation;
- #8417 — OPEN/DRAFT Selection Cohort / Company Theme Exposure work;
- #8432 — OPEN/DRAFT membership lifecycle work;
- #8435 — OPEN/DRAFT structural-owner binding.

So the correct classification is:

- core graph + local-theme plane: **operating / existing owner**;
- ThemeState implementation: **BUILT_NOT_PROVEN / not yet sufficient for every downstream claim**;
- full membership lifecycle / D2C-D2D-D2E acceptance: **PARTIAL**;
- W3C cohort interpretation: **PARTIAL / open carrier**.

The residual gap is **completion and accepted consumption**, not a new taxonomy architecture.

## B4. Terminal adjacency

Terminal is not the canonical expectation source, but it already has adjacent functionality.

### Current estimates

`ingest/collect_us_fund.py` fetches yfinance:

- `earnings_estimate`;
- `revenue_estimate`;
- `eps_trend`;
- recommendation summary;
- price targets and analyst-opinion fields.

These are useful display/current-state inputs. They are **not** a reason to create another historical estimate store. Terminal should remain a consumer/projection. A future convergence can replace duplicated current-state fetching where economically justified, but this study does not authorize that migration.

### Current theme projection

Terminal main contains:

`terminal/app/api/company-theme-context/[symbol]/route.ts`

It serves `mastermind.company-theme-context/v1`, verifies authentication, checks current Company Intelligence generation, and resolves Company Theme Exposure from the incumbent R2 source.

Therefore the old plan's implied need for a new theme-facing product surface is also too broad. A projection already exists; upstream owner maturity and cross-product consumption are the real gaps.

## B5. Research Vault

The current repository identity is `mastermindx-market-intelligence/executive-dr-vault`. Targeted searches for estimates, revisions, analyst, theme, `known_at`, and Fiscal did not identify an implementation owner relevant to this capability. It is not used as an architecture authority in this plan.

---

# C. Prior-study overlap audit

| Prior planned capability | Census result | New disposition | Exact existing owner / action |
|---|---|---|---|
| New canonical security/entity identity contract | Existing identity owners already govern joins | **DELETE-AS-DUPLICATE** | Reuse Stock Identity / Data OS identity. K3E explicitly forbids a new identity plane. |
| New analyst/broker identity store | No accepted contributor-detail owner yet; current SRC-A1 is consensus-level | **NEW ONLY IF REQUIRED** | Add vendor-vintage-scoped contributor identity only inside the accepted source-owner extension after sample proof. Never create a global analyst identity plane preemptively. |
| New raw estimate observation store | Already exists | **DELETE-AS-DUPLICATE** | `collectors/equity_revisions.py` + `expectation_observations.parquet`. |
| New coverage-event store | Attempt/missingness/coverage semantics already exist; contributor coverage lifecycle is residual | **EXTEND** | Extend source-owner records only if analyst-detail samples require explicit contributor start/stop/resume events. |
| New actual-results store | Existing Earnings/FIF owners | **DELETE-AS-DUPLICATE** | Consume owner-native earnings/financial facts. |
| New consensus snapshot truth store | K3E source/read-model architecture already exists | **GENERALIZE / EXTEND** | `EXP-1` should derive lawful snapshots from existing source records; no second truth store. |
| New source receipt contract/store | Existing attempt receipts + evidence foundation + owner provenance | **DELETE-AS-DUPLICATE** | Reuse `expectation_attempts.parquet`, K1 evidence contracts, owner-native receipts. |
| New temporal vocabulary | Data OS + K3E already define clocks | **GENERALIZE** | Map source-specific fields to existing temporal law; do not mint a rival vocabulary. |
| New correction lineage model | SRC-A1 already has append/supersede lineage | **KEEP / EXTEND ONLY** | Add vendor-specific correction generation only where institutional samples require it. |
| New revision breadth/magnitude/dispersion engine | Much already exists | **EXTEND** | Reuse `engine/theme_revisions.py`, existing revision fields, and later `EXP-1`; add only features not already emitted. |
| New recommendation revision feature | Already exists | **KEEP** | `engine/analyst_revisions.py`. Treat separately from EPS/revenue revisions. |
| New theme-membership contract | GMI already owns | **DELETE-AS-DUPLICATE** | Reuse `engine/theme_graph/*`, local-theme identities, membership evidence, `theme_state/v1`. |
| New dynamic-subtheme graph | Already exists | **DELETE-AS-DUPLICATE** | GMI Theme Graph. |
| New theme-state engine | Already merged in GMI | **DELETE-AS-DUPLICATE** | Consume accepted `theme_state/v1`; do not fork. |
| New theme product/API | Terminal already has company-theme-context projection | **DELETE / CONVERGE LATER** | Reuse Company Theme Exposure / Terminal BFF. |
| New validation stack | Existing `portfolio.predictions`, trend-persistence, Eval OS, K3E EVAL-0 | **DELETE-AS-DUPLICATE** | Reuse existing graders/prereg machinery. |
| New decision-time history | Already exists | **DELETE-AS-DUPLICATE** | `brain.signal_history`. |
| New outcome ledger | Already exists | **DELETE-AS-DUPLICATE** | `brain.outcome_ledger` / `brain.outcomes`. |
| New Decision Snapshot | Separate V3 owner; not built | **DELETE FROM THIS PROGRAM** | Wait for Portfolio V3 S0; emit compatible evidence only. |
| Broad vendor landscape research | VEND-0 + open Commission 2 already cover it | **DELETE-AS-REPEAT** | Next vendor step is sample/rights proof only if needed. |
| LLM theme classifier as source truth | Existing research desk + GMI owner; unsafe as truth | **REJECT** | LLM may propose hypotheses/summarize evidence, never mint PIT eligibility or numeric truth. |

---

# D. Existing architecture reuse map

```text
PROSPECTIVE EXPECTATIONS
collectors/equity_revisions.py
  ├─ data/revisions/latest.parquet              [legacy current revision surface]
  ├─ data/revisions/history.parquet             [prospective revision history]
  ├─ expectation_observations.parquet           [SRC-A1 immutable source observations]
  └─ expectation_attempts.parquet               [SRC-A1 attempts / nulls / failures / rate limits]
          │
          ├─ engine/theme_revisions.py           [existing theme breadth/drift/accel]
          └─ K3E EXP-1                           [missing deterministic expectation read model]
                 │
                 ├─ protected Mastermind held-risk / lenses / signal_history
                 ├─ later V3 Decision Snapshot consumer, when separately built
                 └─ research validation via existing prediction/eval owners

RECOMMENDATION REVISIONS
collectors/finnhub_altdata.py
  └─ data/finnhub/recommendation.parquet
       └─ engine/analyst_revisions.py            [existing monthly recommendation delta]

THEMES
GMI Theme Graph
  ├─ nodes / edges / evidence / belief_time
  ├─ local_theme identity (Finviz / THS)
  ├─ membership evidence / lifecycle
  ├─ theme_state/v1
  └─ company_theme_exposure.v1
       ├─ Terminal company-theme-context/v1
       └─ future Mastermind/Prophet consumers through accepted owner adapters

RESEARCH / GRADING
portfolio.predictions + loop/single_name_panel
  ├─ rank IC / HAC / non-overlap / delisted names
  ├─ trend_persistence prereg / holdout / walk-forward / null models
  ├─ brain.signal_history
  └─ brain.outcome_ledger / outcomes
```

---

# E. Genuine residual gaps

## E1. Expectation source proof

The current source is built but not accepted as production-proven on protected/main evidence available to this study. Open #8312 may close that gap; it must be reconciled, not duplicated.

## E2. Deterministic expectation read model

K3E's `EXP-1` remains the clean residual capability: a cutoff-safe, rights-aware, missing-aware, source-owner-derived expectation surface.

This should answer, for a security/metric/horizon/cutoff:

- latest lawful observation;
- prior lawful observation;
- revision magnitude;
- breadth where available;
- contributor/coverage count where lawful;
- staleness;
- dispersion where supplied;
- fiscal-period identity;
- correction lineage;
- missingness/degradation;
- source clocks;
- rights state.

It should not rank, size, gate or trade.

## E3. Historical institutional PIT depth

Prospective accrual beginning in 2026 cannot answer long-history questions by itself. Historical institutional data is justified only for empirical questions requiring older regimes or analyst-level detail.

This is a **data-depth gap**, not an architecture gap.

## E4. Analyst-level contributor detail

Current SRC-A1 explicitly emits `aggregation_level=consensus_snapshot` and `contributor_id=null`.

Contributor detail is therefore genuinely missing. It should be acquired/built only if:

1. a sample proves the vendor can reconstruct PIT contributor history;
2. rights permit intended storage/use;
3. contributor detail adds material incremental value over consensus;
4. identity reshuffles can be handled without false stable-ID assumptions.

## E5. GMI membership lifecycle / accepted ThemeState consumption

The graph exists. Residual work is to finish/accept the incumbent D2/W3B/W3C path and then consume it. Mastermind should not build around open GMI carriers.

## E6. Cross-family independence proof

Mastermind still needs empirical evidence that revisions add information beyond:

- SUE/PEAD;
- earnings/guidance;
- news;
- price momentum;
- options;
- fundamentals;
- institutional/flow context;
- themes;
- macro.

This is a validation gap, not a source-schema gap.

---

# F. Updated external/source landscape — residual gaps only

The broad source survey is no longer a P0 task.

The accepted K3E `VEND-0` research already concluded `SAMPLE_REQUIRED / PROBE_FURTHER`, and open Macro PR #8402 contains a newer hardened vendor audit. Because #8402 is unmerged, it is evidence, not protected law.

The only justified future external-source activity is a **record-level bakeoff** after the internal source/read-model gate:

| Question | Existing estate first | External sample only if… |
|---|---|---|
| Prospective consensus revisions | SRC-A1 | current coverage/history cannot support the experiment |
| Historical PIT consensus | none with mature long history | long-regime validation is required |
| Analyst-level detail | none | consensus passes and contributor detail has a clear incremental hypothesis |
| Actuals/guidance | Earnings/FIF/SEC owners | never replace with analyst vendor data merely for convenience |
| Theme membership | GMI | never buy a second taxonomy until GMI coverage/rights prove insufficient |
| Theme state | GMI `theme_state/v1` | no external substitute should be evaluated before incumbent owner acceptance |

**Do not repeat public vendor marketing research.** The next useful vendor evidence is delivered sample rows, documented cutoff/correction semantics, identifier behavior, rights, and cross-vintage reproducibility.

---

# G. Revised canonical data model — extensions, not new planes

## G1. Keep existing SRC-A1 source records

Do not replace:

- `expectation_observations.parquet`;
- `expectation_attempts.parquet`.

Do not create a parallel `estimate_observation_v1` store in Mastermind.

## G2. Add only a derived EXP-1 contract

The smallest genuinely new contract is a **read-model result**, not another source truth.

Suggested shape, subject to the K3E owner:

`k3e.expectation_surface/v1`

Required fields should reference, not duplicate, owner-native records:

- security/issuer reference from existing identity owner;
- metric;
- raw horizon/fiscal-period identity;
- cutoff;
- eligible observation IDs;
- latest/prior values;
- deterministic revision deltas;
- coverage / contributor counts if actually supplied;
- dispersion if supplied;
- staleness;
- missingness/degradation;
- source clock summary;
- correction/supersession refs;
- rights state;
- source receipt/attempt refs;
- computation version;
- authority = descriptive/context only.

## G3. Contributor identity only as a conditional extension

If an institutional sample includes analyst/broker detail, add a vendor-vintage-scoped mapping inside the accepted source owner. Never assume IDs are globally stable.

Do not create this contract before sample evidence requires it.

## G4. Themes: no new membership contract

Use:

- GMI node/edge/evidence contracts;
- local-theme IDs;
- membership lifecycle;
- `theme_state/v1`;
- `company_theme_exposure.v1`.

Any Mastermind adapter should carry owner refs and cutoff, not copy graph truth into a second store.

## G5. Temporal law

The estate already has overlapping but compatible temporal vocabularies. The read model must preserve source-native fields and map them explicitly to the company temporal law.

For historical eligibility, the controlling rule remains:

> a record may influence a historical decision only if the owner can prove it was knowable/available by the decision cutoff.

Never substitute estimate date, fiscal period, provider observation time or ingestion time for a missing knowable time.

---

# H. Revised derived intelligence

## Already exists — do not rebuild

- per-name revision breadth/current drift fields;
- theme revision breadth;
- coverage-normalized theme breadth;
- PIT breadth acceleration;
- display-only short-history drift proxy;
- monthly recommendation revision momentum;
- SUE/earnings surprise context;
- price/rotation/breadth measurement;
- trend persistence research harness.

## New only inside EXP-1 or later institutional extension

Candidate deterministic outputs:

- cutoff-safe consensus delta by metric/horizon;
- staleness distribution;
- observation age;
- fiscal-roll-aware revision;
- correction-aware revision;
- coverage change;
- dispersion change;
- consensus-vs-recommendation disagreement;
- post-earnings reset trajectory;
- analyst-detail breadth/cluster only if contributor data exists;
- consensus-vs-detail ablation fields.

No opaque master score.

## LLM role

Existing `brain/research_desk.py` already owns hypothesis-oriented LLM research. Use it, if at all, to:

- explain why revisions may have changed;
- connect revisions to guidance/news/competitive mechanisms;
- propose falsifiers;
- suggest theme hypotheses for deterministic owner review.

Do not use an LLM to:

- decide PIT eligibility;
- infer missing numeric estimates;
- repair vendor history;
- normalize currency/units/splits;
- determine correction generation;
- mint theme membership;
- decide rank/size/trade authority.

---

# I. Integration map

| Producer | Existing canonical owner/artifact | Evidence family | Consumer |
|---|---|---|---|
| Yahoo/yfinance prospective expectation collection | Macro `collectors/equity_revisions.py` + SRC-A1 artifacts | earnings expectations / revisions | K3E `EXP-1`; existing theme revisions |
| Legacy revision snapshots | `data/revisions/latest.parquet`, `history.parquet` | revisions | `engine/theme_revisions.py`; published stockdata; protected Mastermind held-risk |
| Recommendation trends | Finnhub collector + `engine/analyst_revisions.py` | recommendation revisions | descriptive research / existing consumers |
| Earnings/actuals/guidance | Earnings Intelligence / FIF / SEC owners | earnings/fundamentals | controls and event conditioning |
| Price/residuals | existing market-data / DRL owners | market response | K3E later MKT-1; validation |
| Themes | GMI Theme Graph | thematic identity/state | Company Theme Exposure, Terminal, later Mastermind consumers |
| Decision-time evidence | `brain.signal_history` | PIT engine evidence | `brain.outcome_ledger`, research grading |
| Validation | `portfolio.predictions`, trend-persistence harness, Eval OS | empirical evidence | promotion/kill decisions |
| Portfolio V3 snapshot | separate Portfolio V3 owner, currently NOT_BUILT | future decision provenance | future only; this program does not implement it |

---

# J. Validation program — reuse existing machinery

## J1. Source proof before alpha tests

Before any return-prediction experiment:

1. reconcile #8312;
2. prove source replay/idempotency/correction/fiscal-roll semantics;
3. verify missingness and rate-limit states cannot masquerade as neutral data;
4. verify no current snapshot is backfilled into earlier cutoffs;
5. verify exact source rights for the intended experiment.

## J2. EXP-1 contract tests

Required:

- cutoff mutation test;
- correction-generation mutation test;
- fiscal-roll test;
- missing/zero distinction;
- failed-attempt cannot overwrite good observation;
- source-clock non-alias test;
- same-session replay idempotency;
- changed-payload supersession;
- rights-blocked fail-closed result;
- no contributor fields fabricated from consensus.

## J3. Incremental information tests

Reuse the existing survivorship-safe/delisted substrate and inference discipline.

Test separately:

- consensus magnitude;
- breadth;
- dispersion;
- staleness;
- coverage change;
- post-event revision response;
- recommendation revisions;
- analyst detail if available.

Controls:

- SUE/PEAD;
- price momentum;
- volatility;
- sector/industry/country/size/liquidity;
- earnings/guidance/news event state;
- options;
- fundamentals;
- theme/rotation state;
- macro.

Use:

- rank IC / ICIR;
- cross-sectional regressions;
- event-conditioned specifications;
- portfolio spreads only after descriptive tests;
- turnover/cost/capacity;
- rolling OOS;
- multiple-testing control;
- missingness-as-signal tests;
- consensus-vs-detail ablations;
- cross-vendor replication where lawful.

## J4. Theme validation

Do not rerun the used-up stock-level Trend Persistence dates.

For group/theme persistence:

- consume the existing C1 preregistration;
- wait for eligible future confirmatory dates;
- use accepted GMI PIT membership only;
- test incremental value beyond member-level momentum;
- kill the family if performance is concentrated in a tiny number of sectors/themes or fails the preregistered controls.

---

# K. Risks and failure modes

1. **Duplicate truth stores** — the largest architecture risk after this census.
2. **Unmerged research promoted to law** — especially Macro #8402 and #8312.
3. **Stale capability ledgers** — current source may be ahead of dated records; live Git and accepted evidence must reconcile before action.
4. **Current-state duplication in Terminal** — useful for display, unsafe as a second canonical research source.
5. **PIT leakage** — corrected vendor histories can look cleaner than historical knowledge.
6. **Fiscal rollover mistaken for revision** — already a known SRC-A1 mutation gate.
7. **Coverage/reviser-count confusion** — existing theme logic explicitly distinguishes them; preserve that.
8. **Recommendation vs earnings-estimate conflation** — `engine/analyst_revisions.py` is a different evidence family from EPS/revenue expectations.
9. **Consensus vs contributor detail conflation** — current SRC-A1 is consensus-level.
10. **Theme graph duplication** — prohibited; GMI owns it.
11. **Theme membership incompleteness** — graph existence does not imply every lifecycle/coverage wave is accepted.
12. **Correlated evidence** — revisions can repackage earnings, guidance, news and price information.
13. **Validation duplication** — new notebooks/graders can silently diverge from existing inference law.
14. **Opaque fusion** — prohibited by K3E/V3 principles.
15. **Premature vendor procurement** — no source purchase is justified before internal estate and sample evidence are exhausted.
16. **LLM truth laundering** — narrative synthesis cannot become numeric or PIT source truth.

---

# L. Revised build priority

## P0 — prove and expose what already exists

1. Reconcile Macro PR #8312 and the incumbent SRC-A1 proof state.
2. Reconcile direct overlapping research PR #8402; adopt useful findings only after accepted merge/review.
3. If SRC-A1 is accepted, build **EXP-1 only** as a read-only deterministic expectation surface.
4. Bind EXP-1 to existing identity/event/financial/price owners; no new stores.
5. Add research-only Mastermind consumption through existing decision-history/validation owners, not portfolio authority.

## P1 — validate incremental value

1. Run preregistered consensus-level tests on the existing prospective estate.
2. Test whether current free-estate history is enough for the target horizon.
3. If not, execute the already-defined VEND-0 next step: record-level sample/rights bakeoff.
4. Add institutional historical PIT consensus only if the empirical question needs it.
5. Add analyst detail only if consensus passes and detail has a clear incremental hypothesis.

## P2 — accepted theme integration

1. Wait for/reconcile GMI D2/W3B/W3C outcomes.
2. Consume `theme_state/v1` / Company Theme Exposure through owner adapters.
3. Use the existing group-persistence preregistration when future dates become eligible.
4. Later test expectation × theme-state interactions only after both families independently pass.

## Defer

- contributor-skill/herding models;
- KPI/segment expectation depth;
- cross-vendor ensemble consensus;
- rich theme exposure weights;
- Portfolio V3 Decision Snapshot integration until that separate owner lands.

## Reject / remove

- new analyst warehouse;
- new theme graph;
- new theme membership store;
- new identity plane;
- new receipt plane;
- new outcome ledger;
- new evaluation stack;
- new broad vendor survey;
- new LLM classification truth plane;
- direct wiring of revisions/themes into rank/size/trade authority.

---

# M. Migration / upgrade path for overlaps

## Old study → new owner-preserving path

```text
OLD: build estimate contracts
NEW: reuse SRC-A1; build only EXP-1 derived read model

OLD: build source receipts
NEW: reuse expectation_attempts + evidence foundation

OLD: build identity mapping
NEW: reuse Stock Identity / Data OS

OLD: build actual-result contract
NEW: reuse Earnings / FIF

OLD: build consensus snapshot store
NEW: derive cutoff-safe surface in EXP-1

OLD: build dynamic subtheme membership
NEW: consume GMI graph/local-theme/ThemeState

OLD: build theme API
NEW: reuse Company Theme Exposure / Terminal projection

OLD: build validation program from scratch
NEW: reuse portfolio.predictions + trend-persistence + Eval OS

OLD: broad vendor research
NEW: only sample/rights bakeoff if internal estate is insufficient

OLD: attach directly to future Decision Snapshot
NEW: emit compatible evidence; Portfolio V3 remains separate owner
```

## Compatibility rule

No migration may destroy the legacy `latest.parquet` / `history.parquet` semantics that existing consumers use. New institutional data must be additive behind the source owner until a separate, accepted migration proves equivalence and consumer safety.

---

# N. Exact bounded follow-on implementation commission

## Commission: K3E expectation source reconciliation and minimal EXP-1 read model

**Purpose:** create the highest-value missing capability with the minimum new surface area.

### Authority

Authorized only after this research is accepted:

- source archaeology;
- tests;
- research-only deterministic read model;
- fixture/sample work using already lawful data;
- read-only Mastermind research consumption.

Not authorized:

- vendor contact or purchase;
- production deployment;
- live portfolio/trading changes;
- rank/size/gate/entry authority;
- new identity/source-receipt/outcome/theme/control plane;
- changing Portfolio V3;
- bypassing active Macro/GMI carriers.

### Phase 0 — collision reconciliation

Read current protected Mastermind + current Macro + current Terminal.

Inspect at minimum:

- Macro PR #8312;
- Macro PR #8402;
- GMI PRs #8417, #8432, #8435 or their accepted successors;
- `CURRENT_CAPABILITY_LEDGER.md`;
- `OWNER_AND_REUSE_MATRIX.md`;
- `DATA_CLOCK_RIGHTS_MATRIX.md`;
- `DEC-SRC-A1-PROSPECTIVE-EXPECTATION-SOURCE-CONTRACT.md`;
- `collectors/equity_revisions.py`;
- `engine/theme_revisions.py`;
- `engine/analyst_revisions.py`.

**DONE_WHEN:** every overlapping active carrier is classified accepted / rejected / still active, exact writer custody is known, and no duplicate modifier is started.

### Phase 1 — source proof decision

If SRC-A1 is already accepted `PROVEN_LIVE`, do not re-prove it without a material invalidator.

If not accepted, repair/prove only the failed invariant in the incumbent owner.

**DONE_WHEN:** the source is either:
- `PROVEN_LIVE` with accepted evidence; or
- blocked by one exact unresolved invariant; or
- rejected.

**Tests/evidence:** existing mutation gates, natural source receipts, cutoff/correction/fiscal-roll proof.

**Safety:** no new store, cadence expansion, universe expansion or manual source replay merely to manufacture proof.

### Phase 2 — minimal EXP-1

Only after Phase 1 passes.

Implement a pure/read-only `k3e.expectation_surface/v1` (exact final name owned by K3E) over existing source artifacts.

It may compute only deterministic, cutoff-safe, rights-aware descriptive fields.

**DONE_WHEN:**
- contract tests pass;
- cutoff mutation changes eligibility correctly;
- correction/fiscal-roll tests pass;
- no source records are mutated;
- no rank/gate/size/trade consumer exists;
- one real research consumer can read the surface.

### Phase 3 — Mastermind research adapter

Add the smallest read-only adapter needed to expose accepted EXP-1 fields to research/shadow evaluation.

Prefer:
- `brain.signal_history` compatible snapshot fields;
- existing lens/read-only research surfaces.

Do not modify held-risk thresholds or portfolio authority in this phase.

**DONE_WHEN:** a historical/replay test proves the exact evidence visible at cutoff and a null/missing source fails closed.

### Phase 4 — incremental validation

Use existing research infrastructure. Pre-register before outcome inspection.

**DONE_WHEN:** the family receives one of:
- `PROMOTE_TO_SHADOW_RESEARCH`;
- `MORE_EVIDENCE_REQUIRED`;
- `REJECT_DATA_FAMILY`.

Promotion is research-only.

### Phase 5 — institutional sample gate

Run only if Phase 4 shows the prospective/free estate is insufficient for the intended question.

Use the existing VEND-0 conclusion. Do not repeat broad research.

Compare delivered samples on:

- PIT reconstructability;
- correction transparency;
- fiscal-period stability;
- identity behavior;
- history/coverage;
- rights;
- sample-level disagreement;
- incremental empirical value.

No procurement authority is implied.

### Theme lane

No theme implementation occurs inside Phases 0–5.

A later separate adapter commission may consume accepted GMI `theme_state/v1` / Company Theme Exposure after the incumbent GMI work is protected and production-proven at the level required.

### Smallest first implementation slice

**If #8312 is accepted:** implement EXP-1 read-only cutoff-safe expectation surface over existing SRC-A1 records, with one research consumer and zero portfolio effect.

**If #8312 is not accepted:** repair/prove the incumbent SRC-A1 source only. Do not start EXP-1 and do not create any replacement source.

---

# Evidence register

## Protected Mastermind

- `portfolio/held_risk.py`
- `tests/test_held_risk.py`
- `portfolio/lenses.py`
- `brain/signal_history.py`
- `brain/outcome_ledger.py`
- `brain/research_desk.py`
- `brain/bottleneck.py`
- `brain/rotation_tensor.py`
- `loop/fundamentals.py`
- `loop/single_name_panel.py`
- `portfolio/predictions.py`
- `research/TREND_PERSISTENCE_PROTOCOL.md`
- `research/TREND_PERSISTENCE_READOUT.md`
- `research/TREND_PERSISTENCE_PREREG_C1.md`
- `docs/source_thematic_rotation_framework.md`
- Portfolio V3 design/spec and S0 plan
- `data/census/CENSUS.md` (stale negative-proof caveat)

## Macro

- `collectors/equity_revisions.py`
- `engine/theme_revisions.py`
- `engine/analyst_revisions.py`
- `lib/dataos/temporal.py`
- `research/alpha_intelligence/expectation_market_dynamics/*`
- `agentos/decisions/DEC-SRC-A1-PROSPECTIVE-EXPECTATION-SOURCE-CONTRACT.md`
- `agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md`
- `engine/theme_graph/*`
- `engine/company_theme_exposure/*`
- GMI Theme Graph workstream / completion freeze
- PR #8312 (open, evidence only)
- PR #8402 (open, evidence only)
- PRs #8379/#8382 (merged)
- PRs #8417/#8432/#8435 (open at census time)

## Terminal

- `ingest/collect_us_fund.py`
- `ingest/collect_us_deep.py`
- `ingest/pull_macro_intel.py`
- `terminal/app/api/company-theme-context/[symbol]/route.ts`
- `terminal/lib/companyThemeExposure.ts` and incumbent R2 projection path

---

## Final recommendation

The estate is much further along than the first study assumed. The strongest plan is now **convergence, proof and selective depth**, not greenfield architecture.

Mastermind should spend engineering effort in this order:

1. prove the existing expectation source;
2. expose it through the missing deterministic K3E read model;
3. measure incremental value with the existing research stack;
4. buy/sample deeper history only if the internal estate cannot answer the question;
5. consume GMI's existing theme intelligence rather than rebuild it;
6. keep all portfolio authority separate until independent evidence and the separately owned Portfolio V3 architecture are ready.
