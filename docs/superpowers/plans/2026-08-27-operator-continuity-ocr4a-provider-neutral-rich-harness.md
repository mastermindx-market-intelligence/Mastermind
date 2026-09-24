# OCR-4A Provider-Neutral Rich Operator Harness Composition Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Codex-specific control-side assumptions around the already-provider-neutral rich Operator Harness so Codex App Server and the later Claude sustained adapter can use the same Executive supervisor, broker wire, Event/Attempt lifecycle and Phase 1F-C orchestration path **without** turning one worker broker into a runtime provider selector.

**Architecture:** Preserve `OperatorHarnessAdapter` as the common rich execution protocol and preserve the current one-broker-process/one-Worker-realm boundary. Generalize the **control-side** `RemoteCodexOperatorAdapter` into a provider-neutral remote OHF proxy, keep a Codex compatibility wrapper, preserve the existing single `OperatorAdapterFactory` constructor seam inside each worker broker, and make each concrete realm factory fail closed unless the sealed `RequestedExecutionProfile` matches that broker realm. Executive OS/CF2 selects the Worker realm before dispatch; the broker never chooses provider/account/harness from a registry.

**Tech Stack:** Python 3.12, existing `OperatorHarnessAdapter`, `control_plane/operator_harness_wire.py`, `control_plane/executive_worker_broker.py`, `control_plane/remote_codex_operator_adapter.py`, `control_plane/executive_operator_supervisor.py`, capability/Model Router identities, pytest.

**Specs:**
- `docs/superpowers/specs/2026-08-27-operator-continuity-realm-rebinding-design.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-fable-root-seat-amendment.md`
- `docs/superpowers/specs/2026-08-27-operator-continuity-one-factory-per-realm-amendment.md`
- existing Operator Harness constitution/source law.

## Dependency / collision gate

Implementation begins only after the current CF2-I/RF1/HF1 source law is accepted/current and no active carrier owns the same generic broker/supervisor paths. OCR-4A must land before OCR-4's real Claude rich adapter is composed into a production-capable realm.

## Global Constraints

- One Executive Runtime, one worker-broker protocol, one OHF Event/state plane. No `claude_worker_broker`, `fable_supervisor`, provider queue, provider session DB or second rich-harness lifecycle.
- **One concrete rich adapter factory per worker-broker process / Worker realm.** No broker-local provider registry, no `(provider,harness_kind)->factory` map, no hidden fallback factory.
- Executive OS/CF2 chooses the claimed Worker realm before a broker request exists. The broker executes only that realm's reviewed concrete factory.
- Existing Codex App Server behavior must remain semantic-compatible unless a separately proven defect requires repair.
- The control side supplies the sealed `RequestedExecutionProfile`; broker/factory/provider never rewrites provider/model/harness/auth/sandbox/network/authority fields.
- A concrete realm factory must refuse a sealed profile whose provider, harness kind, Worker/principal expectation, harness identity/version/digest, capability profile or auth-realm requirement differs from its configured realm.
- Capability descriptions are observations only. They cannot widen the requested capability manifest or bypass `compare_launch()`.
- Phase 1F-C role vocabulary/cardinality remains unchanged.
- No new SQLite schema/table. If provider-neutrality appears to require one, STOP and return to Sol.

---

### Task 1: Generalize the control-side remote OHF proxy without changing the broker wire

**Files:**
- Create: `control_plane/remote_operator_harness_adapter.py`
- Modify: `control_plane/remote_codex_operator_adapter.py`
- Modify: `tests/test_executive_operator_broker.py`
- Create: `tests/test_remote_operator_harness_adapter.py`

**Interfaces:**
- Produces: `RemoteOperatorHarnessAdapter` implementing the same control-side typed operations currently provided by `RemoteCodexOperatorAdapter`.
- Preserves: `RemoteCodexOperatorAdapter` as a compatibility wrapper/subclass, not a second transport.

- [ ] **Step 1: Write RED-first proxy parity tests**

Use the same fake/stub broker client patterns already present in `tests/test_executive_operator_broker.py`. Verify the generic proxy emits exactly the current typed operation vocabulary:

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

For identical typed values, generic proxy request/receipt semantics must match the current Codex proxy.

- [ ] **Step 2: Implement the provider-neutral proxy constructor**

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

`capabilities` is trusted Executive-side composition, not provider/model/caller output. Validate exact interface version and closed supported-operation vocabulary before accepting it.

- [ ] **Step 3: Move only generic request/receipt mechanics**

Move the typed broker-call implementation from the Codex-specific proxy into the generic class without adding provider conditions or provider selection.

- [ ] **Step 4: Retain exact Codex compatibility**

