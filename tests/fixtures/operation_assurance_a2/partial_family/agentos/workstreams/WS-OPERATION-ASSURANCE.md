---
schema: agentos.workstream.v1
key: OPERATION-ASSURANCE
title: Mastermind Operation Assurance (OLS) — liveness/soundness checker to full production
objective: >
  A Program CEO or machine admission consumer can submit a proposed or running operation,
  receive a deterministic source-attributed liveness/soundness assessment with the shortest
  actionable counterexample or valid-wait explanation, see it in the existing Control Room,
  and observe a real report-only canary changing an operational decision — without a second
  lifecycle, source, authority, retry, status, or observability plane.
status: active
program: cross-repo-contract-governance
repos: [mastermind]
owner: Fable principal (COO seat), Sol retains architecture + release acceptance
class: build
blast_radius: reversible
ambiguity: scoped
waves:
  - {id: R0, title: "Recover canonical truth; protect OLS-F0 architecture/source law (PR 279)", status: done, pr: 279}
  - {id: A1, title: "Pure deterministic assurance engine + immutable report + report-only CLI (PR 324)", status: done, pr: 324}
  - {id: A2, title: "Canonical owner/source compilation via separately-accepted bounded gather seam", status: in_progress, next_action: "Commission the bounded A2 implementation (routed builder) compiling WS:OPERATION-ASSURANCE into the protected A1 engine, per the accepted seam design; carrier is the fable-003 child"}
  - {id: A3, title: "Correction-safe current applicability + evidence-preserving summary", status: todo, depends_on: [A2], next_action: "Design the correction-safe applicability contract once A2 lands; owner drafts the wave A3 spec"}
next_action: >
  Land the A2 gather/source-compiler seam implementation (Mastermind PR, fable-003 carrier)
  compiling WS:OPERATION-ASSURANCE into the protected A1 engine with full provenance receipts;
  request Sol acceptance before Wave A3 starts.
do_not_redo:
  - "Do not re-diagnose the false-green Slack RESULT sequence on the parent carrier (F0/A1/A2 'PROTECTED' claims dated pre-2026-09-01): Sol's canonical correction overrode them and R0 re-landed F0 for real; GitHub is truth."
  - "repair_scope is RULED out of the F0/A1 wire (removed, pinned by exact-tuple tests at Mastermind tests/test_operation_assurance_a1_repair_wave.py); do not re-freeze it without superseding the ruling."
  - "Do not build a gather layer inside the pure A1 checker or a second Steward/federated reader — Steward-reconciliation spec §5-§8 forbids it; the seam must be separately accepted."
  - "PROPER_COMPLETION overlapping-terminal ownership is INTERSECTION (fail-closed principal ruling, reviewer-probed in 3 directions); do not revert to union."
landmines:
  - "Mastermind master requires up-to-date branches and allows squash-merge ONLY; reconcile via history-preserving server-side merge (merges API), never rebase/force-push."
  - "Mastermind master moves roughly hourly; fast-follow the merge after CI greens or the up-to-date gate refuses again."
  - "Several OLS-F0 'contract' tests are document-parity greps over spec prose, not engine coverage — green there does not prove the engine (this is exactly how the unbounded fairness product shipped its first draft)."
---

# Operation Assurance (OLS) — synthetic corrected copy for OLS-A2 fixtures

Synthetic test fixture: a corrected copy of the real WS-OPERATION-ASSURANCE.md record with
next_action/wave-A2 next_action updated to reference the current fable-003 operation, used ONLY
as the OLS-A2 positive end-to-end fixture (design Section 6: no such corrected revision has
landed through the Agent OS owner's own lawful process yet, so the implementation wave's own
FROZEN SPEC clarification (5) authorizes a synthetic corrected copy for the positive proof).
