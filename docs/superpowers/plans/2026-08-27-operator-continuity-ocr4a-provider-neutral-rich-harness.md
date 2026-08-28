# OCR-4A Provider-Neutral Rich Operator Harness Composition Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the remaining Codex-specific composition assumptions around the already-provider-neutral rich Operator Harness so Codex App Server and the later Claude sustained adapter can use the **same** Executive supervisor, worker broker, remote proxy, Event/Attempt lifecycle and Phase 1F-C orchestration path without creating a Claude broker/supervisor or weakening existing Codex behavior.

**Architecture:** Preserve `OperatorHarnessAdapter` as the provider-neutral execution contract and the existing one worker broker as the only worker-side typed RPC boundary. Generalize the control-side `RemoteCodexOperatorAdapter` into a provider-neutral `RemoteOperatorHarnessAdapter`, retain a compatibility alias for current Codex callers, and let the worker broker resolve an immutable pre-composed adapter factory by the exact **sealed** `(provider, harness_kind)` in `RequestedExecutionProfile`. Generalize `ExecutiveOperatorSupervisor` so reviewed capability/profile policy determines the provider/harness adapter while the supervisor continues to own Executive lifecycle, prompt/result law and Phase 1F-C role semantics. Provider adapters may observe capabilities and native session mechanics; they never choose Job authority, model tier, account placement, role, retry or completion.

**Tech Stack:** Python 3.12, existing `OperatorHarnessAdapter`, `operator_harness_wire`, `executive_worker_broker`, `ExecutiveOperatorSupervisor`, capability registry/Model Router identities, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- existing Operator Harness constitution/source law.

## Dependency / collision gate

Planning may merge now. Implementation begins only after current CF2-I/RF1/HF1 source law is accepted and no active carrier owns the same generic broker/supervisor paths. OCR-4A must land before OCR-4's real Claude rich adapter is composed into production.

## Global Constraints

- One Executive Runtime, one worker broker protocol, one OHF Event/state plane. No `claude_worker_broker`, `fable_supervisor`, provider queue, per-provider socket or second rich-harness lifecycle.
- Existing Codex App Server behavior must remain byte/semantic compatible unless a separately documented defect requires repair.
- The **control side** supplies the sealed `RequestedExecutionProfile`; the worker broker does not rewrite provider/model/harness/auth/sandbox/network/authority fields.
- The broker's adapter registry is immutable process composition, not mutable routing state. Selection occurs only after exact profile validation and is never based on provider prose, PATH discovery, Slack identity or account availability.
- RF1/CF2 determine lawful model/provider/realm before claim. OCR-4A only executes an already-claimed profile.
- Capability descriptions returned by an adapter are observations/implementation support. They cannot widen the requested capability manifest or bypass `compare_launch()`.
- Phase 1F-C orchestration role vocabulary/cardinality remains unchanged.
- No new SQLite schema/table is expected. If generalization appears to require one, STOP and return to Sol.

---

### Task 1: Generalize the control-side remote OHF proxy without changing the wire

**Files:**
- Create: `control_plane/remote_operator_harness_adapter.py`
- Modify: `control_plane/remote_codex_operator_adapter.py`
- Create: `tests/test_remote_operator_harness_adapter.py`
- Modify: existing `tests/test_remote_codex_operator_adapter.py` if present/current.

**Interfaces:**
- New `RemoteOperatorHarnessAdapter` implements the same local adapter surface currently exposed by `RemoteCodexOperatorAdapter`.
- `RemoteCodexOperatorAdapter` becomes a compatibility subclass/alias with no separate transport/lifecycle behavior.

- [ ] **Step 1: Write RED-first parity tests**

Construct a fake `WorkerBrokerClient` and verify the generic proxy sends the exact existing operations and wire values:

```text
ohf-validate
ohf-start
ohf-resume
ohf-begin-turn
ohf-collect-turn
ohf-interrupt
ohf-stop
ohf-cancel
ohf-reconcile
ohf-reconcile-absence
```

The generated payloads must be byte/semantic equal to current Codex proxy behavior for identical typed values.

- [ ] **Step 2: Pin provider-neutral constructor**

Target shape:

```python
class RemoteOperatorHarnessAdapter:
    interface_version = OPERATOR_HARNESS_INTERFACE_VERSION

    def __init__(
        self,
        client: WorkerBrokerClient,
        *,
        turn_input_loader: TurnInputLoader,
        capabilities: HarnessAdapterCapabilities,
    ) -> None:
        ...
```

`capabilities` is trusted process composition supplied by the Executive-side adapter registry, not model/caller JSON. It must have the exact interface version and closed supported-operation vocabulary.

- [ ] **Step 3: Move generic request/receipt code unchanged**

