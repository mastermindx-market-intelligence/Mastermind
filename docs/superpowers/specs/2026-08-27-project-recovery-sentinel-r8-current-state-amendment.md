# Project Recovery Sentinel R8 — Post-Approval Current-State Amendment

**Date:** 2026-08-27  
**Authority:** Chairman approval of `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` plus current protected source-law reconciliation.  
**Operation key:** `project-recovery-sentinel-r8-20260827-sol-001`  
**Amends:** only repository ownership/current-state facts; the approved R8 product and authority architecture is unchanged.

## Current exact pins

- Protected Mastermind `master`: `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`.
- Protected Skillpack at that SHA: `mastermind.sol_skillpack.v1` v1.0.0, minimum bootstrap major 1.
- Macro `main` observed for planning: `0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e`.
- Active Session Truth predecessor: Mastermind PR #170, observed head `ec1b9bdd7ec9f1d7ea2fca8a7902a2968d1b6681`, still open/draft.
- R8 architecture/plan carrier: Mastermind PR #171 / branch `sol/project-recovery-sentinel-r8-20260827`.
- Mastermind PR #172 merged the hybrid Sol/Codex/Fable workforce source law and explicitly leaves #170 Session Truth and #171 Project Recovery as independent carriers.

These pins are observations for this planning cycle. Implementers must re-pin current heads at pickup and must not relabel old receipts as evidence of later revisions.

## Factual ownership correction

The approved design twice calls the Improvement Agenda the **Macro Improvement Agenda**. Current repository truth shows the Improvement Agenda implementation is owned by **Mastermind**:

- `mastermindx-market-intelligence/Mastermind/brain/improvement_agenda.py`
- `mastermindx-market-intelligence/Mastermind/tests/test_improvement_agenda.py`
- `mastermindx-market-intelligence/Mastermind/app/scheduler.py` owns the existing `improvement_agenda_weekly` schedule.

Therefore the following source-law correction applies wherever the design text is ambiguous:

1. **Mastermind Improvement Agenda** remains the sole ranking engine.
2. R8-C modifies Mastermind, not Macro.
3. Macro remains the sole Agent OS / semantic-program-registry owner for R8-B.
4. R8 implementation must separate **Mastermind recovery + Agenda + Control Room work** from **Macro Agent OS wait-contract work**.
5. No new scheduler is authorized: R8-C must reuse the existing Mastermind `improvement_agenda_weekly` path or remain on-demand until its recovery-assessment provider is proven.

This correction does not change the Chairman-approved user experience, recovery findings, wait semantics, no-rebuild boundaries, projection law, fresh-Sol model, or completion standard.

## Current R1 collision boundary

PR #170 currently owns `control_plane/session_truth_acquire.py`, `control_plane/session_truth_contract.py` and their tests and is still advancing toward the full R1 interfaces frozen in `docs/superpowers/plans/2026-08-27-session-truth-r1.md`:

- `control_plane/session_truth_snapshots.py`
- `control_plane/session_truth_rules.py`
- `control_plane/session_truth.py`
- `scripts/session_truth_receipt.py`

R8-A must not write those files on #171 or create competing versions. Its implementation carrier begins only after R1 is accepted/merged and then consumes the accepted `build_receipt(...)`, `detect_findings(...)`, normalized observation contracts and semantic hashing law.

## Execution topology

The approved R8 program is decomposed into independent bounded carriers:

- **R8-B Agent OS wait contract** — Macro; may begin before R1 because it is parser/schema-owned and disjoint.
- **R8-A recovery classifier** — Mastermind; held until #170 R1 acceptance.
- **R8-C Improvement Agenda ingestion** — Mastermind; depends on R8-A.
- **R8-E Control Room CEO Attention** — Mastermind; depends on R8-A and uses existing read-only Control Room composition.
- **R8-D Linear projection** — dependency-held behind MAS-65/MAS-64/MAS-66 acceptance; no second projector.
- **R8-F Slack visibility** — dependency-held behind the accepted `#build-events` path; no queue/dispatch semantics.
- **R8-G fresh-Sol adversarial canary** — last integration acceptance after the real read paths/projections needed for the test are live.

Fable is the preferred sustained COO for the program. Codex may execute bounded technical waves under the current hybrid workforce law. Neither a Slack post nor a plan file is a runtime claim; Executive OS remains the sole Job/Attempt/Worker authority.
