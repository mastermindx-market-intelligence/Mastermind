# Project Recovery Sentinel R8 — Program Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the Chairman-approved permanent recovery system end to end: typed intentional waits, deterministic dead-project classification, ranked CEO recovery attention, Control Room/Linear projection, and a fresh-Sol production recovery canary—without creating another lifecycle, queue, scheduler, parser, identity or truth store.

**Architecture:** R8 is a downstream consumer/extension of the accepted cross-plane Session Truth architecture. Macro owns Agent OS + semantic-program source extensions; Mastermind owns the recovery classifier, Improvement Agenda and Control Room. Linear and Slack remain dependency-gated projections. Execution is decomposed into independently reviewable verticals so active R1/#170 and existing projector/visibility programs keep their canonical carriers.

**Tech Stack:** Macro Agent OS/PyYAML, Mastermind stdlib `control_plane`, R1 Session Truth, Improvement Agenda, Chairman Control Room HTML/CSS/JS, existing Linear Projector and Slack integrations when accepted, pytest/GitHub Actions, existing fresh-Sol/Executive capabilities when production-proven.

**Spec:** `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-design.md` and `docs/superpowers/specs/2026-08-27-project-recovery-sentinel-r8-current-state-amendment.md`.

## Global Constraints

- Chairman approved the written R8 architecture on 2026-08-27.
- Operation key: `project-recovery-sentinel-r8-20260827-sol-001`.
- Protected planning basis: Mastermind `6f1bc3dd39f1ebecd3c22e44aa11ca7a13fa5182`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0/bootstrap major 1. Every modifying wave re-pins current protected master at pickup.
- Macro planning basis: `0758de6b9a7e9e920a6f44e4c1abcd62dbf8074e`; every Macro wave re-pins current `main` at pickup.
- Mastermind PR #170 is the sole Session Truth R1 implementation carrier. R8-A may not start until R1 is accepted/merged.
- No new `WS:` workstream for Recovery Sentinel. Existing organizational parent remains `WS:CHAIRMAN-CONTROL-ROOM`; implementation/closeout must update that existing durable context or an exact handoff without creating a parallel lifecycle.
- Fable is preferred sustained COO/program integrator. Codex may execute bounded technical waves under current hybrid workforce source law. Neither plan files nor Slack posts prove execution; Executive OS owns runtime Job/Attempt/Worker claim.
- No generic Slack fanout when no real receiver exists.
- Exact joins only; no fuzzy title/name matching.
- No parsing of `next_action`/wait condition prose to infer authority/liveness.
- No universal inactivity threshold.
- Unknown runtime state fails closed to `UNKNOWN_RECONCILE`, not duplicate work.
- No new daemon/scheduler; reuse existing Agenda schedule and accepted projection schedules only.
- Green CI/merge/projection is not full R8 acceptance. R8-G is the final acceptance gate.

## Subplans

1. `docs/superpowers/plans/2026-08-27-project-recovery-r8-agentos-wait-contract.md` — R8-B1.
2. `docs/superpowers/plans/2026-08-27-project-recovery-r8-program-registry-source.md` — R8-B2.
3. `docs/superpowers/plans/2026-08-27-project-recovery-r8-recovery-core.md` — R8-A.
4. `docs/superpowers/plans/2026-08-27-project-recovery-r8-improvement-agenda.md` — R8-C.
5. `docs/superpowers/plans/2026-08-27-project-recovery-r8-control-room.md` — R8-E.
6. `docs/superpowers/plans/2026-08-27-project-recovery-r8-projections.md` — R8-D/F.
7. `docs/superpowers/plans/2026-08-27-project-recovery-r8-fresh-sol-canary.md` — R8-G.

---

## Dependency graph

```text
                      active predecessor
                   Mastermind #170 / R1
                           |
                           v
                    R8-A recovery core
                      /           \
                     v             v
              R8-C Agenda      R8-E Control Room
                     \             /
                      \           /
                       v         v
                         R8-G

R8-B1 Agent OS wait  ----> R8-A
R8-B2 program source ----> R8-A

R8-D Linear projection:
  R8-A + MAS-65 accepted + MAS-64 app + MAS-66 accepted/armed

R8-F Slack visibility:
  dependency-held until an accepted recovery-assessment -> #build-events
  visibility seam exists; MAS-103/104 alone do not provide that seam.
```

R8-B1 and R8-B2 are independent of #170 and may execute in parallel on separate Macro carriers because they touch distinct responsibilities within the same canonical `scripts/agentos.py` owner. Their builders must coordinate changed hunks and merge order; if both modify the same parser sections, land one then reconcile the second onto current main rather than racing blind.

---

## Wave ownership and observable stop conditions

