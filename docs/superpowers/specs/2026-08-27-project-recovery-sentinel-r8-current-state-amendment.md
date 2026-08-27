# Project Recovery Sentinel R8 — Post-Approval Current-State Amendment

**Date:** 2026-08-27  
**Authority:** Chairman approval of `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current protected source-law reconciliation.  
**Operation key:** `project-recovery-sentinel-r8-20260827-sol-001`  
**Amends:** repository ownership, current dependency state and projection-scope facts only; the Chairman-approved R8 product and authority architecture is unchanged.

## Current exact pins

- Protected Mastermind `master`: `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`.
- Protected Skillpack at that SHA: `mastermind.sol_skillpack.v1` v1.0.0, minimum bootstrap major 1.
- Macro `main` observed at closeout: `46e30065d30421fe02a5ac8a5a1008dd507c175e`.
- Active Session Truth predecessor: Mastermind PR #170, observed head `99124d3e5690ae5bffc0acb303f30262c135dad9`, still open/draft.
- R8 architecture/plan carrier before this amendment: Mastermind PR #171 / branch `sol/project-recovery-sentinel-r8-20260827`, head `a8e2c513533d43416d22d7b9f32a62c304191cab`.
- Exact-head CI for that pre-amendment R8 plan head: workflow run `33057912597`, `CI`, SUCCESS.
- Mastermind PR #172 merged the hybrid Sol/Codex/Fable workforce source law and leaves #170 Session Truth and #171 Project Recovery as independent carriers.

These are exact observations, not moving aliases. Every implementing wave must re-pin current heads at pickup and must never relabel an older receipt as evidence of a later revision.

## Factual ownership correction — Improvement Agenda

The approved design calls the Improvement Agenda the **Macro Improvement Agenda** in two places. Current repository truth shows the Improvement Agenda implementation and schedule are owned by **Mastermind**:

- `mastermindx-market-intelligence/Mastermind/brain/improvement_agenda.py`
- `mastermindx-market-intelligence/Mastermind/tests/test_improvement_agenda.py`
- `mastermindx-market-intelligence/Mastermind/app/scheduler.py` owns the existing `improvement_agenda_weekly` schedule.

Therefore this amendment supersedes only those repository-owner statements:

1. **Mastermind Improvement Agenda** remains the sole ranking engine.
2. R8-C modifies Mastermind, not Macro.
3. Macro remains the sole Agent OS / semantic-program-registry owner for R8-B.
4. R8 implementation separates **Mastermind recovery + Agenda + Control Room** from **Macro Agent OS wait/program-source** work.
5. No new scheduler is authorized: R8-C reuses the existing Mastermind `improvement_agenda_weekly` path or remains on-demand until its recovery-assessment provider is accepted.

The ranking authority itself is unchanged; only its repository owner is corrected.

## Current Linear projection constraint

The approved product architecture wants a durable Linear indication such as `CEO Recovery Required`, but the currently accepted MAS-66 first vertical is narrower than that desired end-state. Its project-only mutation contract manages project existence/name/summary, one marked managed-description block, team binding and non-destructive active state; it explicitly does **not** authorize label or status management.

Therefore:

1. R8-D remains dependency-held behind the existing MAS-65 / MAS-64 / MAS-66 path.
2. The first lawful R8 Linear projection may use the existing managed project-description block to show recovery reason/action once that projector path is accepted.
3. A `CEO Recovery Required` label or recovery-status mutation is **not authorized by the current MAS-66 V1 contract** and remains held until a separately reviewed projector-scope widening explicitly permits it.
4. No second projector, direct Sol mutation loop or personal-credential fallback is authorized to obtain the label sooner.

This narrows current implementation scope; it does not change Linear's architectural role as projection rather than truth.

## Current R1 collision boundary

PR #170 is the sole active R1 Session Truth implementation carrier. At observed head `99124d3e5690ae5bffc0acb303f30262c135dad9` it currently owns:

- `control_plane/session_truth_acquire.py`
- `control_plane/session_truth_contract.py`
- `control_plane/session_truth_snapshots.py`
- Session Truth snapshot fixtures/tests
- `tests/test_session_truth_rules.py`

The remaining R1 interfaces are still governed by `docs/superpowers/plans/2026-08-27-session-truth-r1.md`; R8 must not pre-create or fork them.

R8-A therefore stays held until #170 is accepted/merged. After acceptance it consumes the accepted Session Truth contracts and rules; it does not duplicate Session Truth acquisition, snapshot normalization, drift rules or semantic hashing.

## Execution topology

The approved R8 program is decomposed into bounded carriers:

- **R8-B1 Agent OS typed wait** — Macro; independent of R1 and the next executable wave.
- **R8-B2 semantic-program census source** — Macro; separate from B1 so Mastermind never becomes a second YAML/parser owner.
- **R8-A recovery classifier** — Mastermind; held until #170 R1 acceptance.
- **R8-C Improvement Agenda ingestion** — Mastermind; depends on R8-A and reuses the existing Agenda/scheduler.
- **R8-E Control Room CEO Attention** — Mastermind; depends on R8-A and uses the existing read-only Control Room composition.
- **R8-D Linear projection** — dependency-held behind accepted MAS-65/MAS-64/MAS-66; managed-block projection first, label/status only after separate authorization.
- **R8-F Slack visibility** — dependency-held behind a lawful `#build-events` recovery-transition source; no custom queue/relay is authorized merely to unblock R8.
- **R8-G fresh-Sol adversarial canary** — final integration acceptance after the required real read paths and visible surfaces are live.

Fable is the preferred sustained COO for the program. Codex may execute bounded technical waves under the current hybrid workforce law. Neither a Slack post nor a plan file is a runtime claim; Executive OS remains the sole Job/Attempt/Worker authority.

## Closeout of the architecture/plan wave

This carrier is **records/source-law only**. Landing it makes the approved architecture and bounded execution package durable; it does not make Project Recovery Sentinel implemented or proven live.

After this amendment, the exact next executable carrier is **R8-B1 Agent OS typed wait in Macro**, using `docs/superpowers/plans/2026-08-27-project-recovery-r8-agentos-wait-contract.md`. R8-A remains held on #170 acceptance. No implementation is authorized on PR #171 itself.