Move the current typed proxy implementation into the generic class. Do not add provider-specific conditions.

- [ ] **Step 4: Retain Codex compatibility wrapper**

`RemoteCodexOperatorAdapter` may instantiate the exact current Codex `HarnessAdapterCapabilities` and delegate all behavior to the generic class. Existing imports/tests remain valid during migration.

- [ ] **Step 5: Run exact Codex parity suite**

```bash
pytest -q tests/test_remote_operator_harness_adapter.py tests/test_remote_codex_operator_adapter.py
```

Use the actual current test filename if it differs.

- [ ] **Step 6: Commit**

```bash
git add control_plane/remote_operator_harness_adapter.py control_plane/remote_codex_operator_adapter.py tests/test_remote_operator_harness_adapter.py
git commit -m "refactor(exec): generalize remote Operator Harness proxy"
```

---

### Task 2: Make the existing worker broker resolve one immutable adapter registry

**Files:**
- Modify: `control_plane/executive_worker_broker.py`
- Create/modify: `tests/test_executive_worker_broker_operator_registry.py`
- Preserve existing broker tests.

**Interfaces:**
- Existing single broker socket/protocol remains.
- New process-composition input conceptually:

```python
OperatorAdapterKey = tuple[str, str]  # (provider, harness_kind)
OperatorAdapterRegistry = Mapping[OperatorAdapterKey, OperatorAdapterFactory]
```

- [ ] **Step 1: Write RED-first registry selection tests**

Given immutable factories:

```python
{
    ("openai-codex", "codex-app-server"): codex_factory,
    ("claude", "claude-agent-sdk"): fake_claude_factory,
}
```

an `ohf-validate/start/...` request with a sealed Codex profile resolves only the Codex factory; a sealed Claude profile resolves only the Claude factory.

Refuse unknown provider/harness pair, duplicate normalized keys, registry mutation after construction, and a factory whose resulting adapter reports an incompatible interface/capability set.

- [ ] **Step 2: Prove request cannot choose an arbitrary adapter id**

The broker wire must not gain `adapter_id`, executable path, Python module, socket or factory name fields. Resolution is exclusively from `requested.provider` + `requested.harness_kind` after closed-wire reconstruction.

- [ ] **Step 3: Generalize current single `OperatorAdapterFactory` composition**

Keep adapter instances generation/request-scoped according to current broker semantics. Do not retain one long-lived provider session outside the current ProcessGeneration/adapter instance.

- [ ] **Step 4: Add an explicit `ohf-describe` only if needed**

Prefer the control side carrying reviewed `HarnessAdapterCapabilities`. If the worker side must attest implementation support, add a read-only `ohf-describe` operation returning the closed `HarnessAdapterCapabilities` wire and compare it against expected composition. Do not let the response authorize a capability not present in the sealed profile.

- [ ] **Step 5: Run full broker security/parity tests**

```bash
pytest -q tests/test_executive_worker_broker*.py tests/test_operator_harness_wire.py
```

Require existing peer-UID, dedicated-UID sweep, no-generic-shell and response-redaction tests unchanged.

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_worker_broker.py tests/test_executive_worker_broker_operator_registry.py
git commit -m "refactor(exec): compose rich provider adapters in one broker"
```

---

### Task 3: Split Executive operator policy from Codex-specific profile assumptions

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Create: `control_plane/executive_operator_profile.py`
- Create: `tests/test_executive_operator_profile.py`
- Modify: existing `tests/test_executive_operator_supervisor.py`.

**Interfaces:**
- New pure resolver derives an `OperatorExecutionBinding` from **current claimed Job/Attempt/quota + accepted capability registry**, never from provider output.

Target concept:

```python
@dataclass(frozen=True)
class OperatorExecutionBinding:
    provider: str
    harness_kind: str
    harness_binary_digest: str
    harness_version: str
    model: str
    effort: str
    capability_profile_id: str
    capability_profile_digest: str
    auth_realm_requirement: AuthRealmRequirement
    remote_capabilities: HarnessAdapterCapabilities
