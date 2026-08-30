# Sol Executive Capability Surface — End-to-End Program Plan

> **For operators:** Execute one independently useful vertical per carrier. Re-pin protected `docs/sol_skills/INDEX.md` and required procedures at every modifying boundary. Do not treat this plan as authority to start a wave whose named dependency or current carrier is unresolved.

**Program operation:** `mastermind-sol-executive-capability-surface-f0-20260830-sol-001`  
**Workstream:** `WS:CHAIRMAN-CONTROL-ROOM`  
**Architecture:** `docs/superpowers/specs/2026-08-30-sol-executive-capability-surface-design.md`  
**Protected planning basis:** `Mastermind@28d365cceaef6efb0a26e0ac9af51ead44695d60`  
**Program state:** `SPEC_ONLY / RECORDS_ONLY` until individual waves build and prove capabilities

## Goal

Make ChatGPT Sol the primary executive reasoning and operating interface for Mastermind while preserving Executive OS, Agent OS, GitHub, RuntimeBinding, Wake, Capacity, Dialogue, Linear, Steward and CodeIntel as canonical owners.

The program is complete only when the Chairman can give one large objective to Meta-CEO Sol and the real multi-program journey completes without routine message carriage, session hunting, GitHub/CI archaeology, provider/account selection or false-green completion.

## Architecture summary

The static `Mastermind Sol` plugin supplies current-source workflows. Small apps and native connected actions supply typed reads and bounded effects. No app owns company truth. No generic shell, browser, GitHub admin, SQL, filesystem, provider-specific spawn or super-MCP is permitted.

## Existing-owner gates

Before starting any wave, subtract current work from these existing owners:

- BSC program and plugin packages: existing #236/#243 carriers;
- Business OAuth/resource server: existing #237/#258/#269/#272 stack and successors;
- Executive Steward: existing #228 repair/release carrier;
- Web-Sol: existing #219 carrier and successors;
- CodeIntel: existing #276 architecture/program;
- Executive Attention: existing #275 architecture/program;
- GitHub estate governance: existing #259/#271 family;
- Chat-native routing: existing #263/#266 family;
- exact Sol action targeting: protected Stage A and separately gated Stage B;
- autonomous delegation/returns/retry/fleet: existing AD carriers;
- Agent Relay/Company Dialogue/Wake/RuntimeBinding: existing owners.

A current exclusive carrier remains exclusive even when this program wants the capability. Integrate after acceptance; never copy its code into a new branch.

---

## Wave SECS-F0 — architecture and capability inventory

**Observable mission:** Freeze the complete Sol capability taxonomy, native-versus-custom reuse, privilege classes, app boundaries, effect semantics, dependency DAG and end-to-end acceptance ruler.

**Files:**

- `docs/superpowers/specs/2026-08-30-sol-executive-capability-surface-design.md`
- `docs/superpowers/plans/2026-08-30-sol-executive-capability-surface-program.md`
- `docs/superpowers/plans/2026-08-30-sol-github-release-evidence-a1.md`

**Non-goals:** no implementation, app, OAuth, GitHub mutation, runner action, Agent OS mutation, Linear mutation, Slack message, credential, host action or production proof.

**Acceptance:** exact three-record diff on current protected base; hosted repository/security checks; adversarial Sol review; expected-head records merge. Merge makes source law durable only.

**Stop:** return after source review. Do not auto-start dependent runtime waves from merge alone; each requires its own current-source commission or explicit Sol direct implementation edge.

---

## Wave GH-A1 — pure GitHub release-evidence core

**Operation:** `mastermind-sol-github-evidence-a1-20260830-sol-001`

**Observable mission:** Given one exact, complete, current GitHub release snapshot and one exact source-law policy, deterministically return `READY_FOR_EXPECTED_HEAD_RELEASE`, `BLOCKED`, `RECONCILIATION_REQUIRED`, or `ALREADY_MERGED`, with exact reasons and no external effect.

**Owned files:**

- `integrations/mastermind_github_evidence/__init__.py`
- `integrations/mastermind_github_evidence/release_gate.py`
- `tests/test_mastermind_github_release_gate.py`

**Dependencies:** SECS-F0 reviewable source; current protected GitHub/Skillpack read; no collision on the three paths.

**Non-goals:** no network, GitHub SDK, MCP SDK, token, app, server, cache, DB, filesystem, subprocess, merge, rerun, review request, runner action, Executive state, deployment or production claim.

**Acceptance:** RED import failure recorded; focused GREEN; permutation and adversarial cases; manual mutation controls; compile/static read-only fence; current-base hosted CI/security; exact-head independent review.

