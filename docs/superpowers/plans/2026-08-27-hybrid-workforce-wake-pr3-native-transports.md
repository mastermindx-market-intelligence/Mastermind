# Wake PR3 Native Codex/Claude Transport Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the first real Wake Fabric delivery transports so a canonical Executive wake obligation can nudge the exact bound Codex-Sol or Claude/Fable reasoning surface and receive authenticated delivery evidence without Slack/tmux/session registries becoming lifecycle authority.

**Architecture:** Existing `WakeObligation`, `SessionTarget`, `RuntimeBinding`, `DeliveryAttempt`, `WakeNudge`, retry/reconciliation and Executive `events` ledger remain unchanged. PR3 adds provider-native dispatchers under an integration layer and extends the closed transport/reasoning-surface vocabularies. A dispatcher receives only the existing opaque `WakeNudge`; it may deliver a fixed bounded continuation signal to the runtime handle but never receives Job prose/authority. Runtime native handles remain in `RuntimeBinding`, never Git. Codex uses the existing App Server/provider-session substrate. Claude uses a host-proven resume contract only after the installed Claude Code version proves exact native resume behavior; otherwise that transport remains unimplemented. Production arming and target enablement stay separate canary gates.

**Tech Stack:** Python 3.11+, existing Wake Fabric contracts, Codex App Server/OHF seams, Claude Code CLI, asyncio/subprocess, pytest.

**Spec:**
- `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`
- `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`

## Global Constraints

- Re-pin protected Skillpack, Wake Fabric current law, ASD/C1 carriers, and open Wake/OHF PRs before first write.
- Do not create a Wake queue/table/daemon/session DB/cron scheduler. Wake state remains existing Executive `events` plus runtime-only `RuntimeBinding`.
- `ACCEPTED != DELIVERED != TARGET_ACKNOWLEDGED != SOURCE_RESOLVED`.
- Delivery is at-least-once with idempotent consumption/reconciliation; never claim exactly-once external execution.
- A transport cannot author `ALREADY_DELIVERED` or lifecycle completion.
- The nudge contains no objective, result body, free-form authority, credential, Slack message, or provider secret.
- Provider-native timeout/disconnect is not permission to nudge another surface. Reconcile the same wake attempt/destination first.
- Personal ChatGPT/Claude Slack accounts and ASD remain dialogue transport, not Wake delivery authority.
- Production `production_armed` and target enablement remain false until a separate exact canary release.
- PR #174 transport acceptance may end truthfully at `DELIVERED_UNACKNOWLEDGED`; target ACK ingress and source resolution are a later separately approved wave.

---

### Task 1: Extend the closed reasoning-surface/transport vocabulary without arming it

**Files:**
- Modify: `control_plane/session_targets.py`
- Modify: `control_plane/wake_transport.py`
- Modify: `tests/test_executive_wake_fabric.py`
- Modify: `tests/test_executive_wake_fabric_hardening.py`

**Interfaces:**
- Add reasoning surface `claude`.
- Add wake transport `claude-code-session`.
- Preserve existing `codex-app-server` transport.
- Both automated transports require a `RuntimeBinding`.

- [ ] **Step 1: Write RED vocabulary tests**

Add tests that accept:

```python
RuntimeBinding(
    session_alias="EXECUTIVE-COO-A",
    binding_id="bind-claude1234",
    binding_generation=1,
    native_handle="opaque-provider-session",
    reasoning_surface="claude",
)
```

and a `SessionTarget` with `reasoning_surface="claude"`, `wake_transport="claude-code-session"`.

Assert `transport_implemented("claude-code-session") is False` initially and that the transport requires a runtime binding.

- [ ] **Step 2: Run RED**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 3: Extend only the closed vocabularies**

Update:

```python
REASONING_SURFACES = frozenset(
    {"chatgpt-sol", "codex", "claude", "workspace-agent", "human"}
)
```

and add `"claude-code-session"` to `WAKE_TRANSPORTS` and `_REQUIRES_BINDING`.

