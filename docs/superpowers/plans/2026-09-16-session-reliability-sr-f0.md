# Mastermind Session Reliability SR-F0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect one operational session-reliability procedure that extends the existing MAS-198 context-rotation owner without adding a second chat/session control plane.

**Architecture:** Add `SESSION_RELIABILITY.md` as a Skillpack companion; project one compact kernel rule; align the existing rotation law and ACTIVE_EXECUTION final-response gate; preserve the incident as research evidence. Studio Direct enforcement remains a later independent carrier.

**Tech Stack:** Markdown source law, Python/pytest static contract tests, Git/GitHub evidence.

**Spec:** `docs/superpowers/specs/2026-09-16-session-reliability-sr-f0-design.md`

## Global Constraints

- Preserve `mastermind.sol_skillpack.v1`, Skillpack version `1.0.1`, minimum bootstrap major `1`.
- Extend `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`; do not create a second owner.
- Keep PR #706 records/procedure-only and production-inert.
- Do not modify Studio Direct transport, lifecycle, RuntimeBinding, provider, credential, or retry code.
- Preserve held PR #504, #674, and #147 semantics; do not import their unprotected source.
- Use the current PR/branch and operation carrier; no replacement PR.

---

### Task 1: Pin the failing contracts first

**Files:**
- Modify: `tests/test_web_sol_context_rotation_source_law.py`
- Modify: `tests/test_sol_skillpack_active_execution.py`

**Interfaces:**
- Consumes: existing `_read()` and `_normalized()` helpers.
- Produces: source-law assertions for `SESSION_RELIABILITY.md`, INDEX/kernel enrollment, rotation thresholds, budgets, capsule, and `CONTEXT_ROTATION` finalization.

- [ ] Add `SESSION_RELIABILITY_PATH = "docs/sol_skills/SESSION_RELIABILITY.md"` to the existing rotation test owner.
- [ ] Add a test requiring compatible front matter, INDEX registration, and mandatory selection triggers: more than three tool calls, host process, multi-source archaeology, resumed failure, or more than one material phase.
- [ ] Add a test requiring the 8 KiB/16 KiB/100-match/32 KiB/six-call/15s/30s budgets and the 12 KiB/1500-word capsule.
- [ ] Add a test requiring the two-failure threshold, resume-after-timeout/taint/effect threshold, single-failure truth rule, tainted-generation refusal, no raw-history manifest, and durable continuation before retirement.
- [ ] Add a test requiring the compact kernel to load the protected skill and forbid raw tool-history replay.
- [ ] Extend the active-execution test to require `CONTEXT_ROTATION` as a non-completion boundary with reconciled effects, durable capsule, active parent mission, and no ordinary finalization while `MORE_WORK_EXISTS`.
- [ ] Run the two focused test files and confirm RED only on the new assertions.

### Task 2: Add the protected session-reliability companion

**Files:**
- Create: `docs/sol_skills/SESSION_RELIABILITY.md`
- Modify: `docs/sol_skills/INDEX.md`
- Modify: `docs/sol_skills/BOOTSTRAP_KERNEL.md`

**Interfaces:**
- Consumes: current Skillpack metadata and existing source-owner hierarchy.
- Produces: one operational companion selected by INDEX and projected compactly by the kernel.

- [ ] Create compatible front matter and state explicitly that the skill creates no lifecycle, registry, retry ledger, memory store, or transport authority.
- [ ] Encode `SESSION_HEALTHY`, `ROTATION_SUSPECTED`, and `ROTATION_REQUIRED`, including exact thresholds and allowed actions.
- [ ] Encode response, turn, command, search, and process-continuation budgets.
- [ ] Encode the compact continuation capsule fields and the no-secrets/no-hidden-reasoning/no-raw-history rules.
- [ ] Encode timeout/PID reconciliation, taint behavior, provider/browser triage, support diagnostics, closeout/rotation sequence, and K-pass criteria.
- [ ] Register the skill in INDEX with the five mandatory selection triggers.
- [ ] Replace the provisional one-line kernel amendment with the approved compact `SESSION RELIABILITY` law.
- [ ] Run the focused tests; the enrollment/budget/capsule tests should turn GREEN while rotation-law and ACTIVE_EXECUTION assertions remain RED.