**Real capability unlocked:** one reusable deterministic release judgment primitive for Chat/plugin, Control Room and future GitHub Evidence adapter consumers. It does not make release automatic or production-live.

---

## Wave GH-A2 — authenticated read-only GitHub evidence adapter

**Observable mission:** Gather the exact facts consumed by GH-A1 from GitHub using one dedicated least-privilege read principal and expose one bounded read-only tool:

```text
assess_release_gate({operation_ref, repository_ref, pull_request_ref})
```

Caller references are opaque and must resolve through trusted host policy; raw repository/PR selection may be allowed only for explicitly authorized CEO review scope. The adapter owns pagination, API normalization and source timestamps. It supplies no caller-authored check/review/path truth.

**Dependencies:** GH-A1 accepted; BSC-A1 authenticated MCP foundation accepted; app generation/publication plan; GitHub App read permissions; current official GitHub API recheck.

**Expected paths:** new `integrations/mastermind_github_evidence/adapter.py`, schemas/server tests and runbook only. Do not edit GH-A1 semantics except through a separately reviewed version.

**Acceptance:** exact live read of one harmless PR; all pages complete; no secret/token leakage; current head/base/check/review/path values agree with native GitHub; UI/text result remains useful; app disable leaves GitHub unchanged.

**Stop:** read-only production canary. No merge tool in this app generation.

---

## Wave GH-A3 — collision census

**Observable mission:** For one proposed operation scope, return a complete deterministic census of overlapping open PR paths, semantic owners, protected-source movement, duplicate carrier candidates and effect-unknown holds.

**Dependencies:** GH-A2 read path; accepted operation metadata contract; CodeIntel is optional evidence, not a prerequisite for exact GitHub path collision.

**Non-goals:** no writer election, PR closure, branch deletion, carrier transfer or source-law mutation.

**Acceptance:** canaries for exact disjointness, path overlap, semantic overlap without path overlap, stale protected base, duplicate branch/PR, effect-unknown existing operation and incomplete pagination.

---

## Wave GH-A4 — runner observatory

**Observable mission:** Explain GitHub Actions queue pressure and runner health from exact runner, label, group, workflow and job facts.

**Dependencies:** GH-A2 auth pattern; dedicated runner read permission; rights/privacy review; host-reference pseudonymization.

**Initial tools:**

```text
runner_fleet
runner_health
runner_pressure
explain_queued_workflow
```

**Non-goals:** no registration token, runner create/delete, label/group mutation, workflow rerun, SSH, process command or Capacity placement.

**Acceptance:** one real queued/idle/busy/offline matrix; label mismatch explanation; stale observation; permissions failure; incomplete runner page; zero token/host-secret leakage.

---

## Wave BSC-P2 — app-bound Mastermind Sol plugin generation

**Observable mission:** Publish a new immutable plugin generation that references accepted Steward, GitHub Evidence and Executive app generations while keeping workflows source-dynamic and capability-aware.

**Dependencies:** existing P1 #243 accepted/protected/imported as skills-only baseline; relevant app generations accepted; fixed-commit marketplace/canary law.

**Non-goals:** do not edit or silently sync P1; no mutable branch first canary; no embedded app credentials or current company state.

**Acceptance:** exact immutable commit, manifest digest, expected plugin/app inventory, one canary cockpit, two retained controls, invocation/readback receipt and rollback.

---

## Wave ST-A1 — Steward Business read surface

**Observable mission:** Expose accepted Executive Steward facts through a bounded authenticated read app and compact cockpit UI.

**Dependencies:** Executive Steward #228 correctness repaired/protected; gather adapter accepted; BSC-A1 auth; current app schema generation.

**Tools:** preserve the accepted six-read contract. Add no generic query language or owner mutation.

**Acceptance:** real current-source responsibility/attention/runtime/surface canaries, ambiguity/stale/failure states, prompt-injection corpus and disable proof.

---

## Wave EX-A1 — bounded Executive action surface

**Observable mission:** Let an authorized Sol submit one bounded CEO intent and inspect its canonical receipt through the existing CeoIngress/Executive OS owner.

**Dependencies:** BSC auth; CeoIngress production host/security proof; current grounding/state gate; exact principal policy; one harmless canary approved.

**Action law:** `submit_ceo_intent` creates one durable root receipt and stops. It never claims dispatch, execution or completion. Lost response reconciles same intent; no alternate ingress.

**Acceptance:** identical replay one root; changed payload conflict; grounding movement refusal; wrong principal/resource/scope refusal; one harmless real `QUEUED` receipt; disable/rollback.

---

## Wave SF-A1 — Surface read projection

**Observable mission:** Expose exact current RuntimeBinding/presence/action-target evidence without assuming OAuth identifies a Chat conversation.