Do not set any descriptor `transport_implemented=True` in this task.

- [ ] **Step 4: Run GREEN**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 5: Commit**

```bash
git add control_plane/session_targets.py control_plane/wake_transport.py tests/test_executive_wake_fabric.py tests/test_executive_wake_fabric_hardening.py
git commit -m "feat(exec): add Claude wake route vocabulary"
```

---

### Task 2: Create a transport registry and provider-integration boundary

**Files:**
- Create: `integrations/executive_wake/__init__.py`
- Create: `integrations/executive_wake/registry.py`
- Modify: `control_plane/wake_dispatcher.py`
- Create: `tests/test_executive_wake_transport_registry.py`

**Interfaces:**
- `WakeDispatcher` protocol remains exactly `async def nudge(self, wake: WakeNudge) -> TransportReceipt`.
- `WakeDispatcherRegistry` resolves a reviewed dispatcher by exact transport id; it stores no delivery state.
- `control_plane` must not import provider SDKs.

- [ ] **Step 1: Write registry tests**

Pin:

```text
unknown transport -> refusal
unimplemented descriptor -> UnsupportedWakeDispatcher
implemented descriptor without registered dispatcher -> startup/refusal, never fake unsupported success
registered dispatcher id must equal its canonical descriptor transport_id
registry is pure in-memory composition; no persistence/network on import
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_executive_wake_transport_registry.py -q
```

- [ ] **Step 3: Implement registry**

The registry accepts an explicit mapping at composition time. It must not discover arbitrary plugins from environment/PATH/entry points. `dispatch_nudge()` may receive the resolved dispatcher exactly as it already does; do not move provider code into `control_plane`.

- [ ] **Step 4: Keep legacy `dispatcher_for()` fail-closed**

`dispatcher_for()` remains the descriptor-only fallback for unimplemented transports. If a descriptor is marked implemented but no real dispatcher was injected, fail closed as today.

- [ ] **Step 5: Run GREEN and commit**

```bash
python -m pytest \
  tests/test_executive_wake_transport_registry.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q

git add integrations/executive_wake control_plane/wake_dispatcher.py tests/test_executive_wake_transport_registry.py
git commit -m "feat(exec): add explicit wake dispatcher registry"
```

---

### Task 3: Implement Codex App Server wake delivery

**Files:**
- Create: `integrations/executive_wake/codex_app_server.py`
- Create: `tests/test_codex_app_server_wake_dispatcher.py`
- Modify: `control_plane/wake_transport.py`

**Interfaces:**
- `CodexAppServerWakeClient` is a narrow injected protocol that can deliver one fixed wake turn to an existing provider-native thread/session referenced by `WakeNudge.native_handle`.
- `CodexAppServerWakeDispatcher.nudge()` returns only `TransportReceipt`.

- [ ] **Step 1: Write RED dispatcher tests**

Use a deterministic fake client and assert:

```text
missing native_handle -> TARGET_UNAVAILABLE
binding/session mismatch is refused before provider call
one nudge id produces one provider call
provider accepted-but-not-observed -> ACCEPTED, not DELIVERED
provider confirms the turn reached the exact bound thread -> DELIVERED
provider timeout/unknown effect -> FAILED or TARGET_UNAVAILABLE according to the closed transport contract, never a second call
nudge payload contains only opaque obligation/attempt ids plus a fixed continuation instruction
```

