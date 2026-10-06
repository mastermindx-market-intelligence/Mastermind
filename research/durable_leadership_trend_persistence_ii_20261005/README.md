# Durable Leadership & Trend Persistence II — Final Freeze Hardening

**Status:** research-only package. No DL-1 instrument, efficacy read, ranker, lifecycle state, portfolio rule, procurement, or production change is authorized.

**Current source pins**
- Mastermind protected `master`: `877b1e7f275da0b6d3558d2667778b32d628bf67`
- Macro `main`: `0beebb3bd1f246a13396c3bd8f996103a26c3b77`

**Scientific ruling:** **CONTINUE — NARROWED**  
**Operational DL-0 ruling:** **WAIT_FOR_DATA / SOURCE_GATE**  
**DL-1 efficacy status:** **DO_NOT_READ / NOT RUN**

## Freeze authority

Only two files are freeze-authoritative:

1. [06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md](06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md) — owner, collision, data-rights, and route authority.
2. [07_DL1_PREREG_DRAFT_FREEZE_READY.md](07_DL1_PREREG_DRAFT_FREEZE_READY.md) — sole experiment specification.

Files 01/02/03/05 are historical design context and carry an explicit supersession notice. File 04 is already superseded.

## Final experiment ruling

DL-1 asks one additive question:

> Among names in the research-only state `DL1_RS126_Q4`, do identity-qualified, leave-issuer-out GICS-industry-group peer features improve prediction of **20-trading-session horizon occupancy** beyond a strong stock-only baseline?

Endpoint semantics are final:

- **Primary:** `DL1_OCCUPANCY_20` — Q4 occupancy at t+20; exit/re-entry is allowed. It is not continuous survival.
- **Structural secondary:** `DL1_FIRST_EXIT_60` — first exit from Q4 through 60 trading sessions, right-censored at 60.
- **Secondary:** `DL1_OCCUPANCY_60`.
- Failure of the primary occupancy endpoint falsifies only the frozen occupancy/additive claim. It does **not** falsify the distinct first-exit/hazard thesis, which would require a new preregistration and new untouched evidence.
- DL-1 contains no stock×group interaction model. Interaction/refinement belongs only to DL-2 on new evidence.

`DL1_RS126_Q4` is research-only and never redefines Macro Leader Radar's canonical `LEADERSHIP` state.

## Source-route ruling

No currently admitted source closes the required contemporaneous GICS industry-group taxonomy gate:

- EquityDesk-derived GICS industry-group fields exist technically, but the current rights register records acquisition mechanics only; processing, storage, model-use, and redistribution rights remain unresolved.
- Massive has broad enterprise rights, but no exact Massive GICS-industry-group feed/capture contract has been identified and admitted for DL-1.
- Ex-U.S. historical PIT taxonomy remains unqualified.

Therefore neither `EX_US_PIT_CONFIRMATION` nor `PROSPECTIVE_US_POST_FREEZE` may start today. The package is **WAIT_FOR_DATA / SOURCE_GATE** until one immutable source-admission receipt names the exact taxonomy feed, effective/correction semantics, issuer key, publication/observation clock, and five rights.

## Corrected accrual geometry

Formation remains every fifth U.S. market trading session.

A dependence/evaluation block is now exactly **60 market trading sessions**, not 60 formation observations. Each complete block therefore contains **12 formation dates**.

- Burn-in B1–B3: 180 market sessions = 36 formations.
- Confirmation B4–B9: 360 market sessions = 72 formations.
- Last confirmatory formation: market-session offset 535.
- Last primary occupancy maturity: offset 555.
- Conservative one-reveal maturity after every 60-session structural-secondary window: offset 595.
- Anchor-to-reveal geometry: 596 trading sessions, approximately 2.37 trading years.

The source gate must clear before an anchor can exist; there is no valid calendar completion date yet.

## Package

- [01_DECISION_CENSUS_EVIDENCE.md](01_DECISION_CENSUS_EVIDENCE.md) — historical context; superseded where inconsistent.
- [02_TARGETS_GRANULARITY_DATA.md](02_TARGETS_GRANULARITY_DATA.md) — historical context; superseded where inconsistent.
- [03_EXPERIMENT_MASTERPLAN.md](03_EXPERIMENT_MASTERPLAN.md) — historical context; superseded where inconsistent.
- [04_DL1_PREREG_BLUEPRINT.md](04_DL1_PREREG_BLUEPRINT.md) — superseded.
- [05_INTEGRATION_FALSIFICATION_SOURCES.md](05_INTEGRATION_FALSIFICATION_SOURCES.md) — historical context; superseded where inconsistent.
- [06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md](06_DL0_QUALIFICATION_AND_OWNER_RECONCILIATION.md) — **freeze-authoritative DL-0**.
- [07_DL1_PREREG_DRAFT_FREEZE_READY.md](07_DL1_PREREG_DRAFT_FREEZE_READY.md) — **freeze-authoritative DL-1 draft**.

## DO_NOT_READ / DO_NOT_REDO

- No DL-1 efficacy outcome before final eligibility.
- No PSS prospective interim outcome.
- No Top Anatomy OOT before its own eligibility receipt.
- No 2022-07-06 through 2026-06-02 reuse as fresh confirmation.
- No current GICS/industry taxonomy backcast.
- No DL-1 interaction discovery.
- No B2/C1/C2 resurrection or renamed replay.
- No duplicate Leader Radar lifecycle, peer engine, ThemeState, timeframe owner, outcome ledger, or Prophet ranker.
- No DL-1 implementation in this repair pass.