**Dependencies:** HC0 findings; RuntimeBinding/SessionTarget sources; protected exact action-target resolver; Steward composition.

**Acceptance:** multiple chats under one principal remain distinct/unknown unless trusted binding exists; no newest-tab/first-responder election; stale/missing/conflicting target states are explicit.

---

## Wave SF-A2 — provision, rotate and retire Sol surfaces

**Observable mission:** Complete the semantic session lifecycle over existing Executive/Capacity/RuntimeBinding/Wake/Web-Sol owners.

**Dependencies:** Web-Sol installed proof; Stage-B transfer/succession source law; exact model/effort observation contract or truthful `MODEL_MODE_UNVERIFIED`; effect reconciliation.

**Actions:**

```text
provision_sol_surface
rotate_sol_surface
retire_sol_surface
```

No action accepts arbitrary URL, account, browser profile, title, prompt, click, selector or provider session ID.

**Acceptance:** real new responsibility → ACK → START → binding; context rotation with predecessor fence; adverse lost response, stale target, wrong profile and effect-unknown cases.

---

## Wave FL-A1 — fleet and semantic child commission

**Observable mission:** Give Sol one canonical child-commission action and one cross-root fleet view without provider-specific spawn authority.

**Dependencies:** transport-neutral root/child identity; mechanical provider returns; typed retry/rollover; cross-root fleet concurrency; Capacity route evidence; exact action target.

**Action:** `commission_child` takes mission/scope/non-goals/acceptance/resource class only. Provider/account/host/session fields are structurally absent.

**Acceptance:** cheap-capable route chosen; Fable rationale when justified; many independent roots; one action-authoritative child per root; stale worker fenced; provider return mechanically projected; no Chairman quota selection.

---

## Wave OP-A1 — operations observability

**Observable mission:** Expose closed health facts for known services, hosts, tunnels, adapters, indices and transports.

**Dependencies:** identify existing owner for every fact; pseudonymous host/service schema; least-privilege read principal.

**Non-goals:** no generic shell, process listing, environment, arbitrary log, filesystem or credential output.

**Acceptance:** real healthy/degraded/down/stale/unknown examples; source freshness; output size/redaction; no action tool.

---

## Wave OP-A2 — bounded administrative actions

**Observable mission:** Add only the exact administrative actions whose endpoint, precondition, effect and rollback contracts survive independent security review.

**Dependencies:** OP-A1 proves need; explicit A3 authorization; endpoint-specific atomicity/effect design; separate app/principal; current host/vendor policy.

Potential actions are considered individually. A generic admin tool is forbidden. Unsupported atomic mutation families remain assessment-only.

---

## Wave CR-A1 — integrated CEO cockpit

**Observable mission:** Let `open-executive-cockpit` compose Steward, GitHub Evidence, Capacity/Runner, Surface and capability-health results into one compact source-attributed Chat/UI experience.

**Dependencies:** at least ST-A1, GH-A2 and capability introspection; EAF only after its own accepted program.

**Views:** company, attention, runtime, evidence, capacity/runner, exceptions and exact next action.

**Non-goals:** no UI-owned state/authority, task database, scheduler, hidden top-N omission or direct generic actuation.

**Acceptance:** text remains complete if UI fails; compact view has omission receipts; no false-green status; real multi-program composition.

---

## Wave EC-A1 — economics and learning

**Observable mission:** Measure whether the capability surface reduces expensive reasoning and Chairman labor without using raw transcript capture as the default analytics method.

**Metrics:** manual interventions, state-archaeology turns, return-to-adjudication latency, Fable share, metered cognition exceptions, duplicate/effect-unknown incidents, cheap-worker routing, PR/production cycle time, tool failures and source coverage.

**Acceptance:** point-in-time baseline, prospective canary cohort, explicit coverage, no hindsight-only promotion, no autonomous authority/routing change from model summaries.

---

## Final canary and promotion

Promote through:

```text
LOCAL / PURE CORE
-> AUTHENTICATED READ SHADOW
-> ONE COCKPIT CANARY
-> READ + ONE HARMLESS BOUNDED ACTION
-> MULTI-PROGRAM DUAL RUN
-> BUSINESS/CHAT PRIMARY OPERATING CANARY
-> PRODUCTION FLEET
```

Every stage preserves rollback and existing fallback surfaces. Promotion requires real input through the real path, visible user/machine output, adverse proof and exact durable closeout.

## Program stop condition

The program ends only when the complete acceptance journey in the architecture passes and telemetry demonstrates lower Chairman labor, lower state-archaeology burden and no increase in unsafe/duplicate/false-green operations.

At every intermediate return, state the exact capability now unlocked, its capability-state vocabulary, what remains unproven, current blockers and the single next dependency action.
