# MastermindX Masterplan — PIT Expectations & Theme Intelligence

## Upgrade-first implementation plan after deep census

**Status:** MASTERPLAN / NON-EXECUTING. No implementation, procurement, deployment, live pipeline mutation, portfolio/trading change, or new source authority is granted by this document.  
**Companion study:** `research/PIT_ANALYST_REVISIONS_AND_DYNAMIC_SUBTHEMES_RESEARCH_2026-10-04.md`  
**Protected Mastermind census pin:** `715e6ac01f16ef446dc6eba3c215454d0eddb54d`  
**Relevant Macro census pin:** `b0ba2f79c25ac7892c48b24f14a167781e16247b`; current master recheck `80fd8a1b993afe6109d289cb6916809dde70c830` changed only unrelated Entry Radar files.  
**Terminal census pin:** `601db3352044535e327a7700221db062f5eca053`.

---

# 0. Masterplan decision

The program is no longer a greenfield “analyst revisions + dynamic subthemes” build.

It is an **owner-preserving convergence program** with two independent lanes:

1. **Expectation lane:** prove and expose the existing Macro/K3E prospective expectation source, then validate whether deeper institutional history/detail is worth acquiring.
2. **Theme lane:** consume the existing GMI Theme Graph / ThemeState / Company Theme Exposure owners after their incumbent completion gates; build no second graph or membership store.

The expectation lane is the only lane eligible for the first implementation slice.

---

# 1. Overlap matrix

| Desired capability | Existing implementation | Current state | Masterplan action |
|---|---|---|---|
| Prospective EPS/revenue observations | Macro `collectors/equity_revisions.py` + SRC-A1 artifacts | BUILT_NOT_PROVEN pending accepted proof | **PROVE / REUSE** |
| Attempt/null/rate-limit receipts | `expectation_attempts.parquet` | BUILT_NOT_PROVEN | **REUSE** |
| Immutable expectation observations | `expectation_observations.parquet` | BUILT_NOT_PROVEN | **REUSE** |
| Legacy current revision fields | `latest.parquet`, stockdata revisions | EXISTING | **KEEP SEMANTICS** |
| Prospective revision history | `history.parquet` | EXISTING, short history | **KEEP / DO NOT BACKFILL** |
| Theme revision breadth/accel | `engine/theme_revisions.py` | BUILT | **EXTEND, do not rebuild** |
| Recommendation revision momentum | `engine/analyst_revisions.py` | BUILT | **KEEP separate family** |
| Expectation read model | K3E `EXP-1` | NOT_BUILT | **BUILD after source proof** |
| Market-response read model | K3E `MKT-1` | NOT_BUILT | **DEFER behind EXP-1** |
| Coupling/lag/disagreement | K3E `CPL-1` | NOT_BUILT | **DEFER** |
| Vendor research | K3E `VEND-0` | COMPLETE: SAMPLE_REQUIRED / PROBE_FURTHER | **DO NOT REPEAT** |
| Evaluation preregistration | `K3E-EVAL-0-V1` | FROZEN | **REUSE / do not rewrite** |
| Security/entity identity | Stock Identity / Data OS | EXISTING OWNER | **REUSE** |
| Actuals/guidance | Earnings / FIF / SEC owners | EXISTING OWNER | **REUSE** |
| Source/evidence receipts | source-owner attempts + K1 evidence foundation | EXISTING OWNER | **REUSE** |
| Decision-time history | `brain.signal_history` | EXISTING | **REUSE** |
| Outcome grading | `brain.outcome_ledger`, `brain.outcomes` | EXISTING | **REUSE** |
| Cross-sectional research | `portfolio.predictions`, `loop/single_name_panel` | EXISTING | **REUSE** |
| FDR/walk-forward/null tests | Trend Persistence / Eval OS | EXISTING | **REUSE** |
| Dynamic/local theme identity | GMI `engine/theme_graph/*` | EXISTING / PARTIAL completion | **REUSE** |
| Theme state | GMI `theme_state/v1` | BUILT_NOT_PROVEN / completion gates remain | **WAIT / CONSUME** |
| Company-theme projection | `engine/company_theme_exposure/*` | EXISTING | **REUSE** |
| Terminal theme API | `company-theme-context/v1` | EXISTING | **REUSE** |
| Portfolio V3 Decision Snapshot | separate Portfolio V3 S0 | NOT_BUILT | **OUT OF SCOPE** |

