# Wake PR3 Transport-Only Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close Mastermind PR #174 as a truthful provider-native Wake delivery transport wave that proves exact Codex delivery, returns a truthful Claude supported/unsupported verdict, and never launders delivery into target acknowledgement or source resolution.

**Architecture:** Keep the existing Executive Wake obligation, routing, RuntimeBinding, delivery-attempt, receipt and Executive-events authorities unchanged. PR #174 owns only provider-native delivery; target reasoning-session ACK ingress is a later separately approved architecture that must reuse existing acknowledgement law and Executive events. Codex uses the existing App Server JSON-RPC substrate with exact `thread/resume` identity and one bounded `turn/start`; Claude stays unimplemented unless a real installed-host preflight proves discovery, same-conversation resurrection and one scriptable same-conversation nudge ingress.

**Tech Stack:** Python 3.12 in hosted CI, existing Executive Wake Fabric contracts, `scripts.ohf.laboratory.AppServerClient`, Codex App Server JSON-RPC, Claude Code CLI host preflight, pytest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`

## Global Constraints

- Planning pickup: protected `Mastermind@f81e29cc2a3f945fd79096e8ca10e8b2daec9e18`, Skillpack `mastermind.sol_skillpack.v1` v1.0.0, bootstrap major 1. Re-pin protected master and all material source law before every modifying task.
- Existing carrier only: PR #174, branch `sol/wake-pr3-native-transports-20260827`, operation key `wake-pr3-native-transports-20260827-sol-001`.
- Current planning head: `dae1ae677dec670db6426c25708b5d864ecc3500`. If the head moves, reconcile the movement before writing; never reset, force-push or create a replacement carrier.
- Execute at most one primary task from this plan per interactive Chairman turn. Do not poll long CI repeatedly in the same turn.
- `ACCEPTED != DELIVERED != TARGET_ACKNOWLEDGED != SOURCE_RESOLVED`.
- PR #174 acceptance may end at `DELIVERED_UNACKNOWLEDGED`; it must not synthesize or persist target ACK or source resolution.
- Checked-in `production_armed=false` remains the production kill switch and checked-in targets remain disabled through merge.
- `claude-code-session` remains `transport_implemented=False` unless the installed-host proof passes all three required sub-capabilities.
- No Wake table, queue, scheduler, daemon, session DB, retry ledger, provider control plane, Slack lifecycle authority, credential copy/read/create, generic remote shell, tmux lifecycle or GUI fallback.
- Runtime/provider handles stay runtime-only. Never persist Codex thread ids, Claude `sessionId`, Claude short supervisor ids, account PII, CODEX_HOME paths or credential metadata in Git, Agent OS or proof artifacts.
- Provider timeout/effect uncertainty stays bound to the same nudge/destination. No blind retry, second provider turn, new thread/conversation or provider/session failover.
- The later ACK-ingress wave is out of scope for this plan. This plan may leave its exact architecture-start handoff, but may not implement it.

## Current Capability Baseline

At planning time #174 already contains the Claude reasoning/transport vocabulary, an explicit in-memory dispatcher registry, the Codex Wake dispatcher contract, Codex descriptor implementation flag, kill-switch regressions and the approved transport/ACK split spec. The remaining closeout work is not to rebuild those pieces; it is to reconcile stale completion law, close the dispatcher-identity composition blocker, bind the Codex dispatcher to the real App Server JSON-RPC substrate, obtain a truthful Claude host verdict, prove one harmless real Codex delivery without ACK, then perform exact-head review/merge at the truthful `BUILT_NOT_PROVEN / PARTIAL` level.

---

### Task 1: Reconcile #174 source law to the approved transport-only boundary

**Files:**
- Modify: `docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md`
- Modify: `research/EXECUTIVE_WAKE_PR3_NATIVE_TRANSPORTS_COMMISSION_2026-08-27.md`
- Read-only authority: `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`
- GitHub metadata: PR #174 body

**Interfaces:**
- Consumes: Chairman-approved transport/ACK split spec.
- Produces: one non-contradictory completion law for the existing #174 carrier.

- [ ] **Step 1: Re-pin protected master and inspect #174 head/collisions**

Record the current protected SHA, exact PR head, current changed-file census and any newer Wake/session/App-Server source-law PR. If a material collision exists, stop and return to Sol before editing.

- [ ] **Step 2: Amend the original PR3 implementation plan**

Change its `**Spec:**` field to include both governing specs:

```markdown
**Spec:**
- `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`
- `docs/superpowers/specs/2026-08-27-wake-pr3-transport-ack-boundary-split-design.md`
```

Replace the old Task 6 Codex canary requirement with this exact acceptance sequence:

```text
canonical harmless Wake obligation
-> exact ceo/codex route + current RuntimeBinding
-> one provider-native Codex transport attempt
-> authenticated exact-thread DELIVERED evidence
-> reconstructed status DELIVERED_UNACKNOWLEDGED
-> stop; do not author TARGET_ACKNOWLEDGED or SOURCE_RESOLVED
```

State explicitly that the checked-in production registry remains disarmed and that a dedicated non-production in-memory canary route may be armed only inside the isolated canary process; it is never persisted or substituted for production configuration.

- [ ] **Step 3: Amend the commission's journey, acceptance proof and stop condition**

The Codex journey must terminate at `DELIVERED_UNACKNOWLEDGED`. Replace every statement that #174 itself must prove or persist target ACK/source resolution with:

```markdown
ACK/source resolution remain later-wave capabilities. PR #174 must prove that no transport success, provider response, canary harness or model output can author them.
```

The stop condition becomes:

```markdown
Stop when the Codex App Server delivery edge is implementation-complete and proven by one harmless exact-thread `DELIVERED_UNACKNOWLEDGED` canary, Claude is either host-proven and separately implemented on this same carrier or explicitly retained `UNSUPPORTED / UNIMPLEMENTED`, exact-head hosted/security gates are green, independent adversarial review is clean, and checked-in production remains disarmed. Return to Sol with ACK ingress still `NOT_BUILT`.
```

- [ ] **Step 4: Run a stale-law scan**

Run:

```bash
rg -n \
  'live Codex Wake obligation.*ACK|existing TARGET_ACKNOWLEDGED path|delivery.*ACK.*source-resolution|production-proven through one harmless dedicated canary' \
  docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md \
  research/EXECUTIVE_WAKE_PR3_NATIVE_TRANSPORTS_COMMISSION_2026-08-27.md
