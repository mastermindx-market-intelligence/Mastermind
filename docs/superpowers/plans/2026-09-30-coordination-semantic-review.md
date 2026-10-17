# Coordination Semantic Review Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this explicitly assigned inline continuation. Reuse the registered #1056 workspace; do not create or transfer a worker.

**Goal:** Carry a verified coordination proposal into an already-admitted independent review, return the complete judgment to the principal, and qualify consumption through the existing COO parent.

**Architecture:** An optional task composer reuses the original bounded Runtime, sealed-artifact reader, work-result consumer, effective-grant validator and review result schema. A supervisor subclass overrides only the selected review Job's prompt. No admission, execution, acceptance, memory, identity or persistence owner changes.

**Tech Stack:** Existing Python 3.12, pytest, Executive Runtime/Supervisor and Fabric result projection.

**Spec:** `docs/superpowers/specs/2026-09-29-pro-led-coordination-consumer.md`, especially the trust boundary and model/parent-consumption qualification boundary.

## Global Constraints

Operation `mastermind-pro-led-project-delivery-20260929-sol-001`, #1056 / draft #1059. Existing branch/workspace and source custody remain. Pro remains the substantive principal; review does not replace its judgment. Current Executive ingress is read-only: no live dispatch, provider CLI, installed service, credential or production-state changes. No new result role, compiler, registry, scheduler or acceptance record. Constructed fixtures/hashes do not authenticate live owners. Original deterministic review output is unchanged and still grants zero authority.

## Review Focus

A full verified candidate, not a shortened summary, reaches the review task. Exact current review/work/project/plan/Attempt identities must agree. Source or artifact drift refuses without fallback or replay. Approval of a policy-held proposal cannot promote it into eligibility. A reviewer citation or parent handoff is not Web Pro consumption or project acceptance.

## Task 1 — Scoped review task and return composition

**Files:** Create `control_plane/chairman_coordination_review.py` and `tests/test_chairman_coordination_review.py`.

**Interfaces:** `read_coordination_review_request(*, sources, runtime, root_job_id, review_job_id, reviewed_job_id, expected_attempt_id, authority_decision, artifact_reader)` composes current source evidence for an already-admitted review. `read_coordination_review_return` selects an exact completed review result and reacquires its reviewed work artifact. `CoordinationReviewSupervisor` overrides only `_prompt` and leaves all original effect methods inherited.

- [x] Write tests showing complete rationale/instruction and source evidence, unchanged review schema, exact identities/grant, source/artifact drift, no synthetic acceptance and bounded content.
- [x] Run the new tests RED before implementation, using the operation's existing hermetic environment.
- [x] Implement owner composition without modifying Runtime, Supervisor, source composer, memory compiler or the prior work consumer.
- [x] Run new tests GREEN and affected narrow regressions; do not repeat unchanged broad campaigns.

## Task 2 — Existing parent consumption qualification

- [x] Exercise concrete sealed-file acquisition and compiled-context binding with the real temporary Runtime/Supervisor, an explicitly fake model and an independently bound reviewer.
- [x] Prove that the existing `CooCycle` consumes the exact reviewed result into its own handoff; prove missing/rejected review does not yield an approved parent handoff.
- [x] Preserve model-fixture versus actual-provider evidence, principal-consumption and acceptance as distinct facts.
- [ ] Inspect exact source diff, test receipts and immutable source hashes; publish only through the existing fenced Studio commit/push actions.
- [ ] Extend the existing spec and cumulative #1056 checkpoint with verified results and exact remaining live gates.

## Execution ruling

This is a source-only continuation of the accepted consumer/host design, not a new live activation. Direct execution is retained for PRINCIPAL_JUDGMENT: the missing semantic handoff must preserve the existing product and authority boundaries. The busy base team is not retasked. No additional approval round or new worker is requested. Independent source review and installed/model/Web qualification remain held.

## Task 3 — Full proposal in the original aggregation parent

**Files:** Create `control_plane/chairman_coordination_parent.py` and `tests/test_chairman_coordination_parent.py`.

**Interface:** `CoordinationParentSupervisor` specializes only `_prompt` for the exact configured aggregation root and coordination work Job. It uses the original canonical handoff getter, derives the qualifying review from that handoff, consumes `read_coordination_review_return` through bounded owner reads and adds complete proposal/current evidence to the original parent prompt. Parent schemas and all effect/lifecycle methods remain inherited.

- [x] Write missing-module and actual parent-prompt/result tests RED.
- [x] Add the bounded composition, exact current parent assignment comparison and canonical handoff/result-digest binding; refuse partial selection, changed sources and absent independent approval.
- [x] Exercise actual temporary parent supervisor/result completion, with explicit fake model output derived from delivered content. Preserve all original aggregation revisions and evidence and show replay does not run the model or next instruction again.
- [ ] Verify the new suites and affected regressions, record immutable scoped evidence and publish the existing branch/checkpoint. Do not claim live inference, semantic usefulness or Web Pro activation from fixtures.

### Implementation rulings from owner validation

Reviewed-result identity is the role-result digest; the envelope digest remains the acquisition selector and the artifact hash identifies candidate bytes. ExactWorkerClaimTarget admission is deliberately work-only; review/parent compositions retain the original generic role admission and do not drop a supplied failing target. Physical principal, worker, account and provider-home independence remain the original parent's responsibility. A completed same-OS fixture review must be refused by that parent. Positive independent consumption uses the existing explicit OHF fixture and is labeled protocol qualification, not physical/live-model proof. Review returns expose `review_independence:NOT_PROJECTED` and `review_supports_proposal`, never a new eligibility or acceptance ruling. Full proposal text must reach the aggregation parent, not merely its handoff's digest list.

## Verified source boundary

New source and protocol qualification is complete: 36 review cases, 17 parent
cases and two existing acquisition integration guards passed (55 total), with all
tested source hashes unchanged. Original dependency source was not modified.
The final receipt is `.pytest_cache/coordination-semantic-final.json`; compact
publishable evidence is `research/evidence/pro-led-coordination-review-20260930.json`.
Publication actions and immutable resulting HEAD are recorded by the existing
#1056 cumulative checkpoint, not inferred from plan checkboxes. Independent source
review, accepted install, actual model/parent usefulness and Web Pro input/turn/return
remain separate gates. MISSION_COMPLETE:false; no busy base team was reassigned.
