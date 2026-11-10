# Chat-Native Cognition Route R1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing deterministic ModelRouter project included Chat web with non-Pro
reasoning as the default Sol-class route, admit turn-billed Pro mode only for fully receipted
80-to-1440-minute frontier work, and keep the existing metered-surface exception separate.

**Architecture:** Extend the existing side-effect-free `control_plane.model_router` only. Lead-class
work remains non-worker-dispatchable through existing `job_constraints()` law; this wave separates
included Chat surface selection (`CognitionRoute`) from Chat reasoning mode
(`ChatReasoningMode`), validates `ProModeReceipt` and the unchanged `MeteredCognitionReceipt`, and
creates no provider call, Chat session, Capacity owner, lifecycle, queue, budget ledger, or second
router. Existing Luna/Terra worker routes and config remain byte-unchanged.

**Tech Stack:** Python dataclasses/enums, deterministic pytest contracts, existing ModelRouter.

**Spec:** `docs/superpowers/specs/2026-08-29-chat-native-meta-ceo-core-model-design.md`

## Global Constraints

- Operation: `chat-native-cognition-route-r1-20260830-sol-001`.
- Protected pickup: `Mastermind@5a7046c46046a2ecf597c849aaab914b4f7cd5e1`, Skillpack v1.0.1 / bootstrap-major 1.
- `docs/EXECUTIVE_CHAT_NATIVE_SOL_HIERARCHY_LAW.md` is controlling cognition-economics source law.
- The default lead receipt is `CognitionRoute.CHAT_INCLUDED_DEFAULT` plus
  `ChatReasoningMode.NON_PRO_DEFAULT`.
- `ChatReasoningMode.PRO_MODE_EXCEPTION` is never default. It requires `ProModeReceipt` with
  `WHY_PRO_MODE`, `WHY_NON_PRO_INSUFFICIENT`, one closed `PRO_MODE_TASK_CLASS`, integer
  `80 <= EXPECTED_DURATION_MINUTES <= 1440`, and `STOP_CONDITION`.
- Closed Pro classes are `LONG_HORIZON_FRONTIER_REASONING`, `CROSS_SYSTEM_ARCHITECTURE`,
  `HARD_DEBUGGING`, and `ADVERSARIAL_JUDGMENT`.
- Handoffs, lifecycle/routing packets, status, monitoring/watchers/polling, relay, placement,
  foregrounding, mechanical edits/tests, simple reviews, and other short bounded work are refused
  Pro mode and remain `NON_PRO_DEFAULT`.
- Historical `CHAT_PRO_DEFAULT` receipts remain historical evidence only. The label is deprecated,
  surface-only, and grants no Pro-mode authorization.
- `METERED_EXCEPTION` requires `WHY_METERED`, `WHY_PRO_CHAT_INSUFFICIENT`, `EXPECTED_MAX_COST`, `HARD_BUDGET_CAP`, `STOP_CONDITION`, and `BUDGET_AUTHORITY`.
- `PRO_MODE_EXCEPTION` and `METERED_EXCEPTION` are independent; neither receipt satisfies or
  authorizes the other.
- The router validates the receipt shape and bounded cost relation only; it does not become budget authority.
- `config/executive_worker_routes.json`, provider aliases, Worker placement, Executive lifecycle, Capacity, RuntimeBinding, Wake, Agent Relay, Business/MCP, browser control, accounts and credentials are out of scope.
- No lead-class decision becomes worker-dispatchable in this wave.

---

### Task 1: RED — require separate Chat surface/mode projection and both exception gates

**Files:**
- Create: `tests/test_chat_native_cognition_route_r1.py`

**Interfaces:**
- Consumes: `ModelRouter.route(WorkRequest(...))`, `ProModeReceipt`, and
  `MeteredCognitionReceipt`.
- Produces: deterministic tests for the included-Chat/non-Pro default, complete and refused Pro
  receipts, complete and refused metered receipts, and unchanged worker routing.

- [x] Assert default lead work projects `CHAT_INCLUDED_DEFAULT` and `NON_PRO_DEFAULT` with neither
  exception receipt present.