---

# 2. Do-not-rebuild list

The implementation owner must not create any of the following unless a later accepted owner decision explicitly reverses this plan:

- a second analyst/expectation raw-history store;
- a second `expectation_observations` or attempt-receipt plane;
- a new security/entity identity database;
- a global analyst identity plane before a real contributor-detail source requires one;
- a second earnings/actuals store;
- a second source-receipt/evidence store;
- a second theme graph;
- a second local-theme taxonomy;
- a second theme-membership history;
- a second ThemeState engine;
- a second Company Theme Exposure organ;
- a second signal-history ledger;
- a second outcome ledger;
- a second research grader/FDR stack;
- a Portfolio V3 Decision Snapshot implementation inside this program;
- a broad vendor marketing survey;
- an LLM-owned numeric/PIT/theme truth plane;
- an opaque fused expectation/theme score;
- direct rank/size/gate/trade authority.

---

# 3. Active collision gates

Before any source or implementation change, re-census these carriers.

## Expectation collisions

- Macro PR #8312 — native SRC-A1 proof / Information→Price carrier.
- Macro PR #8402 — Commission 2 PIT analyst expectations hardened audit.
- K3E `CURRENT_CAPABILITY_LEDGER.md`.
- K3E `MASTERPLAN.md`.
- K3E `OWNER_AND_REUSE_MATRIX.md`.
- K3E `DATA_CLOCK_RIGHTS_MATRIX.md`.
- `DEC-SRC-A1-PROSPECTIVE-EXPECTATION-SOURCE-CONTRACT`.

## Theme collisions

- GMI PR #8417 — Selection Cohort / Company Theme Exposure.
- GMI PR #8432 — membership lifecycle.
- GMI PR #8435 — structural-owner binding.
- merged #8379 — PIT membership-history integrity.
- merged #8382 — ThemeState schema/compiler/reader.

## Rule

An open or unmerged carrier is evidence, not protected law. It is also a collision: do not start a conflicting modifier on the same owner/path while its writer/effect state is unresolved.

---

# 4. Phase plan

## Phase 0 — source-law and collision reconciliation

### Goal

Establish current accepted truth and exact next owner action before code.

### Read

Protected Mastermind:

- `docs/sol_skills/INDEX.md`
- required same-commit procedures
- companion study
- `portfolio/held_risk.py`
- `brain/signal_history.py`
- `brain/outcome_ledger.py`
- `portfolio/predictions.py`
- `research/TREND_PERSISTENCE_PROTOCOL.md`

Macro:

- `collectors/equity_revisions.py`
- `engine/theme_revisions.py`
- `engine/analyst_revisions.py`
- K3E owner matrices/ledger
- relevant decisions/workstreams
- active PRs named above

Terminal:

- current estimate collector;
- company-theme-context projection.

### DONE_WHEN

- exact current SHAs are pinned;
- every active collision is classified;
- incumbent writer/effect state is known;
- no duplicate path/owner is proposed;
- the source capability is classified using the canonical vocabulary;
- exact first modifying carrier is named.

### Tests/evidence

Read-only Git comparisons, current PR metadata, accepted decisions, exact file paths.

### Safety / rollback

No code or data mutation. If source truth cannot be established, modifications are blocked but research may continue.

---

## Phase 1 — SRC-A1 proof reconciliation

### Goal

Do not build a read model on an unproven source.

### Branch A — #8312 accepted/protected

If current accepted source evidence already proves SRC-A1, record:

- exact accepted merge SHA;
- proof artifact;
- source artifact digests/receipts;
- capability state.

**Do not rerun the same proof** unless a material invalidator exists.

Proceed to Phase 2.

### Branch B — #8312 rejected/unaccepted

Repair only the exact failed invariant in the incumbent source owner.

No new store. No replacement collector. No cadence/universe expansion merely to manufacture proof.

### Required source invariants

