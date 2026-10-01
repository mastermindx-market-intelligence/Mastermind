# Adaptive Agent Economics F1 Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for this source-only slice. Keep one independent whole-candidate review before release; no claim of worker dispatch is made.

**Goal:** Make economical-worker policy coherent and make the existing router explain exclusions without claiming live cost or changing admission.
**Architecture:** Extend the existing pure ModelRouter and its read-only CLI. Reuse existing instruction owners and preserve all current routing/Job contracts.
**Tech Stack:** Python standard library, pytest, Markdown; no new dependencies.
**Spec:** `docs/superpowers/specs/2026-09-26-adaptive-agent-economics.md`

## Global constraints
- No live provider, account, host, permission, budget, depth, model-default or queue changes.
- No replacement of #1013/#981/#633/#1000 or the existing Model/Capacity/Provider Control owners.
- One owned source workspace; preserve existing Job constraint keys and legacy CLI output.
- Unknown runtime/price/qualification facts must be explicit; source alias is not enrollment.

## Review focus
- A frontier alias called fast/small must never be described as proven cheap.
- An unconfigured requested alias must remain unconfigured, never an automatically enabled route.
- A later suitability tier must never be promoted by explanation or comparison.
- Invalid explanation options must fail before Runtime.at can create state.
- Portfolio model policy must remain distinct from engineering-worker instructions.

## Task 1: existing router and CLI explanation
Files: `control_plane/model_router.py`, `scripts/executive_os_phase1b.py`, `tests/test_adaptive_agent_economics.py`.
Interface: `ModelRouter.explain_route(request: WorkRequest, *, considered_aliases: Sequence[str] = ()) -> dict[str, Any]`; existing `route --explain [--consider-model-alias ALIAS]`.
- [x] Write failing behavioral tests for unchanged decisions, tier dispositions, configured identity, unknown alias, deterministic alias order, bounded malformed input, no inferred price and lead isolation.
- [x] Run the focused tests and preserve the actual expected failure.
- [x] Implement the minimal pure explanation using `self.route(request)` and the same loaded configuration.
- [x] Wire only the existing route preview branch; reject considered aliases without --explain before runtime access.
- [x] Run focused and incumbent router/CLI tests; preserve actual output and source identities.

## Task 2: coherent engineering policy
Files: `AGENTS.md`, `CLAUDE.md`, `docs/sol_skills/WEB_CEO_DELEGATION.md`, `docs/EXECUTIVE_WORKER_ROUTING_CHAIRMAN_ADDENDUM.md`, the same focused test file.
- [x] Add failing source-conformance checks for adaptive roles, economical-worker candidates, bounded exceptions and portfolio/engineering separation.
- [x] Update existing owners rather than introducing another instruction registry; no version/price assumptions or new runtime enums.
- [x] Run tests, inspect the complete scoped diff and verify all preserved holds.

## Task 3: durable delivery and review
- [ ] Commit and push the exact tested candidate using the owned workspace and native Studio publication actions.
- [ ] Open a draft source PR with honest F1 proof; independent review/full CI and production qualification remain held.
- [ ] Persist Meta-CEO assignment, decision, source evidence and exact continuation in Macro Agent OS under WS:EXECUTIVE-CAPACITY-FABRIC; verify readback.
- [ ] Resume F2 through existing installed Fabric evidence/owner; do not mistake this source-only slice for the completed upgrade.