`RemoteCodexOperatorAdapter` supplies the current reviewed Codex `HarnessAdapterCapabilities` and delegates to the generic class. Existing imports in `scripts/executive_os_phase1c.py` and `control_plane/executive_operator_supervisor.py` remain valid until Task 4 migrates them deliberately.

- [ ] **Step 5: Run focused regression**

```bash
pytest -q tests/test_remote_operator_harness_adapter.py tests/test_executive_operator_broker.py tests/test_executive_operator_supervisor.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/remote_operator_harness_adapter.py control_plane/remote_codex_operator_adapter.py tests/test_remote_operator_harness_adapter.py tests/test_executive_operator_broker.py
git commit -m "refactor(exec): generalize remote Operator Harness proxy"
```

---

### Task 2: Preserve the broker's single-factory realm seam and make realm pinning explicit

**Files:**
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `tests/test_executive_operator_broker.py`
- Create: `tests/test_operator_adapter_factory_realm_pinning.py`

**Interfaces:**
- Existing broker constructor retains exactly one `OperatorAdapterFactory` (or a provider-neutral rename of the same single factory type).
- No provider registry/catalog is added.

- [ ] **Step 1: Write RED-first single-factory tests**

Build two broker fixtures separately:

```text
Codex realm broker + codex_factory
Claude synthetic realm broker + fake_claude_factory
```

Each broker receives one factory only. A Codex profile succeeds only on the Codex broker fixture; a Claude profile succeeds only on the Claude fixture.

- [ ] **Step 2: Pin wrong-realm refusal before provider construction**

For each concrete realm factory, require the sealed `RequestedExecutionProfile` to match configured realm expectations at least across:

```text
provider
harness_kind
worker_id / process-principal binding
harness binary digest/version
execution/capability profile identity
auth realm requirement
```

A Claude-configured factory presented with Codex profile data must refuse without constructing a provider adapter/process. The reverse must also refuse.

- [ ] **Step 3: Prove the wire cannot select provider implementation**

Source/tests must reject any new broker request field or public operation that allows caller/model selection of:

```text
adapter_id
factory_name
provider_module
executable_path chosen by request
provider socket
fallback_provider
```

The sealed requested profile is validated against the already-configured realm; it is not a provider-selection command.

- [ ] **Step 4: Preserve request/generation scope**

Adapter instances remain scoped according to current ProcessGeneration/broker lifecycle. The broker may not retain a provider session independently of the current Executive generation/adapter instance.

- [ ] **Step 5: Run broker security suite**

```bash
pytest -q tests/test_executive_operator_broker.py tests/test_operator_adapter_factory_realm_pinning.py tests/test_operator_harness_wire.py
```