- same logical replay is idempotent;
- unchanged values do not fabricate revisions;
- changed payloads append/supersede;
- prior as-known rows remain recoverable;
- null/failure/429 cannot overwrite good state;
- fiscal rollover is not a revision;
- provider/source/system clocks remain distinct;
- current snapshots cannot backfill earlier cutoffs;
- rights state remains explicit;
- legacy `latest/history` semantics do not drift.

### DONE_WHEN

One of:

- `PROVEN_LIVE` with accepted evidence;
- `BUILT_NOT_PROVEN` with one exact remaining invariant;
- `BROKEN` / rejected with named evidence.

### Tests/evidence

Reuse the existing SRC-A1 mutation gates and natural source receipts.

### Safety / rollback

Source artifacts are append/supersede only. No destructive rewrite. A failed proof does not authorize a new owner.

---

## Phase 2 — EXP-1 deterministic expectation surface

### Gate

Phase 1 must be accepted `PROVEN_LIVE`.

### Goal

Create the smallest missing consumer-facing read model without creating another truth store.

### Extend exact existing owner

Preferred owner remains K3E Expectation Market Dynamics.

### Proposed contract

Final naming belongs to K3E, but the semantic target is:

`k3e.expectation_surface/v1`

### Inputs

Only owner-native, cutoff-eligible records:

- SRC-A1 expectation observations;
- SRC-A1 attempt/missingness receipts;
- existing identity owner;
- optional owner-native earnings/fiscal identity where already accepted.

### Output

For one security / metric / horizon / cutoff:

- subject identity ref;
- metric;
- raw horizon;
- fiscal-period identity if known;
- cutoff;
- eligible observation refs;
- latest/prior lawful values;
- deterministic revision delta;
- coverage/contributor counts if supplied;
- dispersion if supplied;
- staleness/age;
- missingness/degradation;
- source clocks;
- correction/supersession refs;
- rights state;
- computation version;
- descriptive/context-only authority.

### Explicit non-features

No:

- score;
- rank;
- fair value;
- price target;
- trade recommendation;
- size;
- gate;
- inferred analyst identity;
- LLM calculation;
- hidden imputation.

### Tests

1. cutoff mutation;
2. source-clock alias rejection;
3. fiscal-roll boundary;
4. correction supersession;
5. same-session idempotency;
6. missing vs zero;
7. failure cannot overwrite good state;
8. rights-blocked fail closed;
9. consensus cannot fabricate contributor detail;
10. legacy revision artifacts remain unchanged.

### DONE_WHEN

- pure read model passes tests;
- one real research consumer reads it;
- no production/trading consumer exists;
- source bytes remain unchanged;
- output can be reconstructed from retained owner refs.

### Rollback

Remove the derived read-model consumer/adapter. No source migration is required because source truth was never moved.

---

## Phase 3 — Mastermind research-only adapter

### Gate

EXP-1 accepted.

### Goal

Make the evidence measurable inside existing Mastermind research infrastructure without changing portfolio behavior.

### Preferred existing consumers

- `brain.signal_history` for decision-time evidence snapshots;
- read-only lens/research surfaces;
- `portfolio.predictions` / research harness for grading.

### Do not modify yet

- held-risk thresholds;
- confluence weights;
- portfolio sizing;
- entry/exit gates;
- autonomous book behavior.

### Tests

- historical cutoff produces the same eligible EXP-1 record set;
- future observations disappear when cutoff moves backward;
- missing source yields typed absent/degraded state;
- signal-history record references the exact owner artifact;
- no portfolio output changes when adapter is enabled in research-only mode.

### DONE_WHEN

A bounded shadow/research artifact can be joined to outcomes without any trading effect.

### Rollback

Disable/remove the research adapter; existing source and portfolio behavior remain unchanged.

---

## Phase 4 — preregistered incremental validation

### Gate

Research adapter accepted and enough prospective observations exist.

### Reuse

- `loop/single_name_panel.py`;
- `portfolio.predictions.py`;
- trend-persistence inference conventions;
- Eval OS where applicable;
- `brain.outcome_ledger`.

### Features to test separately