### Task 3: Align the canonical rotation owner and active-turn boundary

**Files:**
- Modify: `docs/EXECUTIVE_WEB_SOL_CONTEXT_ROTATION_LAW.md`
- Modify: `docs/sol_skills/ACTIVE_EXECUTION.md`

**Interfaces:**
- Consumes: the new skill’s closed classifications and the existing MAS-198 succession/effect law.
- Produces: one coherent local-turn rotation boundary without changing RuntimeBinding or successor-creation authority.

- [ ] Add a narrow tool-context pressure and transcript-hygiene section to the rotation law.
- [ ] Define two consecutive terminal generation failures with no successful intervening turn as `REPEATED_TERMINAL_GENERATION_FAILURE`.
- [ ] Define one resume failure after unresolved timeout, tainted connector generation, or `EFFECT_UNKNOWN` as rotation-required.
- [ ] Preserve `Thinking failed != context exhausted`, one successor, effect fence, and no blind retry.
- [ ] State that raw tool history is not a continuation manifest and planned retirement requires durable continuation first.
- [ ] Add `CONTEXT_ROTATION` to ACTIVE_EXECUTION’s final-response classifications with exact gates and explicit non-completion semantics.
- [ ] Update Step 7A and K5 for semantic-phase checkpointing and context rotation before another high-context phase.
- [ ] Run the focused tests and confirm GREEN.

### Task 4: Preserve the incident as evidence, not law

**Files:**
- Create: `research/MASTERMIND_SESSION_RELIABILITY_INCIDENT_2026-09-15.md`

**Interfaces:**
- Consumes: the September 15 case-study packet.
- Produces: a sanitized evidence record linked by the spec, with no live program state in the Skillpack.

- [ ] Record confirmed facts: large outputs, timed-out PID `75339`, failed output read, repeated terminal generation failures, prior taint, platform incident, and official clean-chat/support guidance.
- [ ] Separate the strongly inferred local failure chain from the unavailable private OpenAI exception.
- [ ] Record ruled-out primary causes and the exact do-not-build list.
- [ ] Record SR-F0/SR-T1/SR-D1/SR-PROD1 boundaries and metrics without claiming implementation or adoption.
- [ ] Scan for secrets, raw tool payloads, hidden reasoning, and live credentials.

### Task 5: Verify, reconcile collisions, and publish the exact carrier

**Files:**
- Verify: every changed file in this plan
- Update: PR #706 body and evidence comments only after source verification

**Interfaces:**
- Consumes: Tasks 1–4 exact branch head.
- Produces: immutable reviewed records/procedure candidate on the existing PR.

- [ ] Run `git diff --check`.
- [ ] Run `python3 -m pytest -q tests/test_web_sol_context_rotation_source_law.py tests/test_sol_skillpack_active_execution.py`.
- [ ] Run adjacent Skillpack tests that consume INDEX/kernel/ACTIVE_EXECUTION, including watcher, worker-routing, and delegation enrollment tests.
- [ ] Verify front matter compatibility and scan for forbidden duplicate-plane language.
- [ ] Compare candidate-owned paths against current protected master and open PRs #504, #674, and #147; preserve collisions in the PR receipt.
- [ ] Commit the spec/plan first, then the RED tests, then the minimal source-law implementation and incident record in reviewable commits.
- [ ] Push only to `sol/compact-continuation-anti-rehydration-20260916`; do not create a replacement PR.
- [ ] Obtain independent exact-head semantic review and current-base merge-ref proof.
- [ ] Require protected `test` and security checks before release. Vercel is unrelated unless site files enter scope.

## Plan self-review

Every SR-F0 source requirement maps to one task. Studio Direct transport work is explicitly excluded. The plan contains no placeholder implementation step, no new control plane, and no source path outside the existing owner set plus one evidence record. File and state names match the design.