| Wave | Repo | Preferred operator | Start gate | Independently useful stop |
|---|---|---|---|---|
| R8-B1 typed wait | Macro | bounded Codex/Fable | current Skillpack + collision check | Agent OS validates/projects typed waits; no business migration |
| R8-B2 program source | Macro | bounded Codex/Fable | current Skillpack + collision check | `agentos.program_registry.v1` exposed in state; orphan candidates report-only |
| R8-A classifier | Mastermind | Fable sustained + bounded technical worker | R1 accepted + B1/B2 accepted | deterministic current-estate assessment, Sol accepted |
| R8-C Agenda | Mastermind | Fable/bounded worker | A accepted | current recovery findings ranked by existing Agenda |
| R8-E Control Room | Mastermind | Fable/bounded product worker | A accepted | read-only recovery panel + browser proof |
| R8-D Linear | Macro + existing Linear app | existing projector owner/Fable | A + MAS-65/64/66 gates | recovery managed block projected through existing projector |
| R8-F Slack | existing visibility owner | held | accepted generic recovery visibility seam | optional transition visibility; otherwise explicit dependency-held |
| R8-G canary | cross-plane | Sol CEO + Fable sustained executor | A/C/E + runtime gates | fresh Sol recovers one real program end to end |

---

## Phase 0: Land architecture/plans and organizational continuation

- [ ] **Step 1: Reconcile PR #171 against current protected master**

Read current protected Skillpack, PR #170/#171, PR #172 workforce law and current Macro head. Preserve #170/#171 as independent carriers.

- [ ] **Step 2: Verify all plan files against the approved spec**

Required coverage:

```text
wait semantics -> B1
semantic program census -> B2
all nine recovery findings + five dispositions -> A
a sole ranker -> C
Linear projection without authority widening -> D
Control Room product -> E
Slack optional/dependency-held -> F
12-case + real fresh-Sol canary -> G
```

- [ ] **Step 3: Update PR #171 from “review gate” to “approved execution architecture”**

The PR body must state Chairman written-spec approval, current source pins, ownership correction, all subplans, active #170 dependency, and which waves are immediately executable versus held.

- [ ] **Step 4: Hosted CI on #171 exact head**

This is docs/plan proof only. Green CI does not make R8 built.

- [ ] **Step 5: Merge #171 after exact-head review if no source-law collision**

Use expected head SHA. After merge verify protected master contains the spec, amendment and all plans. Do not interpret merge as implementation acceptance.

- [ ] **Step 6: Record one existing-parent Agent OS continuation**

Under normal Agent OS ownership, add an exact continuation/handoff referencing `WS:CHAIRMAN-CONTROL-ROOM`, PR #171 merge, operation key, B1/B2/A/C/E/D/F/G topology and current next action. Prefer a new handoff record over editing a highly contended workstream unless current law requires the wave list itself to change. No new Recovery Sentinel workstream.

---

## Phase 1: Execute the two independent Macro source verticals

### R8-B1

- [ ] Commission/claim one bounded Macro carrier implementing only the typed wait plan.
- [ ] Require RED-first tests, current-store validation and hosted CI.
- [ ] Sol reviews exact head; merge only after schema/parser/view law is preserved.
- [ ] Do not migrate business waits in the same carrier.

### R8-B2

- [ ] Commission/claim a separate bounded Macro carrier implementing only the semantic program source plan.
- [ ] If B1 lands first and touches shared parser areas, reconcile B2 on current main without force or duplicated helpers.
- [ ] Require current-estate lifecycle=`building`/exact inverse-map receipt.
- [ ] Sol reviews and merges.

### Post-B1 business wait migration

- [ ] Sol reviews candidate intentional waits from current canonical evidence.
- [ ] Only evidence-backed waits receive separate Agent OS amendments with explicit `review_after` and `condition`.
- [ ] Never bulk-convert every quiet active project into a wait.
- [ ] At minimum re-evaluate current Prophet Conditional Fusion prospective accrual; choose its review point from current forward evidence, not from this plan’s historical snapshot.

**Phase 1 stop:** canonical Agent OS can distinguish machine-readable intentional inactivity and expose semantic program lifecycle; no recovery classification exists yet.

---

## Phase 2: Accept R1 and build R8-A

- [ ] Keep R8-A held while #170 remains unaccepted.
- [ ] When #170 returns, Sol reviews it under `REVIEW_RETURN.md` against the full R1 outcome.
- [ ] Merge/accept R1 only after current-estate deterministic receipt proof passes.
- [ ] Reconcile R8-A plan interfaces to the actual merged R1 shapes; no copied draft module.
- [ ] Commission R8-A as one Mastermind carrier.
- [ ] Execute contract -> exact indexes -> wait/gate -> recovery findings -> assessment -> CLI -> current-estate census in TDD order.
- [ ] Sol reviews every recovery false-positive/false-negative class before merge.
- [ ] Merge only after hosted CI + current-estate receipt acceptance.

**Phase 2 stop:** Mastermind can deterministically say which material subjects are healthy/waiting/attention/recovery/unknown from explicit normalized current evidence.

---

## Phase 3: Make recovery operationally visible without creating execution authority

### R8-C Agenda

