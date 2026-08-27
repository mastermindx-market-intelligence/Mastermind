# HF1 Common Worker Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove Codex-only types and provider-home mechanics from the common Executive worker boundary so one existing Job/Attempt/Worker lifecycle can execute Codex and later Claude/GLM/Grok/Qwen/DeepSeek adapters without provider-specific brokers, queues, retries, or lifecycle state.

**Architecture:** HF1 extracts genuinely provider-neutral launch/process/result/cancel/validation contracts from `codex_worker.py` into `worker_execution_contract.py`. Provider authentication/home/session mechanics move into adapter construction, not the durable Job or common launch request. `ExecutiveSupervisor` and the existing worker broker consume only `WorkerExecutionAdapter`; the broker remains one fixed, typed service with one configured adapter identity per worker realm. Codex is migrated first and must remain byte-for-byte equivalent at its security/receipt boundaries. A synthetic non-Codex adapter proves the common broker/supervisor path before PF1 adds real Claude.

**Tech Stack:** Python 3.11+, asyncio, dataclasses, existing Executive SQLite Runtime, AF_UNIX broker, pytest.

**Spec:** `docs/superpowers/specs/2026-08-27-executive-workforce-hybrid-role-topology-design.md`

## Global Constraints

- Execute only after CF2-I is accepted, unless a later current Sol source-law ruling explicitly changes the dependency.
- Re-pin protected Skillpack/default branch and inspect current CF2-I changes before editing. CF2-I may have changed claim/placement interfaces; absorb only the accepted interface, never duplicate it.
- Executive Runtime remains the sole Job/Attempt/Worker/Event/lease authority.
- One common broker/adapter lifecycle. Do not create `claude_broker`, `glm_broker`, `grok_broker`, `qwen_broker`, or provider-specific lifecycle services.
- Provider credential/home/session mechanics are adapter-private runtime facts. They must not enter Git config, Job payloads, Events, Agent OS, Slack, or public receipts.
- A timeout/disconnect after provider execution may have begun is `EFFECT_UNKNOWN` until the same Attempt/provider operation is reconciled. Never fail over providers or hosts from an ambiguous effect.
- Tmux, App Server, CLI and API processes are subordinate execution substrates only.
- Preserve Codex dedicated-UID, process identity, secret-canary, workspace, authority, validation and cancellation laws.

---

### Task 1: Extract the provider-neutral execution contract

**Files:**
- Create: `control_plane/worker_execution_contract.py`
- Modify: `control_plane/codex_worker.py`
- Modify: `control_plane/worker_adapter.py`
- Modify: `tests/test_executive_codex_worker.py`
- Create: `tests/test_worker_execution_contract.py`

**Interfaces:**
- `WORKER_EXECUTION_CONTRACT_VERSION = "mastermind.worker_execution_contract/v1"`
- Provider-neutral types: `WorkerRunStatus`, `BinaryAttestation`, `WorkerLaunchSpec`, `WorkerProcessRef`, `ArtifactReceipt`, `WorkerResult`, `CollectionReceipt`, `CancelReceipt`, `ValidationReceipt`.
- `codex_worker.py` re-exports compatibility aliases for the moved names so downstream source imports do not fork a second contract.
- `WorkerLaunchSpec` contains no `codex_home`, token, credential path, account login, API key, or provider-native thread/session locator.

- [ ] **Step 1: Write contract extraction tests RED-first**

Create `tests/test_worker_execution_contract.py` with tests that import every common type from the new module, instantiate a minimal `WorkerLaunchSpec`, and assert the dataclass field names contain no provider-specific token:

```python
fields = {item.name for item in dataclasses.fields(WorkerLaunchSpec)}
assert "codex_home" not in fields
assert "claude_home" not in fields
assert "api_key" not in fields
assert "provider_session_id" not in fields
```

Pin these common launch fields from the existing Codex `LaunchSpec`:

