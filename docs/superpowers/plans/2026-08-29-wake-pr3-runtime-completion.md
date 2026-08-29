# Wake PR3 / WP-TW2 Runtime Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the already-approved Agent Dialogue -> Executive Wake -> exact Codex App Server delivery path without creating a second watcher, Wake, session, lifecycle, retry, or provider-control plane.

**Architecture:** Preserve the existing owners. WP-TW2/#216 remains the stateless dialogue observer and attention->Wake adapter; Wake Fabric remains obligation/routing/persistence/effect-unknown authority; #174 remains the exact-provider dispatcher boundary; the existing long-running Agent Relay runtime remains the eventual observer-loop owner. This plan first lands two production-disarmed libraries that are dependency-clear (W3A/W3B), then holds runtime composition/canary (W3C) until MAS-237 supplies a canonical current RuntimeBinding and a trusted TurnRoutingFacts resolver exists.

**Tech Stack:** Python 3.12, existing `scripts.ohf.laboratory.AppServerClient`, Agent Dialogue V2/WP-TW2, Executive Wake Fabric, Executive OS events, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-worker-presence-dialogue-turn-watcher-amendment.md` plus protected Wake PR3 closeout plan `docs/superpowers/plans/2026-08-27-wake-pr3-transport-only-closeout.md`.

## Global Constraints

- Re-pin then-current protected `mastermindx-market-intelligence/Mastermind` and atomically load the current compatible Sol Skillpack before every modifying carrier.
- Executive OS remains sole Job/Attempt/Worker/Event authority. Agent OS remains durable organizational memory. Slack/Agent Relay remains dialogue transport. Wake Fabric remains Wake obligation/routing/delivery/ack/source-resolution authority.
- Reuse `scripts.ohf.laboratory.AppServerClient`; do not add another JSON-RPC process manager.
- Reuse the existing `CodexAppServerWakeDispatcher`, `WakeLedgerRepository`, `WakeDispatcherRegistry`, `dispatch_persisted_nudge`, `DialogueTurnObserver`, `SessionTargetRegistry`, and Wake ledger/event contracts.
- No new table, queue, scheduler, watcher DB, cursor DB, session registry, provider lifecycle owner, retry plane, generic dispatcher, GUI controller, title/OCR tab selector, or duplicate Agent Relay service.
- `config/wake_session_targets.json` stays `production_armed=false`; no target is enabled by W3A/W3B/W3C hermetic implementation.
- Delivery success is not target consumption. MAS-229 remains the owner of `TARGET_ACKNOWLEDGED -> SOURCE_RESOLVED`.
- An ambiguous write after `turn/start` begins is effect-unknown and must never be downgraded to retryable failure.
- A started/effect-unknown pre-crash FORGE child is not a reusable implementation receiver. Do not reuse/rebind it for these waves until its own effect is reconciled.

---

## Task 1 / W3A: Concrete Codex App Server exact-thread Wake client

**Operation:** `wake-pr3a-codex-app-server-rpc-client-20260829-sol-001`

**Observable capability:** one injected client can use the already-selected exact runtime-only Codex thread id to perform the accepted App Server Wake protocol with no thread creation/fork and with a truthful accepted-vs-delivered boundary.

**Files:**
- Create: `integrations/executive_wake/codex_app_server_rpc.py`
- Create: `tests/test_codex_app_server_wake_rpc.py`
- Read only by default: `integrations/executive_wake/codex_app_server.py`, `scripts/ohf/laboratory.py`, `scripts/ohf/codex_app_server_probe.py`, `control_plane/codex_operator_adapter.py`

**Interfaces:**
- Implements existing `CodexAppServerWakeClient.deliver_wake(...) -> CodexWakeDeliveryObservation`.
- Reuses/injects `AppServerClient`; no second JSON-RPC implementation.
- Input identity is only `native_handle`, `nudge_id`, opaque Wake ids, and fixed bounded Wake instruction.

- [ ] **Step 1: Write RED tests for exact protocol and forbidden methods.**

Use a deterministic fake App Server client that records `start`, `request`, `notify`, `wait_notification`, and `close` calls. Require the successful method sequence:

```text
start
initialize
initialized
thread/resume(threadId=<native_handle>)
turn/start(threadId=<same native_handle>, input=<fixed instruction + opaque ids>)
wait turn/completed for the exact returned turn id
close
```

Assert no call to `thread/start` or `thread/fork`, and no caller/model supplied thread id other than `native_handle`.

- [ ] **Step 2: Add RED for pre-submit refusal.**

If process start, initialize, initialized, or `thread/resume` fails before `turn/start` begins, require `WakePreSubmitError(outcome=TARGET_UNAVAILABLE, reason_code="target_unavailable")`. Verify no `turn/start` call occurred.

- [ ] **Step 3: Add RED for exact resume identity.**

`thread/resume` response must prove the resumed thread id equals `native_handle`; missing/mismatched identity refuses before `turn/start` as pre-submit target-unavailable.

- [ ] **Step 4: Add RED for post-submit uncertainty.**

Once the client begins `turn/start`, any request timeout, transport closure, malformed response, mismatched returned thread id/turn id, or other ambiguous provider result raises an ordinary exception (not `WakePreSubmitError`). Existing `CodexAppServerWakeDispatcher` must therefore map it to `WakeEffectUnknownError`.

- [ ] **Step 5: Add RED for ACCEPTED boundary.**

If `turn/start` returns a valid exact thread/turn identity but bounded `turn/completed` observation times out, return `CodexWakeDeliveryObservation(native_handle=<exact>, nudge_id=<exact>, accepted=True, delivered=False)`.

- [ ] **Step 6: Add RED for DELIVERED boundary.**

A matching `turn/completed` notification for the exact returned turn id produces `accepted=True, delivered=True`. Foreign-thread/foreign-turn notifications cannot satisfy delivery.

- [ ] **Step 7: Implement the smallest client.**

Recommended shape:

```python
class CodexAppServerRpcWakeClient:
    def __init__(
        self,
        *,
        client_factory: Callable[[], AppServerClient],
        request_timeout_seconds: float = 15.0,
        completion_timeout_seconds: float = 15.0,
    ) -> None: ...

    async def deliver_wake(
        self,
        *,
        native_handle: str,
        nudge_id: str,
        opaque_ids: Sequence[str],
        instruction: str,
    ) -> CodexWakeDeliveryObservation: ...