- [ ] Add `project-recovery` + `ceo-sol` to the existing sole ranker.
- [ ] Inject current assessment before existing rank/age stage.
- [ ] Preserve post-rank Agent OS readiness annotation.
- [ ] Reuse `improvement_agenda_weekly`; no new job.
- [ ] If R1 lacks real current external acquisition, keep weekly recovery input dependency-held and prove on-demand assessment injection instead of building duplicate readers.

### R8-E Control Room

- [ ] Add pure additive recovery output.
- [ ] Add current-provider gather only if accepted.
- [ ] Render CEO recovery summary/list and exact navigation.
- [ ] Prove desktop/narrow browser UX and explicit degraded state.
- [ ] No send/wake/assign controls.

**Phase 3 stop:** the Chairman/fresh Sol can see and navigate current recovery debt without relying on chat memory.

---

## Phase 4: Project where current contracts permit

### R8-D Linear

- [ ] Do nothing while MAS-65 remains unmerged or MAS-64/66 unaccepted.
- [ ] After gates, extend the **existing** `linear_portfolio_plan.v1` producer to consume normalized recovery assessment.
- [ ] V1 writes recovery only into the existing managed description block.
- [ ] Explicitly keep `CEO Recovery Required` label/status mutation unauthorized while MAS-66 P1 forbids labels/status.
- [ ] Use MAS-66 dry-run/current re-read/idempotent app path; no direct R8 Linear adapter.

### R8-F Slack

- [ ] Keep dependency-held unless a later accepted generic recovery-event visibility seam exists.
- [ ] Do not create Linear surrogate issues, fake GitHub events, custom bots/relays/cursors or `#agent-dispatch` posts.
- [ ] Record optional Slack projection debt without blocking canonical recovery truth.

**Phase 4 stop:** Linear is useful within current authority; Slack may remain explicitly unavailable.

---

## Phase 5: R8-G fresh-Sol acceptance

- [ ] Run 12-case adversarial corpus through accepted fresh-Sol evaluation capability if available.
- [ ] Generate a current R8 assessment/Agenda and deterministically select one safe real `RECOVERY_REQUIRED` subject.
- [ ] Start a genuinely fresh production Sol session from MastermindX Project/Control Room with only “Take the next CEO Recovery item and own it end to end.”
- [ ] Prove it identifies/reconstructs the correct current program without Chairman archaeology.
- [ ] Prove wait/unknown/duplicate cases are refused.
- [ ] If current Executive/Fable ingress is production-proven, commission one real bounded recovery wave and require actual worker/session claim.
- [ ] Advance one independently useful program capability through its own production/research proof law.
- [ ] Update durable Agent OS state and regenerate assessment/Agenda.
- [ ] Original recovery finding clears or truthfully transforms from canonical evidence.
- [ ] Record final acceptance receipt.

**Program stop:** only after R8-G. If read-only recovery works but actual sustained Executive/Fable handoff remains unavailable, final state is `BUILT_NOT_PROVEN`, not `PROVEN_LIVE`.

---

## Collision rules for operators

1. Never edit #170-owned Session Truth files before R1 merge.
2. B1/B2 share `scripts/agentos.py`; use separate carriers and explicit merge order/current-main reconciliation.
3. Do not create a second semantic-registry parser in Mastermind.
4. Do not create a second Improvement Agenda/current ranker.
5. Do not create a direct R8 Linear API client; extend the existing projector path.
6. Do not create a direct R8 Slack relay.
7. Do not let Control Room store recovery state.
8. Do not convert an advisory Agent OS `claim` into runtime proof.
9. Do not treat a fresh-Sol evaluation harness sample as production runtime claim.
10. Never hide an unavailable canonical source behind an empty list/zero count.

---

## Required operator return for every R8 carrier

Every return to Sol must include:

```text
mission completed
exact repo + branch + immutable head
protected Skillpack SHA used
base/current-main SHA used
changed files
RED evidence
GREEN targeted tests
hosted CI/checks
current-estate/product proof
capability now unlocked
what remains unproven
collisions/source movement
exact next action
explicit stop/non-goals
```

No carrier self-declares full R8 completion.

---

## Plan self-review checklist

- Spec coverage: all approved R8 §§1-22 map to B1/B2/A/C/D/E/F/G above.
- Ownership correction: Agenda is Mastermind-owned everywhere in execution plans.
- R1 collision: A is strictly held behind #170 acceptance.
- Program registry ownership: Macro projects it; Mastermind does not parse YAML.
- Linear authority: current P1 label/status prohibition preserved.
- Slack authority: current official integrations do not masquerade as a recovery-event seam.
- Fresh Sol: isolated behavioral evidence and real production operating proof remain distinct.
- No placeholders/TODO implementation instructions remain; dependency-held tasks name exact gates and refusal behavior.
- No duplicate lifecycle, queue, scheduler, parser, ranker, projector, Slack relay, identity or recovery store is introduced.