- consensus magnitude;
- revision breadth;
- dispersion;
- staleness;
- coverage change;
- post-earnings reset;
- recommendation revision momentum;
- contributor-detail features only if later available.

### Controls

- SUE / PEAD;
- momentum;
- volatility;
- sector / industry / country / size / liquidity;
- earnings/guidance/news;
- options;
- fundamentals;
- themes/rotation;
- macro.

### Statistical discipline

- date-clustered / non-overlapping inference;
- rolling OOS;
- multiple-testing control;
- missingness tests;
- regime/subperiod stability;
- transaction cost/turnover/capacity;
- factor-neutral specifications;
- consensus-vs-detail ablation;
- negative controls/falsifiers.

### Promotion states

Exactly one:

- `PROMOTE_TO_SHADOW_RESEARCH`;
- `MORE_EVIDENCE_REQUIRED`;
- `REJECT_DATA_FAMILY`.

No result grants production portfolio authority.

### Kill criteria

Kill/defer if:

- no incremental OOS value after controls;
- effect disappears after realistic costs;
- result is one-era/one-sector/vendor-definition dependent;
- missingness/coverage selection explains the signal;
- PIT reconstruction is not trustworthy;
- a simpler existing feature performs equivalently.

---

## Phase 5 — institutional historical sample gate

### Gate

Run only if Phase 4 cannot answer the intended question with current prospective history, or if a preregistered analyst-detail hypothesis survives.

### Do not redo

Do not repeat broad VEND-0 research.

### Evaluate delivered sample rows only

- PIT reconstructability;
- original vs corrected vintage behavior;
- fiscal-period mapping;
- corporate-action handling;
- currency/unit/basis changes;
- contributor identity stability;
- coverage start/stop/resume;
- history by metric/region;
- delivery ergonomics;
- retention/use/AI rights;
- cross-vendor disagreement;
- measured incremental value.

### Decision

- `FREE_ESTATE_SUFFICIENT`;
- `PIT_CONSENSUS_SAMPLE_WORTH_TRIAL`;
- `ANALYST_DETAIL_SAMPLE_WORTH_TRIAL`;
- `NO_SOURCE_JUSTIFIES_EXPANSION`.

No procurement is authorized by the decision.

---

## Phase 6 — conditional institutional source extension

### Gate

Separate authorization for an already-approved trial/license.

### Rule

Extend the existing expectation source owner. Do not create a new warehouse.

### New fields/contracts allowed only if required by delivered data

Examples:

- vendor-vintage contributor identity;
- contributor coverage lifecycle;
- vendor correction generation;
- vendor-native publication/availability clocks.

### Invariant

Vendor shape is not the canonical architecture. Normalize only what can be normalized without erasing source meaning.

### DONE_WHEN

Institutional observations can produce the same EXP-1 surface contract while preserving source-specific lineage and rights.

---

# 5. Theme lane — consume, do not rebuild

This lane is independent from expectation Phases 1–6.

## Theme Gate 0 — reconcile incumbent GMI carriers

Read accepted status of:

- #8379;
- #8382;
- #8417;
- #8432;
- #8435;
- current GMI workstream/decision records.

### DONE_WHEN

The accepted state of:

- membership lifecycle;
- local/canonical theme identity;
- `theme_state/v1`;
- Company Theme Exposure;
- Selection Cohort consumption

is explicit.

## Theme Gate 1 — no Mastermind graph build

If GMI is incomplete, wait/route to the incumbent GMI owner.

Do not create a Mastermind-side replacement.

## Theme Gate 2 — read-only adapter

Only after accepted GMI source/state proof:

- consume owner refs;
- preserve `effective_at` / `known_at` / belief-time semantics;
- expose local + canonical theme state where available;
- fail closed on incomplete membership.

No rank/size/trade authority.

## Theme Gate 3 — group-persistence research

Reuse `TREND_PERSISTENCE_PREREG_C1.md`.

Do not reuse the already-consumed stock-level dates.

Confirmatory theme/group claims require future eligible dates and accepted PIT membership.

### Kill criteria

- no incremental group information beyond member momentum;
- concentration in a tiny number of sectors/themes;
- membership history too incomplete;
- theme-state results depend on current-snapshot backfill;
- local/canonical mapping instability dominates the effect.