```

The production factory is injected; W3A itself does not decide Codex binary, CODEX_HOME, workspace, credentials, account, host, or runtime binding.

Because `AppServerClient` is synchronous, execute one bounded call sequence without spawning another reasoning/model loop. Always close/contain the client in `finally`; cleanup uncertainty must not convert a possible provider write into retryability.

- [ ] **Step 8: Run focused + adjacent tests.**

```text
python3 -m pytest -q tests/test_codex_app_server_wake_rpc.py tests/test_codex_app_server_wake_dispatcher.py tests/test_executive_wake_persisted_dispatch.py
python3 -m py_compile integrations/executive_wake/codex_app_server_rpc.py
```

Then exact-head repository CI/security and independent review.

**Stop condition:** one bounded production-disarmed PR containing only the concrete client and tests. No registry/config/runtime/enrollment/production target changes.

---

## Task 2 / W3B: Persisted Agent Dialogue WakeCarrier adapter

**Operation:** `wptw2-persisted-wake-carrier-20260829-sol-001`

**Observable capability:** the existing `DialogueTurnObserver` can reconcile/submit one canonical Wake obligation through the existing Executive events ledger and persisted dispatcher without losing a request-only crash window or duplicating provider submission.

**Files:**
- Create: `integrations/slack_agent_dialogue/persisted_wake_carrier.py`
- Create: `tests/test_slack_agent_dialogue_persisted_wake_carrier.py`
- Modify `turn_observer.py` only if a narrow type/interface defect is proven; otherwise no edit.

**Interfaces:**

```python
class PersistedWakeCarrier:
    def __init__(
        self,
        *,
        repository: WakeLedgerRepository,
        dispatchers: WakeDispatcherRegistry,
        current_binding_for: Callable[[WakeRoute], RuntimeBinding | None],
        retry_policy: WakeRetryPolicy,
    ) -> None: ...

    async def reconcile(
        self, obligation: WakeObligation, route: WakeRoute
    ) -> WakeCarrierState: ...

    async def submit(self, obligation: WakeObligation, route: WakeRoute) -> None: ...
