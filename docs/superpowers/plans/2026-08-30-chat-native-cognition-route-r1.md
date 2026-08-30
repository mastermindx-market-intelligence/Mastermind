# Chat-Native Cognition Route R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing deterministic ModelRouter project ChatGPT Pro Chat as the default Sol-class cognition route and fail closed when a metered Sol cognition route lacks the complete bounded exception receipt.

**Architecture:** Extend the existing side-effect-free `control_plane.model_router` only. Lead-class work remains non-worker-dispatchable through existing `job_constraints()` law; this wave adds cognition economics and metered-exception validation without creating a provider call, Chat session, Capacity owner, lifecycle, queue, budget ledger, or second router. Existing Luna/Terra worker routes and config remain byte-unchanged.

**Tech Stack:** Python dataclasses/enums, deterministic pytest contracts, existing ModelRouter.

**Spec:** `docs/superpowers/specs/2026-08-29-chat-native-meta-ceo-core-model-design.md`

## Global Constraints

- Operation: `chat-native-cognition-route-r1-20260830-sol-001`.
- Protected pickup: `Mastermind@5a7046c46046a2ecf597c849aaab914b4f7cd5e1`, Skillpack v1.0.1 / bootstrap-major 1.
- `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md` is controlling cognition-economics source law.
- ChatGPT Pro Chat is the default Sol-class cognition route.
- `METERED_EXCEPTION` requires `WHY_METERED`, `WHY_PRO_CHAT_INSUFFICIENT`, `EXPECTED_MAX_COST`, `HARD_BUDGET_CAP`, `STOP_CONDITION`, and `BUDGET_AUTHORITY`.
- The router validates the receipt shape and bounded cost relation only; it does not become budget authority.
- `config/executive_worker_routes.json`, provider aliases, Worker placement, Executive lifecycle, Capacity, RuntimeBinding, Wake, Agent Relay, Business/MCP, browser control, accounts and credentials are out of scope.
- No lead-class decision becomes worker-dispatchable in this wave.

---

### Task 1: RED — require cognition route projection and metered refusal

**Files:**
- Create: `tests/test_chat_native_cognition_route_r1.py`

**Interfaces:**
- Consumes: `ModelRouter.route(WorkRequest(...))` and future `MeteredCognitionReceipt`.
- Produces: deterministic tests for default Chat route, complete metered receipt, incomplete/refused metered route, cost-cap validation, and unchanged worker routing.

- [ ] Write tests that import `CognitionRoute` and `MeteredCognitionReceipt`, assert default lead work is `CHAT_PRO_DEFAULT`, and assert explicit metered routing without a complete receipt fails with `METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE`.
- [ ] Assert a complete receipt permits only the lead decision projection, not `job_constraints()` worker dispatch.
- [ ] Assert expected cost cannot exceed hard cap and all string fields must be bounded/non-empty.
- [ ] Assert normal implementation/research/review routes preserve existing worker aliases and carry no Sol cognition route.
- [ ] Push RED and require hosted failure only because the new symbols/behavior do not exist.

### Task 2: GREEN — extend the existing ModelRouter only

**Files:**
- Modify: `control_plane/model_router.py`

**Interfaces:**
- Produces `CognitionRoute`, `MeteredCognitionReceipt`, and lead `RoutingDecision.cognition_route` / `metered_cognition_receipt` projection.

- [ ] Add `CognitionRoute.CHAT_PRO_DEFAULT` and `CognitionRoute.METERED_EXCEPTION`.
- [ ] Add frozen `MeteredCognitionReceipt` with bounded text validation, finite non-negative expected cost, positive hard cap, and `expected_max_cost <= hard_budget_cap`.
- [ ] Extend `RoutingDecision` with nullable cognition-route/receipt fields and JSON-safe `to_dict()` projection.
- [ ] Extend `ModelRouter.route()` and `route_work()` with optional cognition-route/receipt parameters. Default lead work projects `CHAT_PRO_DEFAULT`; explicit metered lead work requires a valid receipt; worker work refuses metered-cognition parameters.
- [ ] Preserve `preferred_model_aliases=("frontier.orchestrator",)` only as the existing non-dispatchable lead capability descriptor; the new cognition route is the controlling economic projection and `job_constraints()` continues to refuse every lead decision.
- [ ] Run focused and existing model-router regressions.

### Task 3: Release honesty

**Files:**
- Verify only: `control_plane/model_router.py`, `tests/test_chat_native_cognition_route_r1.py`, this plan.

- [ ] Require exact changed paths and no config/runtime/provider/account changes.
- [ ] Require repository CI and CodeQL on exact current-base head.
- [ ] Final Sol review must verify this is deterministic routing projection only: no Chat provisioning, no API call, no Business/Workspace-Agent call, no actual budget authority, no provider launch, and no fleet-live claim.
- [ ] Merge with expected-head protection after fresh current-base proof.

## Completion boundary

`CNM-R1` is `BUILT_NOT_PROVEN / PRODUCTION_INERT` when code is protected and exact-head tests pass. It becomes useful as the deterministic route guard consumed by later Chat provisioning/Capacity composition. It does not itself make a Meta-CEO hierarchy or Chat session autonomous.