The fixed continuation instruction tells the target to recover canonical Executive/Agent OS state for the supplied opaque wake identities; it must not embed worker result prose.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_codex_app_server_wake_dispatcher.py -q
```

- [ ] **Step 3: Implement the narrow client/dispatcher**

Reuse/factor the existing Codex App Server/OHF provider-session mechanics rather than spawning a second Codex session system. The integration layer may adapt an existing App Server client/runtime binding into the narrow `deliver_wake(native_handle, nudge_id, opaque_ids)` operation.

Do not persist thread ids. `native_handle` is runtime-only input.

- [ ] **Step 4: Prove authentication against current Wake receipt law**

Run the dispatcher through `dispatch_nudge()` with a fake live route/binding and require `authenticate_transport_receipt()` and `authenticate_receipt()` to accept only exact destination/attempt/nudge identity.

- [ ] **Step 5: Mark the descriptor implemented only after tests exist**

Set only:

```python
WAKE_TRANSPORT_DESCRIPTORS["codex-app-server"].transport_implemented = True
```

through the module's immutable descriptor construction pattern. Do not set `production_armed` or target enabled.

- [ ] **Step 6: Run combined Codex/OHF/Wake tests**

```bash
python -m pytest \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_operator_adapter.py \
  tests/test_executive_operator_broker.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add integrations/executive_wake/codex_app_server.py control_plane/wake_transport.py tests/test_codex_app_server_wake_dispatcher.py
git commit -m "feat(exec): implement Codex App Server wake transport"
```

---

### Task 4: Freeze and implement the Claude native-resume transport

**Files:**
- Create: `integrations/executive_wake/claude_code.py`
- Create: `ops/executive_os/claude-wake-preflight.py`
- Create: `tests/test_claude_code_wake_dispatcher.py`
- Create: `tests/test_claude_wake_preflight.py`
- Modify: `control_plane/wake_transport.py`

**Interfaces:**
- `ClaudeCodeWakeDispatcher` uses an exact host-proven provider-native resume operation against `WakeNudge.native_handle`.
- No Claude credential or session body enters the receipt.

- [ ] **Step 1: Create the read-only host resume preflight**

The preflight must prove on the installed Claude Code version, without login/config mutation, that the CLI exposes a non-interactive resume operation accepting an exact provider session id and a bounded prompt. The accepted V1 contract is:

```text
absolute Claude binary
+ exact installed version
+ exact provider session id supplied as runtime input
+ non-interactive resume/continue invocation
+ bounded fixed wake message
+ structured/bounded output sufficient to establish accepted/delivered status
```

Emit only `mastermind.claude_wake_preflight/v1` fields: binary version/digest, resume_supported boolean, non_interactive_supported boolean, structured_output_supported boolean, auth_ready boolean, and result. No session ids, account PII, paths or credential metadata in durable evidence.

- [ ] **Step 2: Write preflight tests**

Pin supported, unsupported, auth-unready, malformed-help/version and secret-shaped-output cases. Unsupported installed behavior must return `CLAUDE_WAKE_UNSUPPORTED`, not guess a flag.

- [ ] **Step 3: Write dispatcher tests with an injected process runner**

Assert exact-session resume, fixed nudge contents, zero ambient environment credentials, no provider fallback/retry, timeout as uncertain failure, wrong/missing handle refusal, and exact `nudge_id` receipt binding.

- [ ] **Step 4: Implement only after a real host preflight proves the exact command contract**

The implementation may invoke the exact proven provider-native resume syntax; do not hard-code an unverified CLI flag. The installed-version proof becomes the adapter's allowed-version contract and tests use sanitized synthetic fixtures with the same shape.

- [ ] **Step 5: Mark `claude-code-session` implemented only after focused tests + host preflight pass**

Keep all production targets disabled/unarmed.

- [ ] **Step 6: Run combined tests**

```bash
python -m pytest \
  tests/test_claude_wake_preflight.py \
  tests/test_claude_code_wake_dispatcher.py \
  tests/test_executive_wake_transport_registry.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add integrations/executive_wake/claude_code.py ops/executive_os/claude-wake-preflight.py control_plane/wake_transport.py tests/test_claude_code_wake_dispatcher.py tests/test_claude_wake_preflight.py