```

- [ ] **Step 1: RED reconciliation matrix.**

Require:

```text
no records                                         -> MISSING
WAKE_REQUESTED only                                -> MISSING
unfinished DELIVERY_ATTEMPT                        -> EFFECT_UNKNOWN
terminal ACCEPTED / DELIVERED / TARGET_UNAVAILABLE / FAILED -> RECORDED
TARGET_ACKNOWLEDGED / SOURCE_RESOLVED after valid history   -> RECORDED
malformed/conflicting causal ledger                -> fail closed; never MISSING
```

The `WAKE_REQUESTED-only -> MISSING` rule is load-bearing: a Relay crash after request persistence but before attempt creation must remain submit-eligible on restart.

- [ ] **Step 2: RED idempotent request persistence.**

`submit()` must append the canonical `WAKE_REQUESTED` record with the obligation only when absent; identical replay is idempotent through existing repository law. Changed collision refuses.

- [ ] **Step 3: RED current-binding revalidation immediately before provider dispatch.**

Call `current_binding_for(route)` after request persistence and before `dispatch_persisted_nudge`. Require the returned binding to match route alias, binding id, generation, and reasoning surface. Missing/moved binding refuses before provider submission. Do not trust the route's historical values as proof the binding is still current.

- [ ] **Step 4: RED exact dispatcher resolution.**

Resolve `route.wake_transport` through the injected `WakeDispatcherRegistry`; no fallback provider/transport.

- [ ] **Step 5: RED effect-unknown propagation.**

Invoke `dispatch_persisted_nudge(...)` exactly once. If it returns `RECONCILIATION_REQUIRED`, raise `WakeEffectUnknownError`. The observer must then emit its existing `EFFECT_UNKNOWN_HOLD` and never submit a second nudge on the same pass/restart.

- [ ] **Step 6: RED terminal persisted outcomes.**

ACCEPTED/DELIVERED/TARGET_UNAVAILABLE/FAILED from persisted dispatch complete `submit()` without inventing ACK or source resolution. Later observer reconciliation returns RECORDED.

- [ ] **Step 7: Implement and run focused tests.**

```text
python3 -m pytest -q tests/test_slack_agent_dialogue_persisted_wake_carrier.py tests/test_slack_agent_dialogue_turn_observer.py tests/test_executive_wake_persisted_dispatch.py
python3 -m py_compile integrations/slack_agent_dialogue/persisted_wake_carrier.py
```

Then exact-head repository CI/security and independent review.

**Stop condition:** one bounded production-disarmed adapter PR. No Agent Relay runtime loop, config arming, target enablement, host install, or canary.

---

## Task 3 / W3C: Existing Agent Relay runtime composition — HELD UNTIL INPUTS EXIST

**Operation:** `wptw2-agent-relay-wake-runtime-composition-20260829-sol-001`

**Canonical owner:** existing `integrations/slack_agent_dialogue/runtime.py` / `scripts/slack_agent_dialogue_service.py`; do not create another daemon.

**START gates:**

1. MAS-237 current RuntimeBinding projection accepted/protected and available as a trusted read-only resolver.
2. One accepted production `TurnRoutingFacts` resolver exists. Current protected source has constructors only in tests. It must derive operation/commission/root/workstream/target-binding facts from canonical owners; raw Slack cannot invent them.
3. W3A and W3B accepted.
4. Current A2 Agent Relay host/enrollment/activation gates reconciled under the existing #238 stack; no credential or launchd mutation from this plan alone.

**Expected later surface:**
- Modify: `integrations/slack_agent_dialogue/runtime.py`
- Create a focused runtime-observer composition module/test only if needed to keep `runtime.py` small; it remains part of the same Agent Relay process, not another service.
- Modify enrollment/config only in a separately authorized host/config wave if new non-secret runtime coordinates are genuinely required.

**Required runtime behavior:**

```text
Agent Relay start/reconnect
-> bounded Slack history traversal
-> identify exact immutable turn_watch_v1 parents
-> trusted routing-facts resolution
-> DialogueTurnObserver
-> active-waiter suppression when exact waiter exists
-> W3B PersistedWakeCarrier
-> exact current MAS-237 RuntimeBinding
-> W3A Codex App Server dispatcher for codex targets
-> one persisted delivery outcome
-> continue serving existing AF_UNIX dialogue API
```

No persistent observer cursor. Restart recomputes from canonical Slack/Wake identity. No provider-native wake when an exact active waiter already owns the hot path.

**Hermetic acceptance:** prove restart rediscovery, duplicate suppression, request-only crash recovery, effect-unknown hold, route/binding movement refusal, same-seat self-loop refusal, and zero duplicate provider submission.

**Real canary acceptance:** with one accepted current Codex binding and production gates explicitly armed for the canary only:

```text
valid watched opposite-side turn
-> deterministic AgentDialogueAttention
-> same Wake obligation on repeats/restart
-> exact current RuntimeBinding
-> one App Server thread/resume on exact id
-> one turn/start on same id
-> ACCEPTED or DELIVERED persisted
```

Chairman/manual GUI/tab selection = zero. A second identical observation/provider submission = zero.

MAS-229 is still required afterward to prove exact target-turn consumption and source resolution. Do not call W3C delivery `TARGET_ACKNOWLEDGED`.

---

## Current dependency / collision ledger at plan authoring

Protected source: `b8f7414e9906d6b5853640a18de68c3b91ffb44b`, Skillpack v1.0.1.

- #174 merged: Wake transport safety + abstract Codex dispatcher; concrete RPC client absent.
- #216 merged: one-pass observer + Wake adapter; production activation deferred.
- #238/#221 stack: long-running Agent Relay source/enrollment exists, production host activation remains separately governed.
- MAS-237: started pre-crash under original FORGE; current effect remains `EFFECT_UNKNOWN / RUNTIME_BINDING_RECONCILIATION_REQUIRED`; do not replay/rebind.
- MAS-229: blocked by exact binding and real delivery proof.
- #248: watcher procedure/bootstrap hardening release carrier; path-disjoint from W3A/W3B.
- #228: Steward read-core release carrier; path-disjoint.
- open #147: constitutional Skillpack candidate; no W3A/W3B runtime path ownership.
- no current open PR found owning `integrations/executive_wake/codex_app_server.py`, missing `codex_app_server_rpc.py`, or Agent Relay Wake runtime composition paths.

## Completion ruler

This plan is not complete when W3A/W3B merge. The repair outcome is complete only when W3C and MAS-229 together prove a real bilateral loop can resume the exact current Codex reasoning session without Chairman tab hunting and without duplicate Jobs/sessions/Wake/provider writes.