```

Expected: no stale requirement that #174 itself must produce ACK/source resolution. Descriptive statements that distinguish delivery from ACK are allowed only when they explicitly say ACK is later-wave/out-of-scope.

- [ ] **Step 5: Commit the source-law reconciliation**

```bash
git add \
  docs/superpowers/plans/2026-08-27-hybrid-workforce-wake-pr3-native-transports.md \
  research/EXECUTIVE_WAKE_PR3_NATIVE_TRANSPORTS_COMMISSION_2026-08-27.md
git commit -m "docs(exec): align Wake PR3 with transport-only acceptance"
```

- [ ] **Step 6: Update PR #174 metadata without changing the carrier**

Set the PR completion line to:

```text
Completion: hosted-ci+security+adversarial-review+claude-preflight+codex-delivery-canary+sol-acceptance
```

Set its Stop section to require one harmless Codex `DELIVERED_UNACKNOWLEDGED` canary, a truthful Claude verdict, exact-head review, and explicit confirmation that ACK ingress/source resolution remain later-wave `NOT_BUILT`. Preserve the same operation key and all existing collision/non-goal text.

---

### Task 2: Bind concrete dispatcher identity at registry composition

**Files:**
- Modify: `control_plane/wake_dispatcher.py`
- Modify: `integrations/executive_wake/registry.py`
- Modify: `tests/test_executive_wake_transport_registry.py`
- Test: `tests/test_codex_app_server_wake_dispatcher.py`

**Interfaces:**
- Consumes: canonical `WakeTransportDescriptor.transport_id`.
- Produces: `WakeDispatcher.transport_id: str` as composition identity only; it grants no authority.
- Preserves: `async def nudge(self, wake: WakeNudge) -> TransportReceipt`.

- [ ] **Step 1: Write the failing cross-registration test**

Change the fake to carry explicit identity:

```python
@dataclasses.dataclass
class _FakeDispatcher:
    transport_id: str = "codex-app-server"
    calls: int = 0

    async def nudge(self, wake):
        self.calls += 1
        return TransportReceipt(
            outcome=TransportOutcome.ACCEPTED,
            reason_code="accepted",
            created_at="2026-08-27T09:00:00Z",
            details=(("nudge_id", wake.nudge_id),),
        )