```

- [ ] **Step 1: Write RED-first Codex parity tests**

For today's reviewed Codex planner profile, resolver output must preserve current requirements:

```text
provider=openai-codex
harness_kind=codex-app-server
read-only planner grant
current exact capability profile/policy digests
model/effort/harness identity match quota registration
current MCP/native-helper policy exactly as accepted
```

No current Codex test may require changed Job JSON or SQLite schema.

- [ ] **Step 2: Add a synthetic Claude profile fixture only**

Before OCR-4 lands, prove a synthetic accepted profile can resolve:

```text
provider=claude
harness_kind=claude-agent-sdk
SLOT_BOUND_V1
reviewed sandbox/approval/network/capability set
```

This is hermetic policy composition only; it makes no Claude provider live.

- [ ] **Step 3: Refuse authority/routing drift**

Reject if:

- Job provider/model/profile differs from claimed quota/placement;
- provider profile asks for authority not already present on the Job;
- unimplemented provider/harness pair;
- capability policy/routing policy digest mismatch;
- provider adapter is capable of more tools than the reviewed profile and attestation cannot prove the extras absent;
- `owner_seat`/role is inferred from provider.

- [ ] **Step 4: Refactor `_requested_profile()`**

The supervisor still constructs the exact `RequestedExecutionProfile` and workspace identity. Move only provider/harness/profile-specific matching into the pure binding resolver. Preserve role/authority/result-envelope logic in the supervisor.

- [ ] **Step 5: Run Codex supervisor regression**

```bash
pytest -q tests/test_executive_operator_profile.py tests/test_executive_operator_supervisor.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_operator_supervisor.py control_plane/executive_operator_profile.py tests/test_executive_operator_profile.py tests/test_executive_operator_supervisor.py
git commit -m "refactor(exec): resolve provider-neutral operator profiles"
```

---

### Task 4: Generalize supervisor adapter construction without creating provider supervisors

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Modify: `control_plane/remote_operator_harness_adapter.py`
- Modify: relevant supervisor integration tests.

**Interfaces:**
- Replace `RemoteAdapterFactory -> RemoteCodexOperatorAdapter` typing with one generic factory returning `RemoteOperatorHarnessAdapter`/`OperatorHarnessAdapter` proxy.

- [ ] **Step 1: Write RED-first dual-provider composition test**

Using fake broker clients/adapters, run the same supervisor orchestration flow once with current Codex binding and once with a synthetic Claude binding. Both must call the same `OperatorHarnessOrchestrator` and `ExecutiveOperatorHarnessPort` and produce the same Executive TX/Event sequence for equivalent observations.

- [ ] **Step 2: Preserve role law**

This refactor does not make arbitrary roles operator-capable. The currently accepted supervisor role set remains as source law defines it; OCR-5's Fable planner path is enabled only by the reviewed provider profile for that existing `plan` role.

- [ ] **Step 3: Provider-specific code stays behind adapter**

Search/fence production supervisor code against direct imports of `claude_agent_sdk`, Claude CLI argv, Codex App Server JSON-RPC, auth files or provider session-store paths.

- [ ] **Step 4: Run full OHF/Phase 1F-C parity**

```bash
pytest -q \
  tests/test_executive_operator_profile.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_operator_harness_orchestrator.py \
  tests/test_executive_operator_harness_port.py \
  tests/test_executive_os_phase1fc.py
```

- [ ] **Step 5: Commit**

```bash
git add control_plane/executive_operator_supervisor.py control_plane/remote_operator_harness_adapter.py tests
git commit -m "refactor(exec): run rich operators through one supervisor"
```

---

### Task 5: Adversarial no-duplicate-plane proof

**Files:**
- Create: `tests/test_operator_harness_provider_neutral_fences.py`
- Documentation updates only for concrete discoveries.

- [ ] **Step 1: Pin forbidden implementation mutations**

Fail if implementation introduces production symbols/files matching forbidden concepts such as:

```text
ClaudeSupervisor
FableSupervisor
ClaudeWorkerBroker
claude_queue
provider_retry_registry
provider_session_database
```

Permit provider-private `ClaudeOperatorAdapter`/helper from OCR-4 because adapters are the sanctioned private mechanics boundary.

- [ ] **Step 2: Pin one broker/one Runtime**

Tests/source census confirm all rich provider requests still pass through existing `WorkerBrokerClient`/broker protocol and Executive Runtime Event/Attempt state. No provider-specific durable store/socket is introduced.

- [ ] **Step 3: Mutation tests**

Kill these mutations:

- broker chooses adapter from caller-supplied arbitrary name;
- provider capability response widens requested tools;
- provider changes owner seat/role;
- Claude path bypasses TX-2/TX-3/TX-4/TX-5;
- Codex path changes due to generic refactor;
- unknown provider silently falls back to Codex/Claude.

- [ ] **Step 4: Full exact-head CI/security/adversarial review**

Require CodeQL and focused mutation receipts plus current complete Mastermind suite according to repository acceptance practice.

## Stop Condition

OCR-4A stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT` when the existing rich Operator Harness has one provider-neutral broker/proxy/supervisor composition, current Codex behavior remains exact, and a synthetic second provider can traverse the same hermetic contract. It does not itself make Claude live, provision an account, route capacity, change Wake/Slack, or prove cross-realm rollover.