```text
run_id, job_id, worker_id, workspace_path, run_dir, prompt,
result_schema_path, authorities, authority, model, reasoning_effort,
timeout_seconds, cancel_grace_seconds, worker_user, expected_base_sha,
allowed_artifact_paths, isolation_roots, isolation_denied_paths,
isolation_manifest, isolation_manifest_sha256, forbidden_paths,
max_artifacts, max_artifact_bytes, max_artifact_total_bytes,
expected_worker_uid, expected_worker_gid, shared_run_gid,
secret_canary_verdict, require_secret_canary
```

The provider-specific home is deliberately excluded.

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_worker_execution_contract.py -q
```

Expected: import failure because the common contract module does not exist.

- [ ] **Step 3: Create the common dataclasses and enum**

Move the listed provider-neutral dataclasses/enum from `codex_worker.py` into `worker_execution_contract.py` without changing their serialized field meanings, except:

```python
@dataclasses.dataclass(frozen=True)
class WorkerLaunchSpec:
    # fields listed above; deliberately no provider home/session/credential
    ...
```

Keep `provider_session_id` on `WorkerProcessRef` and `WorkerResult` because it is non-secret execution evidence produced after launch; it is not a launch authority or persisted provider-home locator.

- [ ] **Step 4: Re-export compatibility names from `codex_worker.py`**

Import and alias:

```python
from control_plane.worker_execution_contract import (
    ArtifactReceipt,
    BinaryAttestation,
    CancelReceipt,
    CollectionReceipt,
    ValidationReceipt,
    WorkerLaunchSpec,
    WorkerProcessRef,
    WorkerResult,
    WorkerRunStatus,
)

LaunchSpec = WorkerLaunchSpec
ProcessRef = WorkerProcessRef
```

Do not duplicate dataclass definitions after the move.

- [ ] **Step 5: Make `worker_adapter.py` Codex-import-free**

Replace all imports from `control_plane.codex_worker` with imports from `worker_execution_contract`. The protocol becomes:

```python
@runtime_checkable
class WorkerExecutionAdapter(Protocol):
    inspector: ProcessInspector

    async def start(self, spec: WorkerLaunchSpec) -> WorkerProcessRef: ...
    async def collect_result(self, ref: WorkerProcessRef) -> CollectionReceipt: ...
    async def cancel(self, ref: WorkerProcessRef, reason: str) -> CancelReceipt: ...
    async def run_validation_argv(
        self,
        spec: WorkerLaunchSpec,
        argv: Sequence[str],
        *,
        timeout_seconds: float = 300.0,
    ) -> ValidationReceipt: ...
```

Move/define the structural `ProcessInspector` protocol in the common contract if it is currently Codex-owned; Codex's concrete inspector must satisfy it structurally.

- [ ] **Step 6: Run focused compatibility tests**

```bash
python -m pytest \
  tests/test_worker_execution_contract.py \
  tests/test_executive_codex_worker.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/worker_execution_contract.py control_plane/codex_worker.py control_plane/worker_adapter.py tests/test_worker_execution_contract.py tests/test_executive_codex_worker.py
git commit -m "refactor(exec): extract provider-neutral worker contract"
```

---

### Task 2: Move provider-home authority into the Codex adapter

**Files:**
- Modify: `control_plane/codex_worker.py`
- Modify: `control_plane/executive_supervisor.py`
- Modify: `scripts/executive_os_phase1b.py`
- Modify: `scripts/executive_os_phase1c.py`
- Modify: `tests/test_executive_codex_worker.py`
- Modify: `tests/test_executive_operator_supervisor.py`

**Interfaces:**
- `CodexWorkerAdapter(..., codex_home: Path, ...)` owns the private provider home.
- `ExecutiveSupervisor(runtime, adapter, ...)` no longer receives `codex_home`.
- `WorkerLaunchSpec` never carries provider-home identity.

- [ ] **Step 1: Add failing provider-private-home tests**

Pin that a Codex adapter cannot start without a configured private home and that the common launch spec cannot override it. Add a disagreement test where a legacy caller attempts to supply a second home and require a constructor/type failure rather than precedence guessing.

- [ ] **Step 2: Run RED**

```bash
python -m pytest \
  tests/test_executive_codex_worker.py \
  tests/test_executive_operator_supervisor.py \
  -q