```

Add:

```python
def test_registry_refuses_concrete_dispatcher_identity_mismatch(monkeypatch):
    _mark_implemented(monkeypatch, "codex-app-server")
    _mark_implemented(monkeypatch, "claude-code-session")
    fake = _FakeDispatcher(transport_id="claude-code-session")

    with pytest.raises(WakeDispatchError, match="dispatcher transport identity"):
        WakeDispatcherRegistry({"codex-app-server": fake})

    assert fake.calls == 0
```

Also add a malformed/missing identity fake and require construction refusal.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_executive_wake_transport_registry.py -q
```

Expected: the mismatch test fails because the current registry trusts only the mapping key.

- [ ] **Step 3: Extend the structural dispatcher protocol**

In `control_plane/wake_dispatcher.py`:

```python
@runtime_checkable
class WakeDispatcher(Protocol):
    transport_id: str

    async def nudge(self, wake: WakeNudge) -> TransportReceipt: ...
```

Give `UnsupportedWakeDispatcher` the same non-authoritative identity:

```python
class UnsupportedWakeDispatcher:
    def __init__(self, transport_id: str) -> None:
        self.descriptor = _descriptor(transport_id)
        self.transport_id = self.descriptor.transport_id
```

- [ ] **Step 4: Enforce three-way identity equality in the registry**

Immediately before inserting a dispatcher into `_dispatchers`:

```python
dispatcher_id = str(getattr(dispatcher, "transport_id", "") or "").strip()
if dispatcher_id != descriptor.transport_id:
    raise WakeDispatchError(
        "dispatcher transport identity does not match the canonical descriptor"
    )
```

The required invariant is:

```text
mapping key == dispatcher.transport_id == canonical descriptor.transport_id
```

Do not infer missing identity from the key and do not add persistence/discovery.

- [ ] **Step 5: Run GREEN**

```bash
python -m pytest \
  tests/test_executive_wake_transport_registry.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add control_plane/wake_dispatcher.py integrations/executive_wake/registry.py tests/test_executive_wake_transport_registry.py
git commit -m "fix(exec): bind wake dispatcher transport identity"
```

---

### Task 3: Add the real exact-thread Codex App Server RPC client

**Files:**
- Create: `integrations/executive_wake/codex_app_server_rpc.py`
- Modify: `integrations/executive_wake/codex_app_server.py`
- Create: `tests/test_codex_app_server_wake_rpc.py`
- Test: `tests/test_codex_app_server_wake_dispatcher.py`
- Regression: `scripts/ohf/laboratory.py`, `scripts/ohf/codex_app_server_probe.py` remain behavior authority and are not copied.

**Interfaces:**
- Consumes: existing `scripts.ohf.laboratory.AppServerClient` wire behavior (`request`, `notify`, `wait_notification`, `close`).
- Produces: `CodexAppServerRpcWakeClient`, satisfying existing `CodexAppServerWakeClient`.
- Required provider sequence: `initialize -> initialized -> thread/resume(exact id) -> turn/start(exact id) -> turn/completed`.
- Forbidden provider methods: `thread/start`, `thread/fork`.

- [ ] **Step 1: Write a deterministic fake App Server client**