---

# 6. Terminal convergence lane

Terminal currently collects current yfinance estimates and serves Company Theme Exposure.

This masterplan does not require immediate migration.

## Rule

Terminal may remain a current-state/display consumer while K3E/GMI mature.

Later, if duplication has measurable operational cost or semantic drift:

- converge Terminal reads toward accepted Macro owner projections;
- preserve UI contracts;
- do not make Terminal the new canonical source;
- prove no loss of current functionality before removing duplicate fetches.

This is P2/defer, not P0.

---

# 7. Portfolio V3 compatibility

Portfolio V3 Decision Snapshot and reliability/independence fusion remain separate owners and are NOT_BUILT on protected Mastermind at the census pin.

This program must only ensure future compatibility:

- stable owner refs;
- correction lineage;
- cutoff;
- evidence family;
- independence-family metadata where accepted;
- no opaque score;
- no direct authority.

Do not implement V3 S0 here.

---

# 8. Removed / transformed tasks from the old plan

| Old task | New status |
|---|---|
| Build security identity mapping | **REMOVED — reuse existing identity owner** |
| Build raw estimate observation schema/store | **REMOVED — SRC-A1 already owns** |
| Build source receipt schema/store | **REMOVED — attempts/evidence owners already exist** |
| Build actual-result store | **REMOVED — Earnings/FIF already own** |
| Build consensus snapshot truth | **TRANSFORMED — EXP-1 derived read model** |
| Build coverage-event store | **TRANSFORMED — conditional source-owner extension only** |
| Build analyst identity plane | **TRANSFORMED — only vendor-vintage extension if sample requires** |
| Build deterministic revision engine | **TRANSFORMED — extend existing theme revisions + EXP-1** |
| Build dynamic theme membership | **REMOVED — GMI owns** |
| Build theme state | **REMOVED — GMI owns** |
| Build theme API | **REMOVED — Company Theme Exposure/Terminal already exist** |
| Build validation stack | **REMOVED — reuse existing** |
| Build Decision Snapshot | **REMOVED — separate Portfolio V3 owner** |
| Broad vendor research | **REMOVED — VEND-0 already complete** |
| LLM theme classifier | **REJECTED as truth plane** |

---

# 9. First implementation slice

The first slice is conditional on incumbent proof state.

## Case A — SRC-A1 already accepted

**Implement only:**

> A pure, read-only, cutoff-safe K3E expectation surface over existing SRC-A1 observations/attempts, plus one research-only consumer.

### Allowed files

The exact owner must choose final paths after collision census, but changes should stay inside the incumbent K3E/revisions owner and one bounded research adapter.

### Must not touch

- portfolio weights;
- held-risk thresholds;
- execution;
- settlement;
- live scheduler cadence;
- source universe;
- theme graph;
- Terminal product behavior;
- Portfolio V3.

### DONE_WHEN

- source records are unchanged;
- read model passes the 10 mutation/eligibility tests;
- one research consumer can reconstruct a historical cutoff;
- no rank/gate/size/trade effect exists.

## Case B — SRC-A1 not accepted

**Implement no EXP-1.**

Repair/prove only the exact incumbent source invariant. Stop after accepted source proof.

---

# 10. Final acceptance criteria for the whole program

This masterplan is complete only when all of the following are true:

1. no duplicate source/identity/theme/outcome/evaluation plane was created;
2. the expectation source is accepted or explicitly rejected;
3. EXP-1 exists only if the source is proven;
4. research evidence is PIT-reconstructable;
5. incremental value has a preregistered OOS result;
6. vendor expansion, if any, is justified by measured residual need;
7. theme work consumes accepted GMI owners;
8. Terminal remains a projection, not a rival truth owner;
9. Portfolio V3 remains separately owned;
10. no production/trading authority was inferred from research success.

---

# 11. Exact next action

At implementation time:

1. re-pin protected Mastermind;
2. re-pin Macro;
3. inspect #8312 and its accepted successor state;
4. inspect #8402 for research overlap;
5. reconcile active GMI carriers;
6. classify SRC-A1;
7. choose Case A or Case B above.

Nothing else should start first.