```

- [ ] **Step 3: Move `codex_home` to adapter construction**

Change `CodexWorkerAdapter.__init__` so the exact reviewed `codex_home` is configured once with the adapter alongside the absolute binary/version policy. All internal environment/provider-home validation reads `self.codex_home`; `start()` receives no home from the Job/launch request.

- [ ] **Step 4: Remove `codex_home` from supervisor composition**

`ExecutiveSupervisor` must not know the provider-home field. It builds a `WorkerLaunchSpec` only from durable Job/Attempt/authority/workspace inputs and invokes the configured adapter.

Update the CLI composition so:

```python
adapter = CodexWorkerAdapter(
    args.codex_binary,
    codex_home=args.codex_home,
    allowed_versions=frozenset(args.allowed_version),
)
return ExecutiveSupervisor(runtime, adapter)
```

The CLI may still accept `--codex-home` because it is configuring a Codex adapter; that provider-private flag must not leak into the generic supervisor or durable launch contract.

- [ ] **Step 5: Prove receipts remain secret-safe**

Existing launch/provider-home receipts may include reviewed non-secret identity metadata, but no credential bytes or private auth-file contents. Run all existing secret-canary and launch-attestation tests unchanged.

- [ ] **Step 6: Run focused + Phase 1B/1C tests**

```bash
python -m pytest \
  tests/test_executive_codex_worker.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_executive_worker_broker.py \
  -q
```

- [ ] **Step 7: Commit**

```bash
git add control_plane/codex_worker.py control_plane/executive_supervisor.py scripts/executive_os_phase1b.py scripts/executive_os_phase1c.py tests/test_executive_codex_worker.py tests/test_executive_operator_supervisor.py
git commit -m "refactor(exec): keep provider homes adapter-private"
```

---

### Task 3: Make the existing broker adapter-configured rather than Codex-hardcoded

**Files:**
- Modify: `control_plane/executive_worker_broker.py`
- Modify: `control_plane/worker_adapter.py`
- Modify: `tests/test_executive_worker_broker.py`
- Create: `tests/test_worker_adapter_broker_contract.py`

**Interfaces:**
- A broker instance is configured at startup with exactly one reviewed `adapter_id` and one `WorkerExecutionAdapter` instance.
- The request payload never selects an arbitrary provider/adapter.
- `AdapterDescriptor` remains the implementation-state authority.

- [ ] **Step 1: Write broker-injection tests**

Create a small `SyntheticWorkerAdapter` in `tests/test_worker_adapter_broker_contract.py` implementing the common protocol with deterministic fake process/results. Assert:

```text
one broker instance accepts common start/status/collect/cancel/validate through the synthetic adapter
a request cannot name or switch adapter_id
broker configured as codex-cli still emits current response schema
unknown/unimplemented configured adapter refuses startup
```

- [ ] **Step 2: Run RED**

```bash
python -m pytest tests/test_worker_adapter_broker_contract.py -q
```

- [ ] **Step 3: Inject the adapter into the broker service**

Refactor direct `CodexWorkerAdapter` construction/use out of the generic request-handling core. Keep the production Codex entrypoint constructing the existing Codex adapter and passing it into the same service. The service records only the reviewed `adapter_id` descriptor in non-secret startup metadata.

Do not add `adapter_id` to ordinary per-request payloads; Executive Worker placement chooses the worker realm before the request reaches this fixed broker.

- [ ] **Step 4: Keep Codex-only OHF operations fenced**

The current `ohf-*` App Server operations remain available only when the configured adapter exposes the existing OHF capability seam. A synthetic/simple worker adapter must receive a typed refusal for unsupported OHF operations, not a generic shell fallback.

- [ ] **Step 5: Run all broker/OHF regressions**

```bash
python -m pytest \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_worker_broker.py \
  tests/test_executive_operator_broker.py \
  tests/test_codex_operator_adapter.py \
  -q