In `tests/test_codex_app_server_wake_rpc.py`, create a fake with `methods`, `notifications`, `closed`, configurable resume id and configurable completion timeout. Its `request()` returns:

```python
if method == "initialize":
    return {"userAgent": "fixture"}
if method == "thread/resume":
    return {"thread": {"id": self.resume_id}}
if method == "turn/start":
    return {"turn": {"id": "turn-wake-1"}}
raise AssertionError(method)
```

Its `wait_notification("turn/completed")` returns a completed turn unless configured to raise `TimeoutError`.

- [ ] **Step 2: Write RED exact-thread tests**

Pin all of these:

```text
exact resume id -> exactly one turn/start -> DELIVERED observation
resume returns different id -> refuse before turn/start
no thread/start or thread/fork method is ever called
turn/start request exception -> effect unknown/failure; no second turn
turn/start accepted but completion times out -> ACCEPTED observation, not DELIVERED
client is closed exactly once on every path
instruction contains only the fixed Wake instruction + opaque wake ids/nudge id
```

Run:

```bash
python -m pytest tests/test_codex_app_server_wake_rpc.py -q
```

Expected: FAIL because the concrete RPC client does not yet exist.

- [ ] **Step 3: Implement a narrow client-like protocol**

In `integrations/executive_wake/codex_app_server_rpc.py` define:

```python
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Protocol

class AppServerClientLike(Protocol):
    def request(self, method: str, params: Mapping[str, Any] | None = None, *, timeout: float = 15.0) -> dict[str, Any]: ...
    def notify(self, method: str, params: Mapping[str, Any] | None = None) -> None: ...
    def wait_notification(self, method: str, *, timeout: float = 15.0) -> dict[str, Any]: ...
    def close(self) -> None: ...
```

The constructor is:

```python
class CodexAppServerRpcWakeClient:
    def __init__(
        self,
        client_factory: Callable[[], AppServerClientLike],
        *,
        cwd: Path,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._client_factory = client_factory
        self._cwd = Path(cwd)
        self._timeout_seconds = float(timeout_seconds)
```

- [ ] **Step 4: Implement the exact resume + bounded turn sequence**

`deliver_wake()` must delegate to `asyncio.to_thread()` so synchronous App Server I/O does not block the async dispatcher loop. Its synchronous body must:

```python
client = self._client_factory()
try:
    client.request(
        "initialize",
        {
            "clientInfo": {
                "name": "mastermind_wake_pr3",
                "title": "Mastermind Wake PR3",
                "version": "1",
            },
            "capabilities": {"experimentalApi": True},
        },
        timeout=self._timeout_seconds,
    )
    client.notify("initialized", {})

    resumed = client.request(
        "thread/resume",
        {"threadId": native_handle, "cwd": str(self._cwd)},
        timeout=self._timeout_seconds,
    )
    resumed_id = str(((resumed.get("thread") or {}).get("id") or ""))
    if resumed_id != native_handle:
        raise ValueError("Codex wake resumed a different native thread")

    text = "\n".join(
        [
            instruction,
            f"Nudge: {nudge_id}",
            "Wake identities: " + ",".join(str(item) for item in opaque_ids),
        ]
    )
    client.request(
        "turn/start",
        {
            "threadId": native_handle,
            "input": [{"type": "text", "text": text}],
            "cwd": str(self._cwd),
            "approvalPolicy": "never",
        },
        timeout=self._timeout_seconds,
    )
    try:
        client.wait_notification("turn/completed", timeout=self._timeout_seconds)
    except Exception:
        return CodexWakeDeliveryObservation(native_handle, nudge_id, True, False)
    return CodexWakeDeliveryObservation(native_handle, nudge_id, True, True)
finally:
    client.close()
```

A timeout/error from `thread/resume` or `turn/start` must escape to the existing dispatcher, which maps it to `FAILED` and performs no retry. Do not catch it and issue a second request.

- [ ] **Step 5: Export the concrete client without adding process/credential composition**