- [x] Assert `PRO_MODE_EXCEPTION` requires a complete `ProModeReceipt`, admits only the four closed
  task classes, rejects non-integer, sub-80-minute, or over-1440-minute duration, and returns
  `PRO_MODE_REFUSED / USE_NON_PRO_MODE` when incomplete or ineligible.
- [x] Assert handoff/lifecycle/status/monitoring/relay/routing/placement/foregrounding/mechanical
  work/tests/simple review and other short bounded tasks cannot select Pro mode.
- [x] Assert explicit metered routing without a complete receipt fails with
  `METERED_ROUTE_REFUSED / WAITING_FOR_LAWFUL_ROUTE` and never implicitly selects Pro mode.
- [x] Assert a complete receipt permits only the lead decision projection, not `job_constraints()` worker dispatch.
- [x] Assert expected cost cannot exceed hard cap and all string fields must be bounded/non-empty.
- [x] Assert normal implementation/research/review routes preserve existing worker aliases and
  carry no Sol cognition route, reasoning mode, or exception receipt.
- [x] Capture local RED before GREEN; do not publish an intentionally broken intermediate head to
  the existing carrier.

### Task 2: GREEN — extend the existing ModelRouter only

**Files:**
- Modify: `control_plane/model_router.py`

**Interfaces:**
- Produces `CognitionRoute`, `ChatReasoningMode`, `ProModeTaskClass`, `ProModeReceipt`,
  `MeteredCognitionReceipt`, and their nullable `RoutingDecision` projections.

- [x] Replace the ambiguous default with `CognitionRoute.CHAT_INCLUDED_DEFAULT`; retain
  `CognitionRoute.METERED_EXCEPTION` unchanged and reject legacy `CHAT_PRO_DEFAULT` as a current
  route input.
- [x] Add `ChatReasoningMode.NON_PRO_DEFAULT` and `ChatReasoningMode.PRO_MODE_EXCEPTION` plus the
  closed `ProModeTaskClass` values.
- [x] Add frozen `ProModeReceipt` with bounded non-empty text, an allowed task class, and integer
  `80 <= expected_duration_minutes <= 1440` validation.
- [x] Add frozen `MeteredCognitionReceipt` with bounded text validation, finite non-negative expected cost, positive hard cap, and `expected_max_cost <= hard_budget_cap`.
- [x] Extend `RoutingDecision` with nullable cognition route, Chat reasoning mode, Pro receipt, and
  metered receipt fields plus JSON-safe `to_dict()` projection.
- [x] Extend `ModelRouter.route()` and `route_work()` with optional cognition-route,
  `chat_reasoning_mode`, `pro_mode_receipt`, and metered receipt parameters. Default lead work
  projects included Chat/non-Pro; Pro and metered selections each require their own valid receipt;
  worker work refuses all Sol-cognition parameters.
- [x] Preserve `preferred_model_aliases=("frontier.orchestrator",)` only as the existing non-dispatchable lead capability descriptor; the new cognition route is the controlling economic projection and `job_constraints()` continues to refuse every lead decision.
- [x] Run focused and existing model-router regressions.

### Task 3: Release honesty

**Files:**
- Verify exactly: `control_plane/model_router.py`; the two canonical cognition/routing laws;
  `docs/sol_skills/WORKER_AVENUE_ROUTING.md`; this plan; and the five focused source/router tests.

- [x] Require exact changed paths and no config/runtime/provider/account changes.
- [ ] Require repository CI and CodeQL on exact current-base head.
- [ ] Final Sol review must verify this is deterministic routing projection only: no Chat
  provisioning, mode switch, API call, Business/Workspace-Agent call, actual budget authority,
  provider launch, and no fleet-live claim.
- [ ] Merge with expected-head protection after fresh current-base proof.

## Completion boundary

`CNM-R1` is `BUILT_NOT_PROVEN / PRODUCTION_INERT` when code is protected and exact-head tests pass. It becomes useful as the deterministic route guard consumed by later Chat provisioning/Capacity composition. It does not itself make a Meta-CEO hierarchy or Chat session autonomous.