```

- [ ] **Step 6: Commit**

```bash
git add control_plane/executive_worker_broker.py control_plane/worker_adapter.py tests/test_worker_adapter_broker_contract.py tests/test_executive_worker_broker.py
git commit -m "refactor(exec): configure worker broker by adapter"
```

---

### Task 4: Prove a synthetic non-Codex Attempt through the real Executive lineage

**Files:**
- Modify: `tests/test_executive_operator_supervisor.py`
- Modify: `tests/test_worker_adapter_broker_contract.py`
- Modify: `tests/test_executive_os_phase1fb.py`

**Interfaces:**
- Consumes common adapter/broker contract from Tasks 1–3.
- No real provider or credential is added.

- [ ] **Step 1: Add the synthetic vertical test**

Create one queued test Job with a bounded worktree/authority contract, claim it through existing Runtime semantics, launch it through the synthetic non-Codex adapter, collect a valid structured result, and require the existing supervisor/runtime path to transition the same Attempt and Job to `COMPLETED`.

Assert that the test creates exactly:

```text
one Job
one Attempt
one claimed Worker
existing Event lineage only
zero provider-specific lifecycle rows/tables
```

- [ ] **Step 2: Add effect-unknown/cancel falsifiers**

Synthetic adapter cases must prove:

```text
start returns ambiguous/no authenticated process identity -> no RUNNING success
collect timeout/transport ambiguity -> no provider failover and no false COMPLETED
cancel targets the same persisted process identity
a second adapter cannot consume the same active Attempt
```

- [ ] **Step 3: Run RED then GREEN**

```bash
python -m pytest \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_executive_os_phase1fb.py \
  -q
```

Implement only the minimum generic-supervisor typing/composition changes required for the synthetic adapter to satisfy the same lifecycle.

- [ ] **Step 4: Commit**

```bash
git add tests/test_worker_adapter_broker_contract.py tests/test_executive_operator_supervisor.py tests/test_executive_os_phase1fb.py control_plane/executive_supervisor.py
git commit -m "test(exec): prove provider-neutral worker lifecycle"
```

---

### Task 5: Hosted proof, adversarial review, and stop before PF1

**Files:**
- Modify only documentation/evidence required by current repository proof convention.

- [ ] **Step 1: Run current collision census**

Re-read protected master, CF2-I accepted head, open Executive/worker/broker PRs and current Capacity Fabric source law. Any semantic movement in common lifecycle/broker/adapter paths requires reconciliation before push.

- [ ] **Step 2: Run combined test gate**

```bash
python -m pytest \
  tests/test_worker_execution_contract.py \
  tests/test_worker_adapter_broker_contract.py \
  tests/test_executive_codex_worker.py \
  tests/test_executive_worker_broker.py \
  tests/test_executive_operator_broker.py \
  tests/test_codex_operator_adapter.py \
  tests/test_executive_operator_supervisor.py \
  tests/test_executive_os_phase1fb.py \
  -q
python -m compileall -q control_plane

git diff --check
```

- [ ] **Step 3: Independent adversarial review**

Reviewer must attack: a provider-specific home leaking into common contracts; caller-selected adapter switching; hidden second retry/lifecycle; Codex security regression; fake completion on ambiguous effect; synthetic adapter bypassing authority/workspace/validation; and tmux/provider process identity being treated as Job identity.

- [ ] **Step 4: Hosted CI/CodeQL**

Require exact-head hosted gates. Green CI is necessary but HF1 acceptance also requires the synthetic non-Codex lifecycle proof and Codex regression equivalence.

- [ ] **Step 5: Return to Sol**

Return base/head SHA, changed-file census, common contract signatures, Codex equivalence receipts, synthetic-provider lifecycle receipt, full/hosted tests, adversarial verdict, collisions, and explicit `PF1 REAL CLAUDE UNSTARTED`.

## Stop Condition

HF1 stops when the common worker contract/broker/supervisor no longer depends on Codex-owned types/provider homes, current Codex execution remains secure and behaviorally equivalent, and one synthetic non-Codex adapter completes the same canonical Executive lifecycle. It does not add or authenticate a real non-Codex provider.