git commit -m "feat(exec): implement host-proven Claude wake transport"
```

---

### Task 5: Pin wake source policy for Fable/Codex-Sol attention

**Files:**
- Modify: `control_plane/wake_router.py`
- Modify: `tests/test_executive_wake_fabric.py`
- Modify: `docs/EXECUTIVE_WAKE_FABRIC.md`

**Interfaces:**
- Existing trusted Inbox/runtime source admission remains authoritative.
- This task does not create new lifecycle event kinds merely for provider wake.

- [ ] **Step 1: Add attention-policy tests**

Pin that ordinary worker claim/start/progress and successful child completion consumable by an active parent do not automatically target CEO. Existing source facts that already require owner/review/decision attention preserve their `target_seat` and root binding. A COO-owned continuation routes to COO; a material CEO decision routes to CEO; Chairman remains human-required unless separately authorized.

- [ ] **Step 2: Prove reasoning surface is route data, not authority**

For the same `ceo` obligation, route once to a `chatgpt-sol` target and once to a `codex` target under different runtime bindings. Assert obligation identity is unchanged; only route/destination identity changes. This proves Codex-Sol is a technical reasoning surface, not a second CEO lifecycle.

- [ ] **Step 3: Update Wake docs**

Document:

```text
source fact decides that attention is owed
executive seat decides who is accountable
session target decides current reasoning surface
RuntimeBinding decides current provider-native handle
wake transport only delivers the nudge
```

State that ASD decision dialogue can keep an already-active Claude session blocked waiting for a ruling; Wake Fabric is for canonical continuation/resume obligations, not a duplicate Slack inbox.

- [ ] **Step 4: Run tests and commit**

```bash
python -m pytest \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q

git add control_plane/wake_router.py tests/test_executive_wake_fabric.py docs/EXECUTIVE_WAKE_FABRIC.md
git commit -m "test(exec): pin hybrid executive wake routing law"
```

---

### Task 6: Exact-head review and transport-only live proof

**Files:**
- Sanitized proof artifacts only under existing review-evidence conventions.

- [ ] **Step 1: Exact-head hosted CI/CodeQL and adversarial review**

Run full Wake/OHF/adapter suites and require independent attacks on: forged delivered receipts, wrong RuntimeBinding, ABA generation reuse, provider retry, nudge prose leakage, transport-success laundering into ACK/source resolution, and hidden session persistence.

- [ ] **Step 2: Codex-Sol harmless live delivery canary**

With a dedicated non-production in-memory Codex App Server runtime binding, create one canonical harmless Wake obligation and route it to a `ceo`-seat Codex reasoning target. The checked-in production registry remains `production_armed=false` and all checked-in targets remain disabled; only the isolated canary process may construct the bounded delivery-eligible route required to exercise the transport.

Prove exactly this sequence:

```text
canonical harmless Wake obligation
-> exact ceo/codex route + current RuntimeBinding
-> one provider-native Codex transport attempt
-> authenticated exact-thread DELIVERED evidence
-> reconstructed status DELIVERED_UNACKNOWLEDGED
-> stop; do not author TARGET_ACKNOWLEDGED or SOURCE_RESOLVED
```

The canary must prove the exact native thread received the one bounded nudge, no substitute thread/session was minted, and no second provider turn/failover occurred. Do not synthesize an ACK in the canary harness.

- [ ] **Step 3: Claude/Fable verdict and optional delivery canary**

Only if the installed-host Claude preflight proves exact discovery/binding, same-conversation resurrection, and one scriptable same-conversation nudge ingress may a dedicated safe Claude/Fable delivery canary run. Its accepted claim is transport delivery only and likewise stops at `DELIVERED_UNACKNOWLEDGED`. If any native sub-capability is unproven, keep `claude-code-session` `UNSUPPORTED / UNIMPLEMENTED`; do not substitute tmux, Slack, GUI automation, a guessed flag, or a new session manager.

- [ ] **Step 4: Stop and return**

Return exact head, transport descriptors, host-preflight receipts, sanitized live canary obligation/route/delivery identities, reconstructed `DELIVERED_UNACKNOWLEDGED` status, full hosted tests, security review, and confirmation `NO NEW WAKE QUEUE/SESSION DB/SCHEDULER`. State explicitly that target reasoning-session ACK ingress and source resolution remain later-wave `NOT_BUILT`, and production Wake remains disarmed.