Add `CodexAppServerRpcWakeClient` to `integrations/executive_wake/__init__.py` only if that package already exports provider integration types. Do not create CODEX_HOME, read auth files, discover threads, or start new threads in this class. Trusted host/canary composition supplies the `AppServerClient` factory and dedicated environment later.

- [ ] **Step 6: Run combined GREEN**

```bash
python -m pytest \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_executive_wake_transport_registry.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

Then run the existing App Server/OHF continuity regression that contains the `thread/resume` process-restart proof. No `scripts/ohf/**` protocol implementation may be copied or weakened.

- [ ] **Step 7: Commit**

```bash
git add integrations/executive_wake/codex_app_server_rpc.py integrations/executive_wake/codex_app_server.py integrations/executive_wake/__init__.py tests/test_codex_app_server_wake_rpc.py
git commit -m "feat(exec): bind Wake to exact Codex App Server thread"
```

---

### Task 4: Produce a truthful installed-host Claude capability verdict

**Files:**
- Create: `ops/executive_os/claude_wake_preflight.py`
- Create: `tests/test_claude_wake_preflight.py`
- Conditional only after positive proof: `integrations/executive_wake/claude_code.py`, `tests/test_claude_code_wake_dispatcher.py`, `control_plane/wake_transport.py`

**Interfaces:**
- RuntimeBinding canonical provider-conversation identity: Claude full `sessionId` UUID only.
- Claude short background `id` and PID: ephemeral supervisor-control evidence only.
- Required positive sub-capabilities: exact discovery, same-conversation resurrection, scriptable same-conversation nudge ingress.

- [ ] **Step 1: Write RED preflight parsing tests**

Define a sanitized result schema:

```python
{
    "schema": "mastermind.claude_wake_preflight.v2",
    "binary_digest": "<sha256>",
    "version": "<installed version>",
    "agents_json_supported": bool,
    "exact_session_discovery_supported": bool,
    "respawn_supported": bool,
    "same_conversation_resurrection_supported": bool,
    "scriptable_same_conversation_ingress_supported": bool,
    "auth_ready": bool,
    "result": "SUPPORTED" | "CLAUDE_WAKE_UNSUPPORTED",
}
```

Durable output must contain none of: `sessionId`, background short id, PID, home path, email/account name, token, authorization header or credential file contents.

Tests must cover supported command-shape fixtures, malformed `agents --json`, duplicate matching sessions, missing `sessionId`, respawn changing `sessionId`, no scriptable ingress, auth-unready and secret-shaped output. Every ambiguous case returns `CLAUDE_WAKE_UNSUPPORTED`.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_claude_wake_preflight.py -q
```

Expected: FAIL because the preflight does not exist.

- [ ] **Step 3: Implement secret-free command acquisition**

The preflight may execute only capability/version/status commands against the installed binary and a dedicated safe background test conversation. It must never read Claude config/token files or scrape an internal supervisor socket. It must prove `claude agents --json` returns exactly one row matching the supplied runtime-only full `sessionId`, use the observed short `id` only in process memory for `respawn`, and re-read `agents --json` to prove the full `sessionId` is unchanged.

The ingress test must use only a documented/scriptable command surface proven by the installed binary. TUI-only reply semantics, screen driving and assumed hidden commands do not count.

- [ ] **Step 4: Run focused GREEN and a real host preflight**

```bash
python -m pytest tests/test_claude_wake_preflight.py -q
python ops/executive_os/claude_wake_preflight.py --json
```

The durable receipt is sanitized before storage/review.

- [ ] **Step 5A: Negative verdict path**

If any required sub-capability is false, assert:

```python
transport_implemented("claude-code-session") is False
```

Commit only the preflight/tests and the sanitized unsupported verdict. Do not create `claude_code.py` and do not guess a resume/ingress command.

```bash
git add ops/executive_os/claude_wake_preflight.py tests/test_claude_wake_preflight.py
git commit -m "test(exec): record Claude wake transport preflight"
```

Then proceed to Task 5.

- [ ] **Step 5B: Positive verdict return gate**

If all three sub-capabilities are genuinely proven, **stop before Claude dispatcher implementation and return to Sol on the same #174 carrier** with the exact installed binary version/digest and sanitized command contract. Sol must amend this plan with the proven argv/identity semantics before any `claude_code.py` production code is written. This is not permission to widen #174 or invent provider behavior.

---

### Task 5: Prove one harmless real Codex delivery and stop at `DELIVERED_UNACKNOWLEDGED`

**Files:**
- Create: `ops/executive_os/codex_wake_delivery_canary.py`
- Create: `tests/test_codex_wake_delivery_canary.py`
- Create after live run: `research/EXECUTIVE_WAKE_PR3_TRANSPORT_ACCEPTANCE_2026-08-27.md`

**Interfaces:**
- Uses a dedicated non-production in-memory target registry and one runtime-only `RuntimeBinding` supplied at invocation.
- Uses existing `dispatch_nudge`, `WakeRetryPolicy`, exact Codex dispatcher and concrete App Server RPC client.
- Persists no native handle and writes no Executive Wake ACK/source-resolution event.

- [ ] **Step 1: Write RED canary-safety tests**

Pin that the canary:

```text
refuses the checked-in production target registry as a writable/armed destination
creates only a local in-memory canary target/registry
uses exactly one obligation and one delivery attempt
uses one exact RuntimeBinding generation/native handle
requires Codex transport outcome DELIVERED
reconstructs status as DELIVERED_UNACKNOWLEDGED
never calls acknowledge(), ack_record(), source resolution or Executive event persistence
never serializes native_handle/account_label/CODEX_HOME/workspace path
verifies checked-in load_session_targets().production_armed remains False before and after
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_codex_wake_delivery_canary.py -q
```

- [ ] **Step 3: Implement the isolated canary runner**

Expose a function:

```python
def run_canary(
    *,
    binding: RuntimeBinding,
    dispatcher: CodexAppServerWakeDispatcher,
) -> dict[str, object]: ...
```

Inside the function, create a local one-target `SessionTargetRegistry` whose `production_armed=True` and target `target_enabled=True` exist **only in process memory for this non-production canary**. Never write that registry to disk or replace `load_session_targets()` configuration. Use a one-attempt armed retry policy:

```python
WakeRetryPolicy(
    max_delivery_attempts=1,
    retry_cooldown_s=1,
    accepted_ttl_s=60,
    target_unavailable_backoff_s=1,
    reenable_on_binding_rotation=False,
    armed=True,
)
```

Mint one harmless CEO wake obligation, route it to the local Codex target, call `dispatch_nudge()` once with the exact RuntimeBinding and dispatcher, and require the authenticated Wake receipt to be `DELIVERED`.

Reconstruct an in-memory ledger view from `WAKE_REQUESTED`, `DELIVERY_ATTEMPT` and `DELIVERED` records only and require:

```python
status is ObligationStatus.DELIVERED_UNACKNOWLEDGED
```

Do not append ACK or SOURCE_RESOLVED.

- [ ] **Step 4: Sanitize the canary receipt**

The durable JSON/Markdown evidence may contain:

```text
schema
UTC timestamp
protected/master SHA
PR/head SHA
obligation_id
attempt_command_id
nudge_id
binding_generation
destination_digest
transport=codex-app-server
transport_outcome=DELIVERED
obligation_status=DELIVERED_UNACKNOWLEDGED
production_config_armed=false
target_acknowledged=false
source_resolved=false
native_handle_persisted=false
```

It must not contain the native thread id, CODEX_HOME path, account label, prompt transcript or credentials.

- [ ] **Step 5: Run unit GREEN**

```bash
python -m pytest \
  tests/test_codex_wake_delivery_canary.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_executive_wake_transport_registry.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

- [ ] **Step 6: Run one real harmless provider canary**

Use an already-authenticated dedicated Codex home and a runtime-only known safe native thread. The operator must supply those at runtime without copying credentials or writing the thread id into command output/proof. Exactly one Wake turn is allowed. Any timeout/effect-unknown result stops the canary; do not rerun with a new nudge/thread.

- [ ] **Step 7: Write the acceptance research receipt and commit**

`research/EXECUTIVE_WAKE_PR3_TRANSPORT_ACCEPTANCE_2026-08-27.md` records the sanitized fields above, focused/full hosted gate ids, Claude verdict and explicit negatives:

```text
TARGET_ACKNOWLEDGED = NOT_BUILT for this wave
SOURCE_RESOLVED = NOT_PROVEN by this wave
production_armed = false
ACK ingress = NOT_BUILT / separate approved architecture required
```

Commit:

```bash
git add ops/executive_os/codex_wake_delivery_canary.py tests/test_codex_wake_delivery_canary.py research/EXECUTIVE_WAKE_PR3_TRANSPORT_ACCEPTANCE_2026-08-27.md
git commit -m "test(exec): prove Codex wake delivery without ACK laundering"
```

---

### Task 6: Exact-head acceptance, merge and durable handoff

**Files:**
- No new provider implementation files.
- Review all #174 changed files.
- Durable post-merge organizational record: existing Agent OS Autonomy/Wake workstream/handoff in Macro; do not create a new workstream or lifecycle.

**Interfaces:**
- Consumes: exact #174 head, hosted/security results, Claude verdict, sanitized Codex canary receipt.
- Produces: truthful merge receipt and next action = separately design the ACK-ingress architecture.

- [ ] **Step 1: Re-pin protected master and reconcile branch movement**

Require one immutable #174 head. If protected source law advanced materially, reconcile before review. No merge from a stale mutable branch name.

- [ ] **Step 2: Run the complete relevant gate**

At minimum:

```bash
python -m pytest \
  tests/test_executive_wake_pr3_vocab.py \
  tests/test_executive_wake_transport_registry.py \
  tests/test_codex_app_server_wake_dispatcher.py \
  tests/test_codex_app_server_wake_rpc.py \
  tests/test_codex_wake_delivery_canary.py \
  tests/test_executive_wake_fabric.py \
  tests/test_executive_wake_fabric_hardening.py \
  -q
```

Also run the repository's full hosted CI/security gate on that exact head. Do not infer success from a previous head.

- [ ] **Step 3: Independent adversarial review**

A fresh reviewer must attack:

```text
dispatcher key/identity mismatch
wrong RuntimeBinding/native thread
thread/start or thread/fork substitute conversation
second turn after timeout/effect unknown
provider/session failover
prompt/account/credential leakage
transport DELIVERED becoming ACK/source resolution
production kill-switch weakening
target enabling in checked-in config
Claude guessed/unproven resume or ingress
new Wake/session/retry/lifecycle persistence
```

Any Critical/Important issue returns to the same #174 carrier.

- [ ] **Step 4: Verify capability truth before merge**

Required exact statements:

```text
Codex native transport: BUILT_NOT_PROVEN or live-delivery-proven only to the extent of the real canary receipt
Claude native transport: supported/implemented only if host proof says so; otherwise NOT_BUILT / UNSUPPORTED
Wake target ACK ingress: NOT_BUILT
Wake source resolution after target ACK: not proven by #174
production Wake arming: false
end-to-end autonomous Wake: PARTIAL
```

- [ ] **Step 5: Merge only after exact-head gates pass**

Merge #174 without enabling production or creating ACK ingress. Preserve the immutable merge SHA, CI/security run ids, independent review receipt and sanitized canary identity.

- [ ] **Step 6: Close out durable state**

Update the existing Agent OS Autonomy/Wake organizational record with:

```text
#174 transport merge SHA
Codex delivery capability gained
Claude verdict
production remains disarmed
ACK ingress remains NOT_BUILT
end-to-end Wake remains PARTIAL
exact next action: architectural design/review of trusted target ACK ingress reusing existing Wake acknowledgement + Executive events
```

Do not create the ACK-ingress carrier until that architecture has gone through the required Chairman design/spec approval workflow. Do not project #174 merge as full autonomous Wake completion in Linear/Slack.