Require existing dedicated-worker UID, no-generic-shell, response-redaction and effect-uncertainty tests to remain green.

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_worker_broker.py tests/test_executive_operator_broker.py tests/test_operator_adapter_factory_realm_pinning.py
git commit -m "refactor(exec): pin one rich adapter factory per realm"
```

---

### Task 3: Split Executive operator profile resolution from Codex-specific assumptions

**Files:**
- Create: `control_plane/executive_operator_profile.py`
- Modify: `control_plane/executive_operator_supervisor.py`
- Create: `tests/test_executive_operator_profile.py`
- Modify: `tests/test_executive_operator_supervisor.py`

**Interfaces:**
- Produces: `OperatorExecutionBinding` and a pure resolver derived from the current claimed Job/Attempt/quota registration plus accepted capability policy.

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

- [ ] **Step 1: Write current Codex parity tests**

For the current reviewed Codex planner profile require unchanged effective requirements:

```text
provider=openai-codex
harness_kind=codex-app-server
current model/effort/profile-policy identities
current read-only planner capability/authority law
current MCP/native-helper law
```

No Job/SQLite schema change is permitted for parity.

- [ ] **Step 2: Add a hermetic synthetic Claude binding**

A fixture may resolve a synthetic accepted binding:

```text
provider=claude
harness_kind=claude-agent-sdk
auth_realm_requirement=SLOT_BOUND_V1
reviewed synthetic sandbox/approval/network/capability identity
```

No Claude executable/provider call occurs in OCR-4A.

- [ ] **Step 3: Refuse routing/authority drift**

Reject if Job/Attempt/quota/profile identity differs, if a capability profile would widen authority, if provider/harness implementation support is absent, if policy digests mismatch, or if provider identity is used to infer `owner_seat`/orchestration role.

- [ ] **Step 4: Refactor supervisor requested-profile construction**

Keep workspace, authority, role/result and TX law in the supervisor. Move only provider/harness/profile-specific resolution into the pure resolver. The output describes the **already-claimed realm**; it does not choose one.

- [ ] **Step 5: Run profile/supervisor regression**

```bash
pytest -q tests/test_executive_operator_profile.py tests/test_executive_operator_supervisor.py
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_operator_profile.py control_plane/executive_operator_supervisor.py tests/test_executive_operator_profile.py tests/test_executive_operator_supervisor.py
git commit -m "refactor(exec): resolve provider-neutral operator profile"
```

---

### Task 4: Generalize supervisor remote-adapter construction while targeting the already-claimed realm

**Files:**
- Modify: `control_plane/executive_operator_supervisor.py`
- Modify: `control_plane/remote_operator_harness_adapter.py`
- Modify: `scripts/executive_os_phase1c.py` only if its current Codex-specific proxy type prevents the provider-neutral control composition.
- Modify: `tests/test_executive_operator_supervisor.py`
- Modify: `tests/test_executive_operator_broker.py`

**Interfaces:**
- The control-side adapter factory/client is resolved from the claimed Worker realm's already-established broker endpoint/configuration by current Executive composition. It never asks one worker broker to choose a provider.

- [ ] **Step 1: Write dual-realm hermetic composition tests**

Run the same supervisor/OHF flow twice with fake transports:

```text
claimed Codex Worker -> Codex realm broker -> Codex concrete factory
claimed Claude Worker -> Claude realm broker -> synthetic Claude concrete factory
```

Equivalent observations must traverse the same `OperatorHarnessOrchestrator` / `ExecutiveOperatorHarnessPort` TX/Event law.

- [ ] **Step 2: Refuse cross-realm endpoint/factory mismatch**

A claimed Claude Worker paired with a Codex realm broker/factory must refuse before provider dispatch. Likewise for Codex -> Claude. There is no secondary endpoint or provider fallback.

- [ ] **Step 3: Preserve role law and provider-private boundaries**

The provider-neutral supervisor may not import/use Claude Agent SDK or Codex App Server native mechanics directly. Provider-private mechanics stay behind concrete realm adapters. Existing Phase 1F-C role vocabulary remains unchanged.

- [ ] **Step 4: Run OHF/Phase 1F-C parity**

```bash
pytest -q \
  tests/test_executive_operator_profile.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_executive_operator_broker.py \
  tests/test_operator_harness_orchestrator.py \
  tests/test_executive_operator_harness_port.py \
  tests/test_executive_os_phase1fc.py
```

- [ ] **Step 5: Commit**

```bash
git add control_plane/executive_operator_supervisor.py control_plane/remote_operator_harness_adapter.py scripts/executive_os_phase1c.py tests/test_executive_operator_supervisor.py tests/test_executive_operator_broker.py
git commit -m "refactor(exec): drive claimed rich operator realms generically"
```

---

### Task 5: Adversarial no-duplicate-plane / no-hidden-failover proof

**Files:**
- Create: `tests/test_operator_harness_provider_neutral_fences.py`

- [ ] **Step 1: Pin forbidden production concepts**

Fail source census/tests if the implementation introduces provider-specific lifecycle/control-plane concepts such as:

```text
ClaudeSupervisor
FableSupervisor
ClaudeWorkerBroker
provider_adapter_registry inside WorkerBroker
claude_queue
provider_retry_registry
provider_session_database
fallback_provider
```

Provider-private `ClaudeOperatorAdapter`/helper under OCR-4 is permitted because that is the sanctioned adapter boundary.

- [ ] **Step 2: Pin one common wire and per-realm concrete factory**

Assert all rich providers use the existing broker protocol and Executive Runtime/OHF state. Assert every broker process is configured with exactly one concrete factory and cannot instantiate another provider implementation from request data.

- [ ] **Step 3: Kill critical mutations**

Mutation/adversarial tests must catch:

- broker chooses provider factory from request/profile instead of validating against configured realm;
- wrong provider/harness profile is accepted by a realm factory;
- provider capability response widens requested tools;
- provider changes executive seat/role;
- Claude bypasses TX-2/TX-3/TX-4/TX-5;
- Codex behavior changes due to generic refactor;
- unknown provider silently falls back to Codex/Claude.

- [ ] **Step 4: Exact-head proof**

Require focused tests above, current complete repository CI, CodeQL/security and independent adversarial review under current repository procedure.

## Stop Condition

OCR-4A stops at `BUILT_NOT_PROVEN / PRODUCTION_INERT` when the current Codex rich path remains exact, the control proxy/supervisor is provider-neutral, and a synthetic Claude realm can traverse the same hermetic contract **using a distinct broker fixture configured with exactly one Claude concrete factory**. OCR-4A does not make Claude live, provision accounts, route capacity, change Wake/Slack or prove cross-realm rollover.